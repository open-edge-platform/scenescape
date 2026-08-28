#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""DLSPS dual-stream publisher: RadarPillars (OpenVINO) + camera gvadetect.

Radar → scenescape/data/radar/{id}
Camera → scenescape/data/camera/{id}

Set RADAR_MUTE=true or CAM_MUTE=true to verify a single modality.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from radarpillars_infer import RadarPillarsOV, videtec_frame_to_pcd

try:
  import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
  mqtt = None

BROKER = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
ROOT_CA = os.environ.get("MQTT_ROOTCERT", "/run/secrets/certs/scenescape-ca.pem")

RADAR_SENSOR_ID = os.environ.get("RADAR_SENSOR_ID", "intersection-radar1")
RADAR_FRAMES_DIR = os.environ.get(
  "RADAR_FRAMES_DIR", "/home/pipeline-server/videos/radar_intersection/frames")
RADAR_FRAME_RATE = float(os.environ.get("RADAR_FRAME_RATE", "10"))
RADAR_LOOP = os.environ.get("RADAR_LOOP", "true").lower() not in ("0", "false", "no")
RADAR_DEVICE = os.environ.get("RADAR_DEVICE", "CPU").strip().upper()
RADAR_MODEL_CONFIG = os.environ.get(
  "RADAR_MODEL_CONFIG",
  "/home/pipeline-server/models/public/radarpillars/FP16/radarpillars_ov_config.json",
)
RADAR_MUTE = os.environ.get("RADAR_MUTE", "false").lower() in ("1", "true", "yes")
RADAR_TOPIC = f"scenescape/data/radar/{RADAR_SENSOR_ID}"

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


def wall_ts() -> str:
  dt = datetime.now(timezone.utc)
  return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def connect_mqtt(name: str):
  if mqtt is None:
    raise SystemExit("paho-mqtt required")
  client = mqtt.Client(client_id=f"{name}-{uuid.uuid4().hex[:8]}", protocol=mqtt.MQTTv311)
  if os.path.exists(ROOT_CA):
    client.tls_set(ca_certs=ROOT_CA)
    client.tls_insecure_set(True)
  for attempt in range(15):
    try:
      client.connect(BROKER, PORT, 60)
      client.loop_start()
      print(f"[{name}] connected {BROKER}:{PORT}", flush=True)
      return client
    except Exception as exc:
      print(f"[{name}] connect {attempt + 1}/15 failed: {exc}", flush=True)
      time.sleep(2)
  raise SystemExit(f"[{name}] MQTT connect failed")


def publish(client, topic, payload: dict):
  client.publish(topic, json.dumps(payload), qos=0)


def load_frame_paths(directory: str) -> list[Path]:
  d = Path(directory)
  files = sorted(list(d.glob("*.npy")) + list(d.glob("*.npz")))
  if not files:
    raise SystemExit(f"No radar frames in {directory}")
  return files


def read_frame(path: Path) -> np.ndarray:
  if path.suffix == ".npy":
    return np.load(path)
  return np.loadtxt(path, delimiter=",", ndmin=2)


def objects_by_category(objs: list[dict]) -> dict:
  by_cat: dict[str, list] = {}
  for o in objs:
    cat = o.get("category", "vehicle")
    by_cat.setdefault(cat, []).append({
      "id": o.get("id"),
      "category": cat,
      "confidence": o.get("confidence", 0.0),
      "translation": o.get("translation"),
      "size": o.get("size"),
      "rotation": o.get("rotation"),
      "source": "radar",
    })
  return by_cat


def radar_loop(client):
  if RADAR_MUTE:
    print("[radar] muted", flush=True)
    while True:
      time.sleep(3600)
  det = RadarPillarsOV(RADAR_MODEL_CONFIG, device=RADAR_DEVICE)
  files = load_frame_paths(RADAR_FRAMES_DIR)
  print(f"[radar] {len(files)} frames → {RADAR_TOPIC} @ {RADAR_FRAME_RATE} Hz "
        f"device={RADAR_DEVICE}", flush=True)
  idx = 0
  while True:
    frame = read_frame(files[idx % len(files)])
    objs = det.infer(videtec_frame_to_pcd(frame))
    payload = {
      "id": RADAR_SENSOR_ID,
      "timestamp": wall_ts(),
      "rate": RADAR_FRAME_RATE,
      "objects": objects_by_category(objs),
    }
    publish(client, RADAR_TOPIC, payload)
    if idx % max(1, int(RADAR_FRAME_RATE)) == 0:
      n = sum(len(v) for v in payload["objects"].values())
      print(f"[radar] frame {idx} objects={n}", flush=True)
    idx += 1
    if not RADAR_LOOP and idx >= len(files):
      break
    time.sleep(1.0 / RADAR_FRAME_RATE)


def camera_pipeline_cmd() -> list[str]:
  """Build gst-launch argv (tokenized) matching the LiDAR demo camera branch."""
  src = (
    f"multifilesrc location={shlex.quote(CAM_DATA_PATH)} "
    f"start-index={CAM_START_INDEX}"
  )
  if CAM_STOP_INDEX is not None:
    src += f" stop-index={CAM_STOP_INDEX}"
  if CAM_LOOP:
    src += " loop=true"
  src += " caps=image/jpeg"
  pipeline = (
    f"{src} ! jpegdec ! videoconvert ! video/x-raw,format=BGR "
    f"! gvafpsthrottle target-fps={CAM_FRAME_RATE} "
    f"! gvadetect model={shlex.quote(CAM_MODEL)} "
    f"model-proc={shlex.quote(CAM_MODEL_PROC)} "
    f"device={shlex.quote(CAM_DEVICE)} threshold={CAM_SCORE_THRESHOLD} "
    f"! gvametaconvert add-tensor-data=false format=json "
    f"! gvametapublish method=file file-format=json-lines "
    f"file-path={shlex.quote(CAM_FIFO)} "
    f"! fakesink sync=false"
  )
  return shlex.split(f"gst-launch-1.0 -q {pipeline}")


def build_camera_message(raw: dict) -> dict:
  objects: dict[str, list] = {}
  for i, item in enumerate(raw.get("objects") or []):
    detection = item.get("detection") if isinstance(item, dict) else None
    if not isinstance(detection, dict) or "confidence" not in detection:
      continue
    label = (detection.get("label") or str(detection.get("label_id", ""))).strip()
    if CAM_DETECTION_LABELS and label not in CAM_DETECTION_LABELS:
      continue
    try:
      objects.setdefault(label, []).append({
        "id": i + 1,
        "category": label,
        "confidence": detection["confidence"],
        "bounding_box_px": {
          "x": item["x"],
          "y": item["y"],
          "width": item["w"],
          "height": item["h"],
        },
        "source": "camera",
      })
    except (KeyError, TypeError):
      continue
  return {
    "id": CAM_SENSOR_ID,
    "timestamp": wall_ts(),
    "rate": float(CAM_FRAME_RATE),
    "objects": objects,
  }


def camera_loop(client):
  if CAM_MUTE:
    print("[camera] muted", flush=True)
    while True:
      time.sleep(3600)
  if os.path.exists(CAM_FIFO):
    os.remove(CAM_FIFO)
  os.mkfifo(CAM_FIFO)
  cmd = camera_pipeline_cmd()
  print(f"[camera] → {CAM_TOPIC} device={CAM_DEVICE}", flush=True)
  print(f"[camera] gst: {' '.join(cmd[:8])} ...", flush=True)
  proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
  published = 0
  with open(CAM_FIFO, "r", encoding="utf-8", errors="replace") as fifo:
    while True:
      if proc.poll() is not None:
        err = proc.stderr.read() if proc.stderr else ""
        if proc.returncode != 0:
          raise RuntimeError(f"camera pipeline exited {proc.returncode}: {err[-800:]}")
        print(f"[camera] pipeline ended after {published} frames", flush=True)
        break
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
      publish(client, CAM_TOPIC, build_camera_message(raw))
      published += 1
      if published % 50 == 0:
        print(f"[camera] frames={published}", flush=True)


def main():
  client = connect_mqtt("radar-demo-publisher")
  threads = []
  if not RADAR_MUTE:
    threads.append(threading.Thread(target=radar_loop, args=(client,), daemon=True, name="radar"))
  if not CAM_MUTE:
    threads.append(threading.Thread(target=camera_loop, args=(client,), daemon=True, name="camera"))
  if not threads:
    raise SystemExit("Both RADAR_MUTE and CAM_MUTE set")
  for t in threads:
    t.start()
  print("[radar-demo] running (Ctrl+C to stop)", flush=True)
  while True:
    for t in threads:
      if not t.is_alive():
        raise SystemExit(f"thread {t.name} died")
    time.sleep(1)


if __name__ == "__main__":
  main()
