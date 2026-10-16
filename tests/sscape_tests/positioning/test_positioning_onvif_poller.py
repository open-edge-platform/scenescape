# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ONVIF PTZ poller: device client, sample contract, scheduling, events, and secrets."""

import json
import logging
import math
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from fake_onvif_camera import DEGREES_SPACE, GENERIC_SPACE, FakeOnvifCamera
from positioning.onvif import (
  Credentials, OnvifFault, OnvifPtzDevice, OnvifTransportError, PositionSpace, PtzStatus,
  load_credentials)
from positioning.onvif.events import EventMessage, PullPointSubscription, normalize_topic
from positioning.ptz_poller import LoggingSampleSink, MoveEventMonitor, PTZPoller, build_sample
from positioning.v1 import ptz_pb2


class FakeClock:
  def __init__(self, wall_ns=1_790_000_000_000_000_000, monotonic_ns=5_000_000_000):
    self.wall_ns = wall_ns
    self.mono_ns = monotonic_ns

  def advance(self, delta_ns):
    self.wall_ns += delta_ns
    self.mono_ns += delta_ns

  def time_ns(self):
    return self.wall_ns

  def monotonic_ns(self):
    return self.mono_ns


class ScriptedDevice:
  """Device double whose GetStatus takes a fixed simulated round trip."""

  def __init__(self, clock, round_trip_ns=30_000_000, move="IDLE", space_uri=GENERIC_SPACE):
    self.clock = clock
    self.round_trip_ns = round_trip_ns
    self.move = move
    self.space_uri = space_uri
    self.profile_token = "profile_ptz"
    self.position_spaces = (PositionSpace(GENERIC_SPACE, -1.0, 1.0, -1.0, 1.0),)
    self.connected = False
    self.closed = False
    self.failures = 0

  def connect(self):
    self.connected = True

  def close(self):
    self.closed = True

  def get_status(self):
    self.clock.advance(self.round_trip_ns)
    if self.failures:
      self.failures -= 1
      raise OnvifTransportError("simulated timeout")
    return PtzStatus(0.1, -0.2, None, self.space_uri, self.move)

  def position_space(self, uri):
    return self.position_spaces[0] if uri == GENERIC_SPACE else None


class ListSink:
  def __init__(self):
    self.samples = []

  def submit_ptz_sample(self, sample):
    self.samples.append(sample)
    return ptz_pb2.PTZSampleAck(result=ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED,
                                accepted_sequence=sample.sequence)


class CameraTestCase(unittest.TestCase):
  def setUp(self):
    self.camera = FakeOnvifCamera()
    self.addCleanup(self.camera.close)
    self.credentials = Credentials(self.camera.username, self.camera.password)

  def device(self, **kwargs):
    kwargs.setdefault("scheme", "http")
    device = OnvifPtzDevice("127.0.0.1", self.camera.port, kwargs.pop("credentials", self.credentials),
                            timeout_s=2.0, **kwargs)
    self.addCleanup(device.close)
    return device


class TestOnvifDevice(CameraTestCase):
  def test_connect_selects_ptz_profile_and_spaces(self):
    device = self.device().connect()
    self.assertEqual(device.profile_token, "profile_ptz")
    self.assertEqual(device.node_token, "node0")
    self.assertEqual(device.default_space_uri, GENERIC_SPACE)
    self.assertEqual([space.uri for space in device.position_spaces], [GENERIC_SPACE, DEGREES_SPACE])
    self.assertEqual(device.position_space(DEGREES_SPACE).pan_max, 180.0)

  def test_device_defaults_to_https(self):
    device = OnvifPtzDevice("127.0.0.1", self.camera.port, self.credentials)
    self.addCleanup(device.close)
    self.assertEqual(device.scheme, "https")

  def test_service_addresses_never_leave_configured_host(self):
    device = self.device().connect()
    for name, url in device.xaddrs.items():
      self.assertTrue(url.startswith(f"http://127.0.0.1:{self.camera.port}/"), (name, url))

  def test_requested_profile_must_have_ptz(self):
    with self.assertRaises(OnvifTransportError):
      self.device(profile_token="profile_static").connect()

  def test_get_status_parses_position_space_and_move_status(self):
    self.camera.move_status = "MOVING"
    status = self.device().connect().get_status()
    self.assertEqual((status.pan, status.tilt, status.zoom), (0.25, -0.5, 0.0))
    self.assertEqual(status.space_uri, GENERIC_SPACE)
    self.assertEqual(status.pan_tilt_move_status, "MOVING")

  def test_missing_status_space_uses_profile_default(self):
    self.camera.status_space = None
    device = self.device().connect()
    self.assertEqual(device.position_space(device.get_status().space_uri).uri, GENERIC_SPACE)

  def test_skewed_device_clock_is_compensated(self):
    self.camera.clock_offset_s = 3600.0
    device = self.device().connect()
    self.assertAlmostEqual(device.soap.clock_offset_s, 3600.0, delta=2.0)
    device.get_status()

  def test_wrong_password_is_a_not_authorized_fault(self):
    with self.assertRaises(OnvifFault) as raised:
      self.device(credentials=Credentials(self.camera.username, "wrong")).connect()
    self.assertTrue(raised.exception.not_authorized)

  def test_entity_expansion_is_rejected(self):
    self.camera.raw_status_response = (
      '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
      '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body>&a;</env:Body>'
      "</env:Envelope>")
    device = self.device().connect()
    with self.assertRaises(OnvifTransportError):
      device.get_status()

  def test_http_error_without_soap_body_is_transport_error(self):
    self.camera.status_failures = 1
    with self.assertRaises(OnvifTransportError):
      self.device().connect().get_status()

  def test_event_topics_are_listed_without_prefixes(self):
    self.assertEqual(self.device().connect().get_event_topics(), ["PTZController/Move/Channel_1"])


class TestSecrets(CameraTestCase):
  def test_password_is_never_logged_or_repr(self):
    self.assertNotIn(self.camera.password, repr(self.credentials))
    with self.assertLogs("positioning", level="DEBUG") as logs:
      logging.getLogger("positioning").debug("probe")
      sink = ListSink()
      poller = PTZPoller("cam-a", lambda: OnvifPtzDevice(
        "127.0.0.1", self.camera.port, self.credentials, scheme="http", timeout_s=2.0), sink, 0.05)
      stop = threading.Event()
      worker = threading.Thread(target=poller.run, args=(stop,))
      worker.start()
      time.sleep(0.3)
      self.camera.status_failures = 10
      time.sleep(0.5)
      stop.set()
      worker.join(5)
    text = "\n".join(logs.output)
    self.assertNotIn(self.camera.password, text)
    self.assertIn("GetStatus failed", text)

  def test_credentials_file(self):
    with tempfile.TemporaryDirectory() as directory:
      path = os.path.join(directory, "cam.json")
      with open(path, "w", encoding="utf-8") as handle:
        json.dump({"username": "user", "password": "pw"}, handle)
      self.assertEqual(load_credentials(path), Credentials("user", "pw"))
      with open(path, "w", encoding="utf-8") as handle:
        json.dump({"password": "pw"}, handle)
      with self.assertRaises(ValueError):
        load_credentials(path)


class TestSampleContract(unittest.TestCase):
  def test_poll_interval_must_convert_to_at_least_one_nanosecond(self):
    with self.assertRaisesRegex(ValueError, "at least 1 ns"):
      PTZPoller("cam-a", None, ListSink(), poll_interval_s=0.5e-9)
    poller = PTZPoller("cam-a", None, ListSink(), poll_interval_s=1e-9)
    self.assertEqual(int(poller.poll_interval_s * 1e9), 1)

  def test_midpoint_timestamp_and_half_round_trip_uncertainty(self):
    clock = FakeClock()
    start_ns = clock.wall_ns
    sink = ListSink()
    poller = PTZPoller("cam-a", lambda: ScriptedDevice(clock), sink, clock=clock)
    poller.connect()
    sample, ack = poller.poll_once()
    self.assertEqual(sample.measured_at.ToNanoseconds(), start_ns + 15_000_000)
    self.assertEqual(sample.timestamp_uncertainty_ns, 15_000_000)
    self.assertEqual(ack.result, ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED)
    self.assertEqual(sample.camera_id, "cam-a")
    self.assertEqual((sample.position.pan, sample.position.tilt), (0.1, -0.2))
    self.assertFalse(sample.position.HasField("zoom"))
    self.assertEqual(sample.position.position_space_uri, GENERIC_SPACE)
    self.assertEqual((sample.position.pan_min, sample.position.tilt_max), (-1.0, 1.0))

  def test_sequence_is_contiguous_and_restart_changes_instance(self):
    clock = FakeClock()
    first = PTZPoller("cam-a", lambda: ScriptedDevice(clock), ListSink(), clock=clock)
    first.connect()
    sequences = [first.poll_once()[0].sequence for _ in range(4)]
    self.assertEqual(sequences, [1, 2, 3, 4])
    restarted = PTZPoller("cam-a", lambda: ScriptedDevice(clock), ListSink(), clock=clock)
    restarted.connect()
    sample = restarted.poll_once()[0]
    self.assertEqual(sample.sequence, 1)
    self.assertNotEqual(sample.adapter_instance_id, first.adapter_instance_id)

  def test_unknown_position_space_yields_nan_ranges(self):
    status = PtzStatus(0.0, 0.0, 1.0, "urn:vendor:space", "IDLE")
    sample = build_sample("cam-a", "id", 1, 0, 1, status, None, ptz_pb2.REPORTED_MOVE_STATUS_IDLE)
    self.assertEqual(sample.position.position_space_uri, "urn:vendor:space")
    self.assertTrue(all(math.isnan(value) for value in (
      sample.position.pan_min, sample.position.pan_max,
      sample.position.tilt_min, sample.position.tilt_max)))
    self.assertEqual(sample.position.zoom, 1.0)

  def test_reported_move_status_modes(self):
    clock = FakeClock()
    cases = [("get_status", "MOVING", None, ptz_pb2.REPORTED_MOVE_STATUS_MOVING),
             ("get_status", "UNKNOWN", None, ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED),
             ("none", "MOVING", None, ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED),
             ("event", "IDLE", True, ptz_pb2.REPORTED_MOVE_STATUS_MOVING),
             ("event", "MOVING", False, ptz_pb2.REPORTED_MOVE_STATUS_IDLE),
             ("event", "MOVING", None, ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED)]
    for mode, device_move, event_state, expected in cases:
      with self.subTest(mode=mode, device_move=device_move, event_state=event_state):
        monitor = MoveEventMonitor("cam-a", None, "PTZController/Move", "is_moving")
        monitor._set_state(event_state)
        poller = PTZPoller("cam-a", lambda: ScriptedDevice(clock, move=device_move), ListSink(),
                           move_status=mode, move_monitor=monitor, clock=clock)
        poller.connect()
        self.assertEqual(poller.poll_once()[0].reported_move_status, expected)

  def test_event_mode_requires_monitor(self):
    with self.assertRaises(ValueError):
      PTZPoller("cam-a", None, ListSink(), move_status="event")

  def test_unknown_move_status_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "move_status must be one of"):
      PTZPoller("cam-a", None, ListSink(), move_status="unknown")

  def test_connect_closes_device_when_connection_fails(self):
    device = ScriptedDevice(FakeClock())
    device.connect = mock.Mock(side_effect=OnvifTransportError("connect failed"))
    poller = PTZPoller("cam-a", lambda: device, ListSink())
    with self.assertRaises(OnvifTransportError):
      poller.connect()
    self.assertTrue(device.closed)
    self.assertIsNone(poller.device)

  def test_sink_failure_does_not_stop_polling(self):
    class FailingSink:
      def submit_ptz_sample(self, sample):
        raise RuntimeError("resolver bug")

    clock = FakeClock()
    poller = PTZPoller("cam-a", lambda: ScriptedDevice(clock), FailingSink(), clock=clock)
    poller.connect()
    with self.assertLogs("positioning", level="ERROR"):
      self.assertIsNone(poller.poll_once()[1])
    self.assertEqual(poller.poll_once()[0].sequence, 2)

  def test_sink_failure_recovers_on_next_sample(self):
    class RecoveringSink:
      def __init__(self):
        self.calls = 0

      def submit_ptz_sample(self, sample):
        self.calls += 1
        if self.calls == 1:
          raise RuntimeError("temporary sink failure")
        return ptz_pb2.PTZSampleAck(result=ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED,
                                    accepted_sequence=sample.sequence)

    clock = FakeClock()
    poller = PTZPoller("cam-a", lambda: ScriptedDevice(clock), RecoveringSink(), clock=clock)
    poller.connect()
    with self.assertLogs("positioning", level="ERROR"):
      self.assertIsNone(poller.poll_once()[1])
    sample, ack = poller.poll_once()
    self.assertEqual(ack.accepted_sequence, sample.sequence)
    self.assertFalse(poller._sink_failing)

  def test_unexpected_poll_error_disconnects_device(self):
    class StopAfterPollError:
      def __init__(self):
        self.checks = 0

      def is_set(self):
        self.checks += 1
        return self.checks > 1

      def wait(self, timeout):
        return False

    clock = FakeClock()
    device = ScriptedDevice(clock)
    poller = PTZPoller("cam-a", lambda: device, ListSink(), clock=clock)
    poller.device = device
    poller.poll_once = mock.Mock(side_effect=RuntimeError("unexpected poll error"))
    with self.assertLogs("positioning", level="ERROR"):
      poller.run(StopAfterPollError())
    self.assertTrue(device.closed)
    self.assertIsNone(poller.device)

  def test_logging_sink_acknowledges(self):
    sink = LoggingSampleSink()
    sample = build_sample("cam-a", "id", 7, 0, 1, PtzStatus(0, 0, None, GENERIC_SPACE, "IDLE"),
                          None, ptz_pb2.REPORTED_MOVE_STATUS_IDLE)
    with self.assertLogs("positioning", level="INFO") as logs:
      ack = sink.submit_ptz_sample(sample)
    self.assertEqual(ack.accepted_sequence, 7)
    self.assertIn('\"record\": \"ptz_motion_state\"', logs.output[0])
    record = json.loads(logs.records[0].getMessage())
    self.assertIsNone(record["previous_status"])
    with self.assertNoLogs("positioning", level="INFO"):
      sink.submit_ptz_sample(sample)
    sample.sequence = 9
    sample.reported_move_status = ptz_pb2.REPORTED_MOVE_STATUS_MOVING
    with self.assertLogs("positioning", level="INFO") as logs:
      sink.submit_ptz_sample(sample)
    record = json.loads(logs.records[0].getMessage())
    self.assertEqual(record["previous_status"], "REPORTED_MOVE_STATUS_IDLE")
    self.assertEqual(record["reported_move_status"], "REPORTED_MOVE_STATUS_MOVING")
    sample.sequence = 10
    with self.assertNoLogs("positioning", level="INFO"):
      sink.submit_ptz_sample(sample)
    sample.sequence = 11
    sample.reported_move_status = ptz_pb2.REPORTED_MOVE_STATUS_IDLE
    with self.assertLogs("positioning", level="INFO") as logs:
      sink.submit_ptz_sample(sample)
    record = json.loads(logs.records[0].getMessage())
    self.assertEqual(record["previous_status"], "REPORTED_MOVE_STATUS_MOVING")
    self.assertEqual(record["reported_move_status"], "REPORTED_MOVE_STATUS_IDLE")


class TestPollingLoop(CameraTestCase):
  def run_poller(self, poller, seconds):
    stop = threading.Event()
    worker = threading.Thread(target=poller.run, args=(stop,))
    worker.start()
    time.sleep(seconds)
    stop.set()
    worker.join(5)
    self.assertFalse(worker.is_alive())

  def factory(self):
    return OnvifPtzDevice("127.0.0.1", self.camera.port, self.credentials, scheme="http", timeout_s=2.0)

  def test_polls_at_fixed_rate_while_stationary(self):
    sink = ListSink()
    poller = PTZPoller("cam-a", self.factory, sink, poll_interval_s=0.05)
    self.run_poller(poller, 1.0)
    self.assertGreaterEqual(len(sink.samples), 12)
    self.assertLessEqual(len(sink.samples), 22)
    self.assertEqual([s.sequence for s in sink.samples], list(range(1, len(sink.samples) + 1)))
    timestamps = [s.measured_at.ToNanoseconds() for s in sink.samples]
    self.assertEqual(timestamps, sorted(timestamps))
    self.assertTrue(all(s.timestamp_uncertainty_ns > 0 for s in sink.samples))

  def test_slow_device_skips_ticks_without_burst(self):
    self.camera.status_delay_s = 0.12
    sink = ListSink()
    poller = PTZPoller("cam-a", self.factory, sink, poll_interval_s=0.05)
    self.run_poller(poller, 0.8)
    self.assertGreater(poller.overruns, 0)
    gaps = [b.measured_at.ToNanoseconds() - a.measured_at.ToNanoseconds()
            for a, b in zip(sink.samples, sink.samples[1:])]
    self.assertTrue(all(gap >= 100_000_000 for gap in gaps), gaps)
    self.assertGreaterEqual(min(s.timestamp_uncertainty_ns for s in sink.samples), 60_000_000)

  def test_failures_reconnect_without_new_instance_or_sequence_reset(self):
    sink = ListSink()
    poller = PTZPoller("cam-a", self.factory, sink, poll_interval_s=0.02, max_consecutive_failures=2)
    stop = threading.Event()
    worker = threading.Thread(target=poller.run, args=(stop,))
    worker.start()
    time.sleep(0.2)
    before = len(sink.samples)
    self.camera.status_failures = 2
    time.sleep(1.6)
    stop.set()
    worker.join(5)
    self.assertGreater(len(sink.samples), before)
    connects = sum(1 for operation, _ in self.camera.operations if operation == "GetProfiles")
    self.assertEqual(connects, 2)
    self.assertEqual({s.adapter_instance_id for s in sink.samples}, {poller.adapter_instance_id})
    self.assertEqual([s.sequence for s in sink.samples], list(range(1, len(sink.samples) + 1)))

  def test_reconnect_backoff_escalates_until_status_recovers(self):
    class StopAfterBackoffs:
      def __init__(self):
        self.backoffs = []

      def is_set(self):
        return len(self.backoffs) >= 4

      def wait(self, timeout):
        if timeout >= 1:
          self.backoffs.append(timeout)
          return len(self.backoffs) >= 4
        return False

    poller = PTZPoller("cam-a", self.factory, ListSink(), poll_interval_s=0.001,
                       max_consecutive_failures=1, max_backoff_s=8)
    poller.connect = lambda: setattr(poller, "device", object())
    poller.disconnect = lambda: setattr(poller, "device", None)
    actions = ["fail", "fail", "success", "fail", "fail"]

    def poll_once():
      if actions.pop(0) == "fail":
        raise OnvifTransportError("simulated polling failure")

    poller.poll_once = poll_once
    stop = StopAfterBackoffs()
    poller.run(stop)

    self.assertEqual(stop.backoffs, [1, 2, 1, 2])
    self.assertEqual(actions, [])

  def test_connection_errors_retry_with_backoff(self):
    class StopAfterRetries:
      def __init__(self):
        self.waits = []

      def is_set(self):
        return False

      def wait(self, timeout):
        self.waits.append(timeout)
        return len(self.waits) == 2

    poller = PTZPoller("cam-a", self.factory, ListSink())
    poller.connect = mock.Mock(side_effect=[
      OnvifTransportError("camera unavailable"), RuntimeError("unexpected connect failure")])
    stop = StopAfterRetries()
    with self.assertLogs("positioning", level="WARNING"):
      poller.run(stop)
    self.assertEqual(stop.waits, [1.0, 2.0])
    self.assertEqual(poller.connect.call_count, 2)

  def test_polling_recovers_after_transient_status_error(self):
    class StopAfterRecovery:
      def __init__(self):
        self.waits = []
        self.stopped = False

      def is_set(self):
        return self.stopped

      def wait(self, timeout):
        self.waits.append(timeout)
        self.stopped = len(self.waits) == 2
        return self.stopped

    clock = FakeClock()
    device = ScriptedDevice(clock)
    poller = PTZPoller("cam-a", self.factory, ListSink(), poll_interval_s=0.001, clock=clock)
    poller.device = device
    poller.poll_once = mock.Mock(side_effect=[OnvifTransportError("temporary failure"), None])
    with self.assertLogs("positioning", level="INFO") as logs:
      poller.run(StopAfterRecovery())
    self.assertTrue(any("polling recovered after 1 failures" in line for line in logs.output))
    self.assertTrue(device.closed)


class TestMoveEvents(unittest.TestCase):
  def setUp(self):
    self.camera = FakeOnvifCamera(require_reference_parameters=True)
    self.addCleanup(self.camera.close)
    self.credentials = Credentials(self.camera.username, self.camera.password)

  def factory(self):
    return OnvifPtzDevice("127.0.0.1", self.camera.port, self.credentials, scheme="http", timeout_s=2.0)

  def test_normalize_topic(self):
    self.assertEqual(normalize_topic("tns1:PTZController/tnsaxis:Move/Channel_1"),
                     "PTZController/Move/Channel_1")

  def test_reference_parameters_are_echoed_and_subscription_released(self):
    device = self.factory().connect_services()
    self.addCleanup(device.close)
    self.camera.push_move_event(False, "Initialized")
    with PullPointSubscription(device) as subscription:
      self.assertTrue(subscription.address.startswith(f"http://127.0.0.1:{self.camera.port}/"))
      messages = subscription.pull(timeout_s=1)
      subscription.renew()
    self.assertEqual([(m.topic, m.data["is_moving"], m.property_operation) for m in messages],
                     [("PTZController/Move/Channel_1", "0", "Initialized")])
    self.assertEqual(self.camera.unsubscribed, 1)

  def test_renews_using_camera_granted_lease(self):
    self.camera.subscription_lease_s = 10
    device = self.factory().connect_services()
    self.addCleanup(device.close)
    now = [100.0]
    with PullPointSubscription(device, termination_s=60, monotonic=lambda: now[0]) as subscription:
      self.assertAlmostEqual(subscription._lease_s, 10, places=1)
      self.assertAlmostEqual(subscription._expires_at, 110, places=1)
      now[0] = 105
      self.camera.subscription_lease_s = 4
      subscription.pull(timeout_s=0)
      renewals = [operation for operation, _ in self.camera.operations if operation == "Renew"]
      self.assertEqual(len(renewals), 1)
      self.assertAlmostEqual(subscription._lease_s, 4, places=1)
      self.assertAlmostEqual(subscription._expires_at, 109, places=1)

  def test_monitor_tracks_state_and_emits_records(self):
    monitor = MoveEventMonitor("cam-b", self.factory, "PTZController/Move", "is_moving")
    stop = threading.Event()
    with self.assertLogs("positioning", level="INFO") as logs:
      worker = threading.Thread(target=monitor.run, args=(stop,))
      worker.start()
      self.camera.push_move_event(True)
      deadline = time.monotonic() + 3
      while monitor.is_moving is not True and time.monotonic() < deadline:
        time.sleep(0.02)
      self.assertTrue(monitor.is_moving)
      self.camera.push_move_event(False)
      deadline = time.monotonic() + 3
      while monitor.is_moving is not False and time.monotonic() < deadline:
        time.sleep(0.02)
      self.assertFalse(monitor.is_moving)
      stop.set()
      worker.join(5)
    self.assertIsNone(monitor.is_moving)
    self.assertEqual(self.camera.unsubscribed, 1)
    records = [json.loads(line.split(":", 2)[2]) for line in logs.output if "ptz_move_event" in line]
    self.assertEqual([record["is_moving"] for record in records], [True, False])
    self.assertEqual(records[0]["source_id"], "cam-b")

  def test_monitor_ignores_unrelated_topics_and_values(self):
    monitor = MoveEventMonitor("cam-b", None, "PTZController/Move", "is_moving")
    monitor.handle(EventMessage("PTZController/MoveX/Channel_1", None, None, {}, {"is_moving": "1"}))
    monitor.handle(EventMessage("PTZController/Move/Channel_1", None, None, {}, {"is_moving": "x"}))
    self.assertIsNone(monitor.is_moving)

  def test_monitor_retries_subscription_errors_and_clears_state(self):
    class StopAfterRetries:
      def __init__(self):
        self.waits = []

      def is_set(self):
        return False

      def wait(self, timeout):
        self.waits.append(timeout)
        return len(self.waits) == 2

    device = mock.Mock()
    monitor = MoveEventMonitor("cam-b", mock.Mock(return_value=device),
                               "PTZController/Move", "is_moving")
    monitor._set_state(True)
    stop = StopAfterRetries()
    with mock.patch("positioning.ptz_poller.PullPointSubscription",
                    side_effect=[OnvifTransportError("subscription failed"),
                                 RuntimeError("unexpected subscription failure")]):
      with self.assertLogs("positioning", level="WARNING"):
        monitor.run(stop)

    self.assertEqual(stop.waits, [1.0, 2.0])
    self.assertEqual(device.connect_services.call_count, 2)
    self.assertEqual(device.close.call_count, 2)
    self.assertIsNone(monitor.is_moving)

  def test_monitor_handles_factory_failure_without_device(self):
    class StopAfterWait:
      def is_set(self):
        return False

      def wait(self, timeout):
        return True

    factory = mock.Mock(side_effect=RuntimeError("factory failed"))
    monitor = MoveEventMonitor("cam-b", factory, "PTZController/Move", "is_moving")
    with self.assertLogs("positioning", level="ERROR"):
      monitor.run(StopAfterWait())
    factory.assert_called_once_with()
    self.assertIsNone(monitor.is_moving)

  def test_monitor_does_not_start_when_stop_is_already_set(self):
    stop = threading.Event()
    stop.set()
    factory = mock.Mock()
    monitor = MoveEventMonitor("cam-b", factory, "PTZController/Move", "is_moving")
    monitor.run(stop)
    factory.assert_not_called()


if __name__ == "__main__":
  unittest.main()
