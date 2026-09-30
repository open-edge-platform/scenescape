#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Collect multi-view AprilTag correspondences for intrinsics/distortion calibration.

Sweeps a PTZ camera across a grid of pan/tilt positions and, at each one, asks
the autocalibration service to match the scene's AprilTags in a fresh frame.
The resulting 2D pixel / 3D world point pairs are written to a JSON file for
``calibrate_intrinsics.py`` to solve.

Run inside the ptz-pose container (it has the ONVIF, MQTT and REST plumbing):

    docker cp ptz_pose_service/tools scenescape-ptz-pose-1:/tmp/tools
    docker compose exec ptz-pose python3 /tmp/tools/collect_calibration_views.py \\
        --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

A single view only constrains the lens model weakly, so this sweeps many
positions to spread matched points across the whole image - distortion is only
observable where points reach the frame edges.

For a static (non-PTZ) camera, omit ``--onvif-host``: it then grabs
``--static-views`` frames of the one fixed view. Repeated frames only average
out detection jitter; they add no new geometry, so the fit relies on the tags
already spanning the frame and varying in depth.
"""

import argparse
import base64
import json
import os
import struct
import sys
import time

sys.path.insert(0, "/app")

from dlstreamer.onvif import find_ptz_capable_profiles, PTZController
from dlstreamer.onvif.ptz.types import PTZVector

from auto_recalibration import AutoRecalibrator

MIN_POINTS_PER_VIEW = 4


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True, help="Scenescape camera UID")
  parser.add_argument("--onvif-host", help="PTZ camera to sweep; omit for a static camera")
  parser.add_argument("--onvif-port", type=int, default=80)
  parser.add_argument("--static-views", type=int, default=5,
                      help="frames to collect when no --onvif-host is given")
  parser.add_argument("--onvif-username", default=os.environ.get("ONVIF_USERNAME", ""))
  parser.add_argument("--onvif-password", default=os.environ.get("ONVIF_PASSWORD", ""))
  parser.add_argument("--pan-range", type=float, nargs=2, default=[-0.12, 0.12],
                      help="min/max pan to sweep, in the camera's ONVIF units")
  parser.add_argument("--tilt-range", type=float, nargs=2, default=[0.60, 0.80],
                      help="min/max tilt to sweep, in the camera's ONVIF units")
  parser.add_argument("--pan-steps", type=int, default=5)
  parser.add_argument("--tilt-steps", type=int, default=3)
  parser.add_argument("--settle-s", type=float, default=2.5,
                      help="seconds to wait after each move before grabbing a frame")
  parser.add_argument("--output", default="/tmp/calibration_views.json")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1")
  parser.add_argument("--autocalibration-url",
                      default="https://autocalibration.scenescape.intel.com:8443/v1")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  parser.add_argument("--broker", default="broker.scenescape.intel.com")
  parser.add_argument("--brokerauth", default="/run/secrets/browser.auth")
  return parser


def linspace(low, high, steps):
  if steps <= 1:
    return [(low + high) / 2.0]
  span = high - low
  return [low + span * i / (steps - 1) for i in range(steps)]


def jpeg_size(image_b64):
  """(width, height) from a base64 JPEG's SOF header, without an image library."""
  data = base64.b64decode(image_b64)
  i = 2
  while i + 9 < len(data):
    if data[i] != 0xFF:
      i += 1
      continue
    marker = data[i + 1]
    if marker in (0xC0, 0xC1, 0xC2):
      height, width = struct.unpack(">HH", data[i + 5:i + 9])
      return [width, height]
    i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
  return None


def collect_view(recalibrator, camera_uid, image_size=None):
  """Grab a frame and return this view's matched (2D, 3D) point pairs.

  Both the success and rejection paths of the calibration API carry the
  matched correspondences, and a view that's too degenerate to yield a pose on
  its own is still perfectly good calibration data, so failures here are not
  treated as fatal. Pass a list as ``image_size`` to receive the frame's
  [width, height].
  """
  image = recalibrator._waitForCalibrationImage(camera_uid, 10.0)
  if not image:
    return None
  if image_size is not None:
    image_size[:] = jpeg_size(image) or []
  if not recalibrator._startCalibration(camera_uid, image):
    return None
  time.sleep(3.0)
  reply = recalibrator.session.get(
      f"{recalibrator.autocalibration_url}/cameras/{camera_uid}/calibration",
      verify=recalibrator.verify, timeout=15)
  result = reply.json()
  points_2d = result.get("calibration_points_2d")
  points_3d = result.get("calibration_points_3d")
  if not points_2d or not points_3d or len(points_2d) != len(points_3d):
    return None
  return points_2d, points_3d


def collect_static(args, recalibrator):
  views, size = [], []
  for index in range(1, args.static_views + 1):
    collected = collect_view(recalibrator, args.camera_uid, size)
    count = len(collected[0]) if collected else 0
    print(f"[{index}/{args.static_views}] static view -> {count} points")
    if collected and count >= MIN_POINTS_PER_VIEW:
      views.append({"pan": None, "tilt": None,
                    "points_2d": collected[0], "points_3d": collected[1]})
  return views, size


def main():
  args = build_argparser().parse_args()

  recalibrator = AutoRecalibrator(
      args.autocalibration_url, args.rootcert,
      args.broker, args.brokerauth, args.rootcert)
  if not args.onvif_host:
    views, size = collect_static(args, recalibrator)
    return write_views(args, views, size)

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

  views, size = [], []
  positions = [(p, t) for t in linspace(*args.tilt_range, args.tilt_steps)
               for p in linspace(*args.pan_range, args.pan_steps)]
  try:
    for index, (pan, tilt) in enumerate(positions, start=1):
      controller.absolute_move(PTZVector(pan=pan, tilt=tilt))
      time.sleep(args.settle_s)
      actual = controller.get_status().position
      collected = collect_view(recalibrator, args.camera_uid, size)
      if collected is None or len(collected[0]) < MIN_POINTS_PER_VIEW:
        count = 0 if collected is None else len(collected[0])
        print(f"[{index}/{len(positions)}] pan={actual.pan:+.4f} tilt={actual.tilt:+.4f} "
              f"-> skipped ({count} points)")
        continue
      points_2d, points_3d = collected
      views.append({"pan": actual.pan, "tilt": actual.tilt,
                    "points_2d": points_2d, "points_3d": points_3d})
      print(f"[{index}/{len(positions)}] pan={actual.pan:+.4f} tilt={actual.tilt:+.4f} "
            f"-> {len(points_2d)} points")
  finally:
    print(f"Returning to start position pan={start_pan} tilt={start_tilt}")
    controller.absolute_move(PTZVector(pan=start_pan, tilt=start_tilt))

  return write_views(args, views, size)


def write_views(args, views, size):
  if not views:
    print("No usable views collected")
    return 1

  with open(args.output, "w", encoding="utf-8") as handle:
    json.dump({"camera_uid": args.camera_uid, "image_size": size or None,
               "views": views}, handle)
  total = sum(len(v["points_2d"]) for v in views)
  print(f"\nWrote {len(views)} views / {total} points (frame {size}) to {args.output}")
  return 0


if __name__ == "__main__":
  exit(main())
