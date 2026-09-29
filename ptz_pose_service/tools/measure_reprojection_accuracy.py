#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Measure how well the running ptz-pose service tracks a camera.

Drives the camera along a path of pan/tilt offsets from its current position.
At each stop it waits for the service to write the new pose, then projects
freshly detected AprilTag world points through that stored pose and compares
them with where the tags were actually detected in the frame.

Unlike the other tools this needs ``ptz-pose`` *running*, since its output is
what is being measured. Run inside the ptz-pose container:

    docker compose exec ptz-pose python3 /tmp/tools/measure_reprojection_accuracy.py \\
        --camera-uid atag-ptzcam3 --onvif-host 192.168.0.91 --onvif-port 2020

The default path visits each tilt position from both directions so backlash
shows up as a direction-dependent error. The error at the start position is
the floor: tag detection and the scene mesh carry a few pixels on their own.
The output file feeds ``fit_ptz_curves.py``.
"""

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dlstreamer.onvif import find_ptz_capable_profiles, PTZController
from dlstreamer.onvif.ptz.types import PTZVector
from scene_common.rest_client import RESTClient

from auto_recalibration import AutoRecalibrator
from collect_calibration_views import collect_view
from pose_math import project_world_points_to_pixels

DEFAULT_PAN_PATH = [0.0, -0.05, -0.10, -0.15, -0.20, -0.10, 0.0,
                    0.05, 0.10, 0.15, 0.20, 0.10, 0.0]
DEFAULT_TILT_PATH = [0.0, 0.05, 0.10, 0.05, 0.0, -0.10, -0.20, -0.30, -0.20, -0.10, 0.0]


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True, help="Scenescape camera UID")
  parser.add_argument("--onvif-host", required=True)
  parser.add_argument("--onvif-port", type=int, default=80)
  parser.add_argument("--onvif-username", default=os.environ.get("ONVIF_USERNAME", ""))
  parser.add_argument("--onvif-password", default=os.environ.get("ONVIF_PASSWORD", ""))
  parser.add_argument("--pan-path", type=float, nargs="+", default=DEFAULT_PAN_PATH,
                      help="pan offsets from the start position, visited in order at start tilt")
  parser.add_argument("--tilt-path", type=float, nargs="+", default=DEFAULT_TILT_PATH,
                      help="tilt offsets from the start position, visited in order at start pan")
  parser.add_argument("--settle-s", type=float, default=4.0,
                      help="seconds to wait after each move for the head to stop and "
                           "the service to write the pose")
  parser.add_argument("--output", default="/tmp/reprojection_accuracy.json")
  parser.add_argument("--config", default="/app/config/cameras.json",
                      help="service camera map; this camera's entry is saved with the results "
                           "so fit_ptz_curves.py knows the settings that were measured")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1")
  parser.add_argument("--restauth", default="/run/secrets/calibration.auth")
  parser.add_argument("--autocalibration-url",
                      default="https://autocalibration.scenescape.intel.com:8443/v1")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  parser.add_argument("--broker", default="broker.scenescape.intel.com")
  parser.add_argument("--brokerauth", default="/run/secrets/browser.auth")
  return parser


def stored_pose(rest, camera_uid):
  camera = rest.getCamera(camera_uid)
  if camera.errors:
    raise RuntimeError(f"Failed to fetch {camera_uid}: {camera.errors}")
  return camera


def reprojection_errors(camera, points_2d, points_3d):
  """Pixel error per detected point, None for one the stored pose puts behind the camera."""
  errors = []
  for detected, world in zip(points_2d, points_3d):
    projected = project_world_points_to_pixels(
        [world], camera["rotation"], camera["translation"],
        camera["intrinsics"], camera.get("distortion"))
    if projected is None:
      errors.append(None)
      continue
    errors.append(math.hypot(projected[0][0] - detected[0], projected[0][1] - detected[1]))
  return errors


def camera_config(path, camera_uid):
  try:
    with open(path, encoding="utf-8") as handle:
      cameras = json.load(handle).get("cameras", [])
  except (OSError, ValueError) as err:
    print(f"Could not read {path}: {err}")
    return None
  return next((c for c in cameras if c.get("scene_camera_uid") == camera_uid), None)


def main():
  args = build_argparser().parse_args()
  config = camera_config(args.config, args.camera_uid)

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
  print(f"Starting position: pan={start_pan:+.4f} tilt={start_tilt:+.4f}")

  rest = RESTClient(args.resturl, rootcert=args.rootcert, auth=args.restauth)
  recalibrator = AutoRecalibrator(
      args.autocalibration_url, args.rootcert,
      args.broker, args.brokerauth, args.rootcert)

  path = ([("pan", start_pan + d, start_tilt) for d in args.pan_path]
          + [("tilt", start_pan, start_tilt + d) for d in args.tilt_path])
  results = []
  print(f"\n{'#':>3} {'axis':4} {'pan':>8} {'tilt':>8} {'dir':>4} {'pts':>4} "
        f"{'mean px':>8} {'max px':>8}  rotation")
  previous = {"pan": start_pan, "tilt": start_tilt}
  try:
    for index, (axis, pan, tilt) in enumerate(path, start=1):
      controller.absolute_move(PTZVector(pan=pan, tilt=tilt))
      time.sleep(args.settle_s)
      actual = controller.get_status().position
      moved = (pan if axis == "pan" else tilt) - previous[axis]
      direction = "-" if abs(moved) < 1e-6 else ("up" if moved > 0 else "down")
      previous = {"pan": pan, "tilt": tilt}

      camera = stored_pose(rest, args.camera_uid)
      collected = collect_view(recalibrator, args.camera_uid)
      record = {"axis": axis, "pan": actual.pan, "tilt": actual.tilt,
                "direction": direction, "rotation": camera["rotation"],
                "translation": camera["translation"],
                "intrinsics": camera["intrinsics"],
                "distortion": camera.get("distortion"),
                "points_2d": [], "points_3d": [], "errors": []}
      # Kept even without tags: the move still matters for backlash state.
      results.append(record)
      if not collected:
        print(f"{index:>3} {axis:4} {actual.pan:+8.4f} {actual.tilt:+8.4f} {direction:>4} "
              f"   - no tags detected")
        continue
      points_2d, points_3d = collected
      errors = reprojection_errors(camera, points_2d, points_3d)
      record.update(points_2d=points_2d, points_3d=points_3d, errors=errors)
      valid = [e for e in errors if e is not None]
      mean = sum(valid) / len(valid) if valid else float("nan")
      worst = max(valid) if valid else float("nan")
      rotation = [round(v, 2) for v in camera["rotation"]]
      print(f"{index:>3} {axis:4} {actual.pan:+8.4f} {actual.tilt:+8.4f} {direction:>4} "
            f"{len(valid):>4} {mean:8.2f} {worst:8.2f}  {rotation}")
  finally:
    print(f"\nReturning to start position pan={start_pan:+.4f} tilt={start_tilt:+.4f}")
    controller.absolute_move(PTZVector(pan=start_pan, tilt=start_tilt))

  with open(args.output, "w", encoding="utf-8") as handle:
    json.dump({"camera_uid": args.camera_uid, "start_pan": start_pan,
               "start_tilt": start_tilt, "config": config, "stops": results}, handle)

  for axis in ("pan", "tilt"):
    errors = [e for r in results if r["axis"] == axis for e in r["errors"] if e is not None]
    if errors:
      print(f"{axis:4} overall: {len(errors)} points, mean {sum(errors) / len(errors):.2f} px, "
            f"max {max(errors):.2f} px")
  print(f"Wrote {args.output}")
  return 0


if __name__ == "__main__":
  exit(main())
