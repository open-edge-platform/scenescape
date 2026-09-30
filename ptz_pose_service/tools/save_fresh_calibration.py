#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Auto-calibrate a camera at its current view and save the result.

Does what "Auto calibrate" followed by "Save camera" does in the Scenescape
UI: asks the autocalibration service to match the scene's AprilTags in a
fresh frame, and stores the matched 2D/3D points as the camera's calibration.
A running ptz-pose service adopts it as the trusted home.

Run inside the ptz-pose container:

    docker compose exec ptz-pose python3 /tmp/tools/save_fresh_calibration.py \\
        --camera-uid atag-ptzcam3
"""

import argparse
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scene_common.rest_client import RESTClient

from auto_recalibration import AutoRecalibrator
from collect_calibration_views import collect_view
from pose_math import join_point_correspondence_transforms

# Scenescape's solvePnP needs this many for its iterative solver.
MIN_POINTS = 6


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True)
  parser.add_argument("--min-points", type=int, default=MIN_POINTS)
  parser.add_argument("--dry-run", action="store_true",
                      help="only check the camera exists and enough tags are matched")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1")
  parser.add_argument("--restauth", default="/run/secrets/calibration.auth")
  parser.add_argument("--autocalibration-url",
                      default="https://autocalibration.scenescape.intel.com:8443/v1")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  parser.add_argument("--broker", default="broker.scenescape.intel.com")
  parser.add_argument("--brokerauth", default="/run/secrets/browser.auth")
  return parser


def main():
  args = build_argparser().parse_args()
  rest = RESTClient(args.resturl, rootcert=args.rootcert, auth=args.restauth)
  camera = rest.getCamera(args.camera_uid)
  if camera.errors:
    print(f"Camera {args.camera_uid} not found in Scenescape: {camera.errors}")
    return 1

  recalibrator = AutoRecalibrator(args.autocalibration_url, args.rootcert,
                                  args.broker, args.brokerauth, args.rootcert)
  collected = collect_view(recalibrator, args.camera_uid)
  count = len(collected[0]) if collected else 0
  if count < args.min_points:
    print(f"Only {count} AprilTag points matched (need {args.min_points}); not saved")
    return 1
  if args.dry_run:
    print(f"{args.camera_uid}: {count} AprilTag points matched")
    return 0
  points_2d, points_3d = collected

  result = rest.updateCamera(args.camera_uid, {
      "name": camera["name"],
      "transform_type": "3d-2d point correspondence",
      "transforms": join_point_correspondence_transforms(points_2d, points_3d),
  })
  if result.errors:
    print(f"Failed to save calibration: {result.errors}")
    return 1
  print(f"Saved a fresh calibration from {count} AprilTag points")
  return 0


if __name__ == "__main__":
  exit(main())
