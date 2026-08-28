#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Radar + camera dual-stream publisher for the radar-intersection demo.

Uses generalized DLStreamer ``g3dinference model-type=radarpillars`` (same
GStreamer shape as the LiDAR PointPillars demo). Requires a DLSPS image with
the rebuilt ``libgst3delements.so`` (see ``make build-dlsps-g3d``).

Streams:
  Radar  → scenescape/data/radar/{id}
  Camera → scenescape/data/camera/{id}

Set RADAR_MUTE=true or CAM_MUTE=true to verify a single modality.
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

from radar_file_playback import camera_multifilesrc_parts, radar_multifilesrc_parts
from radar_sensor_contract import (
  MqttState,
  build_camera_message,
  build_radar_message,
  connect_mqtt,
  safe_publish,
)

BROKER = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT = int(os.environ.get("MQTT_PORT", "1883"))

RADAR_SENSOR_ID = os.environ.get("RADAR_SENSOR_ID", "intersection-radar1")
RADAR_DATA_PATH = os.environ.get(
  "RADAR_DATA_PATH",
  "/home/pipeline-server/videos/radar_intersection/pcd_bin/%06d.bin",
)
RADAR_START_INDEX = int(os.environ.get("RADAR_START_INDEX", "0"))
_RADAR_STOP_RAW = os.environ.get("RADAR_STOP_INDEX")
RADAR_STOP_INDEX = (
  int(_RADAR_STOP_RAW.strip()) if _RADAR_STOP_RAW and _RADAR_STOP_RAW.strip() else None)
RADAR_LOOP = os.environ.get("RADAR_LOOP", "true").lower() not in ("0", "false", "no")
RADAR_FRAME_RATE = int(os.environ.get("RADAR_FRAME_RATE", "10"))
RADAR_DEVICE = os.environ.get("RADAR_DEVICE", "CPU").strip().upper()
RADAR_SCORE_THRESHOLD = float(os.environ.get("RADAR_SCORE_THRESHOLD", "0.1"))
RADAR_MODEL_CONFIG = os.environ.get(
  "RADAR_MODEL_CONFIG",
  "/home/pipeline-server/models/public/radarpillars/FP16/radarpillars_ov_config.json",
)
RADAR_ADD_TENSOR_DATA = os.environ.get("RADAR_ADD_TENSOR_DATA", "false").lower()
if RADAR_ADD_TENSOR_DATA not in ("true", "false"):
  RADAR_ADD_TENSOR_DATA = "false"
RADAR_MUTE = os.environ.get("RADAR_MUTE", "false").lower() in ("1", "true", "yes")
RADAR_TOPIC = f"scenescape/data/radar/{RADAR_SENSOR_ID}"
RADAR_FIFO = "/tmp/radar_detections.fifo"

CAM_SENSOR_ID = os.environ.get("CAM_SENSOR_ID", "radar-cam1")
CAM_DATA_PATH = os.environ.get(
  "CAM_DATA_PATH",
  "/home/pipeline-server/videos/radar_intersection/images/%06d.jpg",
)
CAM_START_INDEX = int(os.environ.get("CAM_START_INDEX", "0"))
_CAM_STOP_RAW = os.environ.get("CAM_STOP_INDEX")
CAM_STOP_INDEX = (
  int(_CAM_STOP_RAW.strip()) if _CAM_STOP_RAW and _CAM_STOP_RAW.strip() else None)
CAM_LOOP = os.environ.get("CAM_LOOP", "true").lower() not in ("0", "false", "no")
CAM_FRAME_RATE = int(os.environ.get("CAM_FRAME_RATE", "10"))
CAM_DEVICE = os.environ.get("CAM_DEVICE", "CPU").strip().upper()
CAM_SCORE_THRESHOLD = float(os.environ.get("CAM_SCORE_THRESHOLD", "0.5"))
CAM_MUTE = os.environ.get("CAM_MUTE", "false").lower() in ("1", "true", "yes")
CAM_DETECTION_LABELS = [
  s.strip() for s in os.environ.get("CAM_DETECTION_LABELS", "vehicle,person,cyclist").split(",")
  if s.strip()
]
CAM_MODEL = os.environ.get(
  "CAM_MODEL",
  "/home/pipeline-server/models/omz/person-vehicle-bike-detection-crossroad-1016"
  "/FP32/person-vehicle-bike-detection-crossroad-1016.xml",
)
CAM_MODEL_PROC = os.environ.get(
  "CAM_MODEL_PROC",
  "/home/pipeline-server/videos/radar_intersection/model-proc"
  "/person-vehicle-bike-detection-crossroad-1016.json",
)
CAM_FIFO = "/tmp/radar_demo_camera.fifo"
CAM_TOPIC = f"scenescape/data/camera/{CAM_SENSOR_ID}"


def _make_fifo(path: str) -> None:
  if os.path.exists(path):
    os.remove(path)
  os.mkfifo(path)


def _build_combined_pipeline() -> str:
  parts = ["gst-launch-1.0"]
  if not CAM_MUTE:
    parts += camera_multifilesrc_parts(
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
  if not RADAR_MUTE:
    parts += radar_multifilesrc_parts(
      data_path=RADAR_DATA_PATH,
      start_index=RADAR_START_INDEX,
      stop_index=RADAR_STOP_INDEX,
      loop=RADAR_LOOP,
      frame_rate=RADAR_FRAME_RATE,
      model_config=RADAR_MODEL_CONFIG,
      device=RADAR_DEVICE,
      score_threshold=RADAR_SCORE_THRESHOLD,
      add_tensor_data=RADAR_ADD_TENSOR_DATA,
      fifo_path=RADAR_FIFO,
    )
  if len(parts) == 1:
    raise SystemExit("Both RADAR_MUTE and CAM_MUTE set")
  return " ".join(parts)


def _fifo_publish_loop(
  *,
  name: str,
  fifo_path: str,
  topic: str,
  client,
  builder,
  fps: float,
) -> None:
  published = 0
  with open(fifo_path, "r", encoding="utf-8", errors="replace") as fifo:
    while True:
      line = fifo.readline()
      if not line:
        time.sleep(0.01)
        continue
      line = line.strip()
      if not line:
        continue
      try:
        raw = json.loads(line)
      except json.JSONDecodeError:
        continue
      msg = builder(raw)
      safe_publish(client, topic, msg)
      published += 1
      if published % max(1, int(fps)) == 0:
        objs = msg.get("objects") or {}
        n = sum(len(v) for v in objs.values()) if isinstance(objs, dict) else 0
        print(f"[{name}] frames={published} objects={n}", flush=True)


def main() -> None:
  print(
    f"[radar-publisher] radar_sensor={RADAR_SENSOR_ID} cam_sensor={CAM_SENSOR_ID} "
    f"broker={BROKER}:{PORT} radar_device={RADAR_DEVICE} cam_device={CAM_DEVICE} "
    f"radar_mute={RADAR_MUTE} cam_mute={CAM_MUTE}",
    flush=True,
  )

  state = MqttState()
  atexit.register(state.shutdown)
  client = connect_mqtt("radar-demo-publisher", BROKER, PORT, state)

  if not CAM_MUTE:
    _make_fifo(CAM_FIFO)
  if not RADAR_MUTE:
    _make_fifo(RADAR_FIFO)

  pipeline_cmd = _build_combined_pipeline()
  print(f"[radar-publisher] Starting pipeline: {pipeline_cmd}", flush=True)
  proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr)
  print(f"[radar-publisher] Pipeline started (pid={proc.pid})", flush=True)

  @atexit.register
  def _cleanup():
    if proc.poll() is None:
      proc.terminate()
      try:
        proc.wait(timeout=5)
      except subprocess.TimeoutExpired:
        proc.kill()

  threads: list[threading.Thread] = []
  if not RADAR_MUTE:
    threads.append(threading.Thread(
      target=_fifo_publish_loop,
      kwargs={
        "name": "radar",
        "fifo_path": RADAR_FIFO,
        "topic": RADAR_TOPIC,
        "client": client,
        "builder": lambda raw: build_radar_message(raw, RADAR_SENSOR_ID, float(RADAR_FRAME_RATE)),
        "fps": float(RADAR_FRAME_RATE),
      },
      daemon=True,
      name="radar",
    ))
  if not CAM_MUTE:
    threads.append(threading.Thread(
      target=_fifo_publish_loop,
      kwargs={
        "name": "camera",
        "fifo_path": CAM_FIFO,
        "topic": CAM_TOPIC,
        "client": client,
        "builder": lambda raw: build_camera_message(
          raw, CAM_SENSOR_ID, float(CAM_FRAME_RATE), CAM_DETECTION_LABELS),
        "fps": float(CAM_FRAME_RATE),
      },
      daemon=True,
      name="camera",
    ))

  for t in threads:
    t.start()
  print("[radar-demo] running (Ctrl+C to stop)", flush=True)
  while True:
    if proc.poll() is not None:
      raise SystemExit(f"gstreamer exited {proc.returncode}")
    for t in threads:
      if not t.is_alive():
        raise SystemExit(f"thread {t.name} died")
    time.sleep(1)


if __name__ == "__main__":
  main()
