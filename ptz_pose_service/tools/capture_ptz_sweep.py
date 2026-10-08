#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Capture a PTZ sweep for measuring a camera's pan/tilt scale factors.

Steps the camera across its pan and tilt travel, saving a frame at each
position together with the ONVIF position it reported. ``measure_ptz_scale.py``
then recovers how many degrees each ONVIF unit corresponds to.

Run inside the ptz-pose container (it has the ONVIF and MQTT plumbing):

    docker cp ptz_pose_service/tools scenescape-ptz-pose-1:/tmp/tools
    docker compose exec ptz-pose python3 /tmp/tools/capture_ptz_sweep.py \\
        --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

Unlike the AprilTag-based collection this needs no scene calibration or
markers of any kind - only that the view contains enough texture to match
features between consecutive frames - so the sweep can cover the camera's
whole physical travel rather than just the marked-up part of the scene.
"""

import argparse
import base64
import json
import os
import sys
import threading
import time

sys.path.insert(0, "/app")

from dlstreamer.onvif import find_ptz_capable_profiles, PTZController
from dlstreamer.onvif.ptz.types import PTZVector

from scene_common.mqtt import PubSub


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True, help="Scenescape camera UID")
  parser.add_argument("--onvif-host", required=True)
  parser.add_argument("--onvif-port", type=int, default=80)
  parser.add_argument("--onvif-username", default=os.environ.get("ONVIF_USERNAME", ""))
  parser.add_argument("--onvif-password", default=os.environ.get("ONVIF_PASSWORD", ""))
  parser.add_argument("--pan-range", type=float, nargs=2, default=[-0.9, 0.9],
                      help="pan travel to sweep, in the camera's ONVIF units")
  parser.add_argument("--tilt-range", type=float, nargs=2, default=[0.2, 0.9],
                      help="tilt travel to sweep, in the camera's ONVIF units")
  parser.add_argument("--pan-step", type=float, default=0.05,
                      help="pan increment; small enough that consecutive frames still overlap")
  parser.add_argument("--tilt-step", type=float, default=0.05,
                      help="tilt increment; small enough that consecutive frames still overlap")
  parser.add_argument("--settle-s", type=float, default=2.0,
                      help="seconds to wait after each move before grabbing a frame")
  parser.add_argument("--output-dir", default="/tmp/ptz_sweep")
  parser.add_argument("--broker", default="broker.scenescape.intel.com")
  parser.add_argument("--brokerauth", default="/run/secrets/browser.auth")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  return parser


class FrameGrabber:
  """Requests frames over MQTT, the same channel the calibration UI uses."""

  def __init__(self, camera_uid, broker, brokerauth, rootcert):
    self.camera_uid = camera_uid
    self.topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera_uid)
    self.command_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera_uid)
    self.condition = threading.Condition()
    self.image = None
    self.pubsub = PubSub(brokerauth, None, rootcert, broker)
    self.pubsub.connect()
    self.pubsub.loopStart()
    self.pubsub.addCallback(self.topic, self._onImage, qos=2)
    return

  def _onImage(self, client, userdata, message):
    try:
      payload = json.loads(message.payload.decode("utf-8"))
    except Exception:
      return
    if "image" not in payload:
      return
    with self.condition:
      self.image = payload["image"]
      self.condition.notify_all()
    return

  def grab(self, timeout=10.0):
    with self.condition:
      self.image = None
    self.pubsub.publish(self.command_topic, "getcalibrationimage", qos=2)
    with self.condition:
      if self.image is None:
        self.condition.wait(timeout=timeout)
      return self.image

  def close(self):
    self.pubsub.removeCallback(self.topic)
    self.pubsub.loopStop()
    return


def frange(low, high, step):
  values, current = [], low
  while current <= high + 1e-9:
    values.append(round(current, 6))
    current += step
  return values


def sweep(controller, grabber, positions, settle_s, output_dir, axis, frames):
  """Move through ``positions`` capturing a frame at each, appending to ``frames``."""
  for index, (pan, tilt) in enumerate(positions, start=1):
    controller.absolute_move(PTZVector(pan=pan, tilt=tilt))
    time.sleep(settle_s)
    actual = controller.get_status().position
    image = grabber.grab()
    if not image:
      print(f"  [{index}/{len(positions)}] pan={actual.pan:+.4f} tilt={actual.tilt:+.4f} "
            "-> no frame received")
      continue
    name = f"{axis}_{index:03d}.jpg"
    with open(os.path.join(output_dir, name), "wb") as handle:
      handle.write(base64.b64decode(image))
    frames.append({"axis": axis, "file": name,
                   "pan": actual.pan, "tilt": actual.tilt})
    print(f"  [{index}/{len(positions)}] pan={actual.pan:+.4f} tilt={actual.tilt:+.4f} -> {name}")
  return


def main():
  args = build_argparser().parse_args()
  os.makedirs(args.output_dir, exist_ok=True)

  profiles = list(find_ptz_capable_profiles(
      [{"hostname": args.onvif_host, "port": args.onvif_port}],
      args.onvif_username, args.onvif_password))
  if not profiles:
    print(f"No PTZ-capable profile found on {args.onvif_host}:{args.onvif_port}")
    return 1
  controller = PTZController(args.onvif_host, args.onvif_port, profiles[0].profile_token,
                             args.onvif_username, args.onvif_password)
  start = controller.get_status().position
  start_pan, start_tilt = start.pan, start.tilt
  print(f"Starting position: pan={start_pan} tilt={start_tilt}")

  grabber = FrameGrabber(args.camera_uid, args.broker, args.brokerauth, args.rootcert)
  frames = []
  try:
    mid_tilt = (args.tilt_range[0] + args.tilt_range[1]) / 2.0
    pan_positions = [(p, mid_tilt) for p in frange(*args.pan_range, args.pan_step)]
    print(f"\nPan sweep ({len(pan_positions)} positions at tilt={mid_tilt:.3f}):")
    sweep(controller, grabber, pan_positions, args.settle_s, args.output_dir, "pan", frames)

    mid_pan = (args.pan_range[0] + args.pan_range[1]) / 2.0
    tilt_positions = [(mid_pan, t) for t in frange(*args.tilt_range, args.tilt_step)]
    print(f"\nTilt sweep ({len(tilt_positions)} positions at pan={mid_pan:.3f}):")
    sweep(controller, grabber, tilt_positions, args.settle_s, args.output_dir, "tilt", frames)
  finally:
    grabber.close()
    print(f"\nReturning to start position pan={start_pan} tilt={start_tilt}")
    controller.absolute_move(PTZVector(pan=start_pan, tilt=start_tilt))

  meta_path = os.path.join(args.output_dir, "sweep.json")
  with open(meta_path, "w", encoding="utf-8") as handle:
    json.dump({"camera_uid": args.camera_uid, "frames": frames}, handle)
  print(f"Wrote {len(frames)} frames and {meta_path}")
  return 0


if __name__ == "__main__":
  exit(main())
