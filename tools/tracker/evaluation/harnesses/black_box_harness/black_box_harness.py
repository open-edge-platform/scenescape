# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""BlackBoxHarness — black-box tracker harness that communicates via MQTT.

Architecture
------------
Three containers are involved:

  ┌─────────────────────────────────────────────────┐
  │  Docker network  "black_box_harness_<run_id>"     │
  │                                                 │
  │  ┌──────────────┐     ┌─────────────────────┐  │
  │  │   broker     │ ←── │  tracker container  │  │
  │  │  (mosquitto) │ ──→ │  (user-supplied)    │  │
  │  └──────┬───────┘     └─────────────────────┘  │
  │         │ port 1883 exposed to host             │
  └─────────┼───────────────────────────────────────┘
            │
  ┌─────────┴──────────────────────────┐
  │  BlackBoxHarness process (host)     │
  │  • publishes  DATA_CAMERA frames   │
  │  • subscribes DATA_SCENE output    │
  └────────────────────────────────────┘

Supported container types
-------------------------
* **Controller** (``scenescape-controller``, entrypoint ``controller-cmd``):
  - Scene config loaded via ``--data_source config.json`` (FileSceneDataSource).
  - Config uses REST format: camera dicts contain ``camera points``/``map points``
    directly so ``Camera.__init__`` can construct a PointCorrespondenceTransform.
  - Timestamps from the dataset are rewritten to wall-clock time by the controller
    via ``--rewriteAllTime``.
  - Time-chunking is controlled by ``time_chunking_enabled`` in tracker-config.json.

* **Tracker service** (``scenescape-tracker``, binary ``/scenescape/tracker``):
  - Scene config loaded via ``scenes.source: file`` in config.json.
  - Scene format uses pre-solved ``extrinsics`` (translation, XYZ Euler degrees)
    computed by the harness from the dataset's camera/map point correspondences.
  - Timestamps in published frames are **rewritten to current wall-clock time** by
    the harness (no ``--rewriteAllTime`` equivalent in the tracker binary).
  - Time-chunking is always active via ``tracking.time_chunking_rate_fps``.

Timestamp synchronisation
-------------------------
Consecutive input frames are published with a wall-clock delay equal to the
delta between their ISO 8601 timestamps multiplied by ``1 / playback_rate``.
This reproduces the original capture cadence so the tracker's internal timing
(object ageing, time-chunking) sees a realistic frame rate.

Topics (from scene_common.mqtt.PubSub templates)
-------------------------------------------------
* Publish  →  scenescape/data/camera/{camera_id}
* Subscribe←  scenescape/data/scene/{scene_id}/+      (Controller & Tracker service: full-rate per-frame)

Configuration keys (set_custom_config)
--------------------------------------
Required:
  tracker_config_path (str): path to tracker-config.json mounted into the
                             tracker container at the expected location.
Optional:
  container_type  (str):   ``'controller'`` or ``'tracker'``; auto-detected
                           from image metadata when omitted.
  scene_id        (str):   scene uid used to build the output topic;
                           defaults to config['uid'] from set_scene_config().
  playback_rate   (float): speed multiplier for frame injection (default 1.0).
  drain_timeout   (float): idle timeout — seconds with no new output messages before
                           outputs to arrive (default 5.0).
  broker_image    (str):   mosquitto Docker image (required, e.g. "eclipse-mosquitto:2.0.22").
  broker_port     (int):   host port to bind the broker on (default 0 =
                           choose a free port automatically).
"""

import json
import shutil
import socket
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

import paho.mqtt.client as mqtt
from python_on_whales import docker

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from base.tracker_harness import TrackerHarness
from utils.format_converters import write_jsonl

# ---------------------------------------------------------------------------
# MQTT topic constants (mirrors scene_common.mqtt.PubSub._TopicTemplates)
# ---------------------------------------------------------------------------
_TOPIC_BASE = "scenescape"
_TOPIC_DATA_CAMERA = _TOPIC_BASE + "/data/camera/{camera_id}"
# Both controller (publishSceneDetections) and tracker service publish one
# message per input frame per object-type here — no wall-clock throttling,
# equivalent to the metric test's per-frame buildDetectionsList() output.
_TOPIC_DATA_SCENE  = _TOPIC_BASE + "/data/scene/{scene_id}/+"

# Mosquitto config that allows anonymous connections on port 1883
_MOSQUITTO_CONF = """\
listener 1883
allow_anonymous true
"""

# Shared workspace path inside both container types
_CONTAINER_WORKSPACE       = "/workspace"

# Controller-specific container paths
_CONTAINER_CONFIG          = _CONTAINER_WORKSPACE + "/config.json"
_CONTAINER_TRACKER_CONFIG  = _CONTAINER_WORKSPACE + "/tracker-config.json"

# Tracker-service-specific container paths
_TRACKER_SVC_EXECUTABLE    = "/scenescape/tracker"
_TRACKER_SVC_CONFIG        = _CONTAINER_WORKSPACE + "/tracker_svc_config.json"
_TRACKER_SVC_SCENES        = _CONTAINER_WORKSPACE + "/scenes.json"
_TRACKER_SVC_SCHEMA        = "/scenescape/schema/config.schema.json"

# Container type constants
CONTAINER_TYPE_CONTROLLER = "controller"
CONTAINER_TYPE_TRACKER    = "tracker"


DEFAULT_DRAIN_TIMEOUT = 5.0   # seconds of silence after last received message before stopping
DEFAULT_PLAYBACK_RATE = 1.0   # 1.0 = real-time, 2.0 = 2× speed


def _to_controller_config(scene_config: dict) -> dict:
    """Build a ``FileSceneDataSource``-compatible scene config for ``controller-cmd``.

    The Controller's ``Camera.__init__`` recognises two pose formats:
    ``('translation', 'rotation', 'scale')`` and ``('camera points', 'map points')``.
    It does NOT understand the REST ``transforms`` flat array + ``transform_type``.
    So we embed ``camera points`` and ``map points`` directly in each camera dict;
    ``Camera.__init__`` will then construct a ``PointCorrespondenceTransform`` and
    solve PnP internally.

    Args:
        scene_config: Scene configuration in dataset-specific format.

    Returns:
        Scene configuration dict suitable for ``FileSceneDataSource``.
    """
    scene_uid = scene_config.get("uid") or scene_config["name"]

    cameras = []
    sensors = scene_config.get("sensors", {})
    if isinstance(sensors, dict):
        for cam_name, info in sensors.items():
            fx, fy, cx, cy = info["intrinsics"]
            w = int(info["width"])
            h = int(info["height"])

            cameras.append({
                "uid": cam_name,
                "name": cam_name,
                "intrinsics": {"fx": fx, "fy": fy, "cx": cx, "cy": cy},
                "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0},
                "resolution": [w, h],
                # Embed correspondence points directly so Camera.__init__ builds
                # a PointCorrespondenceTransform (solvePnP) instead of falling back
                # to an identity DEFAULT_TRANSFORM.
                "camera points": info.get("camera points", []),
                "map points": info.get("map points", []),
                "scene": scene_uid,
            })

    return {
        "uid": scene_uid,
        "name": scene_config["name"],
        "scale": scene_config.get("scale"),
        "map": scene_config.get("map"),
        "cameras": cameras,
        "use_tracker": True,
        # Rate fields required by publishExternalDetections / publishRegulatedDetections.
        "regulated_rate": scene_config.get("regulated_rate", 30.0),
        "external_update_rate": scene_config.get("external_update_rate", 30.0),
    }


def _solve_pnp(
    camera_points: List, map_points: List, intrinsics: List
) -> Tuple[List[float], List[float], List[float]]:
    """Solve PnP from 2D-3D point correspondences and return camera extrinsics.

    Replicates ``PointCorrespondenceTransform._calculatePoseMat`` +
    ``CameraPose._poseMatToPose`` from scene_common using cv2 directly so the
    harness does not need scene_common installed.

    Args:
        camera_points: List of (x, y) image-pixel coordinate pairs.
        map_points:    List of (x, y) or (x, y, z) world-coordinate triples.
        intrinsics:    [fx, fy, cx, cy] camera intrinsic parameters.

    Returns:
        (translation, euler_xyz_deg, scale) tuples — matching the format used
        by ``CameraPose.asDict`` / Tracker-service scenes.json extrinsics.
    """
    fx, fy, cx, cy = intrinsics
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    dist = np.zeros(5, dtype=np.float64)

    cam_pts = np.array(camera_points, dtype=np.float32)
    map_pts = np.array(map_points, dtype=np.float32)
    if map_pts.ndim == 2 and map_pts.shape[1] == 2:
        map_pts = np.hstack([map_pts, np.zeros((map_pts.shape[0], 1), dtype=np.float32)])

    _, rvec, tvec = cv2.solvePnP(map_pts, cam_pts, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    rmat = cv2.Rodrigues(rvec)[0]
    # Invert to get camera-in-world (pose_mat) from world-in-camera
    pose_mat = np.linalg.inv(np.vstack([np.hstack([rmat, tvec]), [0, 0, 0, 1]]))
    translation = pose_mat[:3, 3].tolist()
    euler_deg = Rotation.from_matrix(pose_mat[:3, :3]).as_euler("XYZ", degrees=True).tolist()
    scale = [1.0, 1.0, 1.0]
    return translation, euler_deg, scale


def _to_tracker_service_scenes(scene_config: dict) -> List[Dict[str, Any]]:
    """Build a Tracker-service scenes.json array from dataset scene config.

    The Tracker service (C++ binary) expects a JSON *array* of scene objects,
    each camera carrying solved ``extrinsics`` (translation, XYZ Euler degrees,
    scale).  Intrinsics use the nested ``distortion`` sub-object format defined
    in ``tracker/schema/scene.schema.json``.

    Args:
        scene_config: Scene configuration in dataset-specific format.

    Returns:
        JSON-serialisable list suitable for writing to scenes.json.
    """
    scene_uid = scene_config.get("uid") or scene_config["name"]

    cameras = []
    sensors = scene_config.get("sensors", {})
    if isinstance(sensors, dict):
        for cam_name, info in sensors.items():
            fx, fy, cx, cy = info["intrinsics"]
            cam_pts = info.get("camera points", [])
            map_pts = info.get("map points", [])
            translation, euler_deg, scale = _solve_pnp(cam_pts, map_pts, info["intrinsics"])
            cameras.append({
                "uid": cam_name,
                "name": cam_name,
                "intrinsics": {
                    "fx": fx, "fy": fy, "cx": cx, "cy": cy,
                    "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0},
                },
                "extrinsics": {
                    "translation": translation,
                    "rotation": euler_deg,
                    "scale": scale,
                },
            })

    return [{"uid": scene_uid, "name": scene_config["name"], "cameras": cameras}]


def _build_tracker_service_config(
    broker_name: str,
    scenes_container_path: str,
    tracker_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the full config.json for the Tracker service container.

    The Tracker service always operates with time-chunking enabled.  Tracking
    parameters are mapped from the dataset tracker-config.json format.

    Args:
        broker_name:           Hostname of the MQTT broker inside the Docker
                               network (e.g. ``"black_box_harness_broker_<id>"``).
        scenes_container_path: Absolute path to scenes.json *inside* the
                               container.
        tracker_cfg:           Parsed contents of tracker-config.json from the
                               dataset.

    Returns:
        Config dict ready to be JSON-serialised as config.json.
    """
    return {
        "infrastructure": {
            "mqtt": {
                "host": broker_name,
                "port": 1883,
                "insecure": True,
            },
        },
        "scenes": {
            "source": "file",
            "file_path": scenes_container_path,
        },
        "tracking": {
            # Tracker service always uses time-chunking; fall back to 15 fps.
            "time_chunking_rate_fps": tracker_cfg.get("time_chunking_rate_fps", 15),
            "max_unreliable_time_s":        tracker_cfg.get("max_unreliable_time_s", 1.0),
            "non_measurement_time_dynamic_s": tracker_cfg.get("non_measurement_time_dynamic_s", 0.8),
            "non_measurement_time_static_s":  tracker_cfg.get("non_measurement_time_static_s", 1.6),
            # Frames are published with current wall-clock timestamps by the
            # harness (timestamp rewriting), so real-time lag is negligible.
            "max_lag_s": 1.0,
        },
    }


def _detect_container_type(container_image: str) -> str:
    """Auto-detect whether *container_image* is a Controller or Tracker service.

    Inspects the image's ``Entrypoint`` and ``Cmd`` metadata.  Falls back to
    image name heuristics if Docker inspection fails.

    Args:
        container_image: Docker image reference (e.g. ``"scenescape-controller:latest"``).

    Returns:
        ``CONTAINER_TYPE_CONTROLLER`` or ``CONTAINER_TYPE_TRACKER``.
    """
    try:
        img = docker.image.inspect(container_image)
        combined = " ".join((img.config.entrypoint or []) + (img.config.cmd or []))
        if "controller-cmd" in combined:
            return CONTAINER_TYPE_CONTROLLER
        if "/scenescape/tracker" in combined:
            return CONTAINER_TYPE_TRACKER
    except Exception:
        pass
    # Heuristic fallback from image name
    name = container_image.split(":")[0].lower()
    if "tracker" in name and "controller" not in name:
        return CONTAINER_TYPE_TRACKER
    return CONTAINER_TYPE_CONTROLLER


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


def _merge_outputs_by_timestamp(
    outputs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge tracker output messages that share the same timestamp.

    The MQTT tracker publishes one message per (camera-input, object-type)
    combination (e.g. ``scenescape/data/scene/{uid}/person`` and
    ``scenescape/data/scene/{uid}/FW190D``).  When two messages arrive at the
    same wall-clock timestamp they map to the same frame number in TrackEval,
    and having the same tracked-object UUID in both messages causes a
    "duplicate ID in a single timestep" error.

    This function groups all messages by timestamp and merges them into a
    single output per timestep, deduplicating objects by UUID.  The merged
    list is sorted by timestamp so the downstream frame-number calculation
    stays monotone.

    Args:
        outputs: Raw list of dicts from the ``on_message`` callback.

    Returns:
        Sorted list of merged output dicts, one entry per unique timestamp.
    """
    from collections import OrderedDict

    # Group by timestamp (preserve insertion order for stable sort)
    by_ts: Dict[str, Dict[str, Any]] = OrderedDict()
    for msg in outputs:
        ts = msg.get("timestamp", "")
        if ts not in by_ts:
            # Start with a shallow copy so we own the objects list
            by_ts[ts] = {**msg, "objects": []}
        seen_ids = {o["id"] for o in by_ts[ts]["objects"]}
        for obj in msg.get("objects", []):
            if obj.get("id") not in seen_ids:
                by_ts[ts]["objects"].append(obj)
                seen_ids.add(obj["id"])

    # Return sorted by timestamp string (ISO 8601 lexicographic sort is correct)
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
        self._playback_rate: float = DEFAULT_PLAYBACK_RATE
        self._drain_timeout: float = DEFAULT_DRAIN_TIMEOUT
        self._broker_image: str = ""
        self._broker_port: int = 0  # 0 = auto
        self._output_folder: Optional[Path] = None

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
        self._tracker_config_path = tp

        if "scene_id" in config:
            self._scene_id = config["scene_id"]
        if "container_type" in config:
            ct = config["container_type"]
            if ct not in (CONTAINER_TYPE_CONTROLLER, CONTAINER_TYPE_TRACKER):
                raise ValueError(
                    f"container_type must be '{CONTAINER_TYPE_CONTROLLER}' or "
                    f"'{CONTAINER_TYPE_TRACKER}', got: {ct!r}"
                )
            self._container_type = ct
        self._playback_rate  = float(config.get("playback_rate",  DEFAULT_PLAYBACK_RATE))
        self._drain_timeout  = float(config.get("drain_timeout",  DEFAULT_DRAIN_TIMEOUT))
        if "broker_image" not in config:
            raise ValueError("Custom config must contain 'broker_image'")
        self._broker_image   = str(config["broker_image"])
        self._broker_port    = int(config.get("broker_port",      0))
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

        # Resolve container type once so _run_session can use it for timestamp
        # rewriting without repeating the Docker inspect call.
        container_type = self._container_type or _detect_container_type(self._container_image)

        try:
            # Consume the iterator into a list so we can persist it and
            # calculate timestamp deltas without streaming complications.
            input_frames: List[Dict[str, Any]] = list(inputs)
            self._write_inputs(input_frames, tmp_dir)

            host_port = self._broker_port if self._broker_port > 0 else _free_port()

            broker_ctr, tracker_ctr = self._start_containers(
                tmp_dir, net_name, host_port, run_id
            )
            log_thread = self._start_log_streaming(tracker_ctr)
            try:
                outputs = self._run_session(input_frames, host_port, container_type)
            finally:
                self._stop_containers(broker_ctr, tracker_ctr)
                if log_thread is not None:
                    log_thread.join(timeout=5.0)
                docker.network.remove(net_name)

            self._persist_outputs(outputs, tmp_dir)
            return iter(outputs)

        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)

    def reset(self) -> "BlackBoxHarness":
        """Reset mutable state (scene / custom config, output folder).

        Returns:
            Self for method chaining.
        """
        self._scene_config       = None
        self._scene_id           = None
        self._tracker_config_path = None
        self._container_type     = None
        self._playback_rate      = DEFAULT_PLAYBACK_RATE
        self._drain_timeout      = DEFAULT_DRAIN_TIMEOUT
        self._output_folder      = None
        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_inputs(self, frames: List[Dict], tmp_dir: Path) -> None:
        """Persist input frames for debugging / output folder artefacts."""
        inputs_file = tmp_dir / "inputs.json"
        write_jsonl(iter(frames), str(inputs_file))
        if self._output_folder:
            shutil.copy(inputs_file, self._output_folder / "inputs.json")

    def _build_mosquitto_conf(self, tmp_dir: Path) -> Path:
        """Write a minimal anonymous mosquitto.conf and return its path."""
        conf = tmp_dir / "mosquitto.conf"
        conf.write_text(_MOSQUITTO_CONF)
        return conf

    def _start_containers(
        self,
        tmp_dir: Path,
        net_name: str,
        host_port: int,
        run_id: str,
    ):
        """Create Docker network, start broker and tracker containers.

        Selects the correct config format and startup command based on the
        detected container type (Controller vs Tracker service).

        Returns:
            (broker_container, tracker_container) tuple.
        """
        docker.network.create(net_name)
        print(f"[BlackBoxHarness] Created Docker network '{net_name}'")

        conf_path = self._build_mosquitto_conf(tmp_dir)

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

        # --- Resolve container type (auto-detect if not explicitly set) ---
        container_type = self._container_type or _detect_container_type(self._container_image)
        print(f"[BlackBoxHarness] Container type: {container_type}")

        tracker_name = f"black_box_harness_tracker_{run_id}"

        try:
            if container_type == CONTAINER_TYPE_CONTROLLER:
                tracker_ctr = self._start_controller_container(
                    tmp_dir, net_name, broker_name, tracker_name
                )
            else:
                tracker_ctr = self._start_tracker_service_container(
                    tmp_dir, net_name, broker_name, tracker_name
                )
        except Exception:
            # Broker was already started; clean it up before propagating.
            try:
                broker_ctr.stop(time=5)
                broker_ctr.remove()
                docker.network.remove(net_name)
            except Exception:
                pass
            raise

        print(f"[BlackBoxHarness] Tracker container started ({container_type})")
        # Allow tracker to connect to broker and load scene config.
        time.sleep(2.0)

        return broker_ctr, tracker_ctr

    def _start_controller_container(
        self,
        tmp_dir: Path,
        net_name: str,
        broker_name: str,
        tracker_name: str,
    ):
        """Start a Controller container (controller-cmd) with file-based scene config.

        Writes config.json with ``camera points``/``map points`` directly in
        each camera dict so ``Camera.__init__`` constructs a
        ``PointCorrespondenceTransform`` (solvePnP).  Dataset timestamps are
        sent as-is so that frames from two cameras sharing the same timestamp
        produce outputs at the same timestamp and can be merged correctly by
        ``_merge_outputs_by_timestamp``.  ``--max_lag 1e15`` prevents the
        controller from dropping historical (e.g. 2014-era) dataset timestamps.

        Returns:
            Running controller container.
        """
        controller_cfg = _to_controller_config(self._scene_config)
        # Ensure the scene topic UID matches what the controller will announce.
        if self._scene_id == self._scene_config.get("name"):
            self._scene_id = controller_cfg["uid"]
        config_file = tmp_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(controller_cfg, f, indent=2)

        return docker.run(
            self._container_image,
            command=[
                "--data_source",        _CONTAINER_CONFIG,
                "--broker",             broker_name,
                "--tracker_config_file", _CONTAINER_TRACKER_CONFIG,
                "--maxlag",             "1e15",
                "--visibility_topic",   "none",
            ],
            name=tracker_name,
            networks=[net_name],
            volumes=[
                (str(config_file),               _CONTAINER_CONFIG,         "ro"),
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
    ):
        """Start a Tracker service container (/scenescape/tracker) with file scenes.

        The Tracker service always uses time-chunking.  Camera extrinsics are
        pre-solved from the dataset's point correspondences via ``_solve_pnp``.
        The harness rewrites frame timestamps to wall-clock time before
        publishing (see ``_run_session``), so ``max_lag_s: 1.0`` is sufficient.

        Returns:
            Running tracker service container.
        """
        with open(self._tracker_config_path) as f:
            tracker_cfg = json.load(f)

        scenes = _to_tracker_service_scenes(self._scene_config)
        scenes_file = tmp_dir / "scenes.json"
        with open(scenes_file, "w") as f:
            json.dump(scenes, f, indent=2)

        svc_config = _build_tracker_service_config(
            broker_name, _TRACKER_SVC_SCENES, tracker_cfg
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
            volumes=[
                (str(svc_config_file), _TRACKER_SVC_CONFIG, "ro"),
                (str(scenes_file),     _TRACKER_SVC_SCENES, "ro"),
            ],
            detach=True,
            remove=False,
        )

    def _start_log_streaming(self, tracker_ctr) -> Optional[threading.Thread]:
        """Stream tracker container logs to stdout in a background thread.

        Returns the thread so the caller can join it after the session ends,
        or ``None`` if streaming could not be started.
        """
        if tracker_ctr is None:
            return None

        def _stream():
            try:
                # Container.logs() instance method does not support stream/follow;
                # use docker.container.logs() (the CLI wrapper) which yields
                # (source, bytes) tuples where source is 'stdout' or 'stderr'.
                for _source, content in docker.container.logs(
                    tracker_ctr, stream=True, follow=True
                ):
                    line = content.decode("utf-8", errors="replace")
                    print(f"[tracker] {line}", end="" if line.endswith("\n") else "\n",
                          flush=True)
            except Exception as exc:
                print(f"[tracker] log stream ended: {exc}", flush=True)

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

    def _run_session(
        self, frames: List[Dict[str, Any]], host_port: int, container_type: str
    ) -> List[Dict[str, Any]]:
        """Publish input frames and collect tracker outputs.

        Paces publication using the inter-frame timestamp deltas so the
        tracker experiences a realistic frame cadence.

        For the **Tracker service** container type, frame timestamps are
        rewritten to the current wall-clock time before publishing.  The
        Tracker service has no ``--rewriteAllTime`` flag, so historical
        dataset timestamps would be rejected by its ``max_lag_s`` filter.
        Pacing is still driven by the *original* timestamp deltas, so the
        tracker receives frames at the correct capture cadence regardless.

        For the **Controller** container type, frames are published with their
        original dataset timestamps so that the two cameras (which share the
        same timestamps for each logical frame) produce outputs at the same
        timestamp.  Those outputs are then merged by ``_merge_outputs_by_timestamp``
        into one entry per logical frame — matching the metric test's output
        cadence.

        Args:
            frames:         All input detection frames in chronological order.
            host_port:      Local port the broker is listening on.
            container_type: ``CONTAINER_TYPE_CONTROLLER`` or
                            ``CONTAINER_TYPE_TRACKER``.

        Returns:
            List of output dicts collected from the scene output topic.
        """
        rewrite_timestamps = (container_type == CONTAINER_TYPE_TRACKER)
        outputs: List[Dict[str, Any]] = []
        output_lock = threading.Lock()
        # Both controller and tracker service publish one message per input
        # frame per object-type on DATA_SCENE.  This mirrors what the metric
        # test's buildDetectionsList() call produces — one output per frame,
        # no wall-clock throttling.  DATA_REGULATED is wall-clock throttled
        # (regulated_rate Hz) and emits only a handful of messages when frames
        # are replayed faster than real-time.
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

        # Allow subscription to be established
        time.sleep(0.5)

        # --- Publish frames paced by timestamp deltas ---
        prev_ts: Optional[float] = None
        prev_wall: Optional[float] = None

        for frame in frames:
            ts_str = frame.get("timestamp")
            if ts_str:
                frame_ts = _parse_ts(ts_str)
                now = time.monotonic()
                if prev_ts is not None and prev_wall is not None:
                    delta_data = frame_ts - prev_ts          # seconds in data time
                    elapsed    = now - prev_wall             # seconds already waited
                    sleep_for  = delta_data / self._playback_rate - elapsed
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                prev_ts   = frame_ts
                prev_wall = time.monotonic()

            cam_id = frame.get("id", "")
            topic  = _TOPIC_DATA_CAMERA.format(camera_id=cam_id)
            if rewrite_timestamps:
                _now = datetime.now(timezone.utc)
                now_ms = _now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{_now.microsecond // 1000:03d}Z"
                published_frame = {**frame, "timestamp": now_ms}
            else:
                published_frame = frame
            client.publish(topic, json.dumps(published_frame))

        print(f"[BlackBoxHarness] Published {len(frames)} frames, draining (idle timeout {self._drain_timeout}s) ...")
        # Idle-based drain: keep collecting until no new messages arrive for
        # drain_timeout seconds.  Uses nominal sleep increments so behaviour
        # is predictable even when time.sleep is mocked in unit tests.
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
        print(f"[BlackBoxHarness] Merged into {len(merged)} timesteps")
        return merged

    def _persist_outputs(self, outputs: List[Dict], tmp_dir: Path) -> None:
        """Write output frames to the configured output folder."""
        if not self._output_folder:
            return
        out_file = tmp_dir / "outputs.json"
        with open(out_file, "w") as f:
            json.dump(outputs, f)
        shutil.copy(out_file, self._output_folder / "outputs.json")
