#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Capture image pairs for measuring a PTZ head's mechanical backlash.

Drives each axis to a set of positions, arriving at every one from both
directions, and saves a frame at each arrival. ``measure_ptz_backlash.py``
then compares the two frames taken at the same reported position.

Gear slack means the position encoder (on the motor side of the gearbox)
advances before the camera does, so the same reported pan/tilt corresponds to
two different physical orientations depending on which way the head was
travelling. The service has to model that, or every direction reversal leaves
the pose wrong by the slack.

Run inside the ptz-pose container:

    docker cp ptz_pose_service/tools scenescape-ptz-pose-1:/tmp/tools
    docker compose exec ptz-pose python3 /tmp/tools/capture_ptz_backlash.py \\
        --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

Like the scale sweep this needs no markers or scene calibration - the
measurement is image-to-image - so it is far more precise than comparing
calibrated poses, whose own run-to-run noise is larger than the backlash.
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

# How far past a target to go before returning to it, so the mechanism is
# guaranteed to have taken up its slack in a known direction.
APPROACH_OVERSHOOT = 0.12


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True)
  parser.add_argument("--onvif-host", required=True)
  parser.add_argument("--onvif-port", type=int, default=80)
  parser.add_argument("--onvif-username", default=os.environ.get("ONVIF_USERNAME", ""))
  parser.add_argument("--onvif-password", default=os.environ.get("ONVIF_PASSWORD", ""))
  parser.add_argument("--tilt-positions", type=float, nargs="*",
                      default=[0.55, 0.65, 0.75, 0.85])
  parser.add_argument("--pan-positions", type=float, nargs="*",
                      default=[-0.15, -0.05, 0.05, 0.15])
  parser.add_argument("--overshoot", type=float, default=APPROACH_OVERSHOOT,
                      help="how far past each target to go before returning to it")
  parser.add_argument("--settle-s", type=float, default=3.0)
  parser.add_argument("--output-dir", default="/tmp/ptz_backlash")
  parser.add_argument("--broker", default="broker.scenescape.intel.com")
  parser.add_argument("--brokerauth", default="/run/secrets/browser.auth")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  return parser


class FrameGrabber:
  """Requests frames over MQTT, the same channel the calibration UI uses."""

  def __init__(self, camera_uid, broker, brokerauth, rootcert):
    self.topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera_uid)
    self.command_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera_uid)
    self.condition = threading.Condition()
    self.image = None
    self.pubsub = PubSub(brokerauth, None, rootcert, broker)
    self.pubsub.loopStart()
    self.pubsub.addCallback(self.topic, self._onImage, qos=2)
    return

  def _onImage(self, client, userdata, message):
    try:
      payload = json.loads(message.payload.decode("utf-8"))
    except Exception:
      return
    if "image" in payload:
      with self.condition:
        self.image = payload["image"]
        self.condition.notify_all()
    return

  def grab(self, timeout=15.0):
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
  grabber = FrameGrabber(args.camera_uid, args.broker, args.brokerauth, args.rootcert)

  frames = []
  try:
    for axis, positions, fixed in (("tilt", args.tilt_positions, start.pan),
                                   ("pan", args.pan_positions, start.tilt)):
      print(f"\n{axis} axis:")
      for index, target in enumerate(positions, start=1):
        for direction, label in ((+1, "increasing"), (-1, "decreasing")):
          pan = fixed if axis == "tilt" else target
          tilt = target if axis == "tilt" else fixed
          back = -direction * args.overshoot
          controller.absolute_move(PTZVector(
              pan=pan + (back if axis == "pan" else 0.0),
              tilt=tilt + (back if axis == "tilt" else 0.0)))
          time.sleep(args.settle_s)
          controller.absolute_move(PTZVector(pan=pan, tilt=tilt))
          time.sleep(args.settle_s)
          actual = controller.get_status().position
          image = grabber.grab()
          if not image:
            print(f"  {axis}={target:+.3f} {label:10s}: no frame received")
            continue
          name = f"{axis}_{index:02d}_{'inc' if direction > 0 else 'dec'}.jpg"
          with open(os.path.join(args.output_dir, name), "wb") as handle:
            handle.write(base64.b64decode(image))
          frames.append({"axis": axis, "target": target, "direction": direction,
                         "file": name, "pan": actual.pan, "tilt": actual.tilt})
          print(f"  {axis}={target:+.3f} {label:10s}: reported="
                f"{getattr(actual, axis):+.6f} -> {name}")
  finally:
    grabber.close()
    print(f"\nReturning to start pan={start.pan} tilt={start.tilt}")
    controller.absolute_move(PTZVector(pan=start.pan, tilt=start.tilt))

  meta = os.path.join(args.output_dir, "backlash.json")
  with open(meta, "w", encoding="utf-8") as handle:
    json.dump({"camera_uid": args.camera_uid, "frames": frames}, handle)
  print(f"Wrote {len(frames)} frames and {meta}")
  return 0


if __name__ == "__main__":
  exit(main())
