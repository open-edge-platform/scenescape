# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""BlackBoxHarness — black-box tracker harness that communicates via MQTT.

Architecture
------------
Four containers run on a private Docker network:

  ┌──────────────────────────────────────────────────────────┐
  │  Docker network  "black_box_harness_<run_id>"            │
  │                                                          │
  │  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
  │  │   broker     │  │   manager   │  │   tracker /   │  │
  │  │  (mosquitto) │  │  (mock REST)│  │   controller  │  │
  │  └──────┬───────┘  └─────────────┘  └───────────────┘  │
  │         │ port 1883 exposed to host                     │
  └─────────┼──────────────────────────────────────────────-┘
            │
  ┌─────────┴──────────────────────────┐
  │  BlackBoxHarness process (host)     │
  │  • publishes  DATA_CAMERA frames   │
  │  • subscribes DATA_SCENE output    │
  └────────────────────────────────────┘

Supported container types
-------------------------
* **Controller** (``scenescape-controller``, entrypoint ``controller-cmd``):
  - Scene config loaded via ``--resturl http://<manager>/api/v1`` exactly as in
    production; the mock manager container serves ``GET /api/v1/scenes`` with
    the dataset camera calibration data (``camera points`` / ``map points``).
  - Time-chunking is controlled by ``time_chunking_enabled`` in tracker-config.json.

* **Tracker service** (``scenescape-tracker``, binary ``/scenescape/tracker``):
  - Scene config loaded via ``scenes.source: api`` pointing at the same mock
    manager container, matching the production deployment path.
  - ``max_lag_s`` is set to 1e15 so historical dataset timestamps are accepted
    without rewriting.
  - Time-chunking is always active via ``tracking.time_chunking_rate_fps``.

Timestamp synchronisation
-------------------------
Consecutive input frames are published with a wall-clock delay equal to the
delta between their ISO 8601 timestamps.  This reproduces the original capture
cadence so the tracker's internal timing (object ageing, time-chunking) sees a
realistic frame rate.  ``maxlag``/``max_lag_s=1e15`` only suppresses the
tracker's lag-rejection check; it does not affect the wall-clock timer that
drives the time-chunk scheduler.

Topics (from scene_common.mqtt.PubSub templates)
-------------------------------------------------
* Publish  →  scenescape/data/camera/{camera_id}
* Subscribe←  scenescape/data/scene/{scene_id}/+      (Controller & Tracker service: full-rate per-frame)

Configuration keys (set_custom_config)
--------------------------------------
Required:
  tracker_config_path (str): path to tracker-config.json mounted into the
                             tracker container at the expected location.
  container_type  (str):   ``'controller'`` or ``'tracker'``.
  broker_image    (str):   mosquitto Docker image (e.g. "eclipse-mosquitto:2.0.22").
Optional:
  scene_id        (str):   scene uid used to build the output topic;
                           defaults to config['uid'] from set_scene_config().
  drain_timeout   (float): idle timeout — seconds with no new output messages before
                           outputs to arrive (default 5.0).
  broker_port     (int):   host port to bind the broker on (default 0 =
                           choose a free port automatically).
  enable_metrics  (bool):  run an OTEL Collector sidecar to capture the
                           tracker/controller OTLP metrics (default False).
  metrics_collector_image (str): OTEL Collector image (required when
                           ``enable_metrics`` is true,
                           e.g. "otel/opentelemetry-collector-contrib:0.155.0").
  metrics_export_interval_s (int): metrics export interval in seconds
                           (default 2).
  metrics_otlp_port (int): OTLP/gRPC port the collector listens on
                           (default 4317).
"""

import json
import os
import shutil
import socket
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import paho.mqtt.client as mqtt
from python_on_whales import docker

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from base.tracker_harness import TrackerHarness
from utils.format_converters import write_jsonl
from harnesses.black_box_harness.mock_manager import run as _run_mock_manager
from harnesses.black_box_harness import metrics_recorder

# ---------------------------------------------------------------------------
# MQTT topic constants (mirrors scene_common.mqtt.PubSub._TopicTemplates)
# ---------------------------------------------------------------------------
_TOPIC_BASE = "scenescape"
_TOPIC_DATA_CAMERA = _TOPIC_BASE + "/data/camera/{camera_id}"
_TOPIC_DATA_SCENE  = _TOPIC_BASE + "/data/scene/{scene_id}/+"

# Mosquitto config that allows anonymous connections on port 1883
_MOSQUITTO_CONF = """\
listener 1883
allow_anonymous true
"""

# Shared workspace path inside both container types
_CONTAINER_WORKSPACE       = "/workspace"

# Controller-specific container paths
_CONTAINER_TRACKER_CONFIG  = _CONTAINER_WORKSPACE + "/tracker-config.json"

# Tracker-service-specific container paths
_TRACKER_SVC_EXECUTABLE    = "/scenescape/tracker"
_TRACKER_SVC_CONFIG        = _CONTAINER_WORKSPACE + "/tracker_svc_config.json"
_TRACKER_SVC_AUTH          = _CONTAINER_WORKSPACE + "/manager_auth.json"
_TRACKER_SVC_SCHEMA        = "/scenescape/schema/config.schema.json"

# Mock Manager REST credentials (arbitrary — server accepts any)
_MOCK_MANAGER_USER         = "harness"
_MOCK_MANAGER_PASSWORD     = "harness"
_MOCK_MANAGER_PORT         = 8888  # internal Docker-network port

# Container type constants
CONTAINER_TYPE_CONTROLLER = "controller"
CONTAINER_TYPE_TRACKER    = "tracker"

DEFAULT_DRAIN_TIMEOUT  = 5.0   # seconds of silence after last received message before stopping
DEFAULT_STARTUP_WAIT   = 2.0   # seconds to wait after container start before publishing frames

# Observability (optional OTEL Collector sidecar) defaults
DEFAULT_METRICS_EXPORT_INTERVAL_S = 2    # short interval so a short run still exports
DEFAULT_METRICS_OTLP_PORT         = 4317 # OTLP/gRPC port the collector listens on
_COLLECTOR_CONFIG       = _CONTAINER_WORKSPACE + "/collector.yaml"
_COLLECTOR_OUTPUT_DIR   = "/output"
_COLLECTOR_OUTPUT_FILE  = "metrics.json"

def _build_tracker_service_config(
    broker_name: str,
    manager_name: str,
    manager_port: int,
    tracker_cfg: Dict[str, Any],
    otlp_endpoint: Optional[str] = None,
    metrics_interval_s: Optional[int] = None,
) -> Dict[str, Any]:
  """Build the full config.json for the Tracker service container.

  Scene config is loaded via the mock Manager REST API (``scenes.source: api``),
  matching the production deployment path exactly.

  Args:
      broker_name:  Hostname of the MQTT broker inside the Docker network.
      manager_name: Hostname of the mock Manager container inside the Docker
                    network.
      manager_port: Host port the mock Manager REST server is listening on.
      tracker_cfg:  Parsed contents of tracker-config.json from the dataset.

  Returns:
      Config dict ready to be JSON-serialised as config.json.
  """
  tracking_cfg = tracker_cfg.get("tracking", tracker_cfg)
  config: Dict[str, Any] = {
      "infrastructure": {
          "mqtt": {
              "host": broker_name,
              "port": 1883,
              "insecure": True,
          },
          "manager": {
              "url": f"http://{manager_name}:{manager_port}",
              "auth_path": _TRACKER_SVC_AUTH,
          },
      },
      "scenes": {
          "source": "api",
      },
      "tracking": {
          "time_chunking_rate_fps": tracking_cfg.get("time_chunking_rate_fps", 15),
          "max_unreliable_time_s":        tracking_cfg.get("max_unreliable_time_s", 1.0),
          "non_measurement_time_dynamic_s": tracking_cfg.get("non_measurement_time_dynamic_s", 0.8),
          "non_measurement_time_static_s":  tracking_cfg.get("non_measurement_time_static_s", 1.6),
          "max_lag_s": 1e15,
      },
  }
  if otlp_endpoint:
    config["infrastructure"]["otlp"] = {
        "endpoint": otlp_endpoint,
        "insecure": True,
    }
    config["observability"] = {
        "metrics": {
            "enabled": True,
            "export_interval_s": int(metrics_interval_s or DEFAULT_METRICS_EXPORT_INTERVAL_S),
        },
    }
  return config



def _free_port() -> int:
  """Return a free TCP port on localhost."""
  with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 30.0, interval: float = 0.25) -> None:
  """Block until a TCP connection to *host*:*port* succeeds or *timeout* expires.

  Args:
      host:     Hostname or IP to probe.
      port:     TCP port number.
      timeout:  Maximum seconds to wait.
      interval: Seconds between probes.

  Raises:
      RuntimeError: If the port is not reachable within *timeout* seconds.
  """
  deadline = time.monotonic() + timeout
  while True:
    try:
      with socket.create_connection((host, port), timeout=interval):
        return  # port is open
    except OSError:
      if time.monotonic() >= deadline:
        raise RuntimeError(
            f"MQTT broker on {host}:{port} not reachable after {timeout:.0f}s"
        )
      time.sleep(interval)


def _parse_ts(ts_str: str) -> float:
  """Parse ISO 8601 timestamp string to POSIX float seconds."""
  # Handle both 'Z' suffix and '+00:00'
  ts_str = ts_str.replace("Z", "+00:00")
  return datetime.fromisoformat(ts_str).timestamp()


def _sort_by_camera_order(
    frames: List[Dict[str, Any]], camera_order: List[str]
) -> List[Dict[str, Any]]:
  """Return *frames* with same-timestamp groups sorted by *camera_order*.

  Frames that share a timestamp are re-ordered so the camera that appears
  first in *camera_order* is published first.  This gives the tracker a
  deterministic input sequence regardless of OS scheduling, eliminating
  run-to-run variance caused by non-deterministic MQTT delivery order.

  Frames with IDs absent from *camera_order* are appended after the ordered
  ones.  Relative order within a group is otherwise stable.
  """
  order_idx = {cam: i for i, cam in enumerate(camera_order)}
  result: List[Dict[str, Any]] = []
  i = 0
  while i < len(frames):
    ts = frames[i].get("timestamp")
    j = i + 1
    while j < len(frames) and frames[j].get("timestamp") == ts:
      j += 1
    group = sorted(
        frames[i:j],
        key=lambda f: order_idx.get(f.get("id", ""), len(camera_order)),
    )
    result.extend(group)
    i = j
  return result


def _merge_outputs_by_timestamp(
    outputs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
  """Merge per-category MQTT messages that share the same timestamp.

  Both the Controller and the Tracker service publish one MQTT message per
  *object category* per scene update (topic suffix ``/{type}``, e.g.
  ``…/person``, ``…/FW190D``).  The harness subscribes to the wildcard
  ``…/+`` and therefore receives every per-category message separately.
  Additionally, the Controller fires one scene update *per camera input*,
  so a two-camera scene at the same timestamp produces
  ``N_cameras × N_types`` messages.

  This function groups all messages by their ISO 8601 timestamp string and
  merges them into a single dict per logical frame, deduplicating tracked
  objects by UUID.  The result is one entry per timestep containing all
  categories — matching the ground-truth frame cadence expected by the
  evaluators.

  Args:
      outputs: Raw list of dicts collected from the ``on_message`` callback.

  Returns:
      Sorted list of merged output dicts, one entry per unique timestamp.
  """
  from collections import OrderedDict

  by_ts: Dict[str, Dict[str, Any]] = OrderedDict()
  for msg in outputs:
    ts = msg.get("timestamp", "")
    if ts not in by_ts:
      by_ts[ts] = {**msg, "objects": []}
    seen_ids = {o["id"] for o in by_ts[ts]["objects"]}
    for obj in msg.get("objects", []):
      if obj.get("id") not in seen_ids:
        by_ts[ts]["objects"].append(obj)
        seen_ids.add(obj["id"])

  return sorted(by_ts.values(), key=lambda m: m.get("timestamp", ""))


class BlackBoxHarness(TrackerHarness):
  """Black-box tracker harness using MQTT as the communication channel.

  Starts a throw-away mosquitto broker and the tracker container on a private
  Docker network.  Input frames are published camera-by-camera paced by their
  original timestamps; tracker outputs arriving on the scene topic are
  collected and returned as an iterator.
  """

  def __init__(self, container_image: str):
    """Initialise BlackBoxHarness.

    Args:
        container_image: Docker image for the tracker/controller
                         (e.g. ``"scenescape-controller:2026.1.0-dev"``).
    """
    self._container_image = container_image
    self._scene_config: Optional[Dict[str, Any]] = None
    self._scene_id: Optional[str] = None
    self._tracker_config_path: Optional[str] = None
    self._container_type: Optional[str] = None  # auto-detected when None
    self._drain_timeout: float              = DEFAULT_DRAIN_TIMEOUT
    self._startup_wait_s: float             = DEFAULT_STARTUP_WAIT
    self._camera_order: Optional[List[str]] = None
    self._broker_image: str                 = ""
    self._broker_port: int                  = 0
    self._output_folder: Optional[Path]     = None
    # Observability (optional OTEL Collector sidecar)
    self._enable_metrics: bool              = False
    self._metrics_collector_image: str      = ""
    self._metrics_export_interval_s: int    = DEFAULT_METRICS_EXPORT_INTERVAL_S
    self._metrics_otlp_port: int            = DEFAULT_METRICS_OTLP_PORT
    self._collector_ctr                     = None
    self._metrics_out_dir: Optional[Path]   = None

  # ------------------------------------------------------------------
  # TrackerHarness interface
  # ------------------------------------------------------------------

  def set_scene_config(self, config: Dict[str, Any]) -> "BlackBoxHarness":
    """Set scene configuration (dataset-specific format from config.json).

    Args:
        config: Scene configuration dict.  Must contain ``"name"`` and
                ideally ``"uid"`` for the output topic.

    Returns:
        Self for method chaining.
    """
    if not isinstance(config, dict):
      raise ValueError("Scene config must be a dictionary")
    if "name" not in config:
      raise ValueError("Scene config must contain 'name'")
    self._scene_config = config
    self._scene_id = config.get("uid") or config.get("name")
    return self

  def set_custom_config(self, config: Dict[str, Any]) -> "BlackBoxHarness":
    """Set harness-specific options.

    Args:
        config: Dictionary with keys documented in the module docstring.

    Returns:
        Self for method chaining.
    """
    if not isinstance(config, dict):
      raise ValueError("Custom config must be a dictionary")
    if "tracker_config_path" not in config:
      raise ValueError("Custom config must contain 'tracker_config_path'")
    tp = config["tracker_config_path"]
    if not Path(tp).exists():
      raise ValueError(f"Tracker config file not found: {tp}")
    # Resolve to an absolute path: Docker requires absolute host paths for
    # bind mounts, otherwise it treats the value as a named volume.
    self._tracker_config_path = str(Path(tp).resolve())

    if "scene_id" in config:
      self._scene_id = config["scene_id"]
    if "container_type" not in config:
      raise ValueError("Custom config must contain 'container_type'")
    ct = config["container_type"]
    if ct not in (CONTAINER_TYPE_CONTROLLER, CONTAINER_TYPE_TRACKER):
      raise ValueError(
          f"container_type must be '{CONTAINER_TYPE_CONTROLLER}' or "
          f"'{CONTAINER_TYPE_TRACKER}', got: {ct!r}"
      )
    self._container_type = ct
    self._drain_timeout  = float(config.get("drain_timeout",  DEFAULT_DRAIN_TIMEOUT))
    self._startup_wait_s = float(config.get("startup_wait_s", DEFAULT_STARTUP_WAIT))
    if "camera_order" in config:
      self._camera_order = list(config["camera_order"])
    if "broker_image" not in config:
      raise ValueError("Custom config must contain 'broker_image'")
    self._broker_image   = str(config["broker_image"])
    self._broker_port    = int(config.get("broker_port",      0))

    self._enable_metrics = bool(config.get("enable_metrics", False))
    if self._enable_metrics:
      if "metrics_collector_image" not in config:
        raise ValueError(
            "Custom config must contain 'metrics_collector_image' when "
            "'enable_metrics' is true"
        )
      self._metrics_collector_image = str(config["metrics_collector_image"])
      self._metrics_export_interval_s = max(
          1, int(config.get("metrics_export_interval_s", DEFAULT_METRICS_EXPORT_INTERVAL_S))
      )
      self._metrics_otlp_port = int(config.get("metrics_otlp_port", DEFAULT_METRICS_OTLP_PORT))
    return self

  def set_output_folder(self, path: Path) -> "BlackBoxHarness":
    """Set folder for persisted harness artefacts (inputs / outputs JSONL).

    Args:
        path: Destination directory; created if absent.

    Returns:
        Self for method chaining.
    """
    if not isinstance(path, Path):
      path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def process_inputs(
      self, inputs: Iterator[Dict[str, Any]]
  ) -> Iterator[Dict[str, Any]]:
    """Run the tracker over *inputs* via MQTT and return collected outputs.

    Starts broker + tracker containers, publishes all input frames at the
    original capture cadence, waits ``drain_timeout`` seconds for remaining
    outputs, then tears down the containers.

    Args:
        inputs: Iterator of canonical Input Detection Format dicts.

    Returns:
        Iterator over canonical Tracker Output Format dicts.

    Raises:
        RuntimeError: If configuration is incomplete or containers fail.
    """
    if self._scene_config is None:
      raise RuntimeError("Call set_scene_config() before process_inputs()")
    if self._tracker_config_path is None:
      raise RuntimeError("Call set_custom_config() before process_inputs()")

    run_id  = uuid.uuid4().hex[:8]
    net_name = f"black_box_harness_{run_id}"
    tmp_dir  = Path(tempfile.mkdtemp(prefix="black_box_harness_"))
    print(f"[BlackBoxHarness] Temporary workspace: {tmp_dir}")

    try:
      input_frames: List[Dict[str, Any]] = list(inputs)
      self._write_inputs(input_frames, tmp_dir)

      host_port = self._broker_port if self._broker_port > 0 else _free_port()

      broker_ctr, tracker_ctr = self._start_containers(
          tmp_dir, net_name, host_port, run_id
      )
      log_file = self._output_folder / "tracker_logs.txt" if self._output_folder else tmp_dir / "tracker_logs.txt"
      log_thread = self._start_log_streaming(tracker_ctr, log_file=log_file)
      print(f"[BlackBoxHarness] Container logs → {log_file}")
      try:
        outputs = self._run_session(input_frames, host_port)
      finally:
        if self._enable_metrics:
          # The controller exports metrics only on its periodic timer (it has
          # no flush-on-shutdown), so wait for at least one more export cycle
          # to land before the container is stopped.
          time.sleep(self._metrics_export_interval_s + 0.5)
        self._stop_containers(broker_ctr, tracker_ctr)
        if self._enable_metrics:
          # The collector stays up until after the tracker has flushed so the
          # final cumulative export is captured, then is stopped last.
          time.sleep(1.0)
          self._stop_collector()
        if log_thread is not None:
          log_thread.join(timeout=5.0)
        docker.network.remove(net_name)

      self._persist_outputs(outputs, tmp_dir)
      self._persist_config()
      if self._enable_metrics:
        self._record_metrics(output_frame_count=len(outputs))
      return iter(outputs)

    finally:
      if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

  def reset(self) -> "BlackBoxHarness":
    """Reset mutable state (scene / custom config, output folder).

    Returns:
        Self for method chaining.
    """
    self._scene_config        = None
    self._scene_id            = None
    self._tracker_config_path = None
    self._container_type      = None
    self._drain_timeout       = DEFAULT_DRAIN_TIMEOUT
    self._startup_wait_s      = DEFAULT_STARTUP_WAIT
    self._camera_order        = None
    self._output_folder       = None
    self._enable_metrics      = False
    self._metrics_collector_image = ""
    self._metrics_export_interval_s = DEFAULT_METRICS_EXPORT_INTERVAL_S
    self._metrics_otlp_port   = DEFAULT_METRICS_OTLP_PORT
    self._collector_ctr       = None
    self._metrics_out_dir     = None
    return self

  # ------------------------------------------------------------------
  # Internal helpers
  # ------------------------------------------------------------------

  def _write_inputs(self, frames: List[Dict], tmp_dir: Path) -> None:
    """Persist input frames for debugging / output folder artefacts."""
    inputs_file = tmp_dir / "inputs.jsonl"
    write_jsonl(iter(frames), str(inputs_file))
    if self._output_folder:
      shutil.copy(inputs_file, self._output_folder / "inputs.jsonl")

  def _build_mosquitto_conf(self, tmp_dir: Path) -> Path:
    """Write a minimal anonymous mosquitto.conf and return its path."""
    conf = tmp_dir / "mosquitto.conf"
    conf.write_text(_MOSQUITTO_CONF)
    return conf

  def _start_mock_manager(self, net_name: str, manager_name: str) -> Tuple[threading.Thread, int]:
    """Start the mock Manager REST server in a daemon thread.

    Picks a free port per run so that sequential evaluation configs do not
    collide on the same port.  The thread is daemonised so it stops
    automatically when the harness process exits.

    Returns:
        (thread, port) — the port is passed to containers via ``add_hosts``.
    """
    port = _free_port()
    t = threading.Thread(
        target=_run_mock_manager,
        args=(port, self._scene_config),
        daemon=True,
    )
    t.start()
    print(f"[BlackBoxHarness] Mock Manager REST started on port {port}")
    return t, port

  def _start_containers(
      self,
      tmp_dir: Path,
      net_name: str,
      host_port: int,
      run_id: str,
  ):
    """Create Docker network, start broker, mock manager, and tracker containers.

    Selects the correct startup command based on the detected container type
    (Controller vs Tracker service).  Both container types load their scene
    config via the mock Manager REST API.

    Returns:
        (broker_container, tracker_container) tuple.
    """
    docker.network.create(net_name)
    print(f"[BlackBoxHarness] Created Docker network '{net_name}'")

    conf_path = self._build_mosquitto_conf(tmp_dir)
    manager_name = f"black_box_harness_manager_{run_id}"

    # --- Mock Manager REST server (host thread, reachable via host-gateway) ---
    _, manager_port = self._start_mock_manager(net_name, manager_name)

    # --- Broker ---
    broker_name = f"black_box_harness_broker_{run_id}"
    broker_ctr = docker.run(
        self._broker_image,
        name=broker_name,
        networks=[net_name],
        publish=[(host_port, 1883)],
        volumes=[(str(conf_path), "/mosquitto/config/mosquitto.conf", "ro")],
        detach=True,
        remove=False,
    )
    print(f"[BlackBoxHarness] Broker started (host port {host_port})")

    try:
      _wait_for_port("localhost", host_port, timeout=30.0)
    except RuntimeError:
      try:
        logs = broker_ctr.logs()
        print(f"[BlackBoxHarness] Broker container logs:\n{logs}")
      except Exception:
        pass
      try:
        broker_ctr.stop(time=5)
        broker_ctr.remove()
        docker.network.remove(net_name)
      except Exception:
        pass
      raise


    collector_name: Optional[str] = None
    if self._enable_metrics:
      collector_name = f"black_box_harness_collector_{run_id}"
      self._collector_ctr = self._start_collector_container(
          tmp_dir, net_name, collector_name
      )

    host_gateway = self._get_docker_host_gateway(net_name)
    print(f"[BlackBoxHarness] Mock Manager hostname '{manager_name}' → {host_gateway}:{manager_port}")

    container_type = self._container_type
    print(f"[BlackBoxHarness] Container type: {container_type}")

    tracker_name = f"black_box_harness_tracker_{run_id}"

    try:
      if container_type == CONTAINER_TYPE_CONTROLLER:
        tracker_ctr = self._start_controller_container(
            tmp_dir, net_name, broker_name, tracker_name,
            manager_name, host_gateway, manager_port, collector_name,
        )
      else:
        tracker_ctr = self._start_tracker_service_container(
            tmp_dir, net_name, broker_name, tracker_name,
            manager_name, host_gateway, manager_port, collector_name,
        )
    except Exception:
      try:
        broker_ctr.stop(time=5)
        broker_ctr.remove()
        self._stop_collector()
        docker.network.remove(net_name)
      except Exception:
        pass
      raise

    print(f"[BlackBoxHarness] Tracker container started ({container_type})")
    print(f"[BlackBoxHarness] Waiting {self._startup_wait_s}s for container startup ...")
    time.sleep(self._startup_wait_s)

    return broker_ctr, tracker_ctr

  def _get_docker_host_gateway(self, net_name: str) -> str:
    """Return the IP of the Docker host gateway for the given network."""
    info = docker.network.inspect(net_name)
    try:
      return info.ipam.config[0]["Gateway"]
    except (KeyError, IndexError, TypeError):
      return "host-gateway"

  def _start_controller_container(
      self,
      tmp_dir: Path,
      net_name: str,
      broker_name: str,
      tracker_name: str,
      manager_name: str,
      host_gateway: str,
      manager_port: int,
      collector_name: Optional[str] = None,
  ):
    """Start a Controller container using the mock Manager REST API.

    Passes ``--resturl http://<manager>/api/v1`` so the Controller uses
    ``RestSceneDataSource`` — identical to the production path.
    ``--restauth harness:harness`` supplies credentials; the mock server
    accepts any username/password.  ``--maxlag 1e15`` allows historical
    dataset timestamps.

    Returns:
        Running controller container.
    """
    manager_url = f"http://{manager_name}:{manager_port}/api/v1"
    rest_auth   = f"{_MOCK_MANAGER_USER}:{_MOCK_MANAGER_PASSWORD}"

    envs: Dict[str, str] = {}
    if collector_name:
      envs = {
          "CONTROLLER_ENABLE_METRICS": "true",
          "CONTROLLER_METRICS_ENDPOINT": f"{collector_name}:{self._metrics_otlp_port}",
          "CONTROLLER_METRICS_EXPORT_INTERVAL_S": str(self._metrics_export_interval_s),
      }

    return docker.run(
        self._container_image,
        command=[
            "--resturl",            manager_url,
            "--restauth",           rest_auth,
            "--broker",             broker_name,
            "--tracker_config_file", _CONTAINER_TRACKER_CONFIG,
            "--maxlag",             "1e15",
            "--visibility_topic",   "none",
        ],
        name=tracker_name,
        networks=[net_name],
        add_hosts=[(manager_name, host_gateway)],
        envs=envs,
        volumes=[
            (str(self._tracker_config_path), _CONTAINER_TRACKER_CONFIG, "ro"),
        ],
        detach=True,
        remove=False,
    )

  def _start_tracker_service_container(
      self,
      tmp_dir: Path,
      net_name: str,
      broker_name: str,
      tracker_name: str,
      manager_name: str,
      host_gateway: str,
      manager_port: int,
      collector_name: Optional[str] = None,
  ):
    """Start a Tracker service container using the mock Manager REST API.

    Uses ``scenes.source: api`` pointing at the mock Manager container,
    matching the production deployment path.  A JSON auth file is written
    to the workspace and mounted read-only into the container.

    Returns:
        Running tracker service container.
    """
    with open(self._tracker_config_path) as f:
      tracker_cfg = json.load(f)
    auth_file = tmp_dir / "manager_auth.json"
    auth_file.write_text(json.dumps({
        "user": _MOCK_MANAGER_USER,
        "password": _MOCK_MANAGER_PASSWORD,
    }))

    svc_config = _build_tracker_service_config(
        broker_name, manager_name, manager_port, tracker_cfg,
        otlp_endpoint=(f"{collector_name}:{self._metrics_otlp_port}" if collector_name else None),
        metrics_interval_s=self._metrics_export_interval_s,
    )
    svc_config_file = tmp_dir / "tracker_svc_config.json"
    with open(svc_config_file, "w") as f:
      json.dump(svc_config, f, indent=2)

    return docker.run(
        self._container_image,
        command=[
            _TRACKER_SVC_EXECUTABLE,
            "--config", _TRACKER_SVC_CONFIG,
            "--schema", _TRACKER_SVC_SCHEMA,
        ],
        name=tracker_name,
        networks=[net_name],
        add_hosts=[(manager_name, host_gateway)],
        volumes=[
            (str(svc_config_file), _TRACKER_SVC_CONFIG, "ro"),
            (str(auth_file),       _TRACKER_SVC_AUTH,   "ro"),
        ],
        detach=True,
        remove=False,
    )

  def _start_log_streaming(
      self, tracker_ctr, log_file: Path
  ) -> Optional[threading.Thread]:
    """Stream tracker container logs to a file.

    Mirrors the pacing model of tests/system/metric/tc_tracker_metric.py:
    logs are collected continuously from container start so the full
    startup sequence is captured before any frames are published.

    Args:
        tracker_ctr: Running Docker container object.
        log_file:    Path to write logs to.  Parent directory must already
                     exist.

    Returns:
        Background thread (join after session ends), or ``None``.
    """
    if tracker_ctr is None:
      return None

    def _stream():
      with open(log_file, "w") as fh:
        try:
          for _source, content in docker.container.logs(
              tracker_ctr, stream=True, follow=True
          ):
            line = content.decode("utf-8", errors="replace")
            fh.write(line if line.endswith("\n") else line + "\n")
            fh.flush()
        except Exception as exc:
          fh.write(f"log stream ended: {exc}\n")

    t = threading.Thread(target=_stream, daemon=True)
    t.start()
    return t

  def _stop_containers(self, broker_ctr, tracker_ctr) -> None:
    """Stop and remove broker and tracker containers."""
    for ctr in (tracker_ctr, broker_ctr):
      if ctr is None:
        continue
      try:
        ctr.stop(time=5)
        ctr.remove()
      except Exception as exc:
        print(f"[BlackBoxHarness] Warning: container cleanup failed: {exc}")

  def _build_collector_config(self, tmp_dir: Path) -> Path:
    """Write the OTEL Collector config (OTLP receiver → file exporter)."""
    out_path = f"{_COLLECTOR_OUTPUT_DIR}/{_COLLECTOR_OUTPUT_FILE}"
    conf = (
        "receivers:\n"
        "  otlp:\n"
        "    protocols:\n"
        "      grpc:\n"
        f"        endpoint: 0.0.0.0:{self._metrics_otlp_port}\n"
        "exporters:\n"
        "  file:\n"
        f"    path: {out_path}\n"
        "service:\n"
        "  telemetry:\n"
        "    metrics:\n"
        "      level: none\n"
        "  pipelines:\n"
        "    metrics:\n"
        "      receivers: [otlp]\n"
        "      exporters: [file]\n"
    )
    cfg_file = tmp_dir / "collector.yaml"
    cfg_file.write_text(conf)
    return cfg_file

  def _start_collector_container(
      self, tmp_dir: Path, net_name: str, collector_name: str
  ):
    """Start the OTEL Collector sidecar that captures OTLP metrics to a file."""
    out_dir = tmp_dir / "collector_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # The collector image runs as a non-root UID; make the bind-mounted output
    # directory world-writable so it can write the metrics file.
    os.chmod(out_dir, 0o777)
    self._metrics_out_dir = out_dir

    cfg_path = self._build_collector_config(tmp_dir)
    ctr = docker.run(
        self._metrics_collector_image,
        command=["--config", _COLLECTOR_CONFIG],
        name=collector_name,
        networks=[net_name],
        volumes=[
            (str(cfg_path), _COLLECTOR_CONFIG, "ro"),
            (str(out_dir),  _COLLECTOR_OUTPUT_DIR, "rw"),
        ],
        detach=True,
        remove=False,
    )
    print(f"[BlackBoxHarness] OTEL Collector started ({collector_name})")
    # Give the OTLP receiver a moment to bind before the tracker connects; the
    # OTLP exporter retries, so an exact readiness probe is unnecessary.
    time.sleep(1.0)
    return ctr

  def _stop_collector(self) -> None:
    """Stop and remove the OTEL Collector container, if running."""
    ctr = self._collector_ctr
    if ctr is None:
      return
    try:
      ctr.stop(time=5)
      ctr.remove()
    except Exception as exc:
      print(f"[BlackBoxHarness] Warning: collector cleanup failed: {exc}")
    finally:
      self._collector_ctr = None

  def _record_metrics(self, output_frame_count: int = 0) -> None:
    """Parse the collector output and write metrics_summary.txt.

    After writing the summary, verifies the number of dropped frames and warns
    if the dropped-to-output ratio exceeds the configured threshold.
    """
    if not self._output_folder or self._metrics_out_dir is None:
      return
    metrics_file = self._metrics_out_dir / _COLLECTOR_OUTPUT_FILE
    summary_file = self._output_folder / "metrics_summary.txt"
    metadata = {
        "container_type": self._container_type,
        "endpoint": f"<collector>:{self._metrics_otlp_port}",
        "export_interval_s": self._metrics_export_interval_s,
    }
    try:
      metrics_recorder.write_summary(metrics_file, summary_file, metadata)
      print(f"[BlackBoxHarness] Metrics summary → {summary_file}")
    except Exception as exc:
      print(f"[BlackBoxHarness] Warning: metrics summary failed: {exc}")
      return

    self._verify_dropped_frames(metrics_file, output_frame_count)

  def _verify_dropped_frames(
      self, metrics_file: Path, output_frame_count: int
  ) -> None:
    """Report dropped frames and warn when the drop ratio is too high."""
    try:
      values = metrics_recorder.collect_metric_values(metrics_file)
      result = metrics_recorder.check_dropped_frames(values, output_frame_count)
    except Exception as exc:
      print(f"[BlackBoxHarness] Warning: dropped-frame check failed: {exc}")
      return

    print(
        f"[BlackBoxHarness] Dropped frames: {result['dropped']} "
        f"({result['ratio'] * 100:.2f}% of {result['output_frames']} "
        "output frames)"
    )
    if result["exceeded"]:
      print(
          "[BlackBoxHarness] WARNING: results are unreliable! Dropped-frame ratio "
          f"{result['ratio'] * 100:.2f}% exceeds threshold "
          f"{result['threshold'] * 100:.2f}%"
      )

  def _run_session(
      self, frames: List[Dict[str, Any]], host_port: int
  ) -> List[Dict[str, Any]]:
    """Publish input frames and collect tracker outputs.

    Paces publication using the inter-frame timestamp deltas so the
    tracker experiences a realistic frame cadence.  Frames are always
    published with their original dataset timestamps; both the Controller
    (``--maxlag 1e15``) and the Tracker service (``max_lag_s: 1e15``) are
    configured to accept historical timestamps, so no rewriting is needed.

    Args:
        frames:    All input detection frames in chronological order.
        host_port: Local port the broker is listening on.

    Returns:
        List of output dicts collected from the scene output topic.
    """
    outputs: List[Dict[str, Any]] = []
    output_lock = threading.Lock()
    scene_topic = _TOPIC_DATA_SCENE.format(scene_id=self._scene_id)

    # --- MQTT client setup ---
    client = mqtt.Client(client_id=f"black_box_harness_client_{uuid.uuid4().hex[:6]}")

    def _on_message(_client, _userdata, message):
      try:
        payload = json.loads(message.payload.decode("utf-8"))
        with output_lock:
          outputs.append(payload)
      except Exception as exc:
        print(f"[BlackBoxHarness] Warning: failed to parse output message: {exc}")

    def _on_connect(_client, _userdata, _flags, rc):
      if rc == 0:
        client.subscribe(scene_topic)
        print(f"[BlackBoxHarness] Subscribed to '{scene_topic}'")
      else:
        print(f"[BlackBoxHarness] Warning: MQTT connect failed rc={rc}")

    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect("localhost", host_port, keepalive=60)
    client.loop_start()

    time.sleep(0.5)

    if self._camera_order:
      frames = _sort_by_camera_order(frames, self._camera_order)

    session_start_wall: Optional[float] = None
    session_start_data: Optional[float] = None

    published_count = 0
    publish_start = time.monotonic()
    for frame in frames:
      ts_str = frame.get("timestamp")
      if ts_str:
        frame_ts = _parse_ts(ts_str)
        if session_start_wall is None:
          session_start_wall = time.monotonic()
          session_start_data = frame_ts
        else:
          data_offset = frame_ts - session_start_data
          expected_wall = session_start_wall + data_offset
          sleep_for = expected_wall - time.monotonic()
          if sleep_for > 0:
            time.sleep(sleep_for)

      cam_id = frame.get("id", "")
      topic  = _TOPIC_DATA_CAMERA.format(camera_id=cam_id)
      client.publish(topic, json.dumps(frame))
      published_count += 1

    publish_elapsed = time.monotonic() - publish_start
    avg_publish_fps = published_count / publish_elapsed if publish_elapsed > 0 else 0.0
    print(
        f"[BlackBoxHarness] Published {published_count} frames in "
        f"{publish_elapsed:.2f}s (avg {avg_publish_fps:.2f} frames/s)"
    )

    print(f"[BlackBoxHarness] Published {len(frames)} frames, draining (idle timeout {self._drain_timeout}s) ...")
    poll_interval = min(0.25, self._drain_timeout) if self._drain_timeout > 0 else 0.25
    last_count = len(outputs)
    idle_time = 0.0
    while idle_time < self._drain_timeout:
      time.sleep(poll_interval)
      with output_lock:
        current_count = len(outputs)
      if current_count != last_count:
        last_count = current_count
        idle_time = 0.0
      else:
        idle_time += poll_interval

    client.loop_stop()
    client.disconnect()

    print(f"[BlackBoxHarness] Collected {len(outputs)} output messages")
    merged = _merge_outputs_by_timestamp(outputs)
    print(f"[BlackBoxHarness] Merged into {len(merged)} logical frames")
    return merged

  def _persist_outputs(self, outputs: List[Dict], tmp_dir: Path) -> None:
    """Write output frames to the configured output folder."""
    if not self._output_folder:
      return
    self._output_folder.mkdir(parents=True, exist_ok=True)
    out_file = tmp_dir / "outputs.jsonl"
    write_jsonl(iter(outputs), str(out_file))
    shutil.copy(out_file, self._output_folder / "outputs.jsonl")

  def _persist_config(self) -> None:
    """Copy the tracker configuration file into the output ``config`` folder.

    Applies to both container types: ``self._tracker_config_path`` is the
    source config supplied via ``set_custom_config()`` (mounted directly for
    the controller, and the basis for the tracker service config).  The file
    is copied under ``<output_folder>/config/`` preserving its basename.
    """
    if not self._output_folder or not self._tracker_config_path:
      return
    config_dir = self._output_folder / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    dest = config_dir / Path(self._tracker_config_path).name
    shutil.copy(self._tracker_config_path, dest)
    print(f"[BlackBoxHarness] Config → {dest}")
