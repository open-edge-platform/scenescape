#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Long-running performance degradation system test.

Runs the full Scenescape stack for a configurable duration and watches for
the failure modes that matter on a long run:

1. Liveness — is the pipeline still producing data at all? A total
   throughput collapse would otherwise score as "stable" (a flat line has
   no variance), so this is checked as an absolute floor.
2. Variability growth — are the swings (standard deviation) in MQTT
   throughput, CPU, and Memory usage getting wider the longer the system
   runs? Growing variance indicates the system is becoming less stable even
   if the mean looks fine.
3. Saturation — does CPU/Memory usage reach a critical, crash-risking
   ceiling and stay there? Checked live, every cycle, so a run that
   saturates and then crashes is still caught even if the process dies
   before a final end-of-run analysis would otherwise run.
4. Memory trend — a steady leak is the canonical soak-test failure and is
   invisible to both of the checks above: a linear ramp has equal variance
   in both halves of the run and may never reach the ceiling within the
   test window. The memory trend is therefore extrapolated forward to see
   whether it would reach the saturation ceiling.
5. REST response-time guarantees — tail latency (p99/p99.9), not just the
   mean, is what determines whether real users experience delays. Multiple
   REST round-trips are sampled per cycle to build a latency distribution,
   which is checked against absolute SLA ceilings and for tail-latency
   growth between the early and late halves of the run.
6. MQTT pipeline latency — how long it takes for a scene update produced by
   the controller to actually reach a subscriber.

"""

import json
import math
import os
import statistics
import time
from datetime import datetime, timedelta

import psutil
import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_epoch_time
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  require_password=True,
  extra_args=["--hours", os.environ.get("PERFORMANCE_HOURS", "2")],
)

TEST_NAME = "NEX-T28185"

### How often to sample throughput/resource/latency metrics (seconds).
CYCLE_INTERVAL_SECONDS = 60

### Cycles to skip before a sample counts towards analysis, so container
### start-up/model warm-up isn't mistaken for a degradation signal.
WARMUP_CYCLES = 4

### Minimum number of post-warmup samples required before the early/late
### split comparisons below are statistically meaningful.
MIN_SAMPLES_FOR_ANALYSIS = 40

### Number of REST round-trips sampled per cycle to build a latency
### distribution for percentile-based (p50/p99/p99.9) response-time checks.
QUERY_SAMPLES_PER_CYCLE = 5

### Liveness: is the pipeline still producing data at all?
MIN_THROUGHPUT_MSGS_PER_SEC = 1.0

### Variability: are baseline swings getting wider the longer we run?
VARIABILITY_MAX_GROWTH_PCT = 50
VARIABILITY_STDEV_FLOOR = {
  "throughput": 1.0,  # msgs/sec
  "cpu": 1.0,         # percentage points
  "mem": 0.5,         # percentage points
}

### Saturation: is the system approaching a crash-inducing resource limit?
CPU_SATURATION_PCT = 90
MEM_SATURATION_PCT = 90
MAX_CONSECUTIVE_SATURATION_CYCLES = 3

### Memory trend: would a slow leak saturate the system eventually?
MEM_PROJECTION_HOURS = 24
### Ignore trends too small to distinguish from drift.
MEM_TREND_MIN_RISE_PCT = 1.0

### REST response-time guarantees (tail latency, not just the mean)
REST_P50_MAX_SECONDS = 0.15
REST_P99_MAX_SECONDS = 0.40
REST_P999_MAX_SECONDS = 0.60
### A p99.9 estimate needs at least this many samples to describe anything
### other than the largest value observed; below it the check is skipped.
MIN_SAMPLES_FOR_P999 = 1000
### Tail latency shouldn't blow up over the run either: compare p99 in the
### early half of the run against the late half.
REST_P99_MAX_GROWTH_PCT = 100

### MQTT pipeline latency: publisher timestamp to subscriber receive time.
MQTT_P50_MAX_SECONDS = 4.5
MQTT_P99_MAX_SECONDS = 7.5
MQTT_P999_MAX_SECONDS = 8.0
MQTT_P99_MAX_GROWTH_PCT = 100
### Cap on latency samples kept per cycle.
MQTT_LATENCY_SAMPLES_PER_CYCLE = 200

objects_detected = 0
connected = False
cycle_mqtt_latencies = []


def on_connect(mqttc, userdata, flags, rc):
  """Subscribe to all scenescape topics once the MQTT connection is up."""
  global connected
  connected = True
  log.info("Connected to MQTT Broker")
  mqttc.subscribe("scenescape/#", 0)
  return None


def on_disconnect(mqttc, userdata, rc):
  """Record that the broker connection dropped."""
  global connected
  connected = False
  log.error(f"Disconnected from MQTT Broker (rc={rc})")
  return None


def on_message(mqttc, userdata, msg):
  """Count every message and sample how long it took to arrive.

  Latency is the gap between the timestamp the publisher stamped on the
  message and the time it reached this subscriber. Messages without a
  usable timestamp (control/command topics also matched by the wildcard
  subscription) only count towards throughput.
  """
  global objects_detected
  objects_detected += 1

  if len(cycle_mqtt_latencies) >= MQTT_LATENCY_SAMPLES_PER_CYCLE:
    return None
  try:
    published = json.loads(msg.payload)["timestamp"]
    ### get_epoch_time() falls back to the current time when handed an
    ### empty value, which would record a bogus zero latency, so only
    ### genuine timestamp strings are sampled.
    if isinstance(published, str) and published:
      cycle_mqtt_latencies.append(time.time() - get_epoch_time(published))
  except (ValueError, TypeError, KeyError, UnicodeDecodeError):
    pass
  return None


def collect_mqtt_msgs(client):
  """Run the MQTT loop for one sampling window."""
  client.loopStart()
  time.sleep(CYCLE_INTERVAL_SECONDS)
  client.loopStop()
  return None


def measure_query_time(rest_client):
  """Time a single lightweight REST round-trip used as a responsiveness signal."""
  start = time.time()
  rest_client.getScenes(None)
  return time.time() - start


def sample_query_latencies(rest_client, count):
  """Collect 'count' REST round-trip latencies for percentile analysis."""
  return [measure_query_time(rest_client) for _ in range(count)]


def sample_resources(env, cpu_count, total_memory):
  """Sample CPU and Memory usage of this deployment's containers only.

  Measuring the containers rather than the host isolates Scenescape's own
  usage from the test process itself and other host-level overhead.

  Returns:
    (cpu_pct, mem_pct) where cpu_pct is the share of the host's total CPU
    capacity used by the deployment and mem_pct is its share of total
    system memory.
  """
  containers = env.docker.compose.ps()
  assert containers, "No running containers found for the deployment"
  stats = env.docker.stats(containers=[c.id for c in containers])
  assert stats, "Could not read container resource statistics"
  cpu_pct = sum(s.cpu_percentage for s in stats) / cpu_count
  mem_pct = sum(s.memory_used for s in stats) / total_memory * 100
  return cpu_pct, mem_pct


def stdev(values):
  """Sample standard deviation; 0.0 if fewer than 2 points are available."""
  if len(values) < 2:
    return 0.0
  return statistics.stdev(values)


def percentile(values, pct):
  """Linear-interpolated percentile (0-100) of 'values'; 0.0 if empty."""
  if not values:
    return 0.0
  data = sorted(values)
  k = (len(data) - 1) * (pct / 100)
  lower = math.floor(k)
  upper = math.ceil(k)
  if lower == upper:
    return data[int(k)]
  return data[lower] + (data[upper] - data[lower]) * (k - lower)


def split_halves(values):
  """Split 'values' into (early_half, late_half) of equal length.

  The extra middle element on an odd-length input is dropped from both
  halves so the comparison stays symmetric.
  """
  mid = len(values) // 2
  return values[:mid], values[-mid:]


def linear_slope(xs, ys):
  """Least-squares slope of 'ys' against 'xs'; 0.0 if it is undefined."""
  if len(xs) < 2:
    return 0.0
  mean_x = sum(xs) / len(xs)
  mean_y = sum(ys) / len(ys)
  variance = sum((x - mean_x) ** 2 for x in xs)
  if not variance:
    return 0.0
  covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
  return covariance / variance


def check_liveness(rows):
  """Fail if the pipeline stopped producing messages at any point.

  A stalled pipeline produces a flat line, which every variance-based check
  would report as "stable", so this is checked as an absolute floor.

  Returns:
    True if every sampled cycle stayed above the throughput floor.
  """
  stalled = [row for row in rows if row[1] < MIN_THROUGHPUT_MSGS_PER_SEC]
  log.info(
    f"Throughput liveness: {len(stalled)} of {len(rows)} cycles below "
    f"{MIN_THROUGHPUT_MSGS_PER_SEC} msgs/sec"
  )
  if stalled:
    log.error(
      f"Pipeline stalled: throughput fell below "
      f"{MIN_THROUGHPUT_MSGS_PER_SEC} msgs/sec at "
      f"{[round(row[0]) for row in stalled]} seconds into the run!"
    )
    return False
  return True


def check_memory_trend(rows):
  """Fail if the memory trend projects past the saturation ceiling.

  A steady leak is invisible to the variability check (a linear ramp has
  equal variance in both halves) and to the saturation check (it may not
  reach the ceiling within the test window), so the fitted trend is
  extrapolated MEM_PROJECTION_HOURS ahead instead.

  Returns:
    True if memory is flat, falling, or projected to stay below the ceiling.
  """
  if len(rows) < MIN_SAMPLES_FOR_ANALYSIS:
    log.error(
      f"Only collected {len(rows)} samples; need at least "
      f"{MIN_SAMPLES_FOR_ANALYSIS} to assess the memory trend."
    )
    return False

  elapsed = [row[0] for row in rows]
  memory = [row[3] for row in rows]
  slope = linear_slope(elapsed, memory)
  run_rise = slope * (elapsed[-1] - elapsed[0])
  projected = memory[-1] + (slope * MEM_PROJECTION_HOURS * 3600)
  log.info(
    f"Memory trend: {slope * 3600:+.3f} %/hour (rise of {run_rise:+.2f} "
    f"points across the run), projecting {projected:.1f}% after "
    f"{MEM_PROJECTION_HOURS} hours (ceiling {MEM_SATURATION_PCT}%)"
  )
  if run_rise >= MEM_TREND_MIN_RISE_PCT and projected > MEM_SATURATION_PCT:
    log.error(
      f"Memory usage is trending upwards and would reach "
      f"{projected:.1f}% within {MEM_PROJECTION_HOURS} hours, past the "
      f"{MEM_SATURATION_PCT}% saturation ceiling. This looks like a leak."
    )
    return False
  return True


def check_variability(rows):
  """Fail if any metric's swing (stdev) grows too much from early to late run.

  Returns:
    True if no metric's variability grew beyond its threshold, otherwise False.
  """
  if len(rows) < MIN_SAMPLES_FOR_ANALYSIS:
    log.error(
      f"Only collected {len(rows)} samples; need at least "
      f"{MIN_SAMPLES_FOR_ANALYSIS} to assess variability."
    )
    return False

  passed = True
  for label, col, floor_key in (
    ("MQTT throughput (msgs/sec)", 1, "throughput"),
    ("Host CPU usage (%)", 2, "cpu"),
    ("Host Memory usage (%)", 3, "mem"),
  ):
    values = [row[col] for row in rows]
    early_half, late_half = split_halves(values)
    early_stdev = stdev(early_half)
    late_stdev = stdev(late_half)
    floor = VARIABILITY_STDEV_FLOOR[floor_key]
    baseline = max(early_stdev, floor)
    growth_pct = ((late_stdev - baseline) / baseline) * 100
    degraded = late_stdev > floor and growth_pct > VARIABILITY_MAX_GROWTH_PCT
    log.info(
      f"{label} variability: early stdev {early_stdev:.3f}, late stdev "
      f"{late_stdev:.3f}, change {growth_pct:+.1f}% "
      f"(limit +{VARIABILITY_MAX_GROWTH_PCT}%)"
    )
    if degraded:
      log.error(
        f"Variability grew beyond threshold for {label}! The system may be "
        f"becoming less stable the longer it runs."
      )
      passed = False
  return passed


def check_saturation(cpu, mem, saturation_counters):
  """Track consecutive cycles at/above the resource saturation ceiling.

  Updates 'saturation_counters' (e.g. {"cpu": 0, "mem": 0}) in place.

  Returns:
    True once either resource has been at/above its ceiling for
    MAX_CONSECUTIVE_SATURATION_CYCLES consecutive cycles, signaling the run
    should be aborted before an actual crash/OOM occurs.
  """
  saturated = False
  for label, value, ceiling, key in (
    ("CPU", cpu, CPU_SATURATION_PCT, "cpu"),
    ("Memory", mem, MEM_SATURATION_PCT, "mem"),
  ):
    if value >= ceiling:
      saturation_counters[key] += 1
      log.warning(
        f"{label} usage {value:.1f}% at/above saturation ceiling {ceiling}% "
        f"— consecutive cycle {saturation_counters[key]}/"
        f"{MAX_CONSECUTIVE_SATURATION_CYCLES}"
      )
    else:
      saturation_counters[key] = 0
    if saturation_counters[key] >= MAX_CONSECUTIVE_SATURATION_CYCLES:
      log.error(
        f"{label} usage sustained at/above {ceiling}% for "
        f"{MAX_CONSECUTIVE_SATURATION_CYCLES} consecutive cycles — system "
        f"is at risk of saturation/crash!"
      )
      saturated = True
  return saturated


def check_latency_slas(label, latencies, p50_max, p99_max, p999_max, growth_max):
  """Check a latency distribution against absolute SLAs and tail growth.

  Used for both REST round-trip times and MQTT message delivery latency.

  Returns:
    True if p50/p99/p99.9 stay within their SLA ceilings and p99 doesn't
    grow beyond threshold between the early and late halves of the run,
    otherwise False.
  """
  if len(latencies) < MIN_SAMPLES_FOR_ANALYSIS:
    log.error(
      f"Only collected {len(latencies)} {label} samples; need at least "
      f"{MIN_SAMPLES_FOR_ANALYSIS} to assess latency SLAs."
    )
    return False

  passed = True
  p50 = percentile(latencies, 50)
  p99 = percentile(latencies, 99)
  log.info(f"{label} latency: p50 {p50:.3f}s, p99 {p99:.3f}s")

  slas = [
    ("p50", p50, p50_max),
    ("p99", p99, p99_max),
  ]
  ### Below MIN_SAMPLES_FOR_P999 a "p99.9" is just the largest observed
  ### value, so it is reported but not enforced.
  p999 = percentile(latencies, 99.9)
  if len(latencies) >= MIN_SAMPLES_FOR_P999:
    slas.append(("p99.9", p999, p999_max))
    log.info(f"{label} latency: p99.9 {p999:.3f}s")
  else:
    log.info(
      f"{label} latency: p99.9 {p999:.3f}s (not enforced, needs "
      f"{MIN_SAMPLES_FOR_P999} samples, have {len(latencies)})"
    )

  for name, value, limit in slas:
    if value > limit:
      log.error(f"{label} latency {name} ({value:.3f}s) exceeds SLA of {limit:.3f}s!")
      passed = False

  early, late = split_halves(latencies)
  early_p99 = percentile(early, 99)
  late_p99 = percentile(late, 99)
  growth_pct = ((late_p99 - early_p99) / early_p99) * 100 if early_p99 else 0.0
  log.info(
    f"{label} p99 tail latency trend: early {early_p99:.3f}s, late "
    f"{late_p99:.3f}s, change {growth_pct:+.1f}% "
    f"(limit +{growth_max}%)"
  )
  if early_p99 and growth_pct > growth_max:
    log.error(f"{label} p99 tail latency grew beyond threshold over the run!")
    passed = False

  return passed


@pytest.mark.test_name(TEST_NAME)
def test_sscape_performance_degradation(params, scenescape_env, result_recorder):
  """Run the full stack and fail on stalls, instability, saturation, a
  memory leak, or REST latency SLA violations over the run.

  Every CYCLE_INTERVAL_SECONDS: samples MQTT throughput and the deployment's
  CPU/Memory usage (checked live for saturation), records how long arriving
  MQTT messages took to reach this subscriber, and fires
  QUERY_SAMPLES_PER_CYCLE REST round-trips (used to build a latency
  distribution). Once the configured duration has elapsed, checks pipeline
  liveness, whether throughput/CPU/Memory variability grew between the early
  and late halves of the run, whether the memory trend projects past the
  saturation ceiling, and whether REST and MQTT latency percentiles stayed
  within SLA.
  """
  global connected
  global objects_detected
  log.info(f"Executing: {TEST_NAME}")

  hours = float(params["hours"])
  assert 0 < hours < (24 * 7), "Need a valid test run time"
  duration_secs = hours * 60 * 60

  ### Static host capacity, used to express container usage as a share of
  ### the machine. These do not change during the run.
  cpu_count = psutil.cpu_count()
  total_memory = psutil.virtual_memory().total

  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                   port=int(params["broker_port"]))
  client.onConnect = on_connect
  client.onDisconnect = on_disconnect
  client.onMessage = on_message
  client.connect()

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  collect_mqtt_msgs(client)
  assert connected, "Failed to connect to MQTT broker"

  start_time = datetime.now()
  end_time = start_time + timedelta(seconds=duration_secs)
  log.info(
    f"Test starting at {start_time.strftime('%c')}, running for {hours} "
    f"hours, ending at {end_time.strftime('%c')}"
  )

  rows = []
  query_latencies = []
  mqtt_latencies = []
  saturation_counters = {"cpu": 0, "mem": 0}
  cycle = 0
  passed = False
  while datetime.now() < end_time:
    objects_detected = 0
    cycle_mqtt_latencies.clear()
    collect_mqtt_msgs(client)
    assert connected, "Lost connection to MQTT broker"

    throughput = objects_detected / CYCLE_INTERVAL_SECONDS
    cpu, mem = sample_resources(scenescape_env, cpu_count, total_memory)
    elapsed = (datetime.now() - start_time).total_seconds()

    log.info(
      f"[{elapsed:.0f}s] throughput {throughput:.2f} msgs/sec, cpu {cpu:.1f}%, "
      f"mem {mem:.1f}%"
    )

    if check_saturation(cpu, mem, saturation_counters):
      log.error("Aborting run: system reached its saturation ceiling.")
      break

    if cycle >= WARMUP_CYCLES:
      rows.append([elapsed, throughput, cpu, mem])
      mqtt_latencies.extend(cycle_mqtt_latencies)
      query_latencies.extend(sample_query_latencies(rest_client, QUERY_SAMPLES_PER_CYCLE))

    cycle += 1
  else:
    log.info(f"Test run of {hours} hours completed, checking for performance degradation...")
    ### Every check runs so the log reports all findings, not just the first.
    results = [
      check_liveness(rows),
      check_variability(rows),
      check_memory_trend(rows),
      check_latency_slas(
        "REST", query_latencies, REST_P50_MAX_SECONDS, REST_P99_MAX_SECONDS,
        REST_P999_MAX_SECONDS, REST_P99_MAX_GROWTH_PCT
      ),
      check_latency_slas(
        "MQTT", mqtt_latencies, MQTT_P50_MAX_SECONDS, MQTT_P99_MAX_SECONDS,
        MQTT_P999_MAX_SECONDS, MQTT_P99_MAX_GROWTH_PCT
      ),
    ]
    passed = all(results)

  client.disconnect()
  assert passed, "Performance degradation detected"
  result_recorder.success()
