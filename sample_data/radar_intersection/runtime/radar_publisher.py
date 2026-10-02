#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Radar + multi-camera publisher for the radar-intersection demo.

All radar modes share one GStreamer publish stack via ``g3dinference``:

  classical | roadside | radarpillars
    → g3dlidarparse → g3dinference → gvametaconvert → FIFO → MQTT

Set ``RADAR_PERCEPTION`` to select the backend. Cameras use ``gvadetect``.

``CAM_SENSOR_IDS`` / ``RADAR_SENSOR_IDS`` (comma-separated) run one GST
branch + MQTT topic per id. Optional ``RADAR_DATA_PATHS`` /
``RADAR_INDEX_RANGES`` override per-radar bin paths and start/stop
(time-align radar2 3098–3928 to radar1 3270–4100). Camera JPEGs live under
``{CAM_DATA_ROOT}/{sensor_id}/%06d.jpg``.

Requires a DLSPS image with rebuilt ``libgst3delements.so``
(``make build-dlsps-g3d``).
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

from radar_file_playback import (
  annotate_frame_jpeg_b64,
  camera_multifilesrc_parts,
  playback_index,
  radar_multifilesrc_parts,
  setup_getimage_responder,
)
from radar_sensor_contract import (
  MqttState,
  build_camera_message,
  build_radar_message,
  connect_mqtt,
  safe_publish,
)

BROKER = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT = int(os.environ.get("MQTT_PORT", "1883"))

RADAR_PERCEPTION = os.environ.get("RADAR_PERCEPTION", "classical").strip().lower()
# Multi-radar: RADAR_SENSOR_IDS=intersection-radar1,intersection-radar2
# Legacy RADAR_SENSOR_ID still works when RADAR_SENSOR_IDS is unset.
_RADAR_IDS_RAW = os.environ.get("RADAR_SENSOR_IDS", "").strip()
if _RADAR_IDS_RAW:
  RADAR_SENSOR_IDS = [s.strip() for s in _RADAR_IDS_RAW.split(",") if s.strip()]
else:
  RADAR_SENSOR_IDS = [os.environ.get("RADAR_SENSOR_ID", "intersection-radar1").strip()]
RADAR_SENSOR_ID = RADAR_SENSOR_IDS[0]  # legacy alias

_MODE_DEFAULTS = {
  "classical": {
    "data": "/home/pipeline-server/videos/radar_intersection/frames_bin/%06d.bin",
    "config": "/home/pipeline-server/models/public/classical/classical_ov_config.json",
    "point_features": 5,
    "score": 0.0,
  },
  "roadside": {
    "data": "/home/pipeline-server/videos/radar_intersection/frames_bin/%06d.bin",
    "config": "/home/pipeline-server/models/public/roadside/FP16/roadside_ov_config.json",
    "point_features": 5,
    "score": 0.0,
  },
  "radarpillars": {
    "data": "/home/pipeline-server/videos/radar_intersection/pcd_bin/%06d.bin",
    "config": "/home/pipeline-server/models/public/radarpillars/FP16/radarpillars_ov_config.json",
    "point_features": 7,
    # ~1 person/frame mean on VIDETEC 3270–4100 densify (0.03 floods clutter).
    "score": 0.1,
  },
}

if RADAR_PERCEPTION not in _MODE_DEFAULTS:
  raise SystemExit(
    f"RADAR_PERCEPTION={RADAR_PERCEPTION!r} invalid; "
    "use classical | roadside | radarpillars")

_mode = _MODE_DEFAULTS[RADAR_PERCEPTION]


def _env_or(name: str, default: str) -> str:
  raw = os.environ.get(name)
  if raw is None or not str(raw).strip():
    return default
  return str(raw).strip()


RADAR_DATA_PATH = _env_or("RADAR_DATA_PATH", _mode["data"])
RADAR_MODEL_CONFIG = _env_or("RADAR_MODEL_CONFIG", _mode["config"])
RADAR_POINT_FEATURES = int(_env_or("RADAR_POINT_FEATURES", str(_mode["point_features"])))
RADAR_SCORE_THRESHOLD = float(_env_or("RADAR_SCORE_THRESHOLD", str(_mode["score"])))

RADAR_START_INDEX = int(os.environ.get("RADAR_START_INDEX", "0"))
_RADAR_STOP_RAW = os.environ.get("RADAR_STOP_INDEX")
RADAR_STOP_INDEX = (
  int(_RADAR_STOP_RAW.strip()) if _RADAR_STOP_RAW and _RADAR_STOP_RAW.strip() else None)
RADAR_LOOP = os.environ.get("RADAR_LOOP", "true").lower() not in ("0", "false", "no")
RADAR_FRAME_RATE = int(os.environ.get("RADAR_FRAME_RATE", "10"))
RADAR_DEVICE = os.environ.get("RADAR_DEVICE", "CPU").strip().upper()
RADAR_ADD_TENSOR_DATA = os.environ.get("RADAR_ADD_TENSOR_DATA", "false").lower()
if RADAR_ADD_TENSOR_DATA not in ("true", "false"):
  RADAR_ADD_TENSOR_DATA = "false"
RADAR_MUTE = os.environ.get("RADAR_MUTE", "false").lower() in ("1", "true", "yes")
# Causal densify for live/stream: past frames kept by g3dinference (0 = off).
# past=10 ≈ span of offline ±5 without looking ahead. Prefer single-frame bins.
RADAR_ACCUMULATE_PAST = int(os.environ.get("RADAR_ACCUMULATE_PAST", "0") or "0")

# Optional per-id overrides:
#   RADAR_DATA_PATHS=id:/path/%06d.bin,id2:/path2/%06d.bin
#   RADAR_INDEX_RANGES=id:3270-4100,id2:3098-3928
_RADAR_PATH_MAP: dict[str, str] = {}
for part in os.environ.get("RADAR_DATA_PATHS", "").split(","):
  part = part.strip()
  if not part or ":" not in part:
    continue
  sid, path = part.split(":", 1)
  sid, path = sid.strip(), path.strip()
  if sid and path:
    _RADAR_PATH_MAP[sid] = path
_RADAR_RANGE_MAP: dict[str, tuple[int, int | None]] = {}
for part in os.environ.get("RADAR_INDEX_RANGES", "").split(","):
  part = part.strip()
  if not part or ":" not in part:
    continue
  sid, rng = part.split(":", 1)
  sid, rng = sid.strip(), rng.strip()
  if not sid or "-" not in rng:
    continue
  a, b = rng.split("-", 1)
  _RADAR_RANGE_MAP[sid] = (
    int(a.strip()),
    int(b.strip()) if b.strip() else None,
  )


def _radar_data_path(sensor_id: str) -> str:
  if sensor_id in _RADAR_PATH_MAP:
    return _RADAR_PATH_MAP[sensor_id]
  if len(RADAR_SENSOR_IDS) == 1:
    return RADAR_DATA_PATH
  # Convention: first id uses RADAR_DATA_PATH; others under …/radar2/ sibling.
  if sensor_id == RADAR_SENSOR_IDS[0]:
    return RADAR_DATA_PATH
  root = RADAR_DATA_PATH.rsplit("/pcd_bin/", 1)[0] if "/pcd_bin/" in RADAR_DATA_PATH else (
    RADAR_DATA_PATH.rsplit("/frames_bin/", 1)[0] if "/frames_bin/" in RADAR_DATA_PATH
    else "/home/pipeline-server/videos/radar_intersection")
  sub = "pcd_bin" if RADAR_PERCEPTION == "radarpillars" else "frames_bin"
  return f"{root}/radar2/{sub}/%06d.bin"


def _radar_index_range(sensor_id: str) -> tuple[int, int | None]:
  if sensor_id in _RADAR_RANGE_MAP:
    return _RADAR_RANGE_MAP[sensor_id]
  return RADAR_START_INDEX, RADAR_STOP_INDEX


def _radar_fifo(sensor_id: str) -> str:
  safe = sensor_id.replace("/", "_")
  return f"/tmp/radar_demo_radar_{safe}.fifo"

# Multi-camera: CAM_SENSOR_IDS=radar-cam1,radar-cam-n,... (default single cam).
# Legacy CAM_SENSOR_ID still works when CAM_SENSOR_IDS is unset.
_CAM_IDS_RAW = os.environ.get("CAM_SENSOR_IDS", "").strip()
if _CAM_IDS_RAW:
  CAM_SENSOR_IDS = [s.strip() for s in _CAM_IDS_RAW.split(",") if s.strip()]
else:
  CAM_SENSOR_IDS = [os.environ.get("CAM_SENSOR_ID", "radar-cam1").strip()]

CAM_DATA_ROOT = os.environ.get(
  "CAM_DATA_ROOT",
  "/home/pipeline-server/videos/radar_intersection/images",
).rstrip("/")
# Legacy single-path override (only when exactly one camera).
_CAM_DATA_PATH_LEGACY = os.environ.get("CAM_DATA_PATH", "").strip()

CAM_START_INDEX = int(os.environ.get("CAM_START_INDEX", "0"))
_CAM_STOP_RAW = os.environ.get("CAM_STOP_INDEX")
CAM_STOP_INDEX = (
  int(_CAM_STOP_RAW.strip()) if _CAM_STOP_RAW and _CAM_STOP_RAW.strip() else None)
CAM_LOOP = os.environ.get("CAM_LOOP", "true").lower() not in ("0", "false", "no")
CAM_FRAME_RATE = int(os.environ.get("CAM_FRAME_RATE", "10"))
CAM_DEVICE = os.environ.get("CAM_DEVICE", "CPU").strip().upper()
CAM_SCORE_THRESHOLD = float(os.environ.get("CAM_SCORE_THRESHOLD", "0.6"))
CAM_MUTE = os.environ.get("CAM_MUTE", "false").lower() in ("1", "true", "yes")
# Stricter person post-filters (sign-on-grass FPs) — independent of gvadetect thr.
CAM_PERSON_MIN_SCORE = float(os.environ.get("CAM_PERSON_MIN_SCORE", "0.75"))
CAM_PERSON_MIN_HEIGHT_PX = float(os.environ.get("CAM_PERSON_MIN_HEIGHT_PX", "100"))
CAM_PERSON_MIN_ASPECT = float(os.environ.get("CAM_PERSON_MIN_ASPECT", "1.2"))
# Scene categories after COCO→scene remapping (see build_camera_message).
CAM_DETECTION_LABELS = [
  s.strip() for s in os.environ.get("CAM_DETECTION_LABELS", "vehicle,person,cyclist").split(",")
  if s.strip()
]
# SceneScape OMZ default for multi-class intersection: crossroad-1016
# (person / vehicle / bike). Override with CAM_MODEL / CAM_MODEL_PROC.
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
# Optional shared OpenVINO instance across cameras. Empty by default:
# sharing one id across 8 parallel gvadetect branches can stall preroll.
CAM_MODEL_INSTANCE_ID = os.environ.get("CAM_MODEL_INSTANCE_ID", "").strip()



def _cam_data_path(sensor_id: str) -> str:
  if len(CAM_SENSOR_IDS) == 1 and _CAM_DATA_PATH_LEGACY:
    return _CAM_DATA_PATH_LEGACY
  return f"{CAM_DATA_ROOT}/{sensor_id}/%06d.jpg"


def _cam_fifo(sensor_id: str) -> str:
  safe = sensor_id.replace("/", "_")
  return f"/tmp/radar_demo_camera_{safe}.fifo"


def _make_fifo(path: str) -> None:
  if os.path.exists(path):
    os.remove(path)
  os.mkfifo(path)


def _build_sensor_pipelines() -> list[tuple[str, str]]:
  """Build gst-launch commands for demo sensors.

  Cameras share one multi-branch process (stable ~10 fps on GPU). Each radar
  gets its own process — a single multi-radar gst-launch serializes
  g3dlidarparse frame-rate sleeps and starves the second radar.
  """
  pipelines: list[tuple[str, str]] = []
  if not CAM_MUTE:
    cam_parts = ["gst-launch-1.0"]
    for sensor_id in CAM_SENSOR_IDS:
      cam_parts += camera_multifilesrc_parts(
        data_path=_cam_data_path(sensor_id),
        start_index=CAM_START_INDEX,
        stop_index=CAM_STOP_INDEX,
        loop=CAM_LOOP,
        frame_rate=CAM_FRAME_RATE,
        model=CAM_MODEL,
        model_proc=CAM_MODEL_PROC,
        device=CAM_DEVICE,
        score_threshold=CAM_SCORE_THRESHOLD,
        fifo_path=_cam_fifo(sensor_id),
        model_instance_id=CAM_MODEL_INSTANCE_ID or None,
      )
    pipelines.append(("cameras", " ".join(cam_parts)))
  if not RADAR_MUTE:
    for sensor_id in RADAR_SENSOR_IDS:
      start_i, stop_i = _radar_index_range(sensor_id)
      parts = ["gst-launch-1.0"] + radar_multifilesrc_parts(
        data_path=_radar_data_path(sensor_id),
        start_index=start_i,
        stop_index=stop_i,
        loop=RADAR_LOOP,
        frame_rate=RADAR_FRAME_RATE,
        model_config=RADAR_MODEL_CONFIG,
        model_type=RADAR_PERCEPTION,
        point_features=RADAR_POINT_FEATURES,
        device=RADAR_DEVICE,
        score_threshold=RADAR_SCORE_THRESHOLD,
        add_tensor_data=RADAR_ADD_TENSOR_DATA,
        fifo_path=_radar_fifo(sensor_id),
        accumulate_past=RADAR_ACCUMULATE_PAST,
      )
      pipelines.append((f"radar:{sensor_id}", " ".join(parts)))
  if not pipelines:
    raise SystemExit("Both RADAR_MUTE and CAM_MUTE set")
  return pipelines


def _fifo_publish_loop(
  *,
  name: str,
  fifo_path: str,
  topic: str,
  client,
  builder,
  fps: float,
  frame_index_cell: list | None = None,
  start_index: int = 0,
  stop_index: int | None = None,
  loop: bool = True,
  drive_frame_index: bool = True,
  data_path: str | None = None,
  image_b64_cell: list | None = None,
  objects_cell: list | None = None,
  publish=None,
) -> None:
  published = 0
  t0 = time.monotonic()
  _publish = publish or (lambda _topic, msg: safe_publish(client, _topic, msg))
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
      _publish(topic, msg)
      published += 1
      idx = None
      if drive_frame_index and frame_index_cell is not None:
        idx = playback_index(published, start_index, stop_index, loop)
        frame_index_cell[0] = idx
      # Cache objects for lazy getimage annotation (avoid per-frame JPEG encode).
      if objects_cell is not None:
        objects_cell[0] = msg.get("objects") or {}
      if published % max(1, int(fps)) == 0:
        elapsed = max(1e-3, time.monotonic() - t0)
        objs = msg.get("objects") or {}
        n = sum(len(v) for v in objs.values()) if isinstance(objs, dict) else 0
        print(
          f"[{name}] frames={published} objects={n} "
          f"meas_fps={published / elapsed:.2f}",
          flush=True,
        )


def main() -> None:
  print(
    f"[radar-publisher] perception={RADAR_PERCEPTION} "
    f"radar_sensors={RADAR_SENSOR_IDS} cam_sensors={CAM_SENSOR_IDS} "
    f"broker={BROKER}:{PORT} radar_device={RADAR_DEVICE} "
    f"cam_model={CAM_MODEL} cam_device={CAM_DEVICE} "
    f"point_features={RADAR_POINT_FEATURES} score_thr={RADAR_SCORE_THRESHOLD} "
    f"accumulate_past={RADAR_ACCUMULATE_PAST} "
    f"radar_mute={RADAR_MUTE} cam_mute={CAM_MUTE}",
    flush=True,
  )

  state = MqttState()
  atexit.register(state.shutdown)
  client = connect_mqtt("radar-demo-publisher", BROKER, PORT, state)

  cam_frame_cells: dict[str, list] = {}
  cam_image_cells: dict[str, list] = {}
  cam_objects_cells: dict[str, list] = {}
  if not CAM_MUTE:
    for sensor_id in CAM_SENSOR_IDS:
      cell: list = [CAM_START_INDEX]
      cam_frame_cells[sensor_id] = cell
      img_cell: list = [None]
      cam_image_cells[sensor_id] = img_cell
      obj_cell: list = [{}]
      cam_objects_cells[sensor_id] = obj_cell
      # Seed with raw first frame until detections arrive.
      seed = annotate_frame_jpeg_b64(
        _cam_data_path(sensor_id) % CAM_START_INDEX, {}, fps=float(CAM_FRAME_RATE))
      if seed:
        img_cell[0] = seed
      setup_getimage_responder(
        client, sensor_id, _cam_data_path(sensor_id), cell, CAM_START_INDEX,
        image_b64_cell=img_cell, objects_cell=obj_cell, fps=float(CAM_FRAME_RATE))
      _make_fifo(_cam_fifo(sensor_id))
  if not RADAR_MUTE:
    for sensor_id in RADAR_SENSOR_IDS:
      _make_fifo(_radar_fifo(sensor_id))

  # Open FIFO readers before gst-launch writers so publish never blocks
  # pipeline start / first buffers on a writer-only open.
  threads: list[threading.Thread] = []
  mqtt_lock = threading.Lock()

  def _locked_publish(topic: str, payload: dict) -> None:
    with mqtt_lock:
      safe_publish(client, topic, payload)

  if not RADAR_MUTE:
    for sensor_id in RADAR_SENSOR_IDS:
      sid = sensor_id

      def _radar_builder(raw, _sid=sid):
        return build_radar_message(raw, _sid, float(RADAR_FRAME_RATE))

      threads.append(threading.Thread(
        target=_fifo_publish_loop,
        kwargs={
          "name": f"radar:{sid}",
          "fifo_path": _radar_fifo(sid),
          "topic": f"scenescape/data/radar/{sid}",
          "client": client,
          "builder": _radar_builder,
          "fps": float(RADAR_FRAME_RATE),
          "publish": _locked_publish,
        },
        daemon=True,
        name=f"radar:{sid}",
      ))
  if not CAM_MUTE:
    for sensor_id in CAM_SENSOR_IDS:
      sid = sensor_id

      def _builder(raw, _sid=sid):
        return build_camera_message(
          raw, _sid, float(CAM_FRAME_RATE), CAM_DETECTION_LABELS,
          person_min_score=CAM_PERSON_MIN_SCORE,
          person_min_height_px=CAM_PERSON_MIN_HEIGHT_PX,
          person_min_aspect=CAM_PERSON_MIN_ASPECT,
        )

      threads.append(threading.Thread(
        target=_fifo_publish_loop,
        kwargs={
          "name": f"camera:{sid}",
          "fifo_path": _cam_fifo(sid),
          "topic": f"scenescape/data/camera/{sid}",
          "client": client,
          "builder": _builder,
          "fps": float(CAM_FRAME_RATE),
          "frame_index_cell": cam_frame_cells[sid],
          "start_index": CAM_START_INDEX,
          "stop_index": CAM_STOP_INDEX,
          "loop": CAM_LOOP,
          "drive_frame_index": True,
          "data_path": _cam_data_path(sid),
          "image_b64_cell": cam_image_cells[sid],
          "objects_cell": cam_objects_cells[sid],
          "publish": _locked_publish,
        },
        daemon=True,
        name=f"camera:{sid}",
      ))

  for t in threads:
    t.start()

  pipeline_specs = _build_sensor_pipelines()
  procs: list[tuple[str, subprocess.Popen]] = []
  for name, pipeline_cmd in pipeline_specs:
    print(f"[radar-publisher] Starting {name}: {pipeline_cmd}", flush=True)
    proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr)
    procs.append((name, proc))
    print(f"[radar-publisher] {name} started (pid={proc.pid})", flush=True)

  @atexit.register
  def _cleanup():
    for _, proc in procs:
      if proc.poll() is None:
        proc.terminate()
        try:
          proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
          proc.kill()

  print("[radar-demo] running (Ctrl+C to stop)", flush=True)
  while True:
    for name, proc in procs:
      if proc.poll() is not None:
        raise SystemExit(f"gstreamer {name} exited {proc.returncode}")
    for t in threads:
      if not t.is_alive():
        raise SystemExit(f"thread {t.name} died")
    time.sleep(1)


if __name__ == "__main__":
  main()
