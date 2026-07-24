# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import time

import psutil

from scene_common.mqtt import PubSub
from tests.functional.backend_functional import BackendFunctionalTest
from tests.utils.log import get_logger
from tests.utils.profiles import REID
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=REID,
)

TEST_NAME = "NEX-T10541"

# Test duration variants
SMOKE_DURATION_S = 20 * 60        # 20 minutes
FULL_DURATION_S = 2 * 60 * 60     # 2 hours
SAMPLE_INTERVAL_S = 60            # interval to poll MQTT

# Services whose memory is tracked via their cgroup memory.current counter.
RETAINED_SERVICES = ("scene", "vdms")
INGEST_SERVICES = ("retail-video", "queuing-video")
MEMORY_SERVICES = RETAINED_SERVICES + INGEST_SERVICES

# Leak detection
LEAK_TOLERANCE_RATIO = 0.10     # 10% of baseline per hour
LEAK_ABS_FLOOR_MB_H = 10.0      # ignore growth below this absolute rate (MB/h)
LEAK_DECEL_FRACTION = 0.5       # 2nd-half slope < this*1st-half => warm-up, not leak

# Stabilization gate
STABILIZE_TOLERANCE = 0.05      # 5% of the service's own memory per hour
STABILIZE_ABS_FLOOR_MB_H = 15.0 # always allow at least this absolute slope (MB/h)
STABILIZE_POLL_S = 15           # seconds between stabilization probes
STABILIZE_WINDOW = 6            # number of probes used for the slope
STABILIZE_MIN_WAIT_S = 5 * 60   # wait for at least one full video loop (~179s) + pipeline lag
STABILIZE_MAX_WAIT_S = 10 * 60

# Stopping ingestion
FREE_SETTLE_S = 90                # seconds to observe after stopping ingestion
FREE_POLL_S = 15                  # seconds between post-stop probes
FREE_LEAK_SLOPE_MB_H = 10.0       # post-stop growth above this (MB/h) => leak

# Crash-safety ceiling
CEILING_RATIO = 0.90

QUERY_LATENCY_MAX_RATIO = 3.0

# Poll MQTT for 3 intervals
MAX_MISSED_UPDATES = 3


def resolve_duration():
  """Return (duration_seconds, mode) based on the REID_PERF_MODE env var."""
  mode = os.environ.get("REID_PERF_MODE", "smoke").strip().lower()
  if mode == "full":
    return FULL_DURATION_S, "full"
  return SMOKE_DURATION_S, "smoke"


class REIDPerformanceDegradation(BackendFunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute,
               docker=None, project_name=None,
               duration=SMOKE_DURATION_S, mode="smoke"):
    super().__init__(testName, request, recordXMLAttribute)
    self.vdms_connect()

    self.docker = docker
    self.project_name = project_name
    self.duration = duration
    self.mode = mode
    self.baseline = {}

    self.connected = False
    self.scenes_updates = {
      "3bc091c7-e449-46a0-9540-29c499bca18c": {
        "updated": False
      },
      "302cf49a-97ec-402d-a324-c5077b280b7b": {
        "updated": False
      }
    }
    self.performance_db = []

    self.client = PubSub(self.params["auth"], None, self.params["rootcert"], self.params["broker_url"],
                          port=int(self.params["broker_port"]))
    self.client.onConnect = self.on_connect
    for sc_uid in self.scenes_updates:
      self.client.addCallback(PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person"), self.on_scene_message)
    self.client.connect()
    self.client.loopStart()

  def on_connect(self, mqttc, data, flags, rc):
    """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
    @param    mqttc     The mqtt client object.
    @param    obj       The private user data.
    @param    flags     The response sent by the broker.
    @param    rc        The connection result.
    """
    self.connected = True
    log.info("Connected to MQTT Broker")
    for sc_uid in self.scenes_updates:
      topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person")
      mqttc.subscribe(topic, 0)
      log.info("Subscribed to the topic {}".format(topic))
    return

  def read_container_memory(self, service):
    """! Read a service's current memory usage and limit from its cgroup.
    @param    service   Compose service name.
    @return   (current_bytes, limit_bytes); either value may be None.
    """
    cmd = (
      "cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max 2>/dev/null "
      "|| cat /sys/fs/cgroup/memory/memory.usage_in_bytes "
      "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    )
    try:
      out = self.docker.compose.execute(service, ["sh", "-c", cmd], tty=False)
    except Exception as exc:
      log.warning(f"Could not read cgroup memory for {service}: {exc}")
      return None, None
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    current = int(lines[0]) if lines and lines[0].isdigit() else None
    limit = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else None
    return current, limit

  def sample_container_memory(self, services):
    """! Sample memory (in MB) for the given services and enforce the
    crash-safety ceiling.
    @param    services   Iterable of compose service names.
    @return   dict of service -> memory in MB (unreadable services omitted).
    """
    usage = {}
    for service in services:
      current, limit = self.read_container_memory(service)
      if current is None:
        continue
      usage[service] = current / (1024 * 1024)
      if limit and limit > 0 and current / limit >= CEILING_RATIO:
        raise MemoryError(
          f"{service} is at {current / limit:.0%} of its cgroup memory limit "
          f"({current} / {limit} bytes) - aborting to avoid an OOM crash."
        )
    return usage

  def get_host_cpu(self):
    return psutil.cpu_percent(interval=1)

  def get_vdms_time(self):
    start_time = time.time()
    self.get_similarity_comparison(20)
    end_time = time.time()
    return end_time - start_time

  @staticmethod
  def _linear_slope(xs, ys):
    """! Least-squares slope of ys over xs (units: y per x).
    @param    xs    List of x values.
    @param    ys    List of y values.

    @return   Slope of ys over xs.
    """
    n = len(xs)
    if n < 2:
      return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
      return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom

  def store_performance_results(self, test_time):
    cpu_usage = self.get_host_cpu()
    memory = self.sample_container_memory(MEMORY_SERVICES)
    vdms_time = self.get_vdms_time()
    self.performance_db.append({
      "t": test_time,
      "cpu": cpu_usage,
      "query": vdms_time,
      "mem": memory,
    })
    mem_str = ", ".join(f"{svc}={mb:.1f}MB" for svc, mb in memory.items())
    log.info(f"t={test_time}s cpu={cpu_usage}% query={vdms_time:.4f}s {mem_str}")
    return

  def wait_for_stabilization(self):
    log.info("Waiting for memory to stabilize before capturing the baseline...")
    readings = {svc: [] for svc in RETAINED_SERVICES}
    start = time.time()
    while time.time() - start < STABILIZE_MAX_WAIT_S:
      usage = self.sample_container_memory(RETAINED_SERVICES)
      elapsed = time.time() - start
      for svc, mb in usage.items():
        readings[svc].append((elapsed, mb))
        readings[svc] = readings[svc][-STABILIZE_WINDOW:]
      ready = elapsed >= STABILIZE_MIN_WAIT_S and all(
        len(readings[svc]) >= STABILIZE_WINDOW for svc in RETAINED_SERVICES
      )
      if ready:
        stable = True
        details = []
        for svc in RETAINED_SERVICES:
          xs = [r[0] for r in readings[svc]]
          ys = [r[1] for r in readings[svc]]
          slope_per_hour = self._linear_slope(xs, ys) * 3600
          base = sum(ys) / len(ys)
          allowed = max(base * STABILIZE_TOLERANCE, STABILIZE_ABS_FLOOR_MB_H)
          details.append(f"{svc}={ys[-1]:.1f}MB({slope_per_hour:+.1f}MB/h)")
          if abs(slope_per_hour) >= allowed:
            stable = False
        log.info("  stabilization: " + ", ".join(details))
        if stable:
          log.info("Memory has stabilized.")
          break
      time.sleep(STABILIZE_POLL_S)
    else:
      log.warning(
        f"Memory did not fully stabilize within {STABILIZE_MAX_WAIT_S}s; "
        "capturing baseline anyway."
      )
    self.baseline = self.sample_container_memory(MEMORY_SERVICES)
    log.info(
      "Baseline: "
      + ", ".join(f"{s}={mb:.1f}MB" for s, mb in self.baseline.items())
    )
    return

  def on_scene_message(self, mqttc, condlock, msg):
    real_msg = str(msg.payload.decode("utf-8"))
    json_data = json.loads(real_msg)

    # Verify that everything is still working as expected
    for scene in self.scenes_updates:
      if json_data['id'] == scene:
        self.scenes_updates[scene]["updated"] = True
    return

  def _series(self, service):
    xs, ys = [], []
    for sample in self.performance_db:
      if service in sample["mem"]:
        xs.append(sample["t"])
        ys.append(sample["mem"][service])
    return xs, ys

  def analyze_memory_trend(self):
    """! Check retained services.
    @return   True when no leak-like growth is detected.
    """
    ok = True
    for service in RETAINED_SERVICES:
      xs, ys = self._series(service)
      base = self.baseline.get(service)
      if len(ys) < 2 or not base:
        log.warning(f"Not enough samples to analyze the {service} trend.")
        continue
      slope_per_hour = self._linear_slope(xs, ys) * 3600
      growth_ratio = slope_per_hour / base if base else 0.0

      decelerating = False
      if len(ys) >= 4:
        mid = len(ys) // 2
        slope_first = self._linear_slope(xs[:mid], ys[:mid]) * 3600
        slope_second = self._linear_slope(xs[mid:], ys[mid:]) * 3600
        decelerating = slope_second < slope_first * LEAK_DECEL_FRACTION

      log.info(
        f"-> {service} memory: baseline={base:.1f}MB "
        f"start={ys[0]:.1f}MB end={ys[-1]:.1f}MB "
        f"trend={slope_per_hour:.2f}MB/h ({growth_ratio:.1%}/h)"
        + (" [decelerating/warm-up]" if decelerating else "")
      )

      if (growth_ratio > LEAK_TOLERANCE_RATIO
          and slope_per_hour > LEAK_ABS_FLOOR_MB_H
          and not decelerating):
        log.error(
          f"{service} memory is growing {growth_ratio:.1%} per hour "
          f"(> {LEAK_TOLERANCE_RATIO:.0%}) and is not decelerating; "
          "this looks like a memory leak!"
        )
        ok = False
    return ok

  def analyze_query_latency(self):
    """! Check that VDMS query latency did not explode over the run."""
    ys = [sample["query"] for sample in self.performance_db]
    if len(ys) < 2:
      return True
    avg_first = sum(ys[:5]) / len(ys[:5])
    avg_last = sum(ys[-5:]) / len(ys[-5:])
    log.info(f"-> Query latency: start={avg_first:.4f}s end={avg_last:.4f}s")
    if avg_first > 0 and avg_last >= avg_first * QUERY_LATENCY_MAX_RATIO:
      log.error(
        f"Query latency degraded {avg_last / avg_first:.1f}x "
        f"(> {QUERY_LATENCY_MAX_RATIO:.0f}x)!"
      )
      return False
    return True

  def check_memory_freed(self):
    """! Stop video ingestion and verify retained services stop growing.
    @return   True when no retained service keeps growing post-stop.
    """
    log.info(f"Stopping ingestion services {list(INGEST_SERVICES)} for free-check...")
    try:
      self.docker.compose.stop(list(INGEST_SERVICES))
    except Exception as exc:
      log.error(f"Could not stop ingestion services: {exc}")
      return False

    probes = max(2, FREE_SETTLE_S // FREE_POLL_S)
    series = {svc: [] for svc in RETAINED_SERVICES}
    for i in range(probes):
      time.sleep(FREE_POLL_S)
      usage = self.sample_container_memory(RETAINED_SERVICES)
      elapsed = (i + 1) * FREE_POLL_S
      for svc, mb in usage.items():
        series[svc].append((elapsed, mb))

    ok = True
    for service in RETAINED_SERVICES:
      points = series[service]
      if len(points) < 2:
        continue
      xs = [p[0] for p in points]
      ys = [p[1] for p in points]
      slope_per_hour = self._linear_slope(xs, ys) * 3600
      base = self.baseline.get(service) or 0.0
      log.info(
        f"-> {service} after ingestion stop: {ys[-1]:.1f}MB "
        f"(baseline={base:.1f}MB, post-stop trend={slope_per_hour:+.2f}MB/h)"
      )
      if slope_per_hour > FREE_LEAK_SLOPE_MB_H:
        log.error(
          f"{service} keeps growing ({slope_per_hour:+.2f}MB/h) after ingestion "
          "stopped; memory is being retained (leak)."
        )
        ok = False
    return ok

  def check_perf_degradation(self):
    """! Verify the system does not degrade / leak while running RE-ID.
    @return  BOOL   True for the expected behaviour.
    """
    self.wait_for_stabilization()

    start_time = time.time()
    missed = 0
    log.info(
      f"Running the {self.mode} variant for {self.duration}s, "
      f"sampling every {SAMPLE_INTERVAL_S}s."
    )

    while time.time() - start_time < self.duration:
      time.sleep(SAMPLE_INTERVAL_S)
      time_interval = int(time.time() - start_time)

      updated = False
      for scene in self.scenes_updates:
        if self.scenes_updates[scene]["updated"]:
          updated = True
          self.scenes_updates[scene]["updated"] = False
      if updated:
        missed = 0
      else:
        missed += 1
        log.warning(
          f"-> No scene updates in the past {SAMPLE_INTERVAL_S}s "
          f"({missed}/{MAX_MISSED_UPDATES})."
        )
        if missed >= MAX_MISSED_UPDATES:
          log.error("Scenes stopped publishing updates; aborting the test!")
          return False
        continue

      self.store_performance_results(time_interval)

    if len(self.performance_db) < 2:
      log.error("Not enough samples were collected to assess degradation!")
      return False

    self.write_csv_report()

    log.info("Analyzing performance degradation...")
    trend_ok = self.analyze_memory_trend()
    latency_ok = self.analyze_query_latency()
    freed_ok = self.check_memory_freed()
    return trend_ok and latency_ok and freed_ok

  def write_csv_report(self):
    """! Write the full time series to a CSV artifact for offline analysis."""
    out_dir = os.environ.get("TEST_DATA", "/tmp")
    path = os.path.join(out_dir, f"reid_perf_{self.mode}.csv")
    try:
      with open(path, "w") as fh:
        header = ["t", "cpu", "query"] + list(MEMORY_SERVICES)
        fh.write(",".join(header) + "\n")
        for sample in self.performance_db:
          row = [str(sample["t"]), str(sample["cpu"]), f"{sample['query']:.6f}"]
          for svc in MEMORY_SERVICES:
            value = sample["mem"].get(svc)
            row.append(f"{value:.2f}" if value is not None else "")
          fh.write(",".join(row) + "\n")
      log.info(f"Performance time series written to {path}")
    except Exception as exc:
      log.warning(f"Could not write CSV report: {exc}")
    return

  def verifyThings(self):
    try:
      try:
        result = self.check_perf_degradation()
      except MemoryError as exc:
        log.error(str(exc))
        result = False
      assert result
      self.exitCode = 0
    finally:
      self.client.loopStop()
      self.recordTestResult()
    return

def test_reid_performance_degradation(scenescape_env, request, record_xml_attribute):
  """! Test that the system hasn't suffered a significant performance degradation.

  Runs the short "smoke" variant by default; set REID_PERF_MODE=full for the
  nightly 2-hour run.  Tracks per-container memory (cgroup memory.current),
  captures a baseline only after memory stabilizes, flags sustained memory
  growth as a leak, and verifies that retained services free memory once
  video ingestion is stopped.

  @param    scenescape_env           Compose environment (Docker client).
  @param    request                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  duration, mode = resolve_duration()
  log.info(f"Starting RE-ID performance degradation test ({mode} variant).")

  test = REIDPerformanceDegradation(
    TEST_NAME, request, record_xml_attribute,
    docker=scenescape_env.docker,
    project_name=scenescape_env.project_name,
    duration=duration,
    mode=mode,
  )
  test.verifyThings()
  assert test.exitCode == 0
