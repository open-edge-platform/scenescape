# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ONVIF PTZ poller: emits raw `PTZSample` protobufs to an in-process sink.

The poller never applies calibration math, never retries or replays samples, and
never writes to Manager or MQTT. Each reading is timestamped at the midpoint of the
GetStatus round trip with at least half the round trip as uncertainty.
"""

import datetime
import json
import logging
import math
import threading
import time
import uuid
from typing import Callable, Optional, Protocol

from positioning.onvif import OnvifError, PullPointSubscription
from positioning.v1 import ptz_pb2

log = logging.getLogger(__name__)

MOVE_STATUS_MODES = ("get_status", "event", "none")
_GET_STATUS_MOVE = {
  "IDLE": ptz_pb2.REPORTED_MOVE_STATUS_IDLE,
  "MOVING": ptz_pb2.REPORTED_MOVE_STATUS_MOVING,
}
_EVENT_BOOLEANS = {"1": True, "true": True, "0": False, "false": False}


class SystemClock:
  """Wall clock for sample timestamps; monotonic clock for intervals and scheduling."""

  @staticmethod
  def time_ns():
    return time.time_ns()

  @staticmethod
  def monotonic_ns():
    return time.monotonic_ns()


class PTZSampleSink(Protocol):
  def submit_ptz_sample(self, sample: ptz_pb2.PTZSample) -> ptz_pb2.PTZSampleAck:
    ...


def _iso_from_ns(timestamp_ns):
  moment = datetime.datetime.fromtimestamp(timestamp_ns / 1e9, tz=datetime.timezone.utc)
  return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_sample(source_id, adapter_instance_id, sequence, measured_at_ns, uncertainty_ns,
                 status, space, reported_move_status):
  """Map one GetStatus reading to `PTZSample`; unknown ranges are NaN for the Resolver to reject."""
  sample = ptz_pb2.PTZSample(
    camera_id=source_id,
    adapter_instance_id=adapter_instance_id,
    sequence=sequence,
    timestamp_uncertainty_ns=uncertainty_ns,
    reported_move_status=reported_move_status)
  sample.measured_at.FromNanoseconds(measured_at_ns)
  position = sample.position
  position.pan = status.pan
  position.tilt = status.tilt
  if status.zoom is not None:
    position.zoom = status.zoom
  if space is not None:
    position.position_space_uri = space.uri
    position.pan_min, position.pan_max = space.pan_min, space.pan_max
    position.tilt_min, position.tilt_max = space.tilt_min, space.tilt_max
  else:
    position.position_space_uri = status.space_uri or ""
    position.pan_min = position.pan_max = position.tilt_min = position.tilt_max = math.nan
  return sample


class MoveEventMonitor:
  """Tracks a vendor "is moving" property event (e.g. Axis `PTZController/Move`).

  The state is advisory: it only feeds `reported_move_status` and structured
  `ptz_move_event` records used for calibration; it never gates pose validity.
  """

  def __init__(self, source_id, device_factory, topic, data_item, clock=None,
               pull_timeout_s=1, termination_s=60, max_backoff_s=30.0):
    self.source_id = source_id
    self._device_factory = device_factory
    self.topic = topic.strip("/")
    self.data_item = data_item
    self._clock = clock or SystemClock()
    self.pull_timeout_s = pull_timeout_s
    self.termination_s = termination_s
    self.max_backoff_s = max_backoff_s
    self._lock = threading.Lock()
    self._is_moving: Optional[bool] = None

  @property
  def is_moving(self):
    with self._lock:
      return self._is_moving

  def _set_state(self, value):
    with self._lock:
      self._is_moving = value

  def handle(self, message):
    if message.topic != self.topic and not message.topic.startswith(self.topic + "/"):
      return
    value = _EVENT_BOOLEANS.get(str(message.data.get(self.data_item, "")).strip().lower())
    if value is None:
      return
    self._set_state(value)
    log.info(json.dumps({
      "record": "ptz_move_event",
      "source_id": self.source_id,
      "is_moving": value,
      "property_operation": message.property_operation,
      "device_utc_time": message.utc_time,
      "received_at": _iso_from_ns(self._clock.time_ns()),
    }, sort_keys=True))

  def run(self, stop_event):
    backoff = 1.0
    while not stop_event.is_set():
      device = None
      try:
        device = self._device_factory()
        device.connect_services()
        with PullPointSubscription(device, self.termination_s) as subscription:
          log.info("PTZ move events subscribed for %s", self.source_id)
          backoff = 1.0
          while not stop_event.is_set():
            for message in subscription.pull(self.pull_timeout_s):
              self.handle(message)
      except OnvifError as error:
        log.warning("PTZ move event subscription for %s failed: %s", self.source_id, error)
      except Exception:
        log.exception("Unexpected PTZ move event failure for %s", self.source_id)
      finally:
        self._set_state(None)
        if device is not None:
          device.close()
      if stop_event.wait(backoff):
        break
      backoff = min(backoff * 2, self.max_backoff_s)


class PTZPoller:
  """Polls one camera at a fixed rate, including while stationary, without queuing."""

  def __init__(self, source_id, device_factory: Callable, sink: PTZSampleSink,
               poll_interval_s=0.2, move_status="get_status",
               move_monitor: Optional[MoveEventMonitor] = None, clock=None,
               max_consecutive_failures=5, max_backoff_s=30.0):
    if move_status not in MOVE_STATUS_MODES:
      raise ValueError(f"move_status must be one of {MOVE_STATUS_MODES}")
    if move_status == "event" and move_monitor is None:
      raise ValueError("move_status 'event' requires a move event monitor")
    if not (isinstance(poll_interval_s, (int, float)) and math.isfinite(poll_interval_s)
        and poll_interval_s >= 1e-9):
      raise ValueError("poll_interval_s must be finite and at least 1 ns")
    self.source_id = source_id
    self._device_factory = device_factory
    self._sink = sink
    self.poll_interval_s = float(poll_interval_s)
    self.move_status = move_status
    self.move_monitor = move_monitor
    self._clock = clock or SystemClock()
    self.max_consecutive_failures = max_consecutive_failures
    self.max_backoff_s = max_backoff_s
    # A new id marks a poller restart; sequence is monotonic within it.
    self.adapter_instance_id = str(uuid.uuid4())
    self.sequence = 0
    self.device = None
    self.overruns = 0
    self._sink_failing = False

  def connect(self):
    device = self._device_factory()
    try:
      device.connect()
    except Exception:
      device.close()
      raise
    self.device = device
    log.info("PTZ source %s connected: profile=%s", self.source_id, device.profile_token)

  def disconnect(self):
    if self.device is not None:
      self.device.close()
      self.device = None

  def _reported_move_status(self, status):
    if self.move_status == "get_status":
      return _GET_STATUS_MOVE.get((status.pan_tilt_move_status or "").upper(),
                                  ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED)
    if self.move_status == "event":
      moving = self.move_monitor.is_moving
      if moving is None:
        return ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED
      return ptz_pb2.REPORTED_MOVE_STATUS_MOVING if moving else ptz_pb2.REPORTED_MOVE_STATUS_IDLE
    return ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED

  def poll_once(self):
    """Read GetStatus once and submit the sample; returns `(sample, ack)`."""
    wall_start_ns = self._clock.time_ns()
    monotonic_start_ns = self._clock.monotonic_ns()
    status = self.device.get_status()
    round_trip_ns = max(self._clock.monotonic_ns() - monotonic_start_ns, 0)
    self.sequence += 1
    sample = build_sample(
      self.source_id, self.adapter_instance_id, self.sequence,
      measured_at_ns=wall_start_ns + round_trip_ns // 2,
      uncertainty_ns=max((round_trip_ns + 1) // 2, 1),
      status=status, space=self.device.position_space(status.space_uri),
      reported_move_status=self._reported_move_status(status))
    try:
      ack = self._sink.submit_ptz_sample(sample)
    except Exception:
      if not self._sink_failing:
        log.exception("PTZ sample sink failed for %s", self.source_id)
      self._sink_failing = True
      return sample, None
    self._sink_failing = False
    return sample, ack

  def run(self, stop_event):
    backoff = 1.0
    failures = 0
    period_ns = int(self.poll_interval_s * 1e9)
    next_deadline_ns = self._clock.monotonic_ns()
    while not stop_event.is_set():
      if self.device is None:
        try:
          self.connect()
          failures = 0
        except OnvifError as error:
          log.warning("PTZ source %s connect failed: %s", self.source_id, error)
        except Exception:
          log.exception("Unexpected PTZ connect failure for %s", self.source_id)
        if self.device is None:
          if stop_event.wait(backoff):
            break
          backoff = min(backoff * 2, self.max_backoff_s)
          continue
        next_deadline_ns = self._clock.monotonic_ns()
      try:
        self.poll_once()
        if failures:
          log.info("PTZ source %s polling recovered after %d failures", self.source_id, failures)
        failures = 0
        backoff = 1.0
      except OnvifError as error:
        failures += 1
        if failures == 1:
          log.warning("PTZ source %s GetStatus failed: %s", self.source_id, error)
        if failures >= self.max_consecutive_failures:
          log.warning("PTZ source %s reconnecting after %d failures", self.source_id, failures)
          self.disconnect()
          if stop_event.wait(backoff):
            break
          backoff = min(backoff * 2, self.max_backoff_s)
          continue
      except Exception:
        log.exception("Unexpected PTZ polling failure for %s", self.source_id)
        self.disconnect()
        if stop_event.wait(backoff):
          break
        backoff = min(backoff * 2, self.max_backoff_s)
        continue
      next_deadline_ns += period_ns
      now_ns = self._clock.monotonic_ns()
      if now_ns >= next_deadline_ns:
        # Skip missed ticks instead of bursting to catch up.
        missed = (now_ns - next_deadline_ns) // period_ns + 1
        self.overruns += missed
        next_deadline_ns += missed * period_ns
      stop_event.wait((next_deadline_ns - now_ns) / 1e9)
    self.disconnect()


class LoggingSampleSink:
  """Interim sink that logs per-source motion status changes until the Resolver lands."""

  def __init__(self):
    self._lock = threading.Lock()
    self._last_status = {}

  def submit_ptz_sample(self, sample):
    with self._lock:
      previous_status = self._last_status.get(sample.camera_id)
      current_status = sample.reported_move_status
      self._last_status[sample.camera_id] = current_status
      if previous_status != current_status:
        log.info(json.dumps({
          "record": "ptz_motion_state",
          "source_id": sample.camera_id,
          "adapter_instance_id": sample.adapter_instance_id,
          "sequence": sample.sequence,
          "previous_status": ptz_pb2.ReportedMoveStatus.Name(previous_status)
            if previous_status is not None else None,
          "reported_move_status": ptz_pb2.ReportedMoveStatus.Name(current_status),
          "pan": sample.position.pan,
          "tilt": sample.position.tilt,
          "position_space_uri": sample.position.position_space_uri,
        }, sort_keys=False))
    return ptz_pb2.PTZSampleAck(result=ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED,
                                accepted_sequence=sample.sequence)
