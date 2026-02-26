# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Intel Corporation

"""
Load tests — verify the tracker can sustain the configured camera load.

The Makefile orchestrates the lifecycle:
  compose up (broker, otel-collector, tracker) → k6 run → pytest → compose down

The primary SLI is **dropped messages**: if the tracker can process every
message without drops, it can handle the load.  Latency and throughput are
reported as warnings for trend monitoring but do not gate the build.

Override defaults for boundary testing:
  NUM_CAMERAS=8 FPS=30 NUM_OBJECTS=500 DURATION=5m make test-load
"""

import warnings

import pytest

import pytimeparse2


class LoadTestWarning(UserWarning):
  """Non-critical KPI warning (latency or throughput outside expected range)."""
  pass


# ---------------------------------------------------------------------------
# Metric names (Prometheus-format, as exposed by OTel Collector)
# ---------------------------------------------------------------------------

MESSAGES_TOTAL = "tracker_mqtt_messages_total"
LATENCY_HISTOGRAM = "tracker_mqtt_latency_milliseconds"
DROPPED_TOTAL = "tracker_mqtt_dropped_total"
ACTIVE_TRACKS = "tracker_tracks_active"

# Per-stage latency histograms (informational — no SLI thresholds).
# These map to the pipeline stages recorded by ObservabilityContext:
#   receive → parse → buffer → queue → transform → track → publish
STAGE_METRICS = [
  ("Parse", "tracker_stage_parse_duration_milliseconds"),
  ("Buffer", "tracker_stage_buffer_duration_milliseconds"),
  ("Queue wait", "tracker_stage_queue_duration_milliseconds"),
  ("Transform", "tracker_stage_transform_duration_milliseconds"),
  ("Track", "tracker_stage_track_duration_milliseconds"),
  ("Publish", "tracker_stage_publish_duration_milliseconds"),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSLI:
  """Validate tracker service under load.

  Hard gate: dropped messages < 0.1%.
  Warnings: throughput, latency p50/p99 (informational KPIs).
  """

  def test_dropped_messages(self, load_config, prometheus, metrics_summary):
    """Primary SLI: verify the tracker processes all messages.

    The system can handle the load if it does not drop messages.
    Threshold: < 0.1% dropped messages.
    """
    received = prometheus.wait_for_stable_counter(
      MESSAGES_TOTAL,
      timeout=load_config["metrics_timeout"],
    )
    dropped = prometheus.get_counter(DROPPED_TOTAL) or 0
    drop_reasons = prometheus.get_counter_by_label(DROPPED_TOTAL, "reason")

    metrics_summary["received"] = received
    metrics_summary["dropped"] = dropped
    metrics_summary["drop_reasons"] = drop_reasons

    ratio = dropped / received if received else 0
    reason_detail = ", ".join(
      f"{int(v)}\u00d7{k}" for k, v in sorted(drop_reasons.items()) if v
    )
    assert ratio < load_config["drop_max_ratio"], (
      f"Drop ratio {ratio:.4%} >= {load_config['drop_max_ratio']:.4%} "
      f"({dropped:.0f} dropped / {received:.0f} received"
      + (f": {reason_detail}" if reason_detail else "") + ")"
    )

  def test_active_tracks(self, load_config, prometheus, metrics_summary):
    """Verify the tracker created the expected number of active tracks.

    Each camera publishes NUM_OBJECTS detections per frame.  The tracker
    must maintain exactly that many active tracks once steady state is
    reached.

    Threshold: active_tracks == NUM_OBJECTS.
    """
    tracks = prometheus.get_gauge(ACTIVE_TRACKS)
    metrics_summary["active_tracks"] = tracks

    expected = load_config["num_objects"]
    assert tracks is not None, f"Gauge {ACTIVE_TRACKS} not found"
    assert tracks == expected, (
      f"Active tracks {tracks:.0f} != {expected} objects"
    )

  def test_throughput(self, load_config, prometheus, metrics_summary):
    """KPI warning: sustained message throughput.

    Computes received messages / duration and compares against the
    configured minimum rate (cameras × FPS by default).
    """
    duration_s = pytimeparse2.parse(load_config["duration"])

    received = prometheus.wait_for_stable_counter(
      MESSAGES_TOTAL,
      timeout=load_config["metrics_timeout"],
    )

    rate = received / duration_s if duration_s else 0
    metrics_summary["throughput_rate"] = rate

    if rate < load_config["throughput_min"]:
      warnings.warn(
        f"Throughput {rate:.1f} msg/s < {load_config['throughput_min']} msg/s "
        f"(received {received:.0f} in {duration_s}s)",
        LoadTestWarning,
        stacklevel=2,
      )

  def test_latency_p50(self, load_config, prometheus, metrics_summary):
    """KPI warning: median end-to-end latency.

    Warning threshold: 1 chunk period (1000 / FPS ms).
    Includes time-chunk buffering — if median exceeds one full cycle,
    the system may be falling behind.
    """
    p50 = prometheus.get_histogram_percentile(
      LATENCY_HISTOGRAM, percentile=0.5,
    )
    metrics_summary["latency_p50"] = p50

    if p50 is None:
      warnings.warn(
        f"Histogram {LATENCY_HISTOGRAM} not found",
        LoadTestWarning,
        stacklevel=2,
      )
      return
    if p50 >= load_config["latency_p50_ms"]:
      warnings.warn(
        f"p50 latency {p50:.2f} ms >= {load_config['latency_p50_ms']:.0f} ms",
        LoadTestWarning,
        stacklevel=2,
      )

  def test_latency_p99(self, load_config, prometheus, metrics_summary):
    """KPI warning: tail latency.

    Warning threshold: 2 chunk periods (2000 / FPS ms).
    If p99 exceeds two full cycles, something is consistently backing up.
    """
    p99 = prometheus.get_histogram_percentile(
      LATENCY_HISTOGRAM, percentile=0.99,
    )
    metrics_summary["latency_p99"] = p99

    if p99 is None:
      warnings.warn(
        f"Histogram {LATENCY_HISTOGRAM} not found",
        LoadTestWarning,
        stacklevel=2,
      )
      return
    if p99 >= load_config["latency_p99_ms"]:
      warnings.warn(
        f"p99 latency {p99:.2f} ms >= {load_config['latency_p99_ms']:.0f} ms",
        LoadTestWarning,
        stacklevel=2,
      )

  def test_stage_latency_breakdown(self, prometheus, metrics_summary):
    """Informational: per-stage latency breakdown for pipeline diagnosis.

    Scrapes the per-stage histogram metrics and stores p50/p99 for each
    stage in metrics_summary.  Always passes — no assertions.  Values
    appear as n/a when the tracker does not yet emit stage metrics.
    """
    stages = {}
    for label, metric_name in STAGE_METRICS:
      p50 = prometheus.get_histogram_percentile(metric_name, percentile=0.5)
      p99 = prometheus.get_histogram_percentile(metric_name, percentile=0.99)
      stages[label] = {"p50": p50, "p99": p99}
    metrics_summary["stages"] = stages
