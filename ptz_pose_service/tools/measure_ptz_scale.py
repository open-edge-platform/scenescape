#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Measure a PTZ camera's pan/tilt scale factors from a captured sweep.

Recovers how many degrees of real rotation each ONVIF pan/tilt unit
corresponds to, using only the camera's intrinsics and ordinary scene
texture. No AprilTags, markers or scene calibration are involved, so the
result is a property of the camera hardware and is equally valid whether the
deployment calibrates manually, with markers, or markerlessly.

Run inside the autocalibration container (it has OpenCV):

    docker cp ptz_pose_service/tools scenescape-autocalibration-1:/tmp/tools
    docker cp scenescape-ptz-pose-1:/tmp/ptz_sweep /tmp/ptz_sweep
    docker cp /tmp/ptz_sweep scenescape-autocalibration-1:/tmp/ptz_sweep
    docker compose exec autocalibration python3 /tmp/tools/measure_ptz_scale.py \\
        --camera-uid atag-ptzcam3


How the measurement works
-------------------------

For each consecutive pair of frames in the sweep:

1. **Find distinctive points (SIFT).** SIFT (Scale-Invariant Feature
   Transform) searches each image across a range of blur scales for spots
   that stand out from their surroundings - typically corners and blob-like
   texture. For every such keypoint it records a position, a characteristic
   size, and a dominant local gradient orientation, then summarises the
   gradient pattern around it as a 128-number descriptor. Because that
   descriptor is built relative to the keypoint's own scale and orientation,
   the same physical feature yields a near-identical descriptor even after
   the camera has rotated, zoomed or seen a lighting change - which is
   exactly what happens between two frames of a PTZ sweep.

2. **Match them.** Descriptors from the two frames are paired by nearest
   neighbour. A match is kept only if the best candidate is clearly better
   than the runner-up (Lowe's ratio test), which discards the ambiguous
   matches that repetitive texture such as tiling or brickwork produces.

3. **Fit a rotation homography.** A camera that only rotates sees the whole
   scene transform by ``H = K R K^-1`` regardless of how far away anything
   is. Fitting ``H`` to the matches with RANSAC (which ignores outliers) and
   then computing ``R = K^-1 H K`` recovers the rotation; its angle follows
   from the axis-angle form. Dividing that angle by the ONVIF position
   change the camera reported gives degrees per unit.

Step quality varies: a frame pointing at a blank wall, or a move large
enough to leave little overlap, yields few reliable matches. Such steps are
rejected (see ``MIN_INLIERS`` and the axis/magnitude checks) rather than
averaged in. Each step is also measured independently against its immediate
predecessor, so one unusable frame costs only the steps that touch it
instead of corrupting every later measurement.
"""

import argparse
import json
import os
import statistics

import cv2
import numpy as np

from scene_common.rest_client import RESTClient

# Below this many RANSAC inliers a homography is not trustworthy; in practice
# good steps run into the hundreds while failures sit well under a hundred.
MIN_INLIERS = 100
# A sweep turns about one mechanical axis, so a step whose recovered axis
# points elsewhere is measuring something other than the intended motion.
MAX_AXIS_DEVIATION_DEG = 20.0
# Steps this far from the median degrees-per-unit are treated as failures.
MAX_SCALE_RATIO = 1.6
MIN_STEP_UNITS = 1e-4
LOWE_RATIO = 0.75
RANSAC_REPROJ_THRESHOLD = 3.0
# Beyond this much variation across the travel, one linear scale is a poor model.
LINEARITY_TOLERANCE_PERCENT = 15.0


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True)
  parser.add_argument("--input-dir", default="/tmp/ptz_sweep")
  parser.add_argument("--min-inliers", type=int, default=MIN_INLIERS)
  parser.add_argument("--verbose", action="store_true",
                      help="print every step, including rejected ones")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1")
  parser.add_argument("--result-json",
                      help="also write the measured scales (unsigned) to this file")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  parser.add_argument("--restauth", default="/run/secrets/calibration.auth")
  return parser


def rotation_between(image_a, image_b, matrix, distortion, detector, matcher):
  """Rotation between two frames of the same scene.

  See the module docstring for the SIFT / homography reasoning.

  @return  (angle_degrees, axis_unit_vector, inlier_count) or None
  """
  kp_a, desc_a = detector.detectAndCompute(image_a, None)
  kp_b, desc_b = detector.detectAndCompute(image_b, None)
  if desc_a is None or desc_b is None or len(desc_a) < 2 or len(desc_b) < 2:
    return None

  matches = [m for m, n in matcher.knnMatch(desc_a, desc_b, k=2)
             if m.distance < LOWE_RATIO * n.distance]
  if len(matches) < 4:
    return None

  pts_a = np.float32([kp_a[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
  pts_b = np.float32([kp_b[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
  # Remove lens distortion first so the mapping really is a pure K R K^-1.
  norm_a = cv2.undistortPoints(pts_a, matrix, distortion, P=matrix)
  norm_b = cv2.undistortPoints(pts_b, matrix, distortion, P=matrix)

  homography, mask = cv2.findHomography(norm_a, norm_b, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
  if homography is None:
    return None

  rotation = np.linalg.inv(matrix) @ homography @ matrix
  # The estimate is only approximately a rotation; snap it to the nearest one.
  u, _, vt = np.linalg.svd(rotation)
  rotation = u @ vt
  if np.linalg.det(rotation) < 0:
    rotation = u @ np.diag([1.0, 1.0, -1.0]) @ vt

  rotvec = cv2.Rodrigues(rotation)[0].ravel()
  angle = float(np.degrees(np.linalg.norm(rotvec)))
  if angle < 1e-6:
    return None
  return angle, rotvec / np.linalg.norm(rotvec), int(mask.sum())


def measure_steps(frames, axis, input_dir, matrix, distortion, verbose):
  """Measure each consecutive frame pair along one axis independently."""
  selected = [f for f in frames if f["axis"] == axis]
  if len(selected) < 2:
    return []

  detector = cv2.SIFT_create()
  matcher = cv2.BFMatcher()
  steps = []
  previous = cv2.imread(os.path.join(input_dir, selected[0]["file"]), cv2.IMREAD_GRAYSCALE)
  previous_pos = selected[0][axis]
  for frame in selected[1:]:
    current = cv2.imread(os.path.join(input_dir, frame["file"]), cv2.IMREAD_GRAYSCALE)
    step = frame[axis] - previous_pos
    if current is None or abs(step) < MIN_STEP_UNITS:
      previous, previous_pos = current, frame[axis]
      continue
    result = rotation_between(previous, current, matrix, distortion, detector, matcher)
    if result is not None:
      angle, rot_axis, inliers = result
      steps.append({"file": frame["file"], "at": (previous_pos + frame[axis]) / 2.0,
                    "step": step, "angle": angle, "axis": rot_axis,
                    "inliers": inliers, "scale": angle / step})
    elif verbose:
      print(f"  {frame['file']}: rejected, no homography could be fitted")
    previous, previous_pos = current, frame[axis]
  return steps


def filter_steps(steps, min_inliers, verbose):
  """Drop steps whose match quality, rotation axis or magnitude marks them bad.

  @return  (kept_steps, dominant_axis_or_None)
  """
  kept = []
  for step in steps:
    if step["inliers"] >= min_inliers:
      kept.append(step)
    elif verbose:
      print(f"  {step['file']}: rejected, only {step['inliers']} inliers")
  if len(kept) < 3:
    return kept, None

  # Flip axes by step direction so forward and backward steps agree, then take
  # the median direction as the sweep's true mechanical axis.
  directed = np.array([s["axis"] * np.sign(s["step"]) for s in kept])
  dominant = np.median(directed, axis=0)
  dominant /= np.linalg.norm(dominant)

  aligned = []
  for step, axis_vector in zip(kept, directed):
    deviation = np.degrees(np.arccos(
        np.clip(abs(float(np.dot(axis_vector, dominant))), -1.0, 1.0)))
    if deviation <= MAX_AXIS_DEVIATION_DEG:
      aligned.append(step)
    elif verbose:
      print(f"  {step['file']}: rejected, axis {deviation:.0f}deg off the sweep axis")
  if len(aligned) < 3:
    return aligned, dominant

  median_scale = statistics.median(abs(s["scale"]) for s in aligned)
  final = []
  for step in aligned:
    ratio = abs(step["scale"]) / median_scale if median_scale else 0.0
    if 1.0 / MAX_SCALE_RATIO <= ratio <= MAX_SCALE_RATIO:
      final.append(step)
    elif verbose:
      print(f"  {step['file']}: rejected, {abs(step['scale']):.0f} deg/unit "
            f"vs median {median_scale:.0f}")
  return final, dominant


def report_axis(axis, steps, dominant, total_steps):
  """Summarise surviving steps, including how the scale varies across travel."""
  if len(steps) < 3:
    print(f"\n{axis}: only {len(steps)}/{total_steps} usable steps, not enough to fit a scale")
    return None

  scales = np.array([s["scale"] for s in steps])
  positions = np.array([s["at"] for s in steps])
  median = float(np.median(scales))
  spread = float(np.percentile(np.abs(scales - median), 90))

  print(f"\n{axis}: {len(steps)}/{total_steps} usable steps, "
        f"positions {positions.min():+.3f}..{positions.max():+.3f}")
  if dominant is not None:
    print(f"  rotation axis : [{dominant[0]:+.3f}, {dominant[1]:+.3f}, {dominant[2]:+.3f}]")
  print(f"  scale         : median {median:+.2f} deg/unit (90% within +-{spread:.2f})")

  if positions.max() - positions.min() > 1e-6:
    slope, intercept = np.polyfit(positions, scales, 1)
    low, high = np.polyval([slope, intercept], [positions.min(), positions.max()])
    change = abs(high - low) / abs(median) * 100 if median else 0.0
    print(f"  across travel : {low:+.1f} -> {high:+.1f} deg/unit ({change:.0f}% change)")
    print("  linearity     : " + (
        "roughly constant, a single scale is adequate"
        if change < LINEARITY_TOLERANCE_PERCENT
        else "varies materially, a single linear scale is only approximate"))
  print(f"  implied full travel over ONVIF -1..1: {abs(median) * 2:.0f} deg")
  return median


def main():
  args = build_argparser().parse_args()

  with open(os.path.join(args.input_dir, "sweep.json"), encoding="utf-8") as handle:
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
  print(f"Using fx={intrinsics['fx']:.2f} fy={intrinsics['fy']:.2f} "
        f"k1={distortion[0]:+.5f}  (min {args.min_inliers} inliers per step)")

  summary = {}
  for axis in ("pan", "tilt"):
    steps = measure_steps(frames, axis, args.input_dir, matrix, distortion, args.verbose)
    kept, dominant = filter_steps(steps, args.min_inliers, args.verbose)
    result = report_axis(axis, kept, dominant, len(steps))
    if result is not None:
      summary[axis] = result

  if summary:
    print("\nFor ptz_pose_service/config/cameras.json "
          "(sign follows the stored pose convention, not the measurement):\n")
    for axis, value in summary.items():
      print(f'  "{axis}_scale": {abs(value):.2f},')
  if args.result_json:
    with open(args.result_json, "w", encoding="utf-8") as handle:
      json.dump({f"{axis}_scale": round(abs(value), 2) for axis, value in summary.items()},
                handle)
  return 0


if __name__ == "__main__":
  exit(main())
