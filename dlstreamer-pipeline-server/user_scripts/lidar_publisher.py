#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Publishes PointPillars detections in SceneScape camera detection format.

LiDAR-to-scene coordinate transform: (-y, -x, z) axis swap.
The SceneScape controller adds the camera pose translation to get the
final world position.

Optional raw output: set LIDAR_PUBLISH_RAW=true to mirror each raw
gvametaconvert JSON line to LIDAR_RAW_TOPIC as well.
"""

import atexit
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

# ── LiDAR pipeline ────────────────────────────────────────────────────────────
SENSOR_ID       = os.environ.get("LIDAR_SENSOR_ID", "lidar1")
DATA_PATH       = os.environ.get("LIDAR_DATA_PATH", "/home/pipeline-server/videos/velodyne_bin/%06d.bin")
START_INDEX     = int(os.environ.get("LIDAR_START_INDEX", "010699"))
_STOP_RAW       = os.environ.get("LIDAR_STOP_INDEX")
STOP_INDEX      = int(_STOP_RAW.strip()) if _STOP_RAW and _STOP_RAW.strip() else None
LOOP            = os.environ.get("LIDAR_LOOP", "true").lower() not in ("0", "false", "no")
FRAME_RATE      = int(os.environ.get("LIDAR_FRAME_RATE", "10"))
SCORE_THRESHOLD = float(os.environ.get("LIDAR_SCORE_THRESHOLD", "0.65"))
MODEL_CONFIG    = os.environ.get(
  "LIDAR_MODEL_CONFIG",
  "/home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json",
)

_DEVICE_RAW    = os.environ.get("LIDAR_DEVICE", "CPU").strip().upper()
_ALLOWED_DEVICES = {
  "CPU", "GPU", "MYRIAD",
  "HETERO:CPU,GPU", "HETERO:GPU,CPU",
  "MULTI:CPU,GPU", "MULTI:GPU,CPU",
}
if _DEVICE_RAW not in _ALLOWED_DEVICES:
  raise ValueError(f"LIDAR_DEVICE={_DEVICE_RAW!r} not in allowed set {sorted(_ALLOWED_DEVICES)}")
DEVICE = _DEVICE_RAW

ADD_TENSOR_DATA = os.environ.get("LIDAR_ADD_TENSOR_DATA", "false").lower()
if ADD_TENSOR_DATA not in ("true", "false"):
  ADD_TENSOR_DATA = "false"

CAMERA_TOPIC = f"scenescape/data/camera/{SENSOR_ID}"
FIFO         = "/tmp/lidar_detections.fifo"

# Optional: mirror raw gvametaconvert output to a second topic.
PUBLISH_RAW = os.environ.get("LIDAR_PUBLISH_RAW", "false").lower() not in ("0", "false", "no")
RAW_TOPIC   = os.environ.get("LIDAR_RAW_TOPIC", f"scenescape/data/camera/{SENSOR_ID}-raw")

# KITTI class index → label name (matches OpenVINO PointPillars training order).
KITTI_LABELS: dict[int, str] = {0: "Pedestrian", 1: "Cyclist", 2: "Car"}

# GStreamer monotonic clock → wall-clock offset, anchored on first frame.
_gst_wall_offset: "float | None" = None


def _gst_to_wall(gst_ns: int) -> float:
  global _gst_wall_offset
  gst_s = gst_ns / 1e9
  if _gst_wall_offset is None:
    _gst_wall_offset = time.time() - gst_s
  return gst_s + _gst_wall_offset


# ── Coordinate transform ───────────────────────────────────────────────────────

def lidar_to_scene_offset(x_l: float, y_l: float, z_l: float) -> "tuple[float, float, float]":
  """Map LiDAR coordinates to scene-frame offset via (-y, -x) axis swap.
  Z is forced to 0 to keep objects on the ground plane, since the SceneScape
  controller adds the camera pose translation to get the final world position.
  """
  return -y_l, -x_l, 0.0


def bbox3d_to_quaternion(theta: float) -> "list[float]":
  """
  Convert PointPillars yaw to SceneScape quaternion [qx, qy, qz, qw].

  Two rotations combined:
    1. Z-axis yaw from theta:  q_yaw   = [0,    0,   qz, qw]
    2. X-axis 180 deg flip:    q_flip  = [1,    0,    0,  0]

  Hamilton product q_flip * q_yaw:
    q_combined = [qw_yaw, -qz_yaw, 0, 0]

  This keeps the object XY position unchanged while
  flipping the render orientation so roof faces up.
  """
  half = (-theta - math.pi) / 2.0
  qz = math.sin(half)
  qw = math.cos(half)
  if qw < 0.0:
    qz, qw = -qz, -qw

  # Apply 180 deg X-axis flip: q_flip=[1,0,0,0] * q_yaw=[0,0,qz,qw]
  return [qw, -qz, 0.0, 0.0]


# ── Message builder ────────────────────────────────────────────────────────────

def _resolve_label(obj: dict) -> str:
  label = obj.get("label")
  if label and isinstance(label, str) and label.strip():
    return label.strip()
  lid = obj.get("label_id")
  if lid is not None:
    try:
      return KITTI_LABELS.get(int(lid), f"unknown_{int(lid)}")
    except (ValueError, TypeError):
      pass
  return "object"


def _make_timestamp(ts: float) -> str:
  dt = datetime.fromtimestamp(ts, tz=timezone.utc)
  ms = dt.microsecond // 1000
  return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def build_camera_message(raw: dict, sensor_id: str, fps: float) -> dict:
  """Wrap PointPillars detections in SceneScape camera detection format."""
  gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
  ts = _make_timestamp(_gst_to_wall(int(gst_ns)) if gst_ns is not None else time.time())

  objects: dict = {}
  for i, obj in enumerate(raw.get("objects", [])):
    bbox = obj.get("bbox_3d")
    if not isinstance(bbox, dict):
      continue
    try:
      label = _resolve_label(obj)
      sx, sy, sz = lidar_to_scene_offset(
        bbox.get("x", 0.0), bbox.get("y", 0.0), bbox.get("z", 0.0)
      )
      objects.setdefault(label, []).append({
        "id":      i + 1,
        "category":  label,
        "confidence":  obj.get("confidence", 0.0),
        "translation": [sx, sy, sz],
        "size":    [bbox.get("l", 0.0), bbox.get("w", 0.0), bbox.get("h", 0.0)],
        "rotation":  bbox3d_to_quaternion(bbox.get("theta", 0.0)),
      })
    except (KeyError, TypeError, ValueError):
      continue

  return {"id": sensor_id, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


# ── MQTT helpers ───────────────────────────────────────────────────────────────

class _MqttState:
  """Tracks the active client so atexit always disconnects the right instance."""

  def __init__(self) -> None:
    self.client = None

  def set(self, client: mqtt.Client) -> None:
    self.client = client

  def shutdown(self) -> None:
    if self.client:
      try:
        self.client.loop_stop()
        self.client.disconnect()
      except Exception:
        pass
      self.client = None


_mqtt_state = _MqttState()


def connect_mqtt() -> mqtt.Client:
  client = mqtt.Client(client_id=f"lidar-publisher-{uuid.uuid4().hex[:8]}")
  if os.path.exists(ROOT_CA):
    client.tls_set(ca_certs=ROOT_CA)
  for attempt in range(10):
    try:
      client.connect(BROKER, PORT, keepalive=60)
      client.loop_start()
      print(f"[lidar-publisher] Connected to {BROKER}:{PORT}", flush=True)
      _mqtt_state.set(client)
      return client
    except Exception as exc:
      print(f"[lidar-publisher] Connect attempt {attempt + 1}/10 failed: {exc}", flush=True)
      time.sleep(2)
  raise RuntimeError("Could not connect to MQTT broker after 10 attempts")


def safe_publish(client: mqtt.Client, topic: str, payload: str) -> mqtt.Client:
  result = client.publish(topic, payload, qos=0)
  if result.rc != mqtt.MQTT_ERR_SUCCESS:
    print(f"[lidar-publisher] Publish failed rc={result.rc}, reconnecting...", flush=True)
    try:
      client.loop_stop()
      client.disconnect()
    except Exception:
      pass
    client = connect_mqtt()
    client.publish(topic, payload, qos=0)
  return client


# ── GStreamer pipeline ─────────────────────────────────────────────────────────

def _build_pipeline() -> str:
  parts = [
    "gst-launch-1.0",
    f"multifilesrc location={shlex.quote(DATA_PATH)} start-index={START_INDEX}",
  ]
  if STOP_INDEX is not None:
    parts.append(f"stop-index={STOP_INDEX}")
  if LOOP:
    parts.append("loop=true")
  parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={FRAME_RATE}",
    f"! g3dinference config={shlex.quote(MODEL_CONFIG)}"
    f" device={shlex.quote(DEVICE)}"
    f" score-threshold={SCORE_THRESHOLD}",
    f"! gvametaconvert add-tensor-data={ADD_TENSOR_DATA} format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(FIFO)}",
    "! fakesink",
  ]
  return " ".join(parts)


# ── FIFO ───────────────────────────────────────────────────────────────────────

def _make_fifo() -> None:
  if os.path.exists(FIFO):
    os.remove(FIFO)
  os.mkfifo(FIFO)


def _open_fifo_background(result: list) -> threading.Thread:
  def _worker():
    result[0] = open(FIFO, "r")
  t = threading.Thread(target=_worker, daemon=True, name="fifo-opener")
  t.start()
  return t


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
  print(
    f"[lidar-publisher] sensor={SENSOR_ID} broker={BROKER}:{PORT} "
    f"topic={CAMERA_TOPIC} device={DEVICE} fps={FRAME_RATE} "
    f"score_threshold={SCORE_THRESHOLD} publish_raw={PUBLISH_RAW}",
    flush=True,
  )

  _make_fifo()

  pipeline_cmd = _build_pipeline()
  proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr)
  print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

  fifo_result: list = [None]
  fifo_thread = _open_fifo_background(fifo_result)

  client = connect_mqtt()

  @atexit.register
  def _cleanup():
    if proc.poll() is None:
      proc.terminate()
      try:
        proc.wait(timeout=5)
      except subprocess.TimeoutExpired:
        proc.kill()
    try:
      os.remove(FIFO)
    except FileNotFoundError:
      pass
    _mqtt_state.shutdown()

  fifo_thread.join(timeout=30.0)
  if fifo_result[0] is None:
    raise RuntimeError("FIFO not opened within 30 s — pipeline likely failed to start")

  published = 0
  fps     = float(FRAME_RATE)
  last_ts: "float | None" = None

  with fifo_result[0] as fifo:
    for line in fifo:
      rc = proc.poll()
      if rc is not None and rc != 0:
        raise RuntimeError(f"GStreamer pipeline exited with code {rc}")

      line = line.strip()
      if not line:
        continue

      try:
        raw = json.loads(line)
      except json.JSONDecodeError as exc:
        print(f"[lidar-publisher] JSON error frame={published}: {exc}", flush=True)
        continue

      gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
      now = _gst_to_wall(int(gst_ns)) if gst_ns is not None else time.time()
      if last_ts is not None:
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_ts, 0.001))
      last_ts = now

      msg = build_camera_message(raw, SENSOR_ID, fps)

      if sum(len(v) for v in msg["objects"].values()) > 0:
        client = safe_publish(client, CAMERA_TOPIC, json.dumps(msg))
      if PUBLISH_RAW:
        client = safe_publish(client, RAW_TOPIC, line)

      published += 1
      if published % 100 == 0:
        counts = {k: len(v) for k, v in msg["objects"].items()}
        print(
          f"[lidar-publisher] frames={published} fps={fps:.1f} objects={counts}",
          flush=True,
        )

  print(f"[lidar-publisher] Done — published {published} frames", flush=True)
  try:
    proc.wait(timeout=10)
  except subprocess.TimeoutExpired:
    proc.terminate()


if __name__ == "__main__":
  main()
