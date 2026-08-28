#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LiDAR + camera dual-stream publisher for the LiDAR-intersection demo.

Module split (keep this separation when extending):

- ``lidar_sensor_contract`` — SceneScape MQTT detection contract shared by any
  input (live or recorded): wall-clock stamps, transforms, message builders,
  MQTT helpers. Always publish including empty frames.
- ``lidar_file_playback`` — recorded ``multifilesrc`` / numbered-file proxy
  only: skip-unread feed staging (live drop-stale stand-in), dataset index
  math, file-backed getimage, GStreamer file-source chain fragments.

This file is the demo entrypoint: env config, FIFO/GStreamer process, and
wiring the file-playback adapter into the publish loop.

Streams run independently (no pace-gate). When PointPillars is slower than
the camera, skip-to-live drops unread ``.bin`` frames so LiDAR detections
stay on "now" — the same policy a live capture ring buffer would use.
"""

from __future__ import annotations

import atexit
import json
import os
import shlex
import subprocess
import sys
import threading
import time

from lidar_file_playback import (
  LidarCatchUp,
  camera_multifilesrc_parts,
  lidar_multifilesrc_parts,
  playback_index,
  setup_getimage_responder,
)
from lidar_sensor_contract import (
  MqttState,
  build_camera_message,
  build_lidar_message,
  connect_mqtt,
  safe_publish,
)

# ── MQTT ──────────────────────────────────────────────────────────────────────
BROKER  = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))

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
# File-playback only: skip unread .bin files so inference stays on camera-now
# (live sensors drop stale samples instead; see lidar_file_playback.py).
LIDAR_SKIP_TO_LIVE = os.environ.get("LIDAR_SKIP_TO_LIVE", "true").lower() not in ("0", "false", "no")
LIDAR_FEED_DIR = os.environ.get("LIDAR_FEED_DIR", "/tmp/lidar_feed")

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

_mqtt_state = MqttState()
_lidar_ready = threading.Event()
_stream_frame_counts: dict[str, int] = {"lidar-publisher": 0, "camera-publisher": 0}
_stream_counts_lock = threading.Lock()


def _camera_playback_index() -> int:
  with _stream_counts_lock:
    cam_count = _stream_frame_counts.get("camera-publisher", 0)
  return playback_index(cam_count, CAM_START_INDEX, CAM_STOP_INDEX, CAM_LOOP)


def _build_lidar_msg(raw: dict, fps: float) -> dict:
  return build_lidar_message(raw, LIDAR_SENSOR_ID, fps)


def _build_camera_msg(raw: dict, fps: float) -> dict:
  return build_camera_message(raw, CAM_SENSOR_ID, fps, CAM_DETECTION_LABELS)


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


def run_stream(
  name: str,
  proc: subprocess.Popen,
  fifo_path: str,
  topic: str,
  publish_raw: bool,
  raw_topic: str,
  frame_rate: float,
  build_message,
  image_preview: dict | None = None,
  is_lidar: bool = False,
  catchup: LidarCatchUp | None = None,
) -> None:
  """Read a detection FIFO and publish SceneScape MQTT messages until exit.

  ``catchup`` is optional and file-playback-only (skip-unread staging).
  Streams are independent — no pace-gate between camera and LiDAR.
  """
  fifo_result: list = [None]
  fifo_thread = _open_fifo_background(fifo_path, fifo_result)

  frame_index_cell = [None]
  resubscribe = None
  if image_preview is not None:
    def resubscribe(c) -> None:
      setup_getimage_responder(
        c, image_preview["sensor_id"], image_preview["data_path"], frame_index_cell,
        image_preview["start_index"],
      )

  client = connect_mqtt(name, BROKER, PORT, _mqtt_state, on_connect_setup=resubscribe)

  fifo_thread.join(timeout=30.0)
  if fifo_result[0] is None:
    raise RuntimeError(f"[{name}] FIFO not opened within 30s - pipeline likely failed to start")

  published = 0
  fps = float(frame_rate)
  last_ts: float | None = None
  last_inferred = LIDAR_START_INDEX
  last_behind = 0

  with fifo_result[0] as fifo:
    for line in fifo:
      rc = proc.poll()
      if rc is not None and rc != 0:
        raise RuntimeError(f"[{name}] GStreamer pipeline exited with code {rc}")

      line = line.strip()
      if not line:
        continue

      try:
        raw = json.loads(line)
      except json.JSONDecodeError as exc:
        print(f"[{name}] JSON error frame={published}: {exc}", flush=True)
        # File catch-up: GStreamer already consumed this feed slot.
        if is_lidar and catchup is not None:
          last_inferred, last_behind = catchup.on_lidar_done()
        continue

      if is_lidar and not _lidar_ready.is_set():
        _lidar_ready.set()
        print(f"[{name}] first LiDAR frame processed", flush=True)

      if is_lidar and catchup is not None:
        last_inferred, last_behind = catchup.on_lidar_done()

      now = time.time()
      if last_ts is not None:
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_ts, 0.001))
      last_ts = now

      msg = build_message(raw, fps)

      # Contract: always publish, including empty objects, so tracks can clear.
      client = safe_publish(
        client, name, topic, json.dumps(msg), BROKER, PORT, _mqtt_state,
        on_connect_setup=resubscribe,
      )
      if publish_raw:
        client = safe_publish(
          client, name, raw_topic, line, BROKER, PORT, _mqtt_state,
          on_connect_setup=resubscribe,
        )

      if image_preview is not None:
        start = image_preview["start_index"]
        stop = image_preview["stop_index"]
        span = (stop - start + 1) if (stop is not None and image_preview["loop"]) else None
        frame_index_cell[0] = start + (published % span if span else published)

      published += 1
      with _stream_counts_lock:
        _stream_frame_counts[name] = published

      if not is_lidar and catchup is not None:
        catchup.nudge_lookahead()

      if published % 100 == 0:
        counts = {k: len(v) for k, v in msg["objects"].items()}
        if is_lidar:
          with _stream_counts_lock:
            cam_count = _stream_frame_counts.get("camera-publisher", 0)
          extra = ""
          if catchup is not None:
            extra = (
              f" idx={last_inferred} behind={last_behind}"
              f" skipped={catchup.skipped_total}"
            )
          print(
            f"[{name}] frames={published} fps={fps:.1f} objects={counts}"
            f" cam={cam_count}{extra}",
            flush=True,
          )
        else:
          print(f"[{name}] frames={published} fps={fps:.1f} objects={counts}", flush=True)

  print(f"[{name}] Done - published {published} frames", flush=True)


def _build_combined_pipeline() -> str:
  """Both recorded-file chains as independent branches in one gst-launch."""
  return " ".join(
    ["gst-launch-1.0"]
    + camera_multifilesrc_parts(
      data_path=CAM_DATA_PATH,
      start_index=CAM_START_INDEX,
      stop_index=CAM_STOP_INDEX,
      loop=CAM_LOOP,
      frame_rate=CAM_FRAME_RATE,
      model=CAM_MODEL,
      model_proc=CAM_MODEL_PROC,
      device=CAM_DEVICE,
      score_threshold=CAM_SCORE_THRESHOLD,
      fifo_path=CAM_FIFO,
    )
    + lidar_multifilesrc_parts(
      skip_to_live=LIDAR_SKIP_TO_LIVE,
      feed_dir=LIDAR_FEED_DIR,
      data_path=LIDAR_DATA_PATH,
      start_index=LIDAR_START_INDEX,
      stop_index=LIDAR_STOP_INDEX,
      loop=LIDAR_LOOP,
      frame_rate=LIDAR_FRAME_RATE,
      model_config=LIDAR_MODEL_CONFIG,
      device=LIDAR_DEVICE,
      score_threshold=LIDAR_SCORE_THRESHOLD,
      add_tensor_data=LIDAR_ADD_TENSOR_DATA,
      fifo_path=LIDAR_FIFO,
    )
  )


def main() -> None:
  print(
    f"[lidar-publisher] lidar_sensor={LIDAR_SENSOR_ID} cam_sensor={CAM_SENSOR_ID} "
    f"broker={BROKER}:{PORT} lidar_topic={LIDAR_TOPIC} cam_topic={CAM_TOPIC} "
    f"lidar_device={LIDAR_DEVICE} cam_device={CAM_DEVICE} "
    f"skip_to_live={LIDAR_SKIP_TO_LIVE}",
    flush=True,
  )

  catchup = None
  if LIDAR_SKIP_TO_LIVE:
    catchup = LidarCatchUp(
      data_path=LIDAR_DATA_PATH,
      feed_dir=LIDAR_FEED_DIR,
      start_index=LIDAR_START_INDEX,
      cam_start=CAM_START_INDEX,
      cam_stop=CAM_STOP_INDEX,
      cam_loop=CAM_LOOP,
      camera_index_fn=_camera_playback_index,
    )
    catchup.prime()
    print(
      f"[lidar-publisher] skip-to-live feed={LIDAR_FEED_DIR} "
      f"first_idx={catchup.last_dataset_index}",
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
      run_stream(
        name, proc, fifo_path, topic, publish_raw, raw_topic, frame_rate, build_message,
        image_preview, is_lidar=is_lidar, catchup=catchup,
      )
    except Exception as exc:  # noqa: BLE001 - surface stream failure without killing the sibling stream
      print(f"[{name}] FATAL: {exc}", flush=True)
      errors.append(exc)

  camera_thread = threading.Thread(
    target=_run_and_capture,
    args=("camera-publisher", CAM_FIFO, CAM_TOPIC, CAM_PUBLISH_RAW, CAM_RAW_TOPIC, CAM_FRAME_RATE, _build_camera_msg),
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
    "lidar-publisher", LIDAR_FIFO, LIDAR_TOPIC, LIDAR_PUBLISH_RAW, LIDAR_RAW_TOPIC, LIDAR_FRAME_RATE, _build_lidar_msg,
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
