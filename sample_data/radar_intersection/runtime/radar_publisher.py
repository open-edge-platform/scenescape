#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Radar + multi-camera publisher for the radar-intersection demo.

Radar (custom)::

  g3dlidarparse → g3dinference → FIFO → MQTT

Cameras use the established SceneScape DLStreamer chain
(``sscape_timestamp_capture`` → ``gvadetect`` →
``sscape_post_inference_data_publish``), same as retail/queuing file
replay. That element publishes detections and answers ``getimage`` from
the same buffer — no custom annotate / FIFO / preview path.

Camera JPEGs under ``{CAM_DATA_ROOT}/{sensor_id}/%06d.jpg`` are fused
once to MPEG-TS (``clip_*.ts``) for ``multifilesrc``, matching
``*-config-no-rtsp.json``.
"""

from __future__ import annotations

import atexit
import json
import os
import select
import shlex
import subprocess
import sys
import time
from multiprocessing import Process

from radar_file_playback import (
  camera_clip_path,
  camera_sscape_parts,
  ensure_camera_mpegts,
  radar_multifilesrc_parts,
)
from radar_sensor_contract import (
  MqttState,
  build_radar_message,
  connect_mqtt,
  safe_publish,
)

BROKER = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT = int(os.environ.get("MQTT_PORT", "1883"))

RADAR_PERCEPTION = os.environ.get("RADAR_PERCEPTION", "classical").strip().lower()
_RADAR_IDS_RAW = os.environ.get("RADAR_SENSOR_IDS", "").strip()
if _RADAR_IDS_RAW:
  RADAR_SENSOR_IDS = [s.strip() for s in _RADAR_IDS_RAW.split(",") if s.strip()]
else:
  RADAR_SENSOR_IDS = [os.environ.get("RADAR_SENSOR_ID", "intersection-radar1").strip()]
RADAR_SENSOR_ID = RADAR_SENSOR_IDS[0]

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
RADAR_ACCUMULATE_PAST = int(os.environ.get("RADAR_ACCUMULATE_PAST", "0") or "0")

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


_CAM_IDS_RAW = os.environ.get("CAM_SENSOR_IDS", "").strip()
if _CAM_IDS_RAW:
  CAM_SENSOR_IDS = [s.strip() for s in _CAM_IDS_RAW.split(",") if s.strip()]
else:
  CAM_SENSOR_IDS = [os.environ.get("CAM_SENSOR_ID", "radar-cam1").strip()]

CAM_DATA_ROOT = os.environ.get(
  "CAM_DATA_ROOT",
  "/home/pipeline-server/videos/radar_intersection/images",
).rstrip("/")
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
# SceneScape datapublisher allow-list (CSV). Must match model-proc labels.
CAM_DETECTION_LABELS = os.environ.get(
  "CAM_DETECTION_LABELS", "person,vehicle,cyclist").strip()
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
CAM_NTP_SERVER = os.environ.get("CAM_NTP_SERVER", "ntpserv").strip() or "ntpserv"


def _cam_jpeg_pattern(sensor_id: str) -> str:
  if len(CAM_SENSOR_IDS) == 1 and _CAM_DATA_PATH_LEGACY:
    return _CAM_DATA_PATH_LEGACY
  return f"{CAM_DATA_ROOT}/{sensor_id}/%06d.jpg"


def _make_fifo(path: str) -> None:
  if os.path.exists(path):
    os.remove(path)
  os.mkfifo(path)


def _ensure_camera_clips() -> dict[str, str]:
  clips: dict[str, str] = {}
  for sensor_id in CAM_SENSOR_IDS:
    jpeg_pat = _cam_jpeg_pattern(sensor_id)
    out = camera_clip_path(
      CAM_DATA_ROOT, sensor_id, CAM_START_INDEX, CAM_STOP_INDEX, CAM_FRAME_RATE)
    clips[sensor_id] = ensure_camera_mpegts(
      jpeg_pattern=jpeg_pat,
      start_index=CAM_START_INDEX,
      stop_index=CAM_STOP_INDEX,
      frame_rate=CAM_FRAME_RATE,
      out_path=out,
    )
  return clips


def _build_sensor_pipelines(cam_clips: dict[str, str]) -> list[tuple[str, str]]:
  """One gst-launch per camera (sscape) + one per radar (g3d FIFO)."""
  pipelines: list[tuple[str, str]] = []
  if not CAM_MUTE:
    for sensor_id in CAM_SENSOR_IDS:
      parts = ["gst-launch-1.0"] + camera_sscape_parts(
        video_path=cam_clips[sensor_id],
        sensor_id=sensor_id,
        loop=CAM_LOOP,
        model=CAM_MODEL,
        model_proc=CAM_MODEL_PROC,
        device=CAM_DEVICE,
        score_threshold=CAM_SCORE_THRESHOLD,
        detection_labels=CAM_DETECTION_LABELS,
        ntp_server=CAM_NTP_SERVER,
      )
      pipelines.append((f"camera:{sensor_id}", " ".join(parts)))
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
  pace: bool = False,
) -> None:
  """Read GST JSON lines and publish (radar only)."""
  published = 0
  t0 = time.monotonic()
  interval = (1.0 / fps) if (pace and fps > 0) else 0.0
  next_due = time.monotonic()
  with open(fifo_path, "r", encoding="utf-8", errors="replace") as fifo:
    while True:
      line = fifo.readline()
      if not line:
        time.sleep(0.001)
        continue
      line = line.strip()
      if not line:
        continue
      if interval > 0:
        now = time.monotonic()
        if now + 0.0005 < next_due:
          time.sleep(next_due - now)
        next_due = time.monotonic() + interval
        while True:
          ready, _, _ = select.select([fifo], [], [], 0)
          if not ready:
            break
          extra = fifo.readline()
          if not extra:
            break
          if extra.strip():
            line = extra.strip()
      try:
        raw = json.loads(line)
      except json.JSONDecodeError:
        continue
      msg = builder(raw)
      safe_publish(client, topic, msg)
      published += 1
      if published % max(1, int(fps)) == 0:
        elapsed = max(1e-3, time.monotonic() - t0)
        objs = msg.get("objects") or {}
        n = sum(len(v) for v in objs.values()) if isinstance(objs, dict) else 0
        print(
          f"[{name}] frames={published} objects={n} "
          f"meas_fps={published / elapsed:.2f}",
          flush=True,
        )


def _radar_publish_process(cfg: dict) -> None:
  state = MqttState()
  client = connect_mqtt(cfg["client_name"], BROKER, PORT, state)
  sid = cfg["sensor_id"]
  fps = float(cfg["fps"])

  def builder(raw, _sid=sid, _fps=fps):
    return build_radar_message(raw, _sid, _fps)

  _fifo_publish_loop(
    name=cfg["name"],
    fifo_path=cfg["fifo_path"],
    topic=cfg["topic"],
    client=client,
    builder=builder,
    fps=fps,
    pace=bool(cfg.get("pace", False)),
  )


def main() -> None:
  print(
    f"[radar-publisher] perception={RADAR_PERCEPTION} "
    f"radar_sensors={RADAR_SENSOR_IDS} cam_sensors={CAM_SENSOR_IDS} "
    f"broker={BROKER}:{PORT} radar_device={RADAR_DEVICE} "
    f"cam_model={CAM_MODEL} cam_device={CAM_DEVICE} "
    f"cam_pipeline=sscape_post_inference_data_publish "
    f"point_features={RADAR_POINT_FEATURES} score_thr={RADAR_SCORE_THRESHOLD} "
    f"accumulate_past={RADAR_ACCUMULATE_PAST} "
    f"radar_mute={RADAR_MUTE} cam_mute={CAM_MUTE}",
    flush=True,
  )

  cam_clips: dict[str, str] = {}
  if not CAM_MUTE:
    cam_clips = _ensure_camera_clips()

  workers: list[Process] = []
  if not RADAR_MUTE:
    for sensor_id in RADAR_SENSOR_IDS:
      _make_fifo(_radar_fifo(sensor_id))
      cfg = {
        "sensor_id": sensor_id,
        "name": f"radar:{sensor_id}",
        "client_name": f"radar-pub-{sensor_id}",
        "fifo_path": _radar_fifo(sensor_id),
        "topic": f"scenescape/data/radar/{sensor_id}",
        "fps": float(RADAR_FRAME_RATE),
        "pace": True,
      }
      workers.append(Process(
        target=_radar_publish_process, args=(cfg,),
        name=f"radar:{sensor_id}", daemon=True))
    for w in workers:
      w.start()

  pipeline_specs = _build_sensor_pipelines(cam_clips)
  procs: list[tuple[str, subprocess.Popen]] = []
  for name, pipeline_cmd in pipeline_specs:
    print(f"[radar-publisher] Starting {name}: {pipeline_cmd}", flush=True)
    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    # Same layout as retail/queuing (run.sh appends ADDITIONAL_GST_PLUGIN_PATH
    # to GST_PLUGIN_PATH; plugins are mounted at /home/sscape/python).
    # Do not touch PYTHONPATH: the image's own path provides gstgva.
    plugin_root = env.get("ADDITIONAL_GST_PLUGIN_PATH", "/home/sscape")
    gst_path = env.get("GST_PLUGIN_PATH", "")
    if plugin_root not in gst_path.split(":"):
      env["GST_PLUGIN_PATH"] = f"{gst_path}:{plugin_root}" if gst_path else plugin_root
    env.setdefault("ROOT_CA", "/run/secrets/certs/scenescape-ca.pem")
    env.setdefault("MQTT_HOST", BROKER)
    env.setdefault("MQTT_PORT", str(PORT))
    proc = subprocess.Popen(shlex.split(pipeline_cmd), stderr=sys.stderr, env=env)
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
    for w in workers:
      if w.is_alive():
        w.terminate()

  print("[radar-demo] running (Ctrl+C to stop)", flush=True)
  while True:
    for name, proc in procs:
      if proc.poll() is not None:
        raise SystemExit(f"gstreamer {name} exited {proc.returncode}")
    for w in workers:
      if not w.is_alive():
        raise SystemExit(f"publisher {w.name} exited {w.exitcode}")
    time.sleep(1)


if __name__ == "__main__":
  main()
