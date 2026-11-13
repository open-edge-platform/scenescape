# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the BlackBoxHarness metrics recorder."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from harnesses.black_box_harness import BlackBoxHarness
from harnesses.black_box_harness import metrics_recorder


def _attr(key, value):
  return {"key": key, "value": {"stringValue": value}}


def _export_record(metrics):
  """Wrap a list of OTLP-JSON metric dicts in an ExportMetricsServiceRequest."""
  return {
      "resourceMetrics": [
          {"scopeMetrics": [{"metrics": metrics}]}
      ]
  }


def _dropped_record(totals_by_reason):
  """One export of tracker.mqtt.dropped with one cumulative series per reason."""
  return _export_record([{
      "name": "tracker.mqtt.dropped",
      "unit": "{message}",
      "sum": {"dataPoints": [
          {"attributes": [_attr("scene", "Test_Scene"), _attr("reason", reason)],
           "timeUnixNano": "1000", "asInt": str(total)}
          for reason, total in totals_by_reason.items()
      ]},
  }])


@pytest.fixture
def metrics_file(tmp_path):
  """A two-export collector output with histogram, counter, and gauge metrics."""
  attrs = [_attr("scene", "Test_Scene")]
  # Cumulative export #1
  rec1 = _export_record([
      {
          "name": "tracker.mqtt.latency",
          "unit": "ms",
          "histogram": {"dataPoints": [{
              "attributes": attrs, "timeUnixNano": "1000",
              "count": "2", "sum": 6.0, "min": 1.0, "max": 5.0,
          }]},
      },
      {
          "name": "tracker.mqtt.messages",
          "unit": "{message}",
          "sum": {"dataPoints": [{
              "attributes": attrs, "timeUnixNano": "1000", "asInt": "2",
          }]},
      },
      {
          "name": "tracker.tracks.active",
          "unit": "{track}",
          "gauge": {"dataPoints": [{
              "attributes": attrs, "timeUnixNano": "1000", "asInt": "1",
          }]},
      },
  ])
  # Cumulative export #2 (later timestamp, larger cumulative values)
  rec2 = _export_record([
      {
          "name": "tracker.mqtt.latency",
          "unit": "ms",
          "histogram": {"dataPoints": [{
              "attributes": attrs, "timeUnixNano": "2000",
              "count": "4", "sum": 16.0, "min": 1.0, "max": 9.0,
          }]},
      },
      {
          "name": "tracker.mqtt.messages",
          "unit": "{message}",
          "sum": {"dataPoints": [{
              "attributes": attrs, "timeUnixNano": "2000", "asInt": "5",
          }]},
      },
      {
          "name": "tracker.tracks.active",
          "unit": "{track}",
          "gauge": {"dataPoints": [{
              "attributes": attrs, "timeUnixNano": "2000", "asInt": "3",
          }]},
      },
  ])
  path = tmp_path / "metrics.json"
  path.write_text(json.dumps(rec1) + "\n" + json.dumps(rec2) + "\n")
  return path


class TestBuildSummary:
  def test_histogram_uses_last_cumulative_point(self, metrics_file):
    summary = metrics_recorder.build_summary(metrics_file, {})
    assert "[tracker.mqtt.latency] (histogram, unit=ms)" in summary
    # avg = sum/count from the latest cumulative point = 16/4 = 4.0
    assert "count:  4" in summary
    assert "avg:    4.0000" in summary
    assert "min:    1.0000" in summary
    assert "max:    9.0000" in summary

  def test_counter_total_and_deltas(self, metrics_file):
    summary = metrics_recorder.build_summary(metrics_file, {})
    assert "[tracker.mqtt.messages] (sum, unit={message})" in summary
    # total = last cumulative value = 5
    assert "total:  5" in summary
    # per-interval deltas: [2, 3] -> avg 2.5, min 2, max 3, median 2.5
    assert "avg: 2.50" in summary
    assert "median: 2.50" in summary

  def test_gauge_stats_over_all_values(self, metrics_file):
    summary = metrics_recorder.build_summary(metrics_file, {})
    assert "[tracker.tracks.active] (gauge, unit={track})" in summary
    # values [1, 3] -> avg 2.0, min 1, max 3, median 2.0
    assert "avg: 2.0000" in summary
    assert "min: 1.0000" in summary
    assert "max: 3.0000" in summary

  def test_header_includes_metadata(self, metrics_file):
    summary = metrics_recorder.build_summary(
        metrics_file,
        {"container_type": "tracker", "endpoint": "c:4317", "export_interval_s": 2},
    )
    assert "Container type:   tracker" in summary
    assert "Metrics endpoint: c:4317" in summary
    assert "Export interval:  2s" in summary

  def test_missing_file(self, tmp_path):
    summary = metrics_recorder.build_summary(tmp_path / "absent.json", {})
    assert "No metrics file produced" in summary

  def test_empty_file(self, tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("")
    summary = metrics_recorder.build_summary(path, {})
    assert "No metrics recorded." in summary

  def test_write_summary_creates_file(self, metrics_file, tmp_path):
    out = tmp_path / "out" / "metrics_summary.txt"
    text = metrics_recorder.write_summary(metrics_file, out, {})
    assert out.exists()
    assert out.read_text() == text


class TestMetricsCustomConfig:
  @pytest.fixture
  def tracker_config_file(self, tmp_path):
    p = tmp_path / "tracker-config.json"
    p.write_text(json.dumps({"time_chunking_enabled": False}))
    return str(p)

  def _base(self, tracker_config_file):
    return {
        "tracker_config_path": tracker_config_file,
        "broker_image": "eclipse-mosquitto:2.1-alpine",
        "container_type": "controller",
    }

  def test_metrics_disabled_by_default(self, tracker_config_file):
    harness = BlackBoxHarness("intel/scenescape-controller:test")
    harness.set_custom_config(self._base(tracker_config_file))
    assert harness._enable_metrics is False

  def test_enable_metrics_requires_collector_image(self, tracker_config_file):
    harness = BlackBoxHarness("intel/scenescape-controller:test")
    cfg = self._base(tracker_config_file)
    cfg["enable_metrics"] = True
    with pytest.raises(ValueError, match="metrics_collector_image"):
      harness.set_custom_config(cfg)

  def test_enable_metrics_parses_options(self, tracker_config_file):
    harness = BlackBoxHarness("intel/scenescape-controller:test")
    cfg = self._base(tracker_config_file)
    cfg.update({
        "enable_metrics": True,
        "metrics_collector_image": "otel/opentelemetry-collector-contrib:0.155.0",
        "metrics_export_interval_s": 3,
        "metrics_otlp_port": 5317,
    })
    harness.set_custom_config(cfg)
    assert harness._enable_metrics is True
    assert harness._metrics_collector_image.endswith("0.155.0")
    assert harness._metrics_export_interval_s == 3
    assert harness._metrics_otlp_port == 5317


class TestCollectMetricValues:
  def test_returns_structured_values_per_metric(self, metrics_file):
    values = metrics_recorder.collect_metric_values(metrics_file)
    assert set(values) == {
        "tracker.mqtt.latency",
        "tracker.mqtt.messages",
        "tracker.tracks.active",
    }
    hist = values["tracker.mqtt.latency"]
    assert hist["kind"] == "histogram"
    assert hist["stats"]["count"] == 4
    assert hist["stats"]["avg"] == 4.0
    counter = values["tracker.mqtt.messages"]
    assert counter["kind"] == "sum"
    assert counter["stats"]["total"] == 5
    gauge = values["tracker.tracks.active"]
    assert gauge["kind"] == "gauge"
    assert gauge["stats"]["max"] == 3

  def test_missing_file_returns_empty(self, tmp_path):
    assert metrics_recorder.collect_metric_values(tmp_path / "absent.json") == {}

  def test_counter_totals_per_reason(self, tmp_path):
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(_dropped_record({"rejected_schema": 4, "dropped_queue_full": 2})) + "\n")
    stats = metrics_recorder.collect_metric_values(path)["tracker.mqtt.dropped"]["stats"]
    assert stats["total"] == 6
    assert stats["by_reason"] == {"rejected_schema": 4, "dropped_queue_full": 2}

  def test_all_rejected_tracker_run_is_flagged(self, tmp_path):
    # Every message failed validation: tracker.mqtt.messages never increments.
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(_dropped_record({"rejected_schema": 500})) + "\n")
    result = metrics_recorder.check_dropped_frames(metrics_recorder.collect_metric_values(path))
    assert result["dropped"] == 500
    assert result["received"] == 500
    assert result["ratio"] == 1.0
    assert result["exceeded"] is True


class TestCheckDroppedFrames:
  def _values(self, dropped, messages=1000):
    return {
        "scenescape_controller_mqtt_messages_dropped": {
            "kind": "sum",
            "unit": "1",
            "stats": {"total": dropped, "delta": {}},
        },
        "scenescape_controller_mqtt_messages": {
            "kind": "sum",
            "unit": "1",
            "stats": {"total": messages, "delta": {}},
        },
    }

  def test_counts_dropped_and_ratio(self):
    result = metrics_recorder.check_dropped_frames(self._values(5))
    assert result["dropped"] == 5
    assert result["received"] == 1000
    assert result["ratio"] == pytest.approx(0.005)
    assert result["exceeded"] is False

  def test_exceeds_threshold(self):
    result = metrics_recorder.check_dropped_frames(self._values(50))
    assert result["ratio"] == pytest.approx(0.05)
    assert result["exceeded"] is True

  def test_sums_controller_and_tracker_metrics(self):
    values = self._values(3, messages=600)
    values["tracker.mqtt.dropped"] = {
        "kind": "sum", "unit": "1", "stats": {"total": 7, "delta": {}},
    }
    values["tracker.mqtt.messages"] = {
        "kind": "sum", "unit": "1", "stats": {"total": 400, "delta": {}},
    }
    result = metrics_recorder.check_dropped_frames(values)
    assert result["dropped"] == 10
    assert result["received"] == 1000

  def test_ratio_is_per_message_not_per_frame(self):
    # 2 cameras x 800 frames = 1600 messages; 64 drops is 4%, not 8% of 800 frames.
    result = metrics_recorder.check_dropped_frames(self._values(64, messages=1600))
    assert result["ratio"] == pytest.approx(0.04)

  def test_dropped_without_received_messages_is_flagged(self):
    result = metrics_recorder.check_dropped_frames(self._values(5, messages=0))
    assert result["ratio"] == 1.0
    assert result["exceeded"] is True

  def test_nothing_received_or_dropped_yields_zero_ratio(self):
    result = metrics_recorder.check_dropped_frames(self._values(0, messages=0))
    assert result["ratio"] == 0.0
    assert result["exceeded"] is False

  def test_tracker_rejections_count_as_received(self):
    # tracker.mqtt.messages counts accepted messages only; rejected ones are only in tracker.mqtt.dropped.
    values = {
        "tracker.mqtt.messages": {
            "kind": "sum", "unit": "1", "stats": {"total": 900, "delta": {}},
        },
        "tracker.mqtt.dropped": {
            "kind": "sum", "unit": "1",
            "stats": {"total": 150, "delta": {},
                      "by_reason": {"rejected_lag": 100, "dropped_queue_full": 50}},
        },
    }
    result = metrics_recorder.check_dropped_frames(values)
    assert result["received"] == 1000
    assert result["ratio"] == pytest.approx(0.15)

  def test_no_dropped_metric_reports_zero(self):
    result = metrics_recorder.check_dropped_frames({})
    assert result["dropped"] == 0
    assert result["exceeded"] is False

  def test_custom_threshold(self):
    result = metrics_recorder.check_dropped_frames(self._values(5), threshold=0.001)
    assert result["exceeded"] is True


class TestCheckDroppedFramesCategories:
  """Loss is judged per category; the worst category is the reported ratio."""

  def _values(self, by_category, messages=1600, metric="scenescape_controller_mqtt_messages"):
    dropped_metric = (
        "tracker.mqtt.dropped" if metric == "tracker.mqtt.messages"
        else "scenescape_controller_mqtt_messages_dropped"
    )
    total = sum(v for reasons in by_category.values() for v in reasons.values())
    by_reason = {}
    for reasons in by_category.values():
      for reason, value in reasons.items():
        by_reason[reason] = by_reason.get(reason, 0) + value
    return {
        dropped_metric: {
            "kind": "sum", "unit": "1",
            "stats": {"total": total, "by_reason": by_reason, "by_category": by_category,
                      "delta": {}},
        },
        metric: {"kind": "sum", "unit": "1", "stats": {"total": messages, "delta": {}}},
    }

  def test_worst_category_is_the_reported_ratio(self):
    # The average over both categories is 0.97%, but FW190D lost 1.19% of its inputs.
    values = self._values({"person": {"tracker_busy": 12}, "FW190D": {"tracker_busy": 19}})
    result = metrics_recorder.check_dropped_frames(
        values, inputs_per_category={"person": 1600, "FW190D": 1593})
    assert result["dropped"] == 31
    assert result["worst_category"] == "FW190D"
    assert result["ratio"] == pytest.approx(19 / 1593)
    assert result["categories"]["person"] == {"dropped": 12, "inputs": 1600, "ratio": 12 / 1600}
    assert result["exceeded"] is True

  def test_all_categories_below_the_threshold_is_not_flagged(self):
    values = self._values({"person": {"tracker_busy": 4}, "FW190D": {"tracker_busy": 8}})
    result = metrics_recorder.check_dropped_frames(
        values, inputs_per_category={"person": 1600, "FW190D": 1600})
    assert result["ratio"] == pytest.approx(0.005)
    assert result["exceeded"] is False

  def test_category_without_drops_is_listed(self):
    values = self._values({"person": {"tracker_busy": 16}})
    result = metrics_recorder.check_dropped_frames(
        values, inputs_per_category={"person": 1600, "FW190D": 1600})
    assert result["categories"]["FW190D"]["ratio"] == 0.0
    assert result["worst_category"] == "person"

  def test_message_level_drops_count_for_every_category(self):
    values = self._values({
        "": {"fell_behind": 8, "ptz_dwell": 8},
        "person": {"tracker_busy": 16},
    })
    result = metrics_recorder.check_dropped_frames(
        values, inputs_per_category={"person": 1600, "FW190D": 1600})
    assert result["categories"]["FW190D"]["dropped"] == 16
    assert result["categories"]["person"]["dropped"] == 32
    assert result["ratio"] == pytest.approx(0.02)

  def test_message_level_drops_are_an_upper_bound_for_a_rare_category(self):
    # Documented limit: the counter has no category, so one dropped person-only message is
    # also counted against the rare "car" category, which lost nothing itself.
    values = self._values({"": {"ptz_dwell": 1}}, messages=1000)
    result = metrics_recorder.check_dropped_frames(
        values, inputs_per_category={"person": 990, "car": 10})
    assert result["categories"]["car"]["ratio"] == pytest.approx(0.1)
    assert result["worst_category"] == "car"
    assert result["exceeded"] is True

  def test_category_drops_without_inputs_use_the_received_count(self):
    result = metrics_recorder.check_dropped_frames(self._values({"person": {"tracker_busy": 96}}))
    assert result["categories"]["person"]["inputs"] == 1600
    assert result["ratio"] == pytest.approx(0.06)

  def test_tracker_service_rejections_count_for_every_category(self):
    values = self._values(
        {"": {"rejected_lag": 100}, "person": {"dropped_queue_full": 40, "dropped_max_workers": 20}},
        messages=900, metric="tracker.mqtt.messages")
    result = metrics_recorder.check_dropped_frames(values, inputs_per_category={"person": 1000})
    # 100 rejected messages plus 60 queue and worker-limit drops out of 1000 inputs.
    assert result["received"] == 1000
    assert result["categories"]["person"]["dropped"] == 160
    assert result["ratio"] == pytest.approx(0.16)

  def test_drops_without_a_category_breakdown_are_taken_as_message_level(self):
    values = {
        "scenescape_controller_mqtt_messages_dropped": {
            "kind": "sum", "unit": "1", "stats": {"total": 20, "delta": {}},
        },
        "scenescape_controller_mqtt_messages": {
            "kind": "sum", "unit": "1", "stats": {"total": 1000, "delta": {}},
        },
    }
    result = metrics_recorder.check_dropped_frames(values)
    assert result["categories"] == {}
    assert result["worst_category"] is None
    assert result["ratio"] == pytest.approx(0.02)

  def test_collected_counter_keeps_totals_per_category_and_reason(self, tmp_path):
    record = _export_record([{
        "name": "scenescape_controller_mqtt_messages_dropped",
        "unit": "1",
        "sum": {"dataPoints": [
            {"attributes": [_attr("category", category), _attr("reason", reason)],
             "timeUnixNano": "1000", "asInt": str(total)}
            for category, reason, total in (
                ("person", "tracker_busy", 12), ("FW190D", "tracker_busy", 19),
                ("", "fell_behind", 3))
        ]},
    }])
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(record) + "\n")
    stats = metrics_recorder.collect_metric_values(path)[
        "scenescape_controller_mqtt_messages_dropped"]["stats"]
    assert stats["by_category"] == {
        "person": {"tracker_busy": 12}, "FW190D": {"tracker_busy": 19}, "": {"fell_behind": 3}}

