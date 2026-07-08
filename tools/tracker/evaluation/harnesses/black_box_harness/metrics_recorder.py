# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Parse OTLP metrics captured by the OTEL Collector and summarise them.

The BlackBoxHarness optionally runs an OpenTelemetry Collector container that
receives OTLP/gRPC metrics pushed by the tracker / controller container and
writes them to a JSON file via the ``file`` exporter.  Each line of that file
is the OTLP-JSON encoding of an ``ExportMetricsServiceRequest`` produced once
per export interval.

Both services export with *cumulative* aggregation temporality, so the most
recent data point of each time series carries the full run total.  This module
reads the file, aggregates statistics per metric (across all attribute series),
and writes a human-readable ``metrics_summary.txt``.

Statistic semantics
-------------------
* **Histogram** metrics (latencies): ``count``, ``avg`` (sum / count), ``min``
  and ``max`` taken from the cumulative data point's recorded min/max.  Median
  is intentionally omitted because raw samples are not retained (only bucketed
  counts), so any percentile would be a bucket estimate.
* **Counter** (monotonic sum) metrics: cumulative ``total`` plus the per-export
  delta distribution (``avg`` / ``min`` / ``max`` / ``median``).
* **Gauge** metrics: ``avg`` / ``min`` / ``max`` / ``median`` over every
  observed value across the run.
"""

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# OTLP data-point "kind" keys as they appear in OTLP-JSON metric objects.
_KIND_HISTOGRAM = "histogram"
_KIND_SUM = "sum"
_KIND_GAUGE = "gauge"

# Counter metrics whose cumulative total reports messages/frames the service
# dropped (e.g. due to lag, queue overflow, or worker saturation).  Both the
# legacy controller and the tracker service expose an equivalent counter.
DROPPED_FRAME_METRICS = (
    "scenescape_controller_mqtt_messages_dropped",
    "tracker.mqtt.dropped",
)

# Default warning threshold for the dropped-frame ratio (1%).
DEFAULT_DROPPED_FRAME_THRESHOLD = 0.01


def _to_float(value: Any) -> Optional[float]:
  """Convert an OTLP-JSON scalar (string or number) to float, or None."""
  if value is None:
    return None
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def _point_scalar(point: Dict[str, Any]) -> Optional[float]:
  """Return the numeric value of a sum/gauge data point (asInt or asDouble)."""
  if "asInt" in point:
    return _to_float(point["asInt"])
  if "asDouble" in point:
    return _to_float(point["asDouble"])
  return None


def _series_key(point: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
  """Build a hashable key identifying the attribute set of a data point."""
  attrs = point.get("attributes", []) or []
  pairs: List[Tuple[str, str]] = []
  for attr in attrs:
    key = attr.get("key", "")
    raw = attr.get("value", {}) or {}
    # Only string/int/double/bool attribute values are expected here.
    val = (
        raw.get("stringValue")
        if "stringValue" in raw
        else raw.get("intValue")
        if "intValue" in raw
        else raw.get("doubleValue")
        if "doubleValue" in raw
        else raw.get("boolValue")
    )
    pairs.append((str(key), str(val)))
  return tuple(sorted(pairs))


def _point_time(point: Dict[str, Any]) -> int:
  """Return the data point's timeUnixNano as int (0 when absent).

  ``timeUnixNano`` is a nanosecond timestamp (~1e18) that exceeds the exact
  integer range of a float (2^53), so it is parsed directly as an integer
  from its (usually string) OTLP-JSON encoding.  Going through ``float()``
  would round it and could mis-order points when sorting or selecting the
  latest per series.
  """
  value = point.get("timeUnixNano")
  if value is None:
    return 0
  try:
    return int(value)
  except (TypeError, ValueError):
    return 0


def _load_records(path: Path) -> List[Dict[str, Any]]:
  """Load all OTLP-JSON export records (one per line) from *path*."""
  records: List[Dict[str, Any]] = []
  with open(path, "r", encoding="utf-8") as handle:
    for line in handle:
      line = line.strip()
      if not line:
        continue
      try:
        records.append(json.loads(line))
      except json.JSONDecodeError:
        continue
  return records


def _collect_metrics(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
  """Group every metric data point by metric name.

  Returns a mapping ``name -> {"kind", "unit", "points": [...]}`` where each
  point is the raw OTLP-JSON data-point dict augmented with the metric kind.
  """
  metrics: Dict[str, Dict[str, Any]] = {}
  for record in records:
    for resource_metric in record.get("resourceMetrics", []) or []:
      for scope_metric in resource_metric.get("scopeMetrics", []) or []:
        for metric in scope_metric.get("metrics", []) or []:
          name = metric.get("name")
          if not name:
            continue
          for kind in (_KIND_HISTOGRAM, _KIND_SUM, _KIND_GAUGE):
            if kind not in metric:
              continue
            entry = metrics.setdefault(
                name,
                {"kind": kind, "unit": metric.get("unit", ""), "points": []},
            )
            entry["points"].extend(metric[kind].get("dataPoints", []) or [])
            break
  return metrics


def _stats(values: List[float]) -> Dict[str, float]:
  """Return avg / min / max / median for a non-empty list of values."""
  return {
      "avg": statistics.fmean(values),
      "min": min(values),
      "max": max(values),
      "median": statistics.median(values),
  }


def _last_per_series(points: List[Dict[str, Any]]) -> Dict[Tuple, Dict[str, Any]]:
  """Return the latest (max timeUnixNano) data point for each attribute series."""
  latest: Dict[Tuple, Dict[str, Any]] = {}
  for point in points:
    key = _series_key(point)
    if key not in latest or _point_time(point) >= _point_time(latest[key]):
      latest[key] = point
  return latest


def _summarise_histogram(points: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
  """Aggregate cumulative histogram series into count/avg/min/max."""
  latest = _last_per_series(points)
  total_count = 0.0
  total_sum = 0.0
  mins: List[float] = []
  maxs: List[float] = []
  for point in latest.values():
    count = _to_float(point.get("count")) or 0.0
    total_count += count
    total_sum += _to_float(point.get("sum")) or 0.0
    pmin = _to_float(point.get("min"))
    pmax = _to_float(point.get("max"))
    if pmin is not None:
      mins.append(pmin)
    if pmax is not None:
      maxs.append(pmax)
  if total_count <= 0:
    return None
  return {
      "count": total_count,
      "avg": total_sum / total_count,
      "min": min(mins) if mins else float("nan"),
      "max": max(maxs) if maxs else float("nan"),
  }


def _summarise_counter(points: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
  """Aggregate cumulative counter series into a total plus per-export deltas."""
  # Group points by series so deltas are computed within a single time series.
  by_series: Dict[Tuple, List[Dict[str, Any]]] = {}
  for point in points:
    by_series.setdefault(_series_key(point), []).append(point)

  total = 0.0
  deltas: List[float] = []
  for series_points in by_series.values():
    series_points.sort(key=_point_time)
    previous = 0.0
    for point in series_points:
      value = _point_scalar(point)
      if value is None:
        continue
      if value < previous:
        # Counter reset/restart; treat this point as a new baseline.
        deltas.append(value)
      else:
        deltas.append(value - previous)
      previous = value
    total += previous
  if not deltas:
    return None
  return {"total": total, "delta": _stats(deltas)}


def _summarise_gauge(points: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
  """Aggregate gauge values across all series and timestamps."""
  values = [v for v in (_point_scalar(p) for p in points) if v is not None]
  if not values:
    return None
  return _stats(values)


def collect_metric_values(metrics_file: Path) -> Dict[str, Dict[str, Any]]:
  """Return aggregated metric and latency values keyed by metric name.

  Each entry has the shape::

      {
          "kind": "histogram" | "sum" | "gauge",
          "unit": <str>,
          "stats": <dict | None>,
      }

  where ``stats`` is the per-kind aggregation (histogram: ``count``/``avg``/
  ``min``/``max``; sum: ``total`` plus a ``delta`` distribution; gauge:
  ``avg``/``min``/``max``/``median``) or ``None`` when the series had no data.

  Args:
      metrics_file: Path to the OTEL Collector ``file`` exporter output.

  Returns:
      Mapping of metric name to its aggregated values (empty when the file is
      missing or contained no metrics).
  """
  if not metrics_file.exists():
    return {}

  metrics = _collect_metrics(_load_records(metrics_file))
  values: Dict[str, Dict[str, Any]] = {}
  for name, entry in metrics.items():
    kind = entry["kind"]
    if kind == _KIND_HISTOGRAM:
      stats = _summarise_histogram(entry["points"])
    elif kind == _KIND_SUM:
      stats = _summarise_counter(entry["points"])
    else:
      stats = _summarise_gauge(entry["points"])
    values[name] = {"kind": kind, "unit": entry["unit"], "stats": stats}
  return values


def check_dropped_frames(
    metric_values: Dict[str, Dict[str, Any]],
    output_frame_count: int,
    threshold: float = DEFAULT_DROPPED_FRAME_THRESHOLD,
) -> Dict[str, Any]:
  """Verify how many frames the tracker/controller dropped during the run.

  Sums the cumulative totals of the known dropped-frame counters and compares
  the dropped count against the number of tracker output frames.

  Args:
      metric_values:      Output of :func:`collect_metric_values`.
      output_frame_count: Number of tracker output frames collected.
      threshold:          Ratio above which the run is flagged (default 1%).

  Returns:
      Mapping with ``dropped`` (int), ``output_frames`` (int), ``ratio``
      (float; 0.0 when no output frames), ``threshold`` (float) and
      ``exceeded`` (bool).
  """
  dropped = 0
  for name in DROPPED_FRAME_METRICS:
    entry = metric_values.get(name)
    if entry and entry.get("stats"):
      dropped += int(entry["stats"].get("total", 0) or 0)

  ratio = dropped / output_frame_count if output_frame_count > 0 else 0.0
  return {
      "dropped": dropped,
      "output_frames": int(output_frame_count),
      "ratio": ratio,
      "threshold": threshold,
      "exceeded": ratio > threshold,
  }


def build_summary(metrics_file: Path, metadata: Dict[str, Any]) -> str:
  """Build the metrics summary text from a collector output file.

  Args:
      metrics_file: Path to the OTEL Collector ``file`` exporter output.
      metadata:     Context shown in the header (container type, endpoint,
                    export interval).

  Returns:
      The formatted summary text.
  """
  lines: List[str] = ["=== Observability Metrics ==="]
  lines.append(f"Container type:   {metadata.get('container_type', 'unknown')}")
  lines.append(f"Metrics endpoint: {metadata.get('endpoint', 'unknown')}")
  lines.append(f"Export interval:  {metadata.get('export_interval_s', 'unknown')}s")
  lines.append("")

  if not metrics_file.exists():
    lines.append("No metrics file produced by the collector.")
    return "\n".join(lines)

  values = collect_metric_values(metrics_file)
  if not values:
    lines.append("No metrics recorded.")
    return "\n".join(lines)

  for name in sorted(values):
    entry = values[name]
    kind = entry["kind"]
    unit = entry["unit"]
    summary = entry["stats"]
    unit_suffix = f", unit={unit}" if unit else ""
    lines.append(f"[{name}] ({kind}{unit_suffix})")

    if summary is None:
      lines.append("  no data points")
    elif kind == _KIND_HISTOGRAM:
      lines.append(f"  count:  {int(summary['count'])}")
      lines.append(f"  avg:    {summary['avg']:.4f}")
      lines.append(f"  min:    {summary['min']:.4f}")
      lines.append(f"  max:    {summary['max']:.4f}")
    elif kind == _KIND_SUM:
      delta = summary["delta"]
      lines.append(f"  total:  {summary['total']:.0f}")
      lines.append(
          "  per-interval delta  "
          f"avg: {delta['avg']:.2f}  min: {delta['min']:.0f}  "
          f"max: {delta['max']:.0f}  median: {delta['median']:.2f}"
      )
    else:  # gauge
      lines.append(
          f"  avg: {summary['avg']:.4f}  min: {summary['min']:.4f}  "
          f"max: {summary['max']:.4f}  median: {summary['median']:.4f}"
      )
    lines.append("")

  return "\n".join(lines).rstrip() + "\n"


def write_summary(
    metrics_file: Path, output_file: Path, metadata: Dict[str, Any]
) -> str:
  """Write the metrics summary to *output_file* and return its text."""
  summary = build_summary(metrics_file, metadata)
  output_file.parent.mkdir(parents=True, exist_ok=True)
  output_file.write_text(summary)
  return summary
