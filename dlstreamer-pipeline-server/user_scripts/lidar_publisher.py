#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Dual-stream pipeline: LiDAR (PointPillars) + Camera (person-vehicle-bike detection).

Two parallel GStreamer branches are merged via gvametaaggregate for per-frame
synchronisation.  The combined JSON is published on two separate MQTT topics:
  - scenescape/data/camera/<LIDAR_SENSOR_ID>  (3-D LiDAR detections)
  - scenescape/data/camera/<CAM_SENSOR_ID>    (2-D camera detections)

LiDAR-to-scene coordinate transform: (-y, -x, z) axis swap.
Optional raw mirror: set LIDAR_PUBLISH_RAW=true.
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
SCORE_THRESHOLD = float(os.environ.get("LIDAR_SCORE_THRESHOLD", "0.7"))
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

# ── Camera pipeline ────────────────────────────────────────────────────────────
CAM_SENSOR_ID   = os.environ.get("CAM_SENSOR_ID", "intersection-cam1")
CAM_DATA_PATH   = os.environ.get("CAM_DATA_PATH",
                    "/home/pipeline-server/videos/images/%06d.jpg")
CAM_START_INDEX = int(os.environ.get("CAM_START_INDEX", str(START_INDEX)))
_CAM_STOP_RAW   = os.environ.get("CAM_STOP_INDEX")
CAM_STOP_INDEX  = (int(_CAM_STOP_RAW.strip()) if _CAM_STOP_RAW and _CAM_STOP_RAW.strip()
                   else (STOP_INDEX if STOP_INDEX is not None else 10949))
CAM_DEVICE      = os.environ.get("CAM_DEVICE", "CPU").strip().upper()
CAM_SCORE_THRESHOLD = float(os.environ.get("CAM_SCORE_THRESHOLD", "0.3"))
CAM_MODEL       = os.environ.get(
    "CAM_MODEL",
    "/home/pipeline-server/models/intel/person-vehicle-bike-detection-crossroad-1016"
    "/FP32/person-vehicle-bike-detection-crossroad-1016.xml",
)
CAM_MODEL_PROC  = os.environ.get(
    "CAM_MODEL_PROC",
    "/home/pipeline-server/models/object_detection/person-vehicle"
    "/person-vehicle-bike-detection-crossroad-1016.json",
)
_CAM_LABELS_RAW       = os.environ.get("CAM_DETECTION_LABELS", "vehicle,person")
CAM_DETECTION_LABELS  = [l.strip() for l in _CAM_LABELS_RAW.split(",") if l.strip()]
SSCAPE_ADAPTER        = os.environ.get(
    "SSCAPE_ADAPTER",
    "/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py",
)
CAM_TOPIC = f"scenescape/data/camera/{CAM_SENSOR_ID}"

# KITTI class index → label name, normalised to match camera model output labels.
KITTI_LABELS: dict[int, str] = {0: "person", 1: "cyclist", 2: "vehicle"}

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


def build_lidar_message(raw: dict, sensor_id: str, fps: float) -> dict:
  """Wrap PointPillars 3-D detections in SceneScape camera detection format."""
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
        "id":         i + 1,
        "category":   label,
        "confidence": obj.get("confidence", 0.0),
        "translation": [sx, sy, sz],
        "size":       [bbox.get("l", 0.0), bbox.get("w", 0.0), bbox.get("h", 0.0)],
        "rotation":   bbox3d_to_quaternion(bbox.get("theta", 0.0)),
      })
    except (KeyError, TypeError, ValueError):
      continue

  return {"id": sensor_id, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


def build_cam_message(raw: dict, sensor_id: str, fps: float) -> dict:
  """Wrap 2-D camera detections (from gvadetect) in SceneScape detection format."""
  # PostDecodeTimestampCapture writes 'postdecode_timestamp' as a GVA message
  # that gvametapublish serialises to the top-level JSON.  Fall back to
  # the LiDAR wall-clock anchor when the camera message is absent.
  ts_raw = raw.get("postdecode_timestamp")
  if ts_raw:
    ts = ts_raw
  else:
    gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
    ts = _make_timestamp(_gst_to_wall(int(gst_ns)) if gst_ns is not None else time.time())

  objects: dict = {}
  for i, obj in enumerate(raw.get("objects", [])):
    det = obj.get("detection")
    if not isinstance(det, dict) or "confidence" not in det:
      continue  # skip LiDAR objects (no 'detection' key)
    label = det.get("label") or str(det.get("label_id", "unknown"))
    if CAM_DETECTION_LABELS and label not in CAM_DETECTION_LABELS:
      continue
    objects.setdefault(label, []).append({
      "id":             i + 1,
      "category":       label,
      "confidence":     det["confidence"],
      "bounding_box_px": {
        "x":      obj.get("x", 0),
        "y":      obj.get("y", 0),
        "width":  obj.get("w", 0),
        "height": obj.get("h", 0),
      },
    })

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
  # ── Camera branch ──────────────────────────────────────────────────────────
  # gvafpsthrottle caps throughput to FRAME_RATE regardless of inference time,
  # keeping the camera branch in step with g3dlidarparse frame-rate=FRAME_RATE.
  # PostInferenceDataPublish publishes detections directly to MQTT (proven path
  # used by retail/queuing pipelines); no FIFO needed for the camera branch.
  cam_kwarg = json.dumps({
    "cameraid":           CAM_SENSOR_ID,
    "metadatagenpolicy":  "detectionPolicy",
    "detection_labels":   CAM_DETECTION_LABELS,
  })
  cam = " ".join([
    "multifilesrc",
    f"location={shlex.quote(CAM_DATA_PATH)}",
    f"start-index={CAM_START_INDEX}",
    f"stop-index={CAM_STOP_INDEX}",
    "loop=true",
    "caps=image/jpeg",
    "! jpegdec",
    "! videoconvert",
    "! video/x-raw,format=BGR",
    f"! gvafpsthrottle target-fps={FRAME_RATE}",
    f"! gvapython class=PostDecodeTimestampCapture function=processFrame"
    f" module={shlex.quote(SSCAPE_ADAPTER)} name=timesync",
    f"! gvadetect model={shlex.quote(CAM_MODEL)}"
    f" model-proc={shlex.quote(CAM_MODEL_PROC)}"
    f" device={shlex.quote(CAM_DEVICE)}"
    f" threshold={CAM_SCORE_THRESHOLD}",
    "! gvametaconvert add-tensor-data=false name=metaconvert",
    f"! gvapython class=PostInferenceDataPublish function=processFrame"
    f" module={shlex.quote(SSCAPE_ADAPTER)} name=datapublisher"
    f" kwarg={shlex.quote(cam_kwarg)}",
    "! fakesink sync=false",
  ])

  # ── LiDAR branch ──────────────────────────────────────────────────────────
  # gvametaaggregate is NOT used: it requires GST_FORMAT_TIME on all pads but
  # g3dlidarparse produces application/x-lidar (GST_FORMAT_BYTES).  Both
  # branches run in the same gst-launch-1.0 process and publish independently
  # via their own FIFOs; Python reads them in parallel threads.
  lidar_parts = [
    "multifilesrc",
    f"location={shlex.quote(DATA_PATH)}",
    f"start-index={START_INDEX}",
  ]
  if STOP_INDEX is not None:
    lidar_parts.append(f"stop-index={STOP_INDEX}")
  if LOOP:
    lidar_parts.append("loop=true")
  lidar_parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={FRAME_RATE}",
    f"! g3dinference config={shlex.quote(MODEL_CONFIG)}"
    f" device={shlex.quote(DEVICE)}"
    f" score-threshold={SCORE_THRESHOLD}",
    f"! gvametaconvert add-tensor-data={ADD_TENSOR_DATA} format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(FIFO)}",
    "! fakesink sync=false",
  ]
  lidar = " ".join(lidar_parts)

  return f"gst-launch-1.0 {cam} {lidar}"


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
    f"[lidar-publisher] lidar_sensor={SENSOR_ID} cam_sensor={CAM_SENSOR_ID} "
    f"broker={BROKER}:{PORT} "
    f"lidar_topic={CAMERA_TOPIC} cam_topic={CAM_TOPIC} "
    f"lidar_device={DEVICE} cam_device={CAM_DEVICE} fps={FRAME_RATE} "
    f"score_threshold={SCORE_THRESHOLD} cam_score_threshold={CAM_SCORE_THRESHOLD} "
    f"publish_raw={PUBLISH_RAW}",
    flush=True,
  )

  _make_fifo()

  pipeline_cmd = _build_pipeline()
  proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr)
  print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

  fifo_result: list = [None]
  fifo_thread = _open_fifo_background(fifo_result)

  client = connect_mqtt()

  # Subscribe to CAM_TOPIC so the main process can log what PostInferenceDataPublish
  # publishes from inside the GStreamer pipeline.
  _cam_rx_count = [0]
  _cam_last_objects: list = [{}]

  def _on_cam_message(_c, _u, msg):
    try:
      data = json.loads(msg.payload)
      _cam_rx_count[0] += 1
      _cam_last_objects[0] = data.get("objects", {})
    except Exception:
      pass

  client.subscribe(CAM_TOPIC)
  client.on_message = _on_cam_message

  @atexit.register
  def _cleanup():
    if proc.poll() is None:
      proc.terminate()
      try:
        proc.wait(timeout=5)
      except subprocess.TimeoutExpired:
        proc.kill()
    for path in (FIFO,):
      try:
        os.remove(path)
      except FileNotFoundError:
        pass
    _mqtt_state.shutdown()

  fifo_thread.join(timeout=30.0)
  if fifo_result[0] is None:
    raise RuntimeError("LiDAR FIFO not opened within 30 s — pipeline likely failed to start")

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

      lidar_msg = build_lidar_message(raw, SENSOR_ID, fps)

      if sum(len(v) for v in lidar_msg["objects"].values()) > 0:
        client = safe_publish(client, CAMERA_TOPIC, json.dumps(lidar_msg))
      if PUBLISH_RAW:
        client = safe_publish(client, RAW_TOPIC, line)

      published += 1
      if published % 100 == 0:
        lidar_counts = {k: len(v) for k, v in lidar_msg["objects"].items()}
        cam_counts   = {k: len(v) for k, v in _cam_last_objects[0].items()}
        print(
          f"[lidar-publisher] frames={published} fps={fps:.1f}"
          f" lidar={lidar_counts} cam_rx={_cam_rx_count[0]} cam={cam_counts}",
          flush=True,
        )

  print(f"[lidar-publisher] Done — published {published} frames", flush=True)
  try:
    proc.wait(timeout=10)
  except subprocess.TimeoutExpired:
    proc.terminate()


if __name__ == "__main__":
  main()
