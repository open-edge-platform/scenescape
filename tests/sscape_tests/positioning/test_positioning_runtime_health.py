# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""NTP clock monitor and runtime metrics registry for the Positioning service."""

import json
import threading
import unittest
from unittest import mock

import ntplib

from positioning.clock_sync import ClockMonitor
from positioning.metrics import PositioningMetrics


class FakeMonotonic:
  def __init__(self):
    self.now = 100.0

  def __call__(self):
    return self.now


def ntp_client(*offsets):
  client = mock.Mock()
  client.request.side_effect = [
    offset if isinstance(offset, Exception) else mock.Mock(offset=offset) for offset in offsets]
  return client


class TestClockMonitor(unittest.TestCase):
  def test_offset_within_bound_is_synchronized_and_recorded(self):
    metrics = PositioningMetrics()
    monitor = ClockMonitor("ntpserv", 0.05, client=ntp_client(0.01), metrics=metrics)

    self.assertTrue(monitor.check())
    self.assertTrue(monitor.is_synchronized())
    self.assertEqual(monitor.offset_s, 0.01)
    self.assertEqual(metrics.snapshot()["positioning_clock_offset_seconds"], 0.01)

  def test_offset_beyond_bound_is_not_synchronized(self):
    monitor = ClockMonitor("ntpserv", 0.05, client=ntp_client(-0.2))

    self.assertFalse(monitor.check())
    self.assertFalse(monitor.is_synchronized())

  def test_unsynchronized_before_first_measurement(self):
    self.assertFalse(ClockMonitor("ntpserv", 0.05, client=mock.Mock()).is_synchronized())

  def test_missing_server_fails_closed_without_request(self):
    client = mock.Mock()
    monitor = ClockMonitor(None, 0.05, client=client)

    self.assertFalse(monitor.check())
    client.request.assert_not_called()

  def test_failed_request_keeps_recent_measurement_until_it_ages_out(self):
    monotonic = FakeMonotonic()
    client = ntp_client(0.01, ntplib.NTPException("timeout"), OSError("unreachable"))
    monitor = ClockMonitor("ntpserv", 0.05, check_interval_s=10, client=client,
                           monotonic=monotonic)
    monitor.check()

    monotonic.now += 20
    self.assertTrue(monitor.check())
    monotonic.now += 11
    self.assertFalse(monitor.check())

  def test_non_finite_offset_is_ignored(self):
    monitor = ClockMonitor("ntpserv", 0.05, client=ntp_client(float("nan")))

    self.assertFalse(monitor.check())
    self.assertIsNone(monitor.offset_s)

  def test_invalid_bounds_are_rejected(self):
    for value in (0, -1, float("inf"), True):
      with self.subTest(value=value):
        with self.assertRaises(ValueError):
          ClockMonitor("ntpserv", value)
    with self.assertRaises(ValueError):
      ClockMonitor("ntpserv", 0.05, check_interval_s=0)

  def test_run_checks_until_stopped(self):
    monitor = ClockMonitor("ntpserv", 0.05, check_interval_s=0.01, client=mock.Mock())
    stop = mock.Mock()
    stop.wait.side_effect = [False, False, True]
    with mock.patch.object(monitor, "check") as check:
      monitor.run(stop)
    self.assertEqual(check.call_count, 2)


class TestPositioningMetrics(unittest.TestCase):
  def test_snapshot_contains_resolver_metrics(self):
    metrics = PositioningMetrics()
    metrics.observe_pose_age("cam-a", 0.03)
    metrics.observe_pose_age("cam-a", 3.0)
    metrics.inc_sequence_gap("cam-a")
    metrics.inc_rejected_sample("cam-a", "PTZ_SAMPLE_RESULT_INVALID")
    metrics.set_calibration_version("cam-a", "v1")
    metrics.set_clock_offset(-0.002)

    snapshot = metrics.snapshot()

    pose_age = snapshot["positioning_pose_age_seconds"]["cam-a"]
    self.assertEqual(pose_age["count"], 2)
    self.assertAlmostEqual(pose_age["sum"], 3.03)
    self.assertEqual(pose_age["buckets"]["0.05"], 1)
    self.assertEqual(pose_age["buckets"]["5.0"], 2)
    self.assertEqual(snapshot["positioning_pose_sequence_gaps_total"], {"cam-a": 1})
    self.assertEqual(snapshot["positioning_rejected_samples_total"], [
      {"source_id": "cam-a", "result": "PTZ_SAMPLE_RESULT_INVALID", "value": 1}])
    self.assertEqual(snapshot["positioning_calibration_version_info"], [
      {"source_id": "cam-a", "calibration_version": "v1"}])
    self.assertEqual(snapshot["positioning_clock_offset_seconds"], -0.002)

  def test_motion_state_duration_is_recorded_on_state_change(self):
    metrics = PositioningMetrics()
    metrics.observe_motion_state("cam-a", "slewing", 1_000_000_000)
    metrics.observe_motion_state("cam-a", "slewing", 1_400_000_000)
    metrics.observe_motion_state("cam-a", "stationary", 2_500_000_000)

    states = metrics.snapshot()["positioning_motion_state_seconds"]

    self.assertEqual(len(states), 1)
    self.assertEqual(states[0]["motion_state"], "slewing")
    self.assertEqual(states[0]["count"], 1)
    self.assertAlmostEqual(states[0]["sum"], 1.5)

  def test_log_snapshot_emits_structured_record(self):
    metrics = PositioningMetrics()
    metrics.inc_sequence_gap("cam-a")
    with self.assertLogs("positioning.metrics", level="INFO") as logs:
      metrics.log_snapshot()
    record = json.loads(logs.records[0].getMessage())
    self.assertEqual(record["record"], "positioning_metrics")
    self.assertEqual(record["positioning_pose_sequence_gaps_total"], {"cam-a": 1})

  def test_run_logs_until_stopped(self):
    metrics = PositioningMetrics()
    stop = threading.Event()
    with mock.patch.object(metrics, "log_snapshot", side_effect=stop.set) as log_snapshot:
      metrics.run(stop, interval_s=0.001)
    log_snapshot.assert_called_once_with()


if __name__ == "__main__":
  unittest.main()
