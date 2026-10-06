#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Answer Scenescape UI image requests for SI cameras by grabbing RTSP frames.

The UI does not play RTSP directly. It publishes on
scenescape/cmd/camera/<id>:
  - getimage            → JPEG on scenescape/image/camera/<id>
  - getcalibrationimage → JPEG on scenescape/image/calibration/camera/<id>

This bridge keeps the latest frame from each si-cameraN RTSP path and replies
to those requests (calibration page uses the unannotated calibration topic).

Example (on the scenescape docker network):
  python3 si_snapshot_bridge.py \\
    --broker broker.scenescape.intel.com \\
    --auth /run/secrets/controller.auth \\
    --rootcert /run/secrets/certs/scenescape-ca.pem
"""

from __future__ import annotations

import argparse
import base64
import json
import threading
import time

import cv2

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

# sensor_id in SmartIntersection scene → RTSP path on mediaserver
CAMERAS = {
  "si_camera1": "rtsp://mediaserver:8554/si-camera1",
  "si_camera2": "rtsp://mediaserver:8554/si-camera2",
  "si_camera3": "rtsp://mediaserver:8554/si-camera3",
  "si_camera4": "rtsp://mediaserver:8554/si-camera4",
}


class FrameStore:
  def __init__(self):
    self._lock = threading.Lock()
    self._jpeg = {cid: None for cid in CAMERAS}

  def set_jpeg(self, camera_id, jpeg_bytes):
    with self._lock:
      self._jpeg[camera_id] = jpeg_bytes

  def get_jpeg(self, camera_id):
    with self._lock:
      return self._jpeg.get(camera_id)


def grabber(camera_id, url, store, stop):
  while not stop.is_set():
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
      time.sleep(1.0)
      continue
    while not stop.is_set():
      ok, frame = cap.read()
      if not ok or frame is None:
        break
      ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
      if ok:
        store.set_jpeg(camera_id, buf.tobytes())
      time.sleep(0.05)
    cap.release()
    time.sleep(0.5)


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--broker", default="broker.scenescape.intel.com")
  ap.add_argument("--port", type=int, default=1883)
  ap.add_argument("--auth", required=True, help="user:pass or path to auth file")
  ap.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  args = ap.parse_args()

  store = FrameStore()
  stop = threading.Event()
  threads = []
  for cid, url in CAMERAS.items():
    t = threading.Thread(target=grabber, args=(cid, url, store, stop), daemon=True)
    t.start()
    threads.append(t)

  # PubSub accepts a JSON auth file path or user:password string.
  auth = args.auth

  state = {"client": None}

  def on_connect(client, userdata, flags, rc):
    print("mqtt connected", rc, flush=True)
    for cid in CAMERAS:
      topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=cid)
      client.subscribe(topic)
      print("subscribed", topic, flush=True)

  def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8", errors="replace").strip()
    if payload == "getimage":
      out_kind = PubSub.IMAGE_CAMERA
    elif payload == "getcalibrationimage":
      out_kind = PubSub.IMAGE_CALIBRATE
    else:
      return
    # topic .../cmd/camera/<id>
    camera_id = message.topic.rstrip("/").split("/")[-1]
    jpeg = store.get_jpeg(camera_id)
    if jpeg is None:
      print("no frame yet for", camera_id, flush=True)
      return
    msg = {
      "timestamp": get_iso_time(),
      "image": base64.b64encode(jpeg).decode("ascii"),
      "id": camera_id,
    }
    out = PubSub.formatTopic(out_kind, camera_id=camera_id)
    client.publish(out, json.dumps(msg))
    print("served", payload, camera_id, flush=True)

  client = PubSub(auth, None, args.rootcert, args.broker, args.port, 60)
  client.onConnect = on_connect
  client.onMessage = on_message
  state["client"] = client
  print("connecting to", args.broker, flush=True)
  client.connect()
  try:
    client.loopForever()
  finally:
    stop.set()


if __name__ == "__main__":
  raise SystemExit(main())
