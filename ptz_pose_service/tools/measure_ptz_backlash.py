#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Measure a PTZ head's mechanical backlash from captured image pairs.

Consumes the frames written by ``capture_ptz_backlash.py``. For every probed
position it compares the frame taken while arriving from below with the one
taken while arriving from above - both at the *same* reported pan/tilt - and
reports how far apart the camera actually was.

Run inside the autocalibration container (it has OpenCV):

    docker cp ptz_pose_service/tools scenescape-autocalibration-1:/tmp/tools
    docker cp scenescape-ptz-pose-1:/tmp/ptz_backlash /tmp/ptz_backlash
    docker cp /tmp/ptz_backlash scenescape-autocalibration-1:/tmp/ptz_backlash
    docker compose exec autocalibration python3 /tmp/tools/measure_ptz_backlash.py \\
        --camera-uid atag-ptzcam3

The rotation between the two frames is recovered the same way as in
``measure_ptz_scale.py`` (SIFT matches plus the rotation homography
``H = K R K^-1``); see that module for the method. Measuring image-to-image
rather than comparing calibrated poses matters here, because a calibrated
pose's own run-to-run noise is of the same order as the backlash being
measured.
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scene_common.rest_client import RESTClient

from measure_ptz_scale import MIN_INLIERS, rotation_between

# Below this the asymmetry is indistinguishable from measurement noise.
SIGNIFICANT_BACKLASH_DEG = 0.5


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True)
  parser.add_argument("--input-dir", default="/tmp/ptz_backlash")
  parser.add_argument("--min-inliers", type=int, default=MIN_INLIERS)
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  parser.add_argument("--restauth", default="/run/secrets/calibration.auth")
  return parser


def main():
  args = build_argparser().parse_args()

  with open(os.path.join(args.input_dir, "backlash.json"), encoding="utf-8") as handle:
    frames = json.load(handle)["frames"]

  rest = RESTClient(args.resturl, rootcert=args.rootcert, auth=args.restauth)
  camera = rest.getCamera(args.camera_uid)
  if camera.errors:
    print(f"Failed to fetch camera {args.camera_uid}: {camera.errors}")
    return 1
  intrinsics, dist = camera["intrinsics"], camera["distortion"] or {}
  matrix = np.array([[intrinsics["fx"], 0, intrinsics["cx"]],
                     [0, intrinsics["fy"], intrinsics["cy"]],
                     [0, 0, 1]], dtype=np.float64)
  distortion = np.array([dist.get(k) or 0.0 for k in ("k1", "k2", "p1", "p2", "k3")])
  detector = cv2.SIFT_create()
  matcher = cv2.BFMatcher()

  summary = {}
  for axis in ("pan", "tilt"):
    rows = [f for f in frames if f["axis"] == axis]
    targets = sorted({f["target"] for f in rows})
    if not targets:
      continue
    print(f"\n{axis} axis:")
    measurements = []
    for target in targets:
      pair = {f["direction"]: f for f in rows if f["target"] == target}
      if len(pair) < 2:
        print(f"  {axis}={target:+.3f}: only one direction captured")
        continue
      if abs(pair[+1][axis] - pair[-1][axis]) > 1e-6:
        print(f"  {axis}={target:+.3f}: camera reported different positions, skipped")
        continue
      images = {d: cv2.imread(os.path.join(args.input_dir, f["file"]), cv2.IMREAD_GRAYSCALE)
                for d, f in pair.items()}
      if any(image is None for image in images.values()):
        print(f"  {axis}={target:+.3f}: missing frame")
        continue
      result = rotation_between(images[-1], images[+1], matrix, distortion, detector, matcher)
      if result is None or result[2] < args.min_inliers:
        inliers = 0 if result is None else result[2]
        print(f"  {axis}={target:+.3f}: unreliable match ({inliers} inliers)")
        continue
      angle, rot_axis, inliers = result
      measurements.append(angle)
      print(f"  {axis}={target:+.3f} (reported {pair[+1][axis]:+.6f}): {angle:5.2f} deg "
            f"axis=[{rot_axis[0]:+.2f},{rot_axis[1]:+.2f},{rot_axis[2]:+.2f}] "
            f"{inliers} inliers")
    if measurements:
      median = float(np.median(measurements))
      spread = float(np.max(measurements) - np.min(measurements))
      print(f"  -> median {median:.2f} deg, spread {spread:.2f} deg across positions")
      summary[axis] = median

  if summary:
    print("\nFor ptz_pose_service/config/cameras.json:\n")
    for axis, value in summary.items():
      if value < SIGNIFICANT_BACKLASH_DEG:
        print(f'  "{axis}_backlash_deg": 0.0,   # {value:.2f} deg measured, within noise')
      else:
        print(f'  "{axis}_backlash_deg": {value:.2f},')
    print("\nThe service applies half of this either side of the reported position, "
          "\nso a move that reverses direction is corrected by the full amount.")
  return 0


if __name__ == "__main__":
  exit(main())
