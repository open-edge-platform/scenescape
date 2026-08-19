#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Long-running performance degradation system test.

Runs the full Scenescape stack for a configurable duration and checks for a
sustained drop in performance: MQTT message throughput, host CPU/Memory usage,
and REST API response latency are sampled every cycle.
Once the run completes, the average of the first few
cycles (baseline) is compared against the average of the last few cycles
(trailing); a regression beyond the configured threshold for any metric
fails the test.

"""

import os
import time
from datetime import datetime, timedelta

import pytest

try:
  import psutil
except ImportError:
  import subprocess
  import sys
  subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
  # Make sure that if Python doesn't have the import directory in the search path, refresh it
  import site
  from importlib import reload
  reload(site)
  import psutil

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
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

### Cycles to skip before a sample counts towards the baseline/trailing
### windows, so container start-up/model warm-up isn't mistaken for a drop.
WARMUP_CYCLES = 4

### Number of cycles averaged for the baseline (start) and trailing (end)
### windows used to detect degradation.
TEST_AVG_WINDOW = 5

### Degradation thresholds comparing the trailing average to the baseline average.
METRICS = (
  # (label, row index, max allowed % change, higher value is worse)
  ("MQTT throughput (msgs/sec)", 1, 20, False),
  ("Host CPU usage (%)", 2, 20, True),
  ("Host Memory usage (%)", 3, 10, True),
  ("REST query time (s)", 4, 200, True),
)

objects_detected = 0
connected = False


def on_connect(mqttc, userdata, flags, rc):
  """Subscribe to all scenescape topics once the MQTT connection is up."""
  global connected
  connected = True
  log.info("Connected to MQTT Broker")
  mqttc.subscribe("scenescape/#", 0)
  return None


def on_message(mqttc, userdata, msg):
  """Count every message received; used to derive throughput per cycle."""
  global objects_detected
  objects_detected += 1
  return None


def collect_mqtt_msgs(client):
  """Run the MQTT loop for one sampling window."""
  client.loopStart()
  time.sleep(CYCLE_INTERVAL_SECONDS)
  client.loopStop()
  return None


def measure_query_time(rest_client):
  """Time a lightweight REST round-trip used as a responsiveness signal."""
  start = time.time()
  rest_client.getScenes(None)
  return time.time() - start


def average(rows, col, count):
  """Average `count` values from the front and back of `rows` at `col`."""
  first = [row[col] for row in rows[:count]]
  last = [row[col] for row in rows[-count:]]
  return sum(first) / len(first), sum(last) / len(last)


def check_degradation(rows):
  """Compare baseline vs trailing averages for every tracked metric.

  Returns:
    True if no metric exceeded its degradation threshold, otherwise False.
  """
  if len(rows) < (TEST_AVG_WINDOW * 2):
    log.error(
      f"Only collected {len(rows)} samples; need at least "
      f"{TEST_AVG_WINDOW * 2} to evaluate performance degradation."
    )
    return False

  passed = True
  for label, col, max_pct, higher_is_worse in METRICS:
    baseline, trailing = average(rows, col, TEST_AVG_WINDOW)
    change_pct = ((trailing - baseline) / baseline) * 100 if baseline else 0.0
    degraded = change_pct > max_pct if higher_is_worse else change_pct < -max_pct
    limit = f"limit +{max_pct}%" if higher_is_worse else f"limit -{max_pct}%"
    log.info(
      f"{label}: baseline {baseline:.3f} trailing {trailing:.3f} "
      f"change {change_pct:+.1f}% ({limit})"
    )
    if degraded:
      log.error(f"Performance degradation detected for {label}!")
      passed = False
  return passed


@pytest.mark.test_name(TEST_NAME)
def test_sscape_performance_degradation(params, scenescape_env, result_recorder):
  """Run the full stack and fail if performance degrades over the run.

  Samples MQTT throughput, host CPU/Memory usage, and REST query latency
  every CYCLE_INTERVAL_SECONDS. Once the configured duration has elapsed,
  the average of the first TEST_AVG_WINDOW cycles (baseline) is compared
  against the average of the last TEST_AVG_WINDOW cycles (trailing); a
  regression beyond the configured threshold for any metric fails the test.
  """
  global connected
  global objects_detected
  log.info(f"Executing: {TEST_NAME}")

  hours = float(params["hours"])
  assert 0 < hours < (24 * 7), "Need a valid test run time"
  duration_secs = hours * 60 * 60

  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                   port=int(params["broker_port"]))
  client.onConnect = on_connect
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
  cycle = 0
  passed = False
  while datetime.now() < end_time:
    objects_detected = 0
    collect_mqtt_msgs(client)
    assert connected, "Lost connection to MQTT broker"

    throughput = objects_detected / CYCLE_INTERVAL_SECONDS
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    query_time = measure_query_time(rest_client)
    elapsed = (datetime.now() - start_time).seconds

    log.info(
      f"[{elapsed}s] throughput {throughput:.2f} msgs/sec, cpu {cpu:.1f}%, "
      f"mem {mem:.1f}%, query_time {query_time:.3f}s"
    )

    if cycle >= WARMUP_CYCLES:
      rows.append([elapsed, throughput, cpu, mem, query_time])

    cycle += 1
  else:
    log.info(f"Test run of {hours} hours completed, checking for performance degradation...")
    passed = check_degradation(rows)

  client.disconnect()
  assert passed, "Performance degradation detected"
  result_recorder.success()
