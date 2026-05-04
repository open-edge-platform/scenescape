# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MqttHarness — black-box tracker harness that communicates via MQTT.

Architecture
------------
Three containers are involved:

  ┌─────────────────────────────────────────────────┐
  │  Docker network  "mqtt_harness_<run_id>"        │
  │                                                 │
  │  ┌──────────────┐     ┌─────────────────────┐  │
  │  │   broker     │ ←── │  tracker container  │  │
  │  │  (mosquitto) │ ──→ │  (user-supplied)    │  │
  │  └──────┬───────┘     └─────────────────────┘  │
  │         │ port 1883 exposed to host             │
  └─────────┼───────────────────────────────────────┘
            │
  ┌─────────┴──────────────────────────┐
  │  MqttHarness process (host)        │
  │  • publishes  DATA_CAMERA frames   │
  │  • subscribes DATA_SCENE output    │
  └────────────────────────────────────┘

Timestamp synchronisation
-------------------------
Consecutive input frames are published with a wall-clock delay equal to the
delta between their ISO 8601 timestamps multiplied by ``1 / playback_rate``.
This reproduces the original capture cadence so the tracker's internal timing
(object ageing, time-chunking) sees a realistic frame rate.

Topics (from scene_common.mqtt.PubSub templates)
-------------------------------------------------
* Publish  →  scenescape/data/camera/{camera_id}
* Subscribe←  scenescape/data/scene/{scene_id}/+

Configuration keys (set_custom_config)
--------------------------------------
Required:
  tracker_config_path (str): path to tracker-config.json mounted into the
                             tracker container at the expected location.
Optional:
  scene_id        (str):   scene uid used to build the output topic;
                           defaults to config['uid'] from set_scene_config().
  playback_rate   (float): speed multiplier for frame injection (default 1.0).
  drain_timeout   (float): seconds to wait after the last frame for remaining
                           outputs to arrive (default 5.0).
  broker_image    (str):   mosquitto Docker image (default "eclipse-mosquitto").
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
from typing import Any, Dict, Iterator, List, Optional

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
_TOPIC_DATA_SCENE  = _TOPIC_BASE + "/data/scene/{scene_id}/+"

# Mosquitto config that allows anonymous connections on port 1883
_MOSQUITTO_CONF = """\
listener 1883
allow_anonymous true
"""

# Tracker container paths (must match what the image expects)
_CONTAINER_WORKSPACE       = "/workspace"
_CONTAINER_CONFIG          = _CONTAINER_WORKSPACE + "/config.json"
_CONTAINER_TRACKER_CONFIG  = _CONTAINER_WORKSPACE + "/tracker-config.json"

DEFAULT_BROKER_IMAGE  = "eclipse-mosquitto"
DEFAULT_DRAIN_TIMEOUT = 5.0   # seconds to wait after last publish
DEFAULT_PLAYBACK_RATE = 1.0   # 1.0 = real-time, 2.0 = 2× speed


def _to_rest_format(scene_config: dict) -> dict:
    """Convert dataset-format scene config to the REST API format expected by
    ``FileSceneDataSource`` (``controller-cmd --data_source``).

    The dataset format uses a ``sensors`` dict keyed by camera name with
    ``camera points``, ``map points``, ``intrinsics``, ``width``, ``height``.
    The REST API format needs a top-level ``uid``, a ``cameras`` list where
    each entry has ``uid``, ``intrinsics`` dict, ``transform_type``,
    ``transforms`` (flattened cam+map point coords), ``distortion``, and
    ``resolution``.

    Args:
        scene_config: Scene configuration in dataset-specific format.

    Returns:
        Scene configuration dict ready for ``FileSceneDataSource``.
    """
    scene_uid = scene_config.get("uid") or scene_config["name"]

    cameras = []
    sensors = scene_config.get("sensors", {})
    if isinstance(sensors, dict):
        for cam_name, info in sensors.items():
            fx, fy, cx, cy = info["intrinsics"]
            w = int(info["width"])
            h = int(info["height"])

            # Build flat transforms list: all cam-point coords then all map-point coords.
            # Map points may be 3-D; we only use X and Y (controller solvePnP uses 3-D
            # world coords, so we preserve Z as well when present).
            cam_pts = info.get("camera points", [])
            map_pts = info.get("map points", [])
            transforms: List = []
            for pt in cam_pts:
                transforms.extend(pt)
            for pt in map_pts:
                transforms.extend(pt)

            cameras.append({
                "uid": cam_name,
                "name": cam_name,
                "intrinsics": {"fx": fx, "fy": fy, "cx": cx, "cy": cy},
                "transform_type": "3d-2d point correspondence",
                "transforms": transforms,
                "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0},
                "resolution": [w, h],
                "scene": scene_uid,
            })

    rest = {
        "uid": scene_uid,
        "name": scene_config["name"],
        "scale": scene_config.get("scale"),
        "map": scene_config.get("map"),
        "cameras": cameras,
        "use_tracker": True,
        # Rate fields required by publishExternalDetections / publishRegulatedDetections.
        # 30 fps matches the standard SceneScape default.
        "regulated_rate": scene_config.get("regulated_rate", 30.0),
        "external_update_rate": scene_config.get("external_update_rate", 30.0),
    }
    return rest


def _free_port() -> int:
    """Return a free TCP port on localhost."""
    with socket.socket() as s:
        s.bind(("", 0))
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


class MqttHarness(TrackerHarness):
    """Black-box tracker harness using MQTT as the communication channel.

    Starts a throw-away mosquitto broker and the tracker container on a private
    Docker network.  Input frames are published camera-by-camera paced by their
    original timestamps; tracker outputs arriving on the scene topic are
    collected and returned as an iterator.
    """

    def __init__(self, container_image: str):
        """Initialise MqttHarness.

        Args:
            container_image: Docker image for the tracker/controller
                             (e.g. ``"scenescape-controller:2026.1.0-dev"``).
        """
        self._container_image = container_image
        self._scene_config: Optional[Dict[str, Any]] = None
        self._scene_id: Optional[str] = None
        self._tracker_config_path: Optional[str] = None
        self._playback_rate: float = DEFAULT_PLAYBACK_RATE
        self._drain_timeout: float = DEFAULT_DRAIN_TIMEOUT
        self._broker_image: str = DEFAULT_BROKER_IMAGE
        self._broker_port: int = 0  # 0 = auto
        self._output_folder: Optional[Path] = None

    # ------------------------------------------------------------------
    # TrackerHarness interface
    # ------------------------------------------------------------------

    def set_scene_config(self, config: Dict[str, Any]) -> "MqttHarness":
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

    def set_custom_config(self, config: Dict[str, Any]) -> "MqttHarness":
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
        self._playback_rate  = float(config.get("playback_rate",  DEFAULT_PLAYBACK_RATE))
        self._drain_timeout  = float(config.get("drain_timeout",  DEFAULT_DRAIN_TIMEOUT))
        self._broker_image   = str(config.get("broker_image",     DEFAULT_BROKER_IMAGE))
        self._broker_port    = int(config.get("broker_port",      0))
        return self

    def set_output_folder(self, path: Path) -> "MqttHarness":
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
        net_name = f"mqtt_harness_{run_id}"
        tmp_dir  = Path(tempfile.mkdtemp(prefix="mqtt_harness_"))
        print(f"[MqttHarness] Temporary workspace: {tmp_dir}")

        try:
            # Consume the iterator into a list so we can persist it and
            # calculate timestamp deltas without streaming complications.
            input_frames: List[Dict[str, Any]] = list(inputs)
            self._write_inputs(input_frames, tmp_dir)

            host_port = self._broker_port if self._broker_port > 0 else _free_port()

            broker_ctr, tracker_ctr = self._start_containers(
                tmp_dir, net_name, host_port, run_id
            )
            try:
                outputs = self._run_session(input_frames, host_port)
            finally:
                self._stop_containers(broker_ctr, tracker_ctr)
                docker.network.remove(net_name)

            self._persist_outputs(outputs, tmp_dir)
            return iter(outputs)

        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)

    def reset(self) -> "MqttHarness":
        """Reset mutable state (scene / custom config, output folder).

        Returns:
            Self for method chaining.
        """
        self._scene_config       = None
        self._scene_id           = None
        self._tracker_config_path = None
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

        Returns:
            (broker_container, tracker_container) tuple.
        """
        docker.network.create(net_name)
        print(f"[MqttHarness] Created Docker network '{net_name}'")

        # Write mosquitto config
        conf_path = self._build_mosquitto_conf(tmp_dir)

        # --- Broker ---
        broker_name = f"mqtt_harness_broker_{run_id}"
        broker_ctr = docker.run(
            self._broker_image,
            # No command override: the image's default CMD already runs
            # "mosquitto -c /mosquitto/config/mosquitto.conf".
            # We mount our config at that exact path.
            name=broker_name,
            networks=[net_name],
            publish=[(host_port, 1883)],
            volumes=[(str(conf_path), "/mosquitto/config/mosquitto.conf", "ro")],
            detach=True,
            remove=False,
        )
        print(f"[MqttHarness] Broker started (host port {host_port})")

        # Wait until the broker is actually accepting TCP connections.
        try:
            _wait_for_port("localhost", host_port, timeout=30.0)
        except RuntimeError:
            # Collect container logs to aid debugging before re-raising.
            try:
                logs = broker_ctr.logs()
                print(f"[MqttHarness] Broker container logs:\n{logs}")
            except Exception:
                pass
            raise

        # Write scene config in REST API format (required by FileSceneDataSource).
        # The dataset-specific format lacks a top-level `uid`, causing the
        # controller to silently drop the scene and never subscribe to cameras.
        rest_config = _to_rest_format(self._scene_config)
        # Ensure the MQTT topic uses the same uid the controller will announce.
        if self._scene_id == self._scene_config.get("name"):
            self._scene_id = rest_config["uid"]
        config_file = tmp_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(rest_config, f, indent=2)

        # --- Tracker ---
        tracker_name = f"mqtt_harness_tracker_{run_id}"
        tracker_ctr = docker.run(
            self._container_image,
            command=[
                "--data_source",        _CONTAINER_CONFIG,
                "--broker",             broker_name,
                "--tracker_config_file", _CONTAINER_TRACKER_CONFIG,
                "--rewriteAllTime",
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
        print(f"[MqttHarness] Tracker container started")
        # Allow tracker to connect to broker and load scene config.
        # Use a small fixed pause; readiness is not easily probed here.
        time.sleep(2.0)

        return broker_ctr, tracker_ctr

    def _stop_containers(self, broker_ctr, tracker_ctr) -> None:
        """Stop and remove broker and tracker containers."""
        for ctr in (tracker_ctr, broker_ctr):
            if ctr is None:
                continue
            try:
                ctr.stop(time=5)
                ctr.remove()
            except Exception as exc:
                print(f"[MqttHarness] Warning: container cleanup failed: {exc}")

    def _run_session(
        self, frames: List[Dict[str, Any]], host_port: int
    ) -> List[Dict[str, Any]]:
        """Publish input frames and collect tracker outputs.

        Paces publication using the inter-frame timestamp deltas so the
        tracker experiences a realistic frame cadence.

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
        client = mqtt.Client(client_id=f"mqtt_harness_client_{uuid.uuid4().hex[:6]}")

        def _on_message(_client, _userdata, message):
            try:
                payload = json.loads(message.payload.decode("utf-8"))
                with output_lock:
                    outputs.append(payload)
            except Exception as exc:
                print(f"[MqttHarness] Warning: failed to parse output message: {exc}")

        def _on_connect(_client, _userdata, _flags, rc):
            if rc == 0:
                client.subscribe(scene_topic)
                print(f"[MqttHarness] Subscribed to '{scene_topic}'")
            else:
                print(f"[MqttHarness] Warning: MQTT connect failed rc={rc}")

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
            client.publish(topic, json.dumps(frame))

        print(f"[MqttHarness] Published {len(frames)} frames, draining for {self._drain_timeout}s ...")
        time.sleep(self._drain_timeout)

        client.loop_stop()
        client.disconnect()

        print(f"[MqttHarness] Collected {len(outputs)} output messages")
        merged = _merge_outputs_by_timestamp(outputs)
        print(f"[MqttHarness] Merged into {len(merged)} timesteps")
        return merged

    def _persist_outputs(self, outputs: List[Dict], tmp_dir: Path) -> None:
        """Write output frames to the configured output folder."""
        if not self._output_folder:
            return
        out_file = tmp_dir / "outputs.json"
        with open(out_file, "w") as f:
            json.dump(outputs, f)
        shutil.copy(out_file, self._output_folder / "outputs.json")
