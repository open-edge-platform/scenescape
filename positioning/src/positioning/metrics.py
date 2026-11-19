# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""In-process `positioning_*` runtime metrics, emitted as structured JSON log records."""

import json
import logging
import threading

log = logging.getLogger(__name__)

POSE_AGE_BUCKETS_S = (0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)
STATE_DURATION_BUCKETS_S = (0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0)
MOTION_STATES = ("stationary", "slewing", "settling", "unknown")


class _Histogram:
  def __init__(self, buckets):
    self.buckets = buckets
    self.counts = [0] * (len(buckets) + 1)
    self.count = 0
    self.sum = 0.0

  def observe(self, value):
    index = next((i for i, bound in enumerate(self.buckets) if value <= bound), len(self.buckets))
    self.counts[index] += 1
    self.count += 1
    self.sum += value

  def snapshot(self):
    cumulative = []
    total = 0
    for count in self.counts[:-1]:
      total += count
      cumulative.append(total)
    return {"buckets": dict(zip(map(str, self.buckets), cumulative)),
            "count": self.count, "sum": self.sum}


class PositioningMetrics:
  """Resolver-side metrics; labels are bounded to source id, motion state, and reason."""

  def __init__(self):
    self._lock = threading.Lock()
    self._pose_age = {}
    self._sequence_gaps = {}
    self._rejected_samples = {}
    self._motion_state = {}
    self._calibration_version = {}
    self._clock_offset_s = None
    self._state_since = {}

  def observe_pose_age(self, source_id, age_s):
    with self._lock:
      self._pose_age.setdefault(source_id, _Histogram(POSE_AGE_BUCKETS_S)).observe(age_s)

  def inc_sequence_gap(self, source_id):
    with self._lock:
      self._sequence_gaps[source_id] = self._sequence_gaps.get(source_id, 0) + 1

  def inc_rejected_sample(self, source_id, result):
    key = (source_id, result)
    with self._lock:
      self._rejected_samples[key] = self._rejected_samples.get(key, 0) + 1

  def observe_motion_state(self, source_id, motion_state, timestamp_ns):
    """Record time spent in the previous state when `motion_state` changes."""
    with self._lock:
      previous = self._state_since.get(source_id)
      if previous is not None and previous[0] == motion_state:
        return
      if previous is not None and timestamp_ns > previous[1]:
        key = (source_id, previous[0])
        self._motion_state.setdefault(key, _Histogram(STATE_DURATION_BUCKETS_S)).observe(
          (timestamp_ns - previous[1]) / 1e9)
      self._state_since[source_id] = (motion_state, timestamp_ns)

  def set_calibration_version(self, source_id, calibration_version):
    with self._lock:
      self._calibration_version[source_id] = calibration_version

  def set_clock_offset(self, offset_s):
    with self._lock:
      self._clock_offset_s = offset_s

  def snapshot(self):
    with self._lock:
      return {
        "positioning_pose_age_seconds": {
          source: histogram.snapshot() for source, histogram in self._pose_age.items()},
        "positioning_pose_sequence_gaps_total": dict(self._sequence_gaps),
        "positioning_rejected_samples_total": [
          {"source_id": source, "result": result, "value": value}
          for (source, result), value in self._rejected_samples.items()],
        "positioning_motion_state_seconds": [
          {"source_id": source, "motion_state": state, **histogram.snapshot()}
          for (source, state), histogram in self._motion_state.items()],
        "positioning_calibration_version_info": [
          {"source_id": source, "calibration_version": version}
          for source, version in self._calibration_version.items()],
        "positioning_clock_offset_seconds": self._clock_offset_s,
      }

  def log_snapshot(self):
    if log.isEnabledFor(logging.DEBUG):
      message = json.dumps({"record": "positioning_metrics", **self.snapshot()}, sort_keys=True)
      log.debug(f"{message}")

  def run(self, stop_event, interval_s=60.0):
    while not stop_event.wait(interval_s):
      self.log_snapshot()
