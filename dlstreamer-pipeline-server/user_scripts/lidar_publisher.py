#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Dual-stream pipeline: LiDAR (PointPillars) + Camera (person-vehicle-bike detection).

When both streams are enabled (default), gvastreammux (output-mode=container) multiplexes
the heterogeneous video/x-raw + application/x-lidar pair into a single frame-synchronised
batch stream.  g3dinference runs BEFORE the mux so it can read intact LidarMeta
(gvastreamdemux does not preserve custom GStreamer metadata types).
gvastreamdemux unpacks each batch back to per-source pads:

  Camera:  multifilesrc → jpegdec → videoconvert → gvafpsthrottle → mux.sink_0
             demux.src_0 → PostDecodeTimestampCapture → gvadetect
                         → gvametaconvert → gvametapublish (CAM_FIFO)
                         → PostInferenceDataPublish (MQTT)
  LiDAR:   multifilesrc → g3dlidarparse → g3dinference → gvametaconvert → mux.sink_1
             demux.src_1 → gvametapublish (FIFO) → Python → MQTT

Single-stream debug modes (ENABLE_LIDAR=false or ENABLE_CAMERA=false) bypass the mux.

MQTT topics:
  - scenescape/data/camera/<LIDAR_SENSOR_ID>  (3-D LiDAR detections)
  - scenescape/data/camera/<CAM_SENSOR_ID>    (2-D camera detections via sscape_adapter)

LiDAR-to-scene coordinate transform: (-y, -x, z) axis swap.
Optional raw mirror: set LIDAR_PUBLISH_RAW=true.

Requires DLStreamer >= 2026.2.0-20260707.
bbox_3d schema: {x, y, z, l, w, h, yaw, pitch, roll, ...}
"""

import atexit
import json
import math
import os
import queue
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
SENSOR_ID       = os.environ.get("LIDAR_SENSOR_ID", "intersection-lidar1")
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
CAM_FIFO     = "/tmp/camera_detections.fifo"

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
                   else STOP_INDEX)
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
_CAM_LABELS_RAW       = os.environ.get("CAM_DETECTION_LABELS", "vehicle,cyclist")
CAM_DETECTION_LABELS  = [l.strip() for l in _CAM_LABELS_RAW.split(",") if l.strip()]
SSCAPE_ADAPTER        = os.environ.get(
    "SSCAPE_ADAPTER",
    "/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py",
)
CAM_TOPIC = f"scenescape/data/camera/{CAM_SENSOR_ID}"

# ── Stream enable flags ────────────────────────────────────────────────────────
ENABLE_LIDAR  = os.environ.get("ENABLE_LIDAR",  "true").lower() not in ("0", "false", "no")
ENABLE_CAMERA = os.environ.get("ENABLE_CAMERA", "true").lower() not in ("0", "false", "no")
if not ENABLE_LIDAR and not ENABLE_CAMERA:
  raise ValueError("ENABLE_LIDAR and ENABLE_CAMERA cannot both be false")

# KITTI class index → label name.  Person (index 0) intentionally omitted.
KITTI_LABELS: dict[int, str] = {1: "cyclist", 2: "vehicle"}

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


def bbox3d_to_quaternion(yaw: float) -> "list[float]":
  """
  Convert PointPillars yaw to SceneScape quaternion [qx, qy, qz, qw].

  Requires DLStreamer >= 2026.2.0-20260707 which emits 'yaw' in bbox_3d.

  Two rotations combined:
    1. Z-axis yaw:   q_yaw  = [0, 0, qz, qw]
    2. X-axis 180°:  q_flip = [1, 0,  0,  0]

  Hamilton product q_flip * q_yaw → [qw_yaw, -qz_yaw, 0, 0]

  This keeps the object XY position unchanged while
  flipping the render orientation so roof faces up.
  """
  half = (-yaw - math.pi) / 2.0
  qz = math.sin(half)
  qw = math.cos(half)
  if qw < 0.0:
    qz, qw = -qz, -qw

  # Apply 180 deg X-axis flip: q_flip=[1,0,0,0] * q_yaw=[0,0,qz,qw]
  # Clamp to open interval (-1, 1): the SceneScape controller schema requires
  # strict "< 1" on every component (exclusiveMaximum since the initial commit).
  # yaw=0 yields sin(-π/2)=-1 which would set rotation[1]=1.0 exactly.
  _C = 1.0 - 1e-7
  return [max(-_C, min(_C, qw)), max(-_C, min(_C, -qz)), 0.0, 0.0]


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
  """Wrap PointPillars 3-D detections in SceneScape camera detection format.

  Expects DLStreamer >= 2026.2.0-20260707 bbox_3d schema:
    {x, y, z, l, w, h, yaw, pitch, roll}
  Raises KeyError if 'yaw' is absent (i.e. older schema with 'theta' was fed in).
  """
  gst_ns = raw.get("lidar_frame", {}).get("exit_source_timestamp")
  ts = _make_timestamp(_gst_to_wall(int(gst_ns)) if gst_ns is not None else time.time())

  objects: dict = {}
  for i, obj in enumerate(raw.get("objects", [])):
    bbox = obj.get("bbox_3d")
    if not isinstance(bbox, dict):
      continue
    try:
      if "yaw" not in bbox:
        raise KeyError(
          f"bbox_3d missing 'yaw' field in frame {raw.get('lidar_frame', {}).get('frame_id')}; "
          "this script requires DLStreamer >= 2026.2.0-20260707"
        )
      label = _resolve_label(obj)
      if label not in ("vehicle", "cyclist"):
        continue
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
      })
    except KeyError:
      raise
    except (TypeError, ValueError):
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
  cam_kwarg = json.dumps({
    "cameraid":           CAM_SENSOR_ID,
    "metadatagenpolicy":  "detectionPolicy",
    "detection_labels":   CAM_DETECTION_LABELS,
  })

  if ENABLE_LIDAR and ENABLE_CAMERA:
    # ── Muxed pipeline ─────────────────────────────────────────────────────
    # Camera source → mux.sink_0 (raw video, no inference yet)
    cam_src = [
      "multifilesrc",
      f"location={shlex.quote(CAM_DATA_PATH)}",
      f"start-index={CAM_START_INDEX}",
    ]
    if CAM_STOP_INDEX is not None:
      cam_src.append(f"stop-index={CAM_STOP_INDEX}")
    if LOOP:
      cam_src.append("loop=true")
    cam_src += [
      "caps=image/jpeg",
      "! jpegdec",
      "! videoconvert",
      "! video/x-raw,format=BGR",
      f"! gvafpsthrottle target-fps={FRAME_RATE}",
      "! mux.sink_0",
    ]

    # LiDAR source: g3dinference runs HERE (before mux) so LidarMeta is intact.
    # gvastreamdemux does not preserve custom GStreamer metadata types, so
    # inference must complete before the buffer enters the mux.
    lidar_src = [
      "multifilesrc",
      f"location={shlex.quote(DATA_PATH)}",
      f"start-index={START_INDEX}",
    ]
    if STOP_INDEX is not None:
      lidar_src.append(f"stop-index={STOP_INDEX}")
    if LOOP:
      lidar_src.append("loop=true")
    lidar_src += [
      "caps=application/octet-stream",
      f"! g3dlidarparse stride=1 frame-rate={FRAME_RATE}",
      f"! g3dinference config={shlex.quote(MODEL_CONFIG)}"
      f" device={shlex.quote(DEVICE)}"
      f" score-threshold={SCORE_THRESHOLD}",
      f"! gvametaconvert add-tensor-data={ADD_TENSOR_DATA} format=json",
      "! mux.sink_1",
    ]

    # Camera inference branch (demux.src_0)
    cam_infer = " ".join([
      "demux.src_0 ! queue",
      f"! gvapython class=PostDecodeTimestampCapture function=processFrame"
      f" module={shlex.quote(SSCAPE_ADAPTER)} name=timesync",
      f"! gvadetect model={shlex.quote(CAM_MODEL)}"
      f" model-proc={shlex.quote(CAM_MODEL_PROC)}"
      f" device={shlex.quote(CAM_DEVICE)}"
      f" threshold={CAM_SCORE_THRESHOLD}",
      "! gvametaconvert add-tensor-data=true name=metaconvert",
      f"! gvametapublish method=file file-format=json-lines"
      f" file-path={shlex.quote(CAM_FIFO)}",
      f"! gvapython class=PostInferenceDataPublish function=processFrame"
      f" module={shlex.quote(SSCAPE_ADAPTER)} name=datapublisher"
      f" kwarg={shlex.quote(cam_kwarg)}",
      "! fakesink sync=false",
    ])

    # LiDAR output branch (demux.src_1) — inference already done pre-mux.
    # demux.src_1 carries GstGVATensorMeta (JSON) which gvametapublish reads.
    lidar_infer = " ".join([
      "demux.src_1 ! queue",
      f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(FIFO)}",
      "! fakesink sync=false",
    ])

    mux_block = (
      f"gvastreammux name=mux output-mode=container sync-mode=none"
      f" ! queue ! gvastreamdemux name=demux"
    )
    return (
      f"gst-launch-1.0 {mux_block}"
      f" {cam_infer}"
      f" {lidar_infer}"
      f" {' '.join(cam_src)}"
      f" {' '.join(lidar_src)}"
    )

  # ── Single-stream fallback (no mux) ───────────────────────────────────
  if ENABLE_CAMERA:
    parts = [
      "multifilesrc",
      f"location={shlex.quote(CAM_DATA_PATH)}",
      f"start-index={CAM_START_INDEX}",
    ]
    if CAM_STOP_INDEX is not None:
      parts.append(f"stop-index={CAM_STOP_INDEX}")
    if LOOP:
      parts.append("loop=true")
    parts += [
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
      "! gvametaconvert add-tensor-data=true name=metaconvert",
      f"! gvametapublish method=file file-format=json-lines"
      f" file-path={shlex.quote(CAM_FIFO)}",
      f"! gvapython class=PostInferenceDataPublish function=processFrame"
      f" module={shlex.quote(SSCAPE_ADAPTER)} name=datapublisher"
      f" kwarg={shlex.quote(cam_kwarg)}",
      "! fakesink sync=false",
    ]
    return f"gst-launch-1.0 {' '.join(parts)}"

  # ENABLE_LIDAR only
  parts = [
    "multifilesrc",
    f"location={shlex.quote(DATA_PATH)}",
    f"start-index={START_INDEX}",
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
    "! fakesink sync=false",
  ]
  return f"gst-launch-1.0 {' '.join(parts)}"


# ── FIFO ───────────────────────────────────────────────────────────────────────

def _make_fifo() -> None:
  for path in ([FIFO] if ENABLE_LIDAR else []) + ([CAM_FIFO] if ENABLE_CAMERA else []):
    if os.path.exists(path):
      os.remove(path)
    os.mkfifo(path)


def _open_fifo_background(path: str, result: list) -> threading.Thread:
  def _worker():
    result[0] = open(path, "r")
  t = threading.Thread(target=_worker, daemon=True, name=f"fifo-opener-{path}")
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
    f"publish_raw={PUBLISH_RAW} "
    f"enable_lidar={ENABLE_LIDAR} enable_camera={ENABLE_CAMERA} "
    f"dlstreamer_schema=2026.2.0-20260707+",
    flush=True,
  )

  _make_fifo()

  pipeline_cmd = _build_pipeline()
  proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr)
  print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

  if ENABLE_LIDAR:
    fifo_result: list = [None]
    fifo_thread = _open_fifo_background(FIFO, fifo_result)

  if ENABLE_CAMERA:
    cam_fifo_result: list = [None]
    cam_fifo_thread = _open_fifo_background(CAM_FIFO, cam_fifo_result)

  client = connect_mqtt()

  _cam_queue: queue.Queue = queue.Queue()
  _cam_frame_count = [0]
  _cam_last_objects: list = [{}]

  if ENABLE_CAMERA:
    def _on_cam_message(_c, _u, msg):
      try:
        data = json.loads(msg.payload)
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
    for path in ([FIFO] if ENABLE_LIDAR else []) + ([CAM_FIFO] if ENABLE_CAMERA else []):
      try:
        os.remove(path)
      except FileNotFoundError:
        pass
    _mqtt_state.shutdown()

  if ENABLE_LIDAR:
    fifo_thread.join(timeout=30.0)
    if fifo_result[0] is None:
      raise RuntimeError("LiDAR FIFO not opened within 30 s — pipeline likely failed to start")

  if ENABLE_CAMERA:
    cam_fifo_thread.join(timeout=30.0)
    if cam_fifo_result[0] is None:
      raise RuntimeError("Camera FIFO not opened within 30 s — pipeline likely failed to start")

    def _cam_fifo_reader() -> None:
      try:
        with cam_fifo_result[0] as cf:
          for line in cf:
            line = line.strip()
            if line:
              _cam_queue.put(line)
      except Exception:
        pass

    cam_reader = threading.Thread(target=_cam_fifo_reader, daemon=True, name="cam-fifo-reader")
    cam_reader.start()

  if not ENABLE_LIDAR:
    # Camera-only mode: PostInferenceDataPublish handles MQTT publishing.
    # Python just keeps the pipeline alive; Ctrl-C or EOS stops it.
    print("[lidar-publisher] LiDAR disabled — camera-only mode, pipeline running", flush=True)
    while proc.poll() is None:
      time.sleep(5)
    return

  published = 0
  fps     = float(FRAME_RATE)
  last_ts: "float | None" = None
  _startup_flushed = False

  with fifo_result[0] as fifo:
    for line in fifo:
      # On the very first LiDAR frame, GPU init is complete.  Discard any
      # camera frames that arrived during that warm-up so both counters
      # start from the same file index.
      if not _startup_flushed:
        _startup_flushed = True
        if ENABLE_CAMERA:
          flushed = 0
          while not _cam_queue.empty():
            try:
              _cam_queue.get_nowait()
              flushed += 1
            except queue.Empty:
              break
          if flushed:
            print(
              f"[lidar-publisher] startup flush: discarded {flushed} camera"
              " head-start frame(s) — GPU init lag",
              flush=True,
            )

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

      if ENABLE_CAMERA:
        # Drain all camera FIFO lines available since the last LiDAR frame.
        while True:
          try:
            _cam_queue.get_nowait()
            _cam_frame_count[0] += 1
          except queue.Empty:
            break

      if published % 100 == 0:
        lidar_counts = {k: len(v) for k, v in lidar_msg["objects"].items()}
        if ENABLE_CAMERA:
          cam_counts = {k: len(v) for k, v in _cam_last_objects[0].items()}
          cam_info = f" cam={_cam_frame_count[0] + 1} cam_objs={cam_counts}"
        else:
          cam_info = ""
        print(
          f"[lidar-publisher] frames={published} fps={fps:.1f}"
          f" lidar={lidar_counts}{cam_info}",
          flush=True,
        )

  print(f"[lidar-publisher] Done — published {published} frames", flush=True)
  try:
    proc.wait(timeout=10)
  except subprocess.TimeoutExpired:
    proc.terminate()


if __name__ == "__main__":
  main()
