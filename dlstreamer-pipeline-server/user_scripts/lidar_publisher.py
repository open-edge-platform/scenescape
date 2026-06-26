#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Runs the LiDAR GStreamer inference pipeline and republishes each frame to MQTT
in the SceneScape camera detection format so the controller can track objects.

gvametapublish method=file writes one JSON object per line to the FIFO.
This script reads those lines, converts bbox_3d to translation/size/rotation,
and publishes to scenescape/data/camera/{LIDAR_SENSOR_ID}.

Environment variables (all optional — defaults shown):
  MQTT_HOST             broker.scenescape.intel.com
  MQTT_PORT             1883
  LIDAR_SENSOR_ID       lidar1          Camera ID registered in SceneScape
  LIDAR_DATA_PATH       /home/pipeline-server/videos/velodyne_bin/%06d.bin
  LIDAR_START_INDEX     10699           First file index for multifilesrc
  LIDAR_LOOP            true            Loop dataset files indefinitely
  LIDAR_FRAME_RATE      10              LiDAR capture rate in Hz
  LIDAR_DEVICE          CPU             OpenVINO device (CPU / GPU)
  LIDAR_SCORE_THRESHOLD 0.3             PointPillars confidence threshold
  LIDAR_MODEL_CONFIG    /home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json
"""

import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ── MQTT ──────────────────────────────────────────────────────────────────────
BROKER  = os.environ.get("MQTT_HOST", "broker.scenescape.intel.com")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"

# ── LiDAR pipeline ────────────────────────────────────────────────────────────
SENSOR_ID       = os.environ.get("LIDAR_SENSOR_ID", "lidar1")
DATA_PATH       = os.environ.get("LIDAR_DATA_PATH",
                    "/home/pipeline-server/videos/velodyne_bin/%06d.bin")
START_INDEX     = int(os.environ.get("LIDAR_START_INDEX", "10699"))
LOOP            = os.environ.get("LIDAR_LOOP", "true").lower() not in ("0", "false", "no")
FRAME_RATE      = int(os.environ.get("LIDAR_FRAME_RATE", "10"))
DEVICE          = os.environ.get("LIDAR_DEVICE", "CPU")
SCORE_THRESHOLD = float(os.environ.get("LIDAR_SCORE_THRESHOLD", "0.3"))
MODEL_CONFIG    = os.environ.get("LIDAR_MODEL_CONFIG",
                    "/home/pipeline-server/models/public/pointpillars/FP16/pointpillars_ov_config.json")

CAMERA_TOPIC = f"scenescape/data/camera/{SENSOR_ID}"
FIFO         = "/tmp/lidar_detections.fifo"

# PointPillars KITTI label mapping
KITTI_LABELS = {0: "Pedestrian", 1: "Cyclist", 2: "Car"}


def _build_pipeline():
  loop_flag = "loop=true" if LOOP else ""
  return (
    "gst-launch-1.0 "
    f"multifilesrc location=\"{DATA_PATH}\" start-index={START_INDEX} {loop_flag} "
    "caps=application/octet-stream "
    f"! g3dlidarparse stride=1 frame-rate={FRAME_RATE} "
    "! g3dinference "
    f"config=\"{MODEL_CONFIG}\" "
    f"device={DEVICE} score-threshold={SCORE_THRESHOLD} "
    "! gvametaconvert add-tensor-data=true format=json "
    f"! gvametapublish method=file file-format=json-lines file-path={FIFO} "
    "! fakesink"
  )


def yaw_to_quaternion(theta):
  """Convert yaw angle (Z-axis rotation) to quaternion [qx, qy, qz, qw]."""
  half = theta / 2.0
  return [0.0, 0.0, math.sin(half), math.cos(half)]


def convert_frame(raw):
  """
  Convert gvametaconvert JSON-lines frame to SceneScape camera detection format.

  Input (per object):
    {"label_id": 2, "confidence": 0.94,
     "bbox_3d": {"x":17.7, "y":-2.6, "z":-1.5, "w":1.62, "l":3.82, "h":1.51, "theta":-1.57}}

  Output (scenescape/data/camera format):
    {"id": "lidar1", "timestamp": "...", "rate": 7.3,
     "objects": {"Car": [{"id":1, "confidence":0.94,
                          "translation":[17.7,-2.6,-1.5],
                          "size":[3.82,1.62,1.51],
                          "rotation":[0,0,-0.71,0.71]}]}}
  """
  objects = {}
  for i, obj in enumerate(raw.get("objects", [])):
    bbox = obj.get("bbox_3d")
    if bbox is None:
      continue
    label = obj.get("label") or KITTI_LABELS.get(obj.get("label_id", -1), "object")
    det = {
      "id": i + 1,
      "category": label,
      "confidence": obj.get("confidence", 0.0),
      "translation": [bbox["x"], bbox["y"], bbox["z"]],
      "size": [bbox["l"], bbox["w"], bbox["h"]],
      "rotation": yaw_to_quaternion(bbox.get("theta", 0.0)),
    }
    objects.setdefault(label, []).append(det)
  return objects


def connect_mqtt():
  client = mqtt.Client(client_id="lidar-stream-publisher")
  if os.path.exists(ROOT_CA):
    client.tls_set(ca_certs=ROOT_CA)
  for attempt in range(10):
    try:
      client.connect(BROKER, PORT, keepalive=60)
      client.loop_start()
      print(f"[lidar-publisher] Connected to {BROKER}:{PORT}", flush=True)
      return client
    except Exception as e:
      print(f"[lidar-publisher] Connect attempt {attempt + 1} failed: {e}", flush=True)
      time.sleep(2)
  raise RuntimeError("Could not connect to MQTT broker")


def main():
  if os.path.exists(FIFO):
    os.remove(FIFO)
  os.mkfifo(FIFO)

  client = connect_mqtt()

  proc = subprocess.Popen(_build_pipeline(), shell=True, stderr=sys.stderr)
  print(f"[lidar-publisher] Pipeline started (pid={proc.pid})", flush=True)

  published = 0
  fps_alpha = 0.75
  fps = 0.0
  last_ts = None

  with open(FIFO, "r") as fifo:
    for line in fifo:
      line = line.strip()
      if not line:
        continue
      try:
        raw = json.loads(line)
      except json.JSONDecodeError:
        continue

      now = time.time()
      if last_ts:
        fps = fps * fps_alpha + (1 - fps_alpha) * (1.0 / max(now - last_ts, 0.001))
      last_ts = now

      objects = convert_frame(raw)
      msg = {
        "id": SENSOR_ID,
        "timestamp": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "rate": round(fps, 2),
        "objects": objects,
      }

      client.publish(CAMERA_TOPIC, json.dumps(msg), qos=0)
      published += 1
      if published % 100 == 0:
        obj_count = sum(len(v) for v in objects.values())
        print(f"[lidar-publisher] Published {published} frames, last had {obj_count} objects, {fps:.1f} Hz", flush=True)

  proc.wait()
  client.loop_stop()
  client.disconnect()


if __name__ == "__main__":
  main()

