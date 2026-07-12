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
        "broker_image": "eclipse-mosquitto:2.0.22",
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


class TestCheckDroppedFrames:
  def _values_with_dropped(self, total):
    return {
        "scenescape_controller_mqtt_messages_dropped": {
            "kind": "sum",
            "unit": "1",
            "stats": {"total": total, "delta": {}},
        }
    }

  def test_counts_dropped_and_ratio(self):
    result = metrics_recorder.check_dropped_frames(
        self._values_with_dropped(5), output_frame_count=1000
    )
    assert result["dropped"] == 5
    assert result["output_frames"] == 1000
    assert result["ratio"] == pytest.approx(0.005)
    assert result["exceeded"] is False

  def test_exceeds_threshold(self):
    result = metrics_recorder.check_dropped_frames(
        self._values_with_dropped(50), output_frame_count=1000
    )
    assert result["ratio"] == pytest.approx(0.05)
    assert result["exceeded"] is True

  def test_sums_controller_and_tracker_metrics(self):
    values = self._values_with_dropped(3)
    values["tracker.mqtt.dropped"] = {
        "kind": "sum", "unit": "1", "stats": {"total": 7, "delta": {}},
    }
    result = metrics_recorder.check_dropped_frames(values, output_frame_count=1000)
    assert result["dropped"] == 10

  def test_zero_output_frames_yields_zero_ratio(self):
    result = metrics_recorder.check_dropped_frames(
        self._values_with_dropped(5), output_frame_count=0
    )
    assert result["ratio"] == 0.0
    assert result["exceeded"] is False

  def test_no_dropped_metric_reports_zero(self):
    result = metrics_recorder.check_dropped_frames({}, output_frame_count=1000)
    assert result["dropped"] == 0
    assert result["exceeded"] is False

  def test_custom_threshold(self):
    result = metrics_recorder.check_dropped_frames(
        self._values_with_dropped(5), output_frame_count=1000, threshold=0.001
    )
    assert result["exceeded"] is True

