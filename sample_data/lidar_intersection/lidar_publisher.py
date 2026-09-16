#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LiDAR + camera dual-stream publisher for the LiDAR-intersection demo.

One gst-launch-1.0 process, two branches (LiDAR/PointPillars, camera/
person-vehicle-bike), each writing to its own FIFO; read here and published
to MQTT (scenescape/data/camera/<sensor_id>). Fusion happens downstream in
the Scene Controller.
"""

import atexit
import base64
import json
import math
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ── MQTT ──────────────────────────────────────────────────────────────────────
BROKER  = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"

# ── LiDAR pipeline config ──────────────────────────────────────────────────────
LIDAR_SENSOR_ID   = os.environ.get("LIDAR_SENSOR_ID", "intersection-lidar1")
LIDAR_DATA_PATH   = os.environ.get("LIDAR_DATA_PATH", "/home/pipeline-server/videos/lidar_intersection/velodyne_bin/%06d.bin")
LIDAR_START_INDEX = int(os.environ.get("LIDAR_START_INDEX", "010699"))
_LIDAR_STOP_RAW   = os.environ.get("LIDAR_STOP_INDEX")
# Default matches the shipped frame range (010699-010949).
LIDAR_STOP_INDEX  = int(_LIDAR_STOP_RAW.strip()) if _LIDAR_STOP_RAW and _LIDAR_STOP_RAW.strip() else 10949
LIDAR_LOOP        = os.environ.get("LIDAR_LOOP", "true").lower() not in ("0", "false", "no")
LIDAR_FRAME_RATE  = int(os.environ.get("LIDAR_FRAME_RATE", "10"))
LIDAR_SCORE_THRESHOLD = float(os.environ.get("LIDAR_SCORE_THRESHOLD", "0.7"))
LIDAR_MODEL_CONFIG = os.environ.get(
  "LIDAR_MODEL_CONFIG",
  "/home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json",
)

_LIDAR_DEVICE_RAW = os.environ.get("LIDAR_DEVICE", "GPU").strip().upper()
_ALLOWED_DEVICES = {
  "CPU", "GPU", "MYRIAD",
  "HETERO:CPU,GPU", "HETERO:GPU,CPU",
  "MULTI:CPU,GPU", "MULTI:GPU,CPU",
}
if _LIDAR_DEVICE_RAW not in _ALLOWED_DEVICES:
  raise ValueError(f"LIDAR_DEVICE={_LIDAR_DEVICE_RAW!r} not in allowed set {sorted(_ALLOWED_DEVICES)}")
LIDAR_DEVICE = _LIDAR_DEVICE_RAW

LIDAR_ADD_TENSOR_DATA = os.environ.get("LIDAR_ADD_TENSOR_DATA", "false").lower()
if LIDAR_ADD_TENSOR_DATA not in ("true", "false"):
  LIDAR_ADD_TENSOR_DATA = "false"

LIDAR_TOPIC       = f"scenescape/data/camera/{LIDAR_SENSOR_ID}"
LIDAR_FIFO        = "/tmp/lidar_detections.fifo"
LIDAR_PUBLISH_RAW = os.environ.get("LIDAR_PUBLISH_RAW", "false").lower() not in ("0", "false", "no")
LIDAR_RAW_TOPIC   = os.environ.get("LIDAR_RAW_TOPIC", f"scenescape/data/camera/{LIDAR_SENSOR_ID}-raw")

# KITTI class index -> label name (person omitted, camera branch covers it).
LIDAR_KITTI_LABELS: dict[int, str] = {1: "cyclist", 2: "vehicle"}

# ── Camera pipeline config ─────────────────────────────────────────────────────
CAM_SENSOR_ID   = os.environ.get("CAM_SENSOR_ID", "intersection-cam1")
CAM_DATA_PATH   = os.environ.get("CAM_DATA_PATH", "/home/pipeline-server/videos/lidar_intersection/images/%06d.jpg")
CAM_START_INDEX = int(os.environ.get("CAM_START_INDEX", str(LIDAR_START_INDEX)))
_CAM_STOP_RAW   = os.environ.get("CAM_STOP_INDEX")
CAM_STOP_INDEX  = int(_CAM_STOP_RAW.strip()) if _CAM_STOP_RAW and _CAM_STOP_RAW.strip() else LIDAR_STOP_INDEX
CAM_LOOP        = os.environ.get("CAM_LOOP", "true" if LIDAR_LOOP else "false").lower() not in ("0", "false", "no")
CAM_FRAME_RATE  = int(os.environ.get("CAM_FRAME_RATE", str(LIDAR_FRAME_RATE)))
CAM_DEVICE      = os.environ.get("CAM_DEVICE", "GPU").strip().upper()
CAM_SCORE_THRESHOLD = float(os.environ.get("CAM_SCORE_THRESHOLD", "0.8"))
CAM_MODEL = os.environ.get(
  "CAM_MODEL",
  "/home/pipeline-server/models/omz/person-vehicle-bike-detection-crossroad-1016"
  "/FP32/person-vehicle-bike-detection-crossroad-1016.xml",
)
CAM_MODEL_PROC = os.environ.get(
  "CAM_MODEL_PROC",
  "/home/pipeline-server/videos/lidar_intersection/model-proc"
  "/person-vehicle-bike-detection-crossroad-1016.json",
)
_CAM_LABELS_RAW      = os.environ.get("CAM_DETECTION_LABELS", "vehicle,cyclist")
CAM_DETECTION_LABELS = [label.strip() for label in _CAM_LABELS_RAW.split(",") if label.strip()]

CAM_TOPIC       = f"scenescape/data/camera/{CAM_SENSOR_ID}"
CAM_FIFO        = "/tmp/camera_detections.fifo"
CAM_PUBLISH_RAW = os.environ.get("CAM_PUBLISH_RAW", "false").lower() not in ("0", "false", "no")
CAM_RAW_TOPIC   = os.environ.get("CAM_RAW_TOPIC", f"scenescape/data/camera/{CAM_SENSOR_ID}-raw")


# GStreamer clock -> wall clock, anchored independently per stream.
def make_gst_to_wall():
  offset: "list[float | None]" = [None]

  def _gst_to_wall(gst_ns: int) -> float:
    gst_s = gst_ns / 1e9
    if offset[0] is None:
      offset[0] = time.time() - gst_s
    return gst_s + offset[0]

  return _gst_to_wall


# ── Coordinate transform (LiDAR only) ──────────────────────────────────────────

def lidar_to_scene_offset(x_l: float, y_l: float, z_l: float) -> "tuple[float, float, float]":
  """LiDAR (x,y,z) -> scene offset: (-y,-x) axis swap, z forced to 0."""
  return -y_l, -x_l, 0.0


def bbox3d_to_quaternion(yaw: float) -> "list[float]":
  """PointPillars yaw -> SceneScape quaternion (Z-yaw + 180deg X-flip so roof faces up)."""
  half = (-yaw - math.pi) / 2.0
  qz = math.sin(half)
  qw = math.cos(half)
  if qw < 0.0:
    qz, qw = -qz, -qw

  # Clamp <1 (exclusiveMaximum in schema); yaw=0 gives sin(-pi/2)=-1 exactly.
  _C = 1.0 - 1e-7
  return [max(-_C, min(_C, qw)), max(-_C, min(_C, -qz)), 0.0, 0.0]


# ── Message builders ────────────────────────────────────────────────────────────

def _make_timestamp(ts: float) -> str:
  dt = datetime.fromtimestamp(ts, tz=timezone.utc)
  ms = dt.microsecond // 1000
  return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def _resolve_lidar_label(obj: dict) -> "str | None":
  label = obj.get("label")
  if label and isinstance(label, str) and label.strip():
    label = label.strip()
    return label if label in ("vehicle", "cyclist") else None
  lid = obj.get("label_id")
  if lid is not None:
    try:
      return LIDAR_KITTI_LABELS.get(int(lid))
    except (ValueError, TypeError):
      return None
  return None


def build_lidar_message(raw: dict, gst_to_wall, fps: float) -> dict:
  """Wrap PointPillars 3-D detections in SceneScape camera-detection format."""
  gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
  ts = _make_timestamp(gst_to_wall(int(gst_ns)) if gst_ns is not None else time.time())

  objects: dict = {}
  for i, obj in enumerate(raw.get("objects", [])):
    bbox = obj.get("bbox_3d")
    if not isinstance(bbox, dict) or "yaw" not in bbox:
      continue
    label = _resolve_lidar_label(obj)
    if label is None:
      continue
    try:
      sx, sy, sz = lidar_to_scene_offset(
        bbox.get("x", 0.0), bbox.get("y", 0.0), bbox.get("z", 0.0)
      )
      objects.setdefault(label, []).append({
        "id":          i + 1,
        "category":    label,
        "confidence":  obj.get("confidence", 0.0),
        "translation": [sx, sy, sz],
        "size":        [bbox.get("l", 0.0), bbox.get("w", 0.0), bbox.get("h", 0.0)],
        "rotation":    bbox3d_to_quaternion(float(bbox["yaw"])),
        # Lets the UI show which sensor produced this detection.
        "source":      "lidar",
      })
    except (TypeError, ValueError):
      continue

  return {"id": LIDAR_SENSOR_ID, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


def build_camera_message(raw: dict, gst_to_wall, fps: float) -> dict:
  """Wrap gvametaconvert 2-D detections in SceneScape camera-detection format."""
  ts = _make_timestamp(time.time())

  objects: dict = {}
  for i, item in enumerate(raw.get("objects", [])):
    detection = item.get("detection")
    if not isinstance(detection, dict) or "confidence" not in detection:
      continue
    label = detection.get("label") or str(detection.get("label_id", ""))
    label = label.strip()
    if CAM_DETECTION_LABELS and label not in CAM_DETECTION_LABELS:
      continue
    try:
      objects.setdefault(label, []).append({
        "id":              i + 1,
        "category":        label,
        "confidence":      detection["confidence"],
        "bounding_box_px": {
          "x":      item["x"],
          "y":      item["y"],
          "width":  item["w"],
          "height": item["h"],
        },
        "source":          "camera",
      })
    except (KeyError, TypeError):
      continue

  return {"id": CAM_SENSOR_ID, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


# ── MQTT helpers ───────────────────────────────────────────────────────────────

class _MqttState:
  """Tracks active clients so atexit always disconnects every stream's client."""

  def __init__(self) -> None:
    self.clients: "list[mqtt.Client]" = []

  def add(self, client: mqtt.Client) -> None:
    self.clients.append(client)

  def shutdown(self) -> None:
    for client in self.clients:
      try:
        client.loop_stop()
        client.disconnect()
      except Exception:
        pass
    self.clients = []


_mqtt_state = _MqttState()


def connect_mqtt(client_prefix: str, on_connect_setup=None) -> mqtt.Client:
  """Connect and, on every (re)connect, re-run on_connect_setup (subscriptions/on_message)."""
  client = mqtt.Client(client_id=f"{client_prefix}-{uuid.uuid4().hex[:8]}")
  if os.path.exists(ROOT_CA):
    client.tls_set(ca_certs=ROOT_CA)
  for attempt in range(10):
    try:
      client.connect(BROKER, PORT, keepalive=60)
      client.loop_start()
      print(f"[{client_prefix}] Connected to {BROKER}:{PORT}", flush=True)
      if on_connect_setup is not None:
        on_connect_setup(client)
      _mqtt_state.add(client)
      return client
    except Exception as exc:
      print(f"[{client_prefix}] Connect attempt {attempt + 1}/10 failed: {exc}", flush=True)
      time.sleep(2)
  raise RuntimeError(f"[{client_prefix}] Could not connect to MQTT broker after 10 attempts")


def safe_publish(
  client: mqtt.Client, client_prefix: str, topic: str, payload: str, on_connect_setup=None,
) -> mqtt.Client:
  result = client.publish(topic, payload, qos=0)
  if result.rc != mqtt.MQTT_ERR_SUCCESS:
    print(f"[{client_prefix}] Publish failed rc={result.rc}, reconnecting...", flush=True)
    try:
      client.loop_stop()
      client.disconnect()
    except Exception:
      pass
    # New client on reconnect loses prior subscriptions/on_message, so replay them.
    client = connect_mqtt(client_prefix, on_connect_setup=on_connect_setup)
    client.publish(topic, payload, qos=0)
  return client


def _read_frame_as_jpeg_b64(path: str) -> "str | None":
  """Read a frame file and base64 it as-is (already JPEG, no re-encode)."""
  try:
    with open(path, "rb") as f:
      return base64.b64encode(f.read()).decode("ascii")
  except Exception as exc:
    print(f"[camera-publisher] Failed to read preview frame {path}: {exc}", flush=True)
    return None


def setup_getimage_responder(
  client: mqtt.Client, sensor_id: str, data_path: str, frame_index_cell: list, start_index: int,
) -> None:
  """Answer the Manager UI's "getimage" command with the latest frame."""
  image_topic = f"scenescape/image/camera/{sensor_id}"

  def _on_message(msg_client, _userdata, message):
    if message.payload.decode("utf-8", errors="replace").strip() != "getimage":
      return
    idx = frame_index_cell[0]
    if idx is None:
      return
    b64 = _read_frame_as_jpeg_b64(data_path % idx) or _read_frame_as_jpeg_b64(data_path % start_index)
    if b64 is not None:
      msg_client.publish(image_topic, json.dumps({"image": b64}), qos=0)

  client.subscribe(f"scenescape/cmd/camera/{sensor_id}")
  client.on_message = _on_message


# ── FIFO helpers ───────────────────────────────────────────────────────────────

def _make_fifo(path: str) -> None:
  if os.path.exists(path):
    os.remove(path)
  os.mkfifo(path)


def _open_fifo_background(path: str, result: list) -> threading.Thread:
  def _worker():
    result[0] = open(path, "r")
  t = threading.Thread(target=_worker, daemon=True, name=f"fifo-opener-{os.path.basename(path)}")
  t.start()
  return t


# ── Stream runner (shared by both LiDAR and camera branches) ──────────────────

# Both branches replay the same recorded clip but are paced independently (the
# camera by gvafpsthrottle, the LiDAR by inference throughput), so without
# coupling they drift apart without bound. These shared counters plus a
# Condition let each reader back-pressure its own FIFO whenever it gets more
# than LAG_TOLERANCE frames ahead of the sibling, keeping the two aligned in
# either direction (and holding the camera back until LiDAR's first frame).
_lidar_ready = threading.Event()
_stream_frame_counts: "dict[str, int]" = {"lidar-publisher": 0, "camera-publisher": 0}
_stream_finished: "dict[str, bool]" = {"lidar-publisher": False, "camera-publisher": False}
_stream_counts_cond = threading.Condition()

# Max frames one branch may run ahead of the other before it is paced back.
LAG_TOLERANCE = max(1, int(os.environ.get("LIDAR_CAM_LAG_TOLERANCE", "2")))


def _sibling(name: str) -> str:
  return "camera-publisher" if name == "lidar-publisher" else "lidar-publisher"


def _mark_stream_finished(name: str) -> None:
  """Release a sibling that may be waiting on this (now-stopped) stream."""
  with _stream_counts_cond:
    _stream_finished[name] = True
    _stream_counts_cond.notify_all()


def _record_frame(name: str, published: int) -> None:
  with _stream_counts_cond:
    _stream_frame_counts[name] = published
    _stream_counts_cond.notify_all()


def _wait_for_pace(name: str, published: int, proc: subprocess.Popen) -> bool:
  """Block while this stream is >=LAG_TOLERANCE frames ahead of its sibling.

  Not reading the FIFO fills the pipe, back-pressuring this branch's GStreamer
  chain so it physically slows to the sibling's rate. Returns False if the
  pipeline exited while waiting so the caller stops.
  """
  other = _sibling(name)
  with _stream_counts_cond:
    while True:
      # Camera also holds until LiDAR's first frame (GPU model-load skew).
      startup_hold = (name == "camera-publisher") and not _lidar_ready.is_set()
      if _stream_finished.get(other, False):
        return True  # sibling gone: don't stall waiting for it to advance
      ahead = published - _stream_frame_counts.get(other, 0)
      if not startup_hold and ahead < LAG_TOLERANCE:
        return True
      if proc.poll() is not None:
        return False
      _stream_counts_cond.wait(timeout=0.5)


def run_stream(
  name: str,
  proc: subprocess.Popen,
  fifo_path: str,
  topic: str,
  publish_raw: bool,
  raw_topic: str,
  frame_rate: float,
  build_message,
  image_preview: "dict | None" = None,
  is_lidar: bool = False,
) -> None:
  """Read `proc`'s FIFO and publish detections to MQTT until it exits."""
  fifo_result: list = [None]
  fifo_thread = _open_fifo_background(fifo_path, fifo_result)

  gst_to_wall = make_gst_to_wall()

  frame_index_cell = [None]
  resubscribe = None
  if image_preview is not None:
    def resubscribe(c: mqtt.Client) -> None:
      setup_getimage_responder(
        c, image_preview["sensor_id"], image_preview["data_path"], frame_index_cell,
        image_preview["start_index"],
      )

  client = connect_mqtt(name, on_connect_setup=resubscribe)

  fifo_thread.join(timeout=30.0)
  if fifo_result[0] is None:
    raise RuntimeError(f"[{name}] FIFO not opened within 30s - pipeline likely failed to start")

  published = 0
  fps = float(frame_rate)
  last_ts: "float | None" = None

  with fifo_result[0] as fifo:
    for line in fifo:
      rc = proc.poll()
      if rc is not None and rc != 0:
        raise RuntimeError(f"[{name}] GStreamer pipeline exited with code {rc}")

      line = line.strip()
      if not line:
        continue

      # Back-pressure this FIFO if we are running ahead of the sibling stream.
      if not _wait_for_pace(name, published, proc):
        break

      try:
        raw = json.loads(line)
      except json.JSONDecodeError as exc:
        print(f"[{name}] JSON error frame={published}: {exc}", flush=True)
        continue

      if is_lidar and not _lidar_ready.is_set():
        _lidar_ready.set()
        with _stream_counts_cond:
          _stream_counts_cond.notify_all()
        print(f"[{name}] first LiDAR frame processed - releasing camera stream", flush=True)

      gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
      now = gst_to_wall(int(gst_ns)) if gst_ns is not None else time.time()
      if last_ts is not None:
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_ts, 0.001))
      last_ts = now

      msg = build_message(raw, gst_to_wall, fps)

      if sum(len(v) for v in msg["objects"].values()) > 0:
        client = safe_publish(client, name, topic, json.dumps(msg), on_connect_setup=resubscribe)
      if publish_raw:
        client = safe_publish(client, name, raw_topic, line, on_connect_setup=resubscribe)

      if image_preview is not None:
        start = image_preview["start_index"]
        stop = image_preview["stop_index"]
        span = (stop - start + 1) if (stop is not None and image_preview["loop"]) else None
        frame_index_cell[0] = start + (published % span if span else published)

      published += 1
      _record_frame(name, published)

      if published % 100 == 0:
        counts = {k: len(v) for k, v in msg["objects"].items()}
        if is_lidar:
          # With the pace gate the lag stays bounded (|lag| <= LAG_TOLERANCE).
          with _stream_counts_cond:
            cam_count = _stream_frame_counts.get("camera-publisher", 0)
          lag = published - cam_count
          print(
            f"[{name}] frames={published} fps={fps:.1f} objects={counts}"
            f" cam={cam_count} (lag={lag})",
            flush=True,
          )
        else:
          print(f"[{name}] frames={published} fps={fps:.1f} objects={counts}", flush=True)

  print(f"[{name}] Done - published {published} frames", flush=True)


# ── Pipeline builders ──────────────────────────────────────────────────────────

def _lidar_chain_parts() -> list:
  parts = [
    f"multifilesrc location={shlex.quote(LIDAR_DATA_PATH)} start-index={LIDAR_START_INDEX}",
  ]
  if LIDAR_STOP_INDEX is not None:
    parts.append(f"stop-index={LIDAR_STOP_INDEX}")
  if LIDAR_LOOP:
    parts.append("loop=true")
  parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={LIDAR_FRAME_RATE}",
    f"! g3dinference config={shlex.quote(LIDAR_MODEL_CONFIG)}"
    f" device={shlex.quote(LIDAR_DEVICE)}"
    f" score-threshold={LIDAR_SCORE_THRESHOLD}",
    f"! gvametaconvert add-tensor-data={LIDAR_ADD_TENSOR_DATA} format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(LIDAR_FIFO)}",
    "! fakesink sync=false",
  ]
  return parts


def _camera_chain_parts() -> list:
  parts = [
    f"multifilesrc location={shlex.quote(CAM_DATA_PATH)} start-index={CAM_START_INDEX}",
  ]
  if CAM_STOP_INDEX is not None:
    parts.append(f"stop-index={CAM_STOP_INDEX}")
  if CAM_LOOP:
    parts.append("loop=true")
  parts += [
    "caps=image/jpeg",
    "! jpegdec",
    "! videoconvert",
    "! video/x-raw,format=BGR",
    f"! gvafpsthrottle target-fps={CAM_FRAME_RATE}",
    f"! gvadetect model={shlex.quote(CAM_MODEL)}"
    f" model-proc={shlex.quote(CAM_MODEL_PROC)}"
    f" device={shlex.quote(CAM_DEVICE)}"
    f" threshold={CAM_SCORE_THRESHOLD}",
    "! gvametaconvert add-tensor-data=false format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(CAM_FIFO)}",
    "! fakesink sync=false",
  ]
  return parts


def _build_combined_pipeline() -> str:
  """Both chains as independent branches inside one gst-launch-1.0 invocation."""
  return " ".join(["gst-launch-1.0"] + _camera_chain_parts() + _lidar_chain_parts())


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
  print(
    f"[lidar-publisher] lidar_sensor={LIDAR_SENSOR_ID} cam_sensor={CAM_SENSOR_ID} "
    f"broker={BROKER}:{PORT} lidar_topic={LIDAR_TOPIC} cam_topic={CAM_TOPIC} "
    f"lidar_device={LIDAR_DEVICE} cam_device={CAM_DEVICE}",
    flush=True,
  )

  _make_fifo(CAM_FIFO)
  _make_fifo(LIDAR_FIFO)

  pipeline_cmd = _build_combined_pipeline()
  print(f"[lidar-publisher] Starting combined pipeline: {pipeline_cmd}", flush=True)
  proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr)
  print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

  @atexit.register
  def _cleanup():
    if proc.poll() is None:
      proc.terminate()
      try:
        proc.wait(timeout=5)
      except subprocess.TimeoutExpired:
        proc.kill()
    for path in (CAM_FIFO, LIDAR_FIFO):
      try:
        os.remove(path)
      except FileNotFoundError:
        pass

  errors: list = []

  def _run_and_capture(name, fifo_path, topic, publish_raw, raw_topic, frame_rate, build_message, image_preview=None, is_lidar=False):
    try:
      run_stream(name, proc, fifo_path, topic, publish_raw, raw_topic, frame_rate, build_message, image_preview, is_lidar=is_lidar)
    except Exception as exc:  # noqa: BLE001 - surface stream failure without killing the sibling stream
      print(f"[{name}] FATAL: {exc}", flush=True)
      errors.append(exc)
    finally:
      # Unblock a sibling that may be waiting on this stream's pace gate.
      _mark_stream_finished(name)

  camera_thread = threading.Thread(
    target=_run_and_capture,
    args=("camera-publisher", CAM_FIFO, CAM_TOPIC, CAM_PUBLISH_RAW, CAM_RAW_TOPIC, CAM_FRAME_RATE, build_camera_message),
    kwargs={
      "image_preview": {
        "sensor_id": CAM_SENSOR_ID,
        "data_path": CAM_DATA_PATH,
        "start_index": CAM_START_INDEX,
        "stop_index": CAM_STOP_INDEX,
        "loop": CAM_LOOP,
      },
    },
    daemon=True,
  )
  camera_thread.start()

  _run_and_capture(
    "lidar-publisher", LIDAR_FIFO, LIDAR_TOPIC, LIDAR_PUBLISH_RAW, LIDAR_RAW_TOPIC, LIDAR_FRAME_RATE, build_lidar_message,
    is_lidar=True,
  )

  camera_thread.join()
  _mqtt_state.shutdown()

  try:
    proc.wait(timeout=10)
  except subprocess.TimeoutExpired:
    proc.terminate()

  if errors:
    sys.exit(1)


if __name__ == "__main__":
  main()
