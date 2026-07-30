#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for MatchLatencyTracker.
Tests the interface and behavior of per-match latency tracking: the
rolling avg/min/max window, and the OTel metric calls it triggers.
These tests run inside the controller container where all dependencies
are available.
"""

import time
from unittest.mock import patch

import pytest

from controller.latency_metrics import MatchLatencyTracker

class TestMarkTrackStart:
  """Test recording a track's first-seen timestamp."""

  def test_mark_track_start_records_timestamp(self):
    """Verify markTrackStart stores the given timestamp for later latency computation."""
    tracker = MatchLatencyTracker()

    tracker.markTrackStart("track_1", timestamp=100.0)

    assert tracker._start_times["track_1"] == 100.0

  def test_mark_track_start_defaults_to_now(self):
    """Verify markTrackStart uses the current time when no timestamp is given."""
    tracker = MatchLatencyTracker()

    before = time.time()
    tracker.markTrackStart("track_1")
    after = time.time()

    assert before <= tracker._start_times["track_1"] <= after

  def test_mark_track_start_does_not_reset_existing_start_time(self):
    """setdefault semantics: a duplicate call for an already-running track must not reset its clock."""
    tracker = MatchLatencyTracker()

    tracker.markTrackStart("track_1", timestamp=100.0)
    tracker.markTrackStart("track_1", timestamp=200.0)

    assert tracker._start_times["track_1"] == 100.0


class TestRecordMatchLatency:
  """Test computing and recording per-match latency."""

  def test_returns_false_when_no_matching_start_time(self):
    """Verify a track that never had markTrackStart called produces no measurement."""
    tracker = MatchLatencyTracker()

    result = tracker.recordMatchLatency("unknown_track")

    assert result is False

  def test_returns_true_and_records_on_success(self):
    """Verify a normal start->decision pair is recorded and reflected in getStats()."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("track_1", timestamp=100.0)

    result = tracker.recordMatchLatency("track_1", decision_timestamp=102.5)

    assert result is True
    assert tracker.getStats()['average'] == pytest.approx(2.5)

  def test_pops_start_time_so_second_call_returns_false(self):
    """Verify a track's start time is only usable once per lifecycle."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("track_1", timestamp=100.0)

    assert tracker.recordMatchLatency("track_1", decision_timestamp=101.0) is True
    assert tracker.recordMatchLatency("track_1", decision_timestamp=102.0) is False

  def test_negative_latency_is_discarded(self):
    """Verify a decision timestamp before the start time is discarded, not recorded as-is."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("track_1", timestamp=100.0)

    result = tracker.recordMatchLatency("track_1", decision_timestamp=99.0)

    assert result is False
    assert tracker.getStats()['average'] is None

  def test_zero_latency_is_recorded(self):
    """Boundary: exactly-zero latency is valid and recorded; only negative is discarded."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("track_1", timestamp=100.0)

    result = tracker.recordMatchLatency("track_1", decision_timestamp=100.0)

    assert result is True
    assert tracker.getStats()['average'] == 0.0

  def test_decision_timestamp_defaults_to_now(self):
    """Verify decision_timestamp uses the current time when not explicitly given."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("track_1", timestamp=time.time() - 1.0)

    result = tracker.recordMatchLatency("track_1")

    assert result is True
    assert tracker.getStats()['average'] > 0


class TestRollingWindow:
  """Test the bounded rolling window behind avg/min/max."""

  def test_window_respects_maxlen(self):
    """Verify only the most recent max_tracked samples contribute to avg/min/max."""
    tracker = MatchLatencyTracker(max_tracked=3)

    for i in range(5):
      tracker.markTrackStart(f"track_{i}", timestamp=0.0)
      tracker.recordMatchLatency(f"track_{i}", decision_timestamp=float(i + 1))

    # Latencies recorded: 1, 2, 3, 4, 5 -- only the last 3 (3, 4, 5) should remain.
    stats = tracker.getStats()
    assert stats['average'] == pytest.approx((3 + 4 + 5) / 3)
    assert stats['min'] == 3
    assert stats['max'] == 5

  def test_average_min_max_computed_correctly(self):
    """Verify basic arithmetic over a simple set of latencies."""
    tracker = MatchLatencyTracker()

    for i, lat in enumerate([1.0, 2.0, 3.0]):
      tracker.markTrackStart(f"t{i}", timestamp=0.0)
      tracker.recordMatchLatency(f"t{i}", decision_timestamp=lat)

    stats = tracker.getStats()
    assert stats['average'] == pytest.approx(2.0)
    assert stats['min'] == 1.0
    assert stats['max'] == 3.0


class TestDiscardTrackStart:
  """Test discarding a track's start time without recording a latency."""

  def test_discard_removes_start_time(self):
    """Verify a discarded track can no longer produce a latency measurement."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("track_1", timestamp=100.0)

    tracker.discardTrackStart("track_1")

    assert tracker.recordMatchLatency("track_1", decision_timestamp=101.0) is False

  def test_discard_unknown_track_does_not_raise(self):
    """Verify discarding a track that was never started is a safe no-op."""
    tracker = MatchLatencyTracker()

    tracker.discardTrackStart("never_started")  # should not raise


class TestGetStats:
  """Test the summary stats returned for downstream metrics consumers."""

  def test_empty_tracker_returns_none_fields(self):
    """Verify a tracker with no recorded samples reports all-None stats."""
    tracker = MatchLatencyTracker()

    stats = tracker.getStats()

    assert stats == {'average': None, 'min': None, 'max': None, 'camera_count': None}

  def test_camera_count_reflects_latest_sample(self):
    """Verify camera_count in getStats() is whatever the most recent sample carried."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=0.0)
    tracker.recordMatchLatency("t1", decision_timestamp=1.0, camera_count=2)
    tracker.markTrackStart("t2", timestamp=0.0)

    tracker.recordMatchLatency("t2", decision_timestamp=1.0, camera_count=5)

    assert tracker.getStats()['camera_count'] == 5

  def test_camera_count_none_when_not_provided(self):
    """Verify camera_count stays None if the caller never supplied one."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=0.0)

    tracker.recordMatchLatency("t1", decision_timestamp=1.0)

    assert tracker.getStats()['camera_count'] is None


class TestShutdown:
  """Test the interface-stability no-op shutdown method."""

  def test_shutdown_is_a_noop(self):
    """Verify shutdown() can always be called safely and returns nothing."""
    tracker = MatchLatencyTracker()

    assert tracker.shutdown() is None


class TestOtelMetricsIntegration:
  """Verify recordMatchLatency pushes the right values/attributes to OTel."""

  @patch('controller.latency_metrics.metrics')
  def test_records_raw_histogram_sample_with_category_attribute(self, mock_metrics):
    """Verify the raw latency sample is pushed to the histogram, tagged with category."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=100.0)

    tracker.recordMatchLatency("t1", decision_timestamp=102.0, category="person")

    mock_metrics.record_reid_match_latency.assert_called_once_with(2.0, {'category': 'person'})

  @patch('controller.latency_metrics.metrics')
  def test_histogram_sample_has_no_attributes_when_category_is_none(self, mock_metrics):
    """Verify no attrs dict is attached when category is not supplied."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=100.0)

    tracker.recordMatchLatency("t1", decision_timestamp=102.0)

    mock_metrics.record_reid_match_latency.assert_called_once_with(2.0, None)

  @patch('controller.latency_metrics.metrics')
  def test_pushes_rolling_avg_min_max_gauges(self, mock_metrics):
    """Verify a single recorded sample updates all three rolling gauges, tagged with category."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=100.0)

    tracker.recordMatchLatency("t1", decision_timestamp=102.0, category="car")

    mock_metrics.record_reid_rolling_avg_match_latency.assert_called_once_with(2.0, {'category': 'car'})
    mock_metrics.record_reid_rolling_min_match_latency.assert_called_once_with(2.0, {'category': 'car'})
    mock_metrics.record_reid_rolling_max_match_latency.assert_called_once_with(2.0, {'category': 'car'})

  @patch('controller.latency_metrics.metrics')
  def test_pushes_camera_count_gauge_when_provided(self, mock_metrics):
    """Verify the camera-count gauge fires with the rolling stats' camera_count and category tag."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=100.0)

    tracker.recordMatchLatency("t1", decision_timestamp=102.0, camera_count=3, category="person")

    mock_metrics.record_reid_current_camera_count.assert_called_once_with(3, {'category': 'person'})

  @patch('controller.latency_metrics.metrics')
  def test_does_not_push_camera_count_gauge_when_none(self, mock_metrics):
    """Verify the camera-count gauge is skipped entirely when camera_count is unknown."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=100.0)

    tracker.recordMatchLatency("t1", decision_timestamp=102.0)

    mock_metrics.record_reid_current_camera_count.assert_not_called()

  @patch('controller.latency_metrics.metrics')
  def test_no_metrics_pushed_when_no_start_time(self, mock_metrics):
    """Verify no OTel calls happen at all when there's nothing to measure."""
    tracker = MatchLatencyTracker()

    tracker.recordMatchLatency("never_started")

    mock_metrics.record_reid_match_latency.assert_not_called()
    mock_metrics.record_reid_rolling_avg_match_latency.assert_not_called()
    mock_metrics.record_reid_current_camera_count.assert_not_called()

  @patch('controller.latency_metrics.metrics')
  def test_no_metrics_pushed_when_latency_negative(self, mock_metrics):
    """Verify a discarded (negative-latency) measurement pushes nothing to OTel."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("t1", timestamp=100.0)

    tracker.recordMatchLatency("t1", decision_timestamp=99.0)

    mock_metrics.record_reid_match_latency.assert_not_called()
    mock_metrics.record_reid_rolling_avg_match_latency.assert_not_called()
    mock_metrics.record_reid_current_camera_count.assert_not_called()

  @patch('controller.latency_metrics.metrics')
  def test_multiple_categories_produce_separate_tagged_calls(self, mock_metrics):
    """Verify each category's samples are tagged independently, not merged."""
    tracker = MatchLatencyTracker()
    tracker.markTrackStart("person_1", timestamp=100.0)
    tracker.markTrackStart("car_1", timestamp=100.0)

    tracker.recordMatchLatency("person_1", decision_timestamp=102.0, category="person")
    tracker.recordMatchLatency("car_1", decision_timestamp=103.0, category="car")

    calls = mock_metrics.record_reid_match_latency.call_args_list
    assert calls[0].args == (2.0, {'category': 'person'})
    assert calls[1].args == (3.0, {'category': 'car'})