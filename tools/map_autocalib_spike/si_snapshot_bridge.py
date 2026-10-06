#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Answer Scenescape UI image requests for SI cameras from local .ts files.

The UI does not play RTSP directly. It publishes on
scenescape/cmd/camera/<id>:
  - getimage            → JPEG on scenescape/image/camera/<id>
  - getcalibrationimage → JPEG on scenescape/image/calibration/camera/<id>

Smart Intersection pipelines read the 1122*_h264.ts files with multifilesrc
(decode from the start of the file). Grabbing the same files over RTSP joins
mid-GOP and produces frequent H.264 corruption. This bridge loops those
files locally the same way SI does.

Example (on the scenescape docker network):
  python3 si_snapshot_bridge.py \\
    --broker broker.scenescape.intel.com \\
    --auth /run/secrets/controller.auth \\
    --rootcert /run/secrets/certs/scenescape-ca.pem \\
    --media-dir /workspace/media
"""

from __future__ import annotations

import argparse
import base64
import json
import threading
import time
from pathlib import Path

import cv2

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

# sensor_id in SmartIntersection scene → SI sample video stem
CAMERAS = {
  "si_camera1": "1122south_h264.ts",
  "si_camera2": "1122west_h264.ts",
  "si_camera3": "1122north_h264.ts",
  "si_camera4": "1122east_h264.ts",
}

# Match SI CPU pipeline videorate (15 fps).
FRAME_INTERVAL_S = 1.0 / 15.0


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


def grabber(camera_id, path, store, stop):
  """Decode from the start of the .ts file; reopen on EOF (clean keyframes)."""
  while not stop.is_set():
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
      print(f"open failed {camera_id} {path}", flush=True)
      time.sleep(1.0)
      continue
    while not stop.is_set():
      ok, frame = cap.read()
      if not ok or frame is None:
        break
      ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
      if ok:
        store.set_jpeg(camera_id, buf.tobytes())
      time.sleep(FRAME_INTERVAL_S)
    cap.release()
    # Brief pause before restarting the loop (same as SI multifilesrc loop).
    time.sleep(0.05)


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--broker", default="broker.scenescape.intel.com")
  ap.add_argument("--port", type=int, default=1883)
  ap.add_argument("--auth", required=True, help="user:pass or path to auth file")
  ap.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  ap.add_argument(
    "--media-dir",
    type=Path,
    default=Path("/workspace/media"),
    help="Directory with 1122{south,west,north,east}_h264.ts",
  )
  args = ap.parse_args()

  store = FrameStore()
  stop = threading.Event()
  threads = []
  for cid, filename in CAMERAS.items():
    path = args.media_dir / filename
    if not path.is_file():
      raise SystemExit(f"missing SI video {path}")
    t = threading.Thread(target=grabber, args=(cid, path, store, stop), daemon=True)
    t.start()
    threads.append(t)
    print(f"grabbing {cid} from {path}", flush=True)

  auth = args.auth

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
  print("connecting to", args.broker, flush=True)
  client.connect()
  try:
    client.loopForever()
  finally:
    stop.set()


if __name__ == "__main__":
  raise SystemExit(main())
