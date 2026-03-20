# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Intel Corporation

"""Pytest configuration for load tests — env-var-driven SLI budgets."""

import os
import platform
import time

import pytest
import pytimeparse2
import requests
from prometheus_client.parser import text_string_to_metric_families


# ---------------------------------------------------------------------------
# Load configuration fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def load_config(request):
  """Load test configuration from environment variables.

  The primary SLI is dropped messages (< 0.1%).  Latency and throughput
  are warning-only KPIs with FPS-derived defaults:

  - latency p50 warning: 1 chunk period  (1000 / FPS ms)
  - latency p99 warning: 2 chunk periods (2000 / FPS ms)
  - throughput warning:   95% of input rate (num_cameras × FPS × 0.95)

  Override any value:
    LATENCY_P50_MS=80 LATENCY_P99_MS=150 THROUGHPUT_MIN=40 make test-load
  """
  fps = int(os.getenv("FPS", "15"))
  num_cameras = int(os.getenv("NUM_CAMERAS", "4"))

  cfg = {
    "num_cameras": num_cameras,
    "fps": fps,
    "num_objects": int(os.getenv("NUM_OBJECTS", "300")),
    "duration": os.getenv("DURATION", "1m"),
    "latency_p50_ms": float(os.getenv("LATENCY_P50_MS", str(1000.0 / fps))),
    "latency_p99_ms": float(os.getenv("LATENCY_P99_MS", str(2000.0 / fps))),
    "throughput_min": float(os.getenv("THROUGHPUT_MIN",
                                      str(num_cameras * fps * 0.95))),
    "drop_max_ratio": float(os.getenv("DROP_MAX_RATIO", "0.001")),
    "prometheus_url": os.getenv("PROMETHEUS_URL", "http://localhost:8889/metrics"),
    "metrics_timeout": int(os.getenv("METRICS_TIMEOUT", "60")),
  }

  request.config._load_test_config = cfg
  return cfg


# ---------------------------------------------------------------------------
# Prometheus client fixture
# ---------------------------------------------------------------------------

class PrometheusClient:
  """Lightweight Prometheus text-format scraper."""

  def __init__(self, endpoint: str):
    self.endpoint = endpoint

  def fetch(self) -> dict:
    """Fetch and parse all metric families keyed by name."""
    resp = requests.get(self.endpoint, timeout=5)
    resp.raise_for_status()
    return {
      fam.name: fam
      for fam in text_string_to_metric_families(resp.text)
    }

  def get_counter(self, name: str, labels: dict | None = None) -> float | None:
    """Return the summed value of a counter across all label combinations.

    Tries with and without the ``_total`` suffix because the
    prometheus_client parser may normalise the family name.
    """
    metrics = self.fetch()
    family_name = name
    if name not in metrics and name.endswith("_total"):
      family_name = name[:-6]
    if family_name not in metrics:
      return None
    total = 0.0
    found = False
    for sample in metrics[family_name].samples:
      if "_created" in sample.name:
        continue
      if labels and not all(sample.labels.get(k) == v for k, v in labels.items()):
        continue
      total += sample.value
      found = True
    return total if found else None

  def get_counter_by_label(
    self, name: str, label: str
  ) -> dict[str, float]:
    """Return counter values grouped by a single label.

    Returns a dict mapping each distinct value of ``label`` to its
    summed counter value.  Useful for breaking down
    ``tracker_mqtt_dropped_total`` by ``reason``.
    """
    metrics = self.fetch()
    family_name = name
    if name not in metrics and name.endswith("_total"):
      family_name = name[:-6]
    if family_name not in metrics:
      return {}
    result: dict[str, float] = {}
    for sample in metrics[family_name].samples:
      if "_created" in sample.name:
        continue
      key = sample.labels.get(label, "")
      result[key] = result.get(key, 0) + sample.value
    return result

  def get_histogram_percentile(
    self, name: str, labels: dict | None = None, percentile: float = 0.5
  ) -> float | None:
    """Compute a percentile from histogram buckets.

    Uses the same linear interpolation formula as Prometheus's
    ``histogram_quantile()`` function.  Buckets are aggregated across
    all label dimensions so that, for example, ``category=person`` and
    ``category=vehicle`` are merged before the percentile is calculated.
    """
    metrics = self.fetch()
    if name not in metrics:
      return None
    samples = list(metrics[name].samples)
    agg_buckets: dict[str, float] = {}
    for s in samples:
      if labels and not all(s.labels.get(k) == v for k, v in labels.items()):
        continue
      if s.name.endswith("_bucket"):
        le = s.labels.get("le", "+Inf")
        agg_buckets[le] = agg_buckets.get(le, 0) + s.value
    if not agg_buckets:
      return None

    # Sort by upper bound; keep +Inf last.
    sorted_bounds = sorted(
      ((float(le), count) for le, count in agg_buckets.items() if le != "+Inf"),
      key=lambda x: x[0],
    )
    inf_count = agg_buckets.get("+Inf", 0)
    if inf_count == 0:
      return None

    rank = percentile * inf_count
    prev_le = 0.0
    prev_count = 0.0
    for le, count in sorted_bounds:
      if count >= rank:
        # Linear interpolation within this bucket (Prometheus formula).
        denom = count - prev_count
        if denom == 0:
          return prev_le
        return prev_le + (le - prev_le) * (rank - prev_count) / denom
      prev_le = le
      prev_count = count
    return sorted_bounds[-1][0] if sorted_bounds else None

  def get_gauge(self, name: str, labels: dict | None = None) -> float | None:
    """Return the summed value of a gauge across all label combinations."""
    metrics = self.fetch()
    if name not in metrics:
      return None
    total = 0.0
    found = False
    for sample in metrics[name].samples:
      if labels and not all(sample.labels.get(k) == v for k, v in labels.items()):
        continue
      total += sample.value
      found = True
    return total if found else None

  def wait_for_stable_counter(
    self, name: str, timeout: int = 30, stable_readings: int = 3
  ) -> float:
    """Poll until a counter stops changing.

    Returns the final value once ``stable_readings`` consecutive
    scrapes return the same value, or when ``timeout`` expires
    (returns the last observed value).
    """
    deadline = time.monotonic() + timeout
    last_value = None
    stable_count = 0

    while time.monotonic() < deadline:
      value = self.get_counter(name)
      if value is not None and value == last_value:
        stable_count += 1
        if stable_count >= stable_readings:
          return value
      else:
        stable_count = 0
      last_value = value
      time.sleep(1)

    if last_value is not None:
      return last_value
    raise TimeoutError(f"Counter {name} never appeared within {timeout}s")


@pytest.fixture(scope="session")
def prometheus(load_config):
  """Session-scoped Prometheus scraper pointed at the OTel Collector."""
  return PrometheusClient(load_config["prometheus_url"])


@pytest.fixture(scope="session")
def metrics_summary(request):
  """Shared dict for tests to deposit observed metric values.

  Stored on the pytest Config object so ``pytest_terminal_summary``
  can access it without reaching into fixture internals.
  """
  store = {}
  request.config._load_test_summary = store
  return store


# ---------------------------------------------------------------------------
# Summary report plugin
# ---------------------------------------------------------------------------

def _gather_hardware_info():
  """Collect host hardware details for reproducibility.

  Returns a dict with cpu_model, cpu_cores, ram_gb, and kernel.
  Every field falls back to 'n/a' when unavailable.
  """
  info = {"cpu_model": "n/a", "cpu_cores": "n/a", "ram_gb": "n/a",
          "kernel": "n/a"}

  # CPU model from /proc/cpuinfo
  try:
    with open("/proc/cpuinfo") as f:
      for line in f:
        if line.startswith("model name"):
          info["cpu_model"] = line.split(":", 1)[1].strip()
          break
  except OSError:
    pass

  # Logical core count
  cores = os.cpu_count()
  if cores is not None:
    info["cpu_cores"] = str(cores)

  # Total RAM from /proc/meminfo
  try:
    with open("/proc/meminfo") as f:
      for line in f:
        if line.startswith("MemTotal:"):
          kb = int(line.split()[1])
          info["ram_gb"] = f"{kb / 1048576:.1f} GB"
          break
  except (OSError, ValueError):
    pass

  # Kernel version
  try:
    info["kernel"] = platform.release()
  except Exception:
    pass

  return info


def pytest_terminal_summary(terminalreporter, exitstatus, config):
  """Print a load-test summary table after all tests complete."""
  summary = getattr(config, "_load_test_summary", None)
  load_cfg = getattr(config, "_load_test_config", None)
  if not summary or not load_cfg:
    return

  duration_s = pytimeparse2.parse(load_cfg["duration"]) or 0
  w = terminalreporter
  w.section("Load Test Summary", sep="=", bold=True)

  # -- Hardware + test parameters (compact) ----------------------------------
  hw = _gather_hardware_info()
  cores = f" ({hw['cpu_cores']} cores)" if hw["cpu_cores"] != "n/a" else ""
  input_rate = load_cfg["num_cameras"] * load_cfg["fps"]
  w.line("")
  w.line(f"  Hardware: {hw['cpu_model']}{cores}, {hw['ram_gb']}, "
         f"kernel {hw['kernel']}")
  w.line(f"  Load:     {load_cfg['num_cameras']} cam \u00d7 {load_cfg['fps']} FPS "
         f"\u00d7 {load_cfg['num_objects']} obj = {input_rate} msg/s "
         f"for {load_cfg['duration']} ({duration_s}s)")
  w.line("")

  # -- KPI results -----------------------------------------------------------
  hdr = f"  {'KPI':<22} {'Actual':>14}  {'Threshold':>14}  {'Result':>6}"
  w.line(hdr)
  w.line("  " + "-" * (len(hdr) - 2))

  rows = []

  # Drops
  dropped = summary.get("dropped", 0)
  received = summary.get("received", 0)
  drop_ratio = dropped / received if received else 0
  thr = load_cfg["drop_max_ratio"]
  rows.append((
    "Dropped messages",
    f"{drop_ratio:.4%}",
    f"< {thr:.4%}",
    "PASS" if drop_ratio < thr else "FAIL",
  ))

  # Active tracks
  tracks = summary.get("active_tracks")
  expected = load_cfg["num_objects"]
  tracks_str = f"{tracks:.0f}" if tracks is not None else "n/a"
  rows.append((
    "Active tracks",
    tracks_str,
    f"== {expected}",
    "PASS" if tracks == expected else "FAIL"
    if tracks is not None else "n/a",
  ))

  # Throughput
  rate = summary.get("throughput_rate")
  thr_tp = load_cfg["throughput_min"]
  rows.append((
    "Throughput",
    f"{rate:.1f} msg/s" if rate is not None else "n/a",
    f">= {thr_tp:.1f} msg/s",
    "OK" if rate is not None and rate >= thr_tp else "WARN"
    if rate is not None else "n/a",
  ))

  # Latency p50
  p50 = summary.get("latency_p50")
  thr_p50 = load_cfg["latency_p50_ms"]
  rows.append((
    "Latency p50",
    f"{p50:.2f} ms" if p50 is not None else "n/a",
    f"< {thr_p50:.1f} ms",
    "OK" if p50 is not None and p50 < thr_p50 else "WARN"
    if p50 is not None else "n/a",
  ))

  # Latency p99
  p99 = summary.get("latency_p99")
  thr_p99 = load_cfg["latency_p99_ms"]
  rows.append((
    "Latency p99",
    f"{p99:.2f} ms" if p99 is not None else "n/a",
    f"< {thr_p99:.1f} ms",
    "OK" if p99 is not None and p99 < thr_p99 else "WARN"
    if p99 is not None else "n/a",
  ))

  for kpi, actual, thresh, result in rows:
    w.line(f"  {kpi:<22} {actual:>14}  {thresh:>14}  {result:>6}")

  # -- Messages line (drop reasons folded inline when single reason) ---------
  drop_reasons = summary.get("drop_reasons", {})
  non_zero_reasons = {r: int(c) for r, c in drop_reasons.items() if c}
  w.line("")
  if dropped > 0 and len(non_zero_reasons) == 1:
    reason = next(iter(non_zero_reasons))
    w.line(f"  Messages: {received:.0f} received, "
           f"{dropped:.0f} dropped ({reason})")
  elif dropped > 0:
    w.line(f"  Messages: {received:.0f} received, "
           f"{dropped:.0f} dropped")
    for reason, count in sorted(non_zero_reasons.items()):
      w.line(f"    {reason:<30} {count:>6}")
  else:
    w.line(f"  Messages: {received:.0f} received, 0 dropped")

  # -- Stage latency breakdown -----------------------------------------------
  stages = summary.get("stages")
  if stages:
    any_data = any(
      v.get("p50") is not None or v.get("p99") is not None
      for v in stages.values()
    )
    if any_data:
      w.line("")
      w.line("  Stage Latency (informational):")
      w.line(f"    {'Stage':<22} {'p50 (ms)':>10}  {'p99 (ms)':>10}")
      w.line("    " + "-" * 46)

      for label, vals in stages.items():
        sp50 = vals.get("p50")
        sp99 = vals.get("p99")
        p50_str = f"{sp50:.2f}" if sp50 is not None else "n/a"
        p99_str = f"{sp99:.2f}" if sp99 is not None else "n/a"
        w.line(f"    {label:<22} {p50_str:>10}  {p99_str:>10}")

      w.line("    " + "-" * 46)
      e2e_p50 = summary.get("latency_p50")
      e2e_p99 = summary.get("latency_p99")
      e2e_p50_str = f"{e2e_p50:.2f}" if e2e_p50 is not None else "n/a"
      e2e_p99_str = f"{e2e_p99:.2f}" if e2e_p99 is not None else "n/a"
      w.line(f"    {'End-to-end':<22} {e2e_p50_str:>10}  {e2e_p99_str:>10}")

  w.line("")
