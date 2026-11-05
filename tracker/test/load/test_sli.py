# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Intel Corporation

"""Unit tests for the dropped-message SLI computation (no Docker needed)."""

import pytest

from sli import drop_gate, drop_summary, message_counts


class TestMessageCounts:
  def test_rejected_messages_count_as_received(self):
    # tracker.mqtt.messages counts accepted messages only; rejections are only in tracker.mqtt.dropped.
    counts = message_counts(accepted=96, drop_reasons={"rejected_lag": 3472})
    assert counts == {"received": 3568, "accepted": 96, "rejected": 3472, "dropped": 3472}

  def test_later_drops_are_not_added_to_received(self):
    # Messages dropped after acceptance (queue full) were already counted as accepted.
    counts = message_counts(accepted=1000, drop_reasons={"dropped_queue_full": 5, "rejected_schema": 2})
    assert counts["received"] == 1002
    assert counts["rejected"] == 2
    assert counts["dropped"] == 7


class TestDropGate:
  def test_clean_run_passes(self):
    assert drop_gate(dropped=0, received=3564, max_ratio=0.001) == (0.0, True)

  def test_ratio_is_dropped_over_received(self):
    ratio, passed = drop_gate(dropped=3472, received=3568, max_ratio=0.001)
    assert ratio == pytest.approx(0.9731, abs=1e-4)
    assert passed is False

  def test_all_rejected_run_fails(self):
    assert drop_gate(dropped=3500, received=3500, max_ratio=0.001) == (1.0, False)

  def test_nothing_received_fails(self):
    ratio, passed = drop_gate(dropped=0, received=0, max_ratio=0.001)
    assert passed is False


class TestDropSummary:
  def test_not_measured_is_not_reported_as_pass(self):
    # The gate did not store any values (deselected or errored): no PASS without a measurement.
    assert drop_summary({}, max_ratio=0.001) == ("n/a", "n/a")

  def test_nothing_received_reports_fail(self):
    summary = {"received": 0, "dropped": 0}
    assert drop_summary(summary, max_ratio=0.001) == ("n/a", "FAIL")

  def test_reports_measured_ratio(self):
    summary = {"received": 3568, "dropped": 3472}
    assert drop_summary(summary, max_ratio=0.001) == ("97.3094%", "FAIL")
    assert drop_summary({"received": 3564, "dropped": 0}, max_ratio=0.001) == ("0.0000%", "PASS")
