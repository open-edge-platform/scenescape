#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Solve camera intrinsics and lens distortion from collected AprilTag views.

Consumes the JSON written by ``collect_calibration_views.py`` and runs OpenCV's
``calibrateCamera`` over all views at once, reporting the fitted parameters and
before/after reprojection error.

Run inside the autocalibration container (it has OpenCV):

    docker cp ptz_pose_service/tools scenescape-autocalibration-1:/tmp/tools
    docker cp /tmp/calibration_views.json scenescape-autocalibration-1:/tmp/
    docker compose exec autocalibration python3 /tmp/tools/calibrate_intrinsics.py \\
        --camera-uid atag-ptzcam3

Pass ``--apply`` to write the result back to Scenescape, or copy the printed
block into the camera's entry in ``ptz_pose_service/config/cameras.json`` so it
is reapplied automatically on every restart.
"""

import argparse
import json

import cv2
import numpy as np

from scene_common.rest_client import RESTClient

# Tag sweeps yield few distinct world points, and those points carry the scene
# mesh's own error, so an unconstrained fit happily trades physical plausibility
# for a lower residual. Solving a single radial term on square pixels with the
# principal point pinned to the image centre keeps the model identifiable.
DEFAULT_FLAGS = (cv2.CALIB_USE_INTRINSIC_GUESS
                 | cv2.CALIB_ZERO_TANGENT_DIST
                 | cv2.CALIB_FIX_K2
                 | cv2.CALIB_FIX_K3
                 | cv2.CALIB_FIX_PRINCIPAL_POINT
                 | cv2.CALIB_FIX_ASPECT_RATIO)
# A view whose mean error exceeds this multiple of the median view's is treated
# as a mis-detection rather than lens behaviour, and dropped.
OUTLIER_ERROR_RATIO = 2.0


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--camera-uid", required=True)
  parser.add_argument("--input", default="/tmp/calibration_views.json")
  parser.add_argument("--apply", action="store_true",
                      help="write the fitted intrinsics/distortion back to Scenescape")
  parser.add_argument("--fit-principal-point", action="store_true",
                      help="fit cx/cy instead of pinning them to the image centre")
  parser.add_argument("--fit-aspect-ratio", action="store_true",
                      help="fit fx and fy independently instead of assuming square pixels")
  parser.add_argument("--fit-k2", action="store_true",
                      help="also fit the second radial term")
  parser.add_argument("--fit-tangential", action="store_true",
                      help="also fit tangential distortion (needs dense, well-spread points)")
  parser.add_argument("--fit-k3", action="store_true",
                      help="also fit the third radial term (needs strong edge coverage)")
  parser.add_argument("--keep-outliers", action="store_true",
                      help="keep views whose reprojection error marks them as mis-detections")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem")
  parser.add_argument("--restauth", default="/run/secrets/calibration.auth")
  return parser


def per_view_errors(object_points, image_points, matrix, distortion):
  """Per-point reprojection errors (pixels) for each view, solving its pose."""
  errors = []
  for objp, imgp in zip(object_points, image_points):
    ok, rvec, tvec = cv2.solvePnP(objp, imgp, matrix, distortion,
                                  flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
      errors.append(np.array([np.inf]))
      continue
    projected, _ = cv2.projectPoints(objp, rvec, tvec, matrix, distortion)
    errors.append(np.linalg.norm(projected.reshape(-1, 2) - imgp, axis=1))
  return errors


def reprojection_error(object_points, image_points, matrix, distortion):
  """Mean and max reprojection error in pixels across all views."""
  flat = np.concatenate(per_view_errors(object_points, image_points, matrix, distortion))
  return float(np.mean(flat)), float(np.max(flat))


def reject_outlier_views(views, object_points, image_points, matrix, distortion):
  """Drop views whose error is far worse than typical.

  A tag mis-detection or a bad mesh raycast in one view skews the whole fit,
  so those are excluded rather than allowed to bend the lens model.
  """
  means = np.array([np.mean(e) for e in
                    per_view_errors(object_points, image_points, matrix, distortion)])
  threshold = np.median(means) * OUTLIER_ERROR_RATIO
  keep = [i for i, m in enumerate(means) if m <= threshold]
  for i, m in enumerate(means):
    if i not in keep:
      print(f"  dropping view {i} (pan={views[i]['pan']:+.4f} tilt={views[i]['tilt']:+.4f}): "
            f"mean error {m:.1f}px > {threshold:.1f}px")
  return keep


def main():
  args = build_argparser().parse_args()

  with open(args.input, encoding="utf-8") as handle:
    data = json.load(handle)
  views = data["views"]

  object_points = [np.array(v["points_3d"], dtype=np.float32) for v in views]
  image_points = [np.array(v["points_2d"], dtype=np.float32) for v in views]
  total = sum(len(p) for p in image_points)
  print(f"Loaded {len(views)} views / {total} points from {args.input}")

  rest = RESTClient(args.resturl, rootcert=args.rootcert, auth=args.restauth)
  camera = rest.getCamera(args.camera_uid)
  if camera.errors:
    print(f"Failed to fetch camera {args.camera_uid}: {camera.errors}")
    return 1
  intrinsics = camera["intrinsics"]
  width, height = camera["resolution"]
  matrix = np.array([[intrinsics["fx"], 0, intrinsics["cx"]],
                     [0, intrinsics["fy"], intrinsics["cy"]],
                     [0, 0, 1]], dtype=np.float64)
  distortion = np.zeros(5)

  before = reprojection_error(object_points, image_points, matrix, distortion)
  print(f"\nCurrent  fx={intrinsics['fx']:.2f} fy={intrinsics['fy']:.2f} "
        f"cx={intrinsics['cx']:.2f} cy={intrinsics['cy']:.2f}  no distortion")
  print(f"         reprojection error: mean {before[0]:.2f}px  max {before[1]:.2f}px")

  if not args.keep_outliers and len(views) > 2:
    keep = reject_outlier_views(views, object_points, image_points, matrix, distortion)
    if len(keep) < len(views):
      object_points = [object_points[i] for i in keep]
      image_points = [image_points[i] for i in keep]
      print(f"  using {len(keep)}/{len(views)} views")

  flags = DEFAULT_FLAGS
  if args.fit_principal_point:
    flags &= ~cv2.CALIB_FIX_PRINCIPAL_POINT
  if args.fit_aspect_ratio:
    flags &= ~cv2.CALIB_FIX_ASPECT_RATIO
  if args.fit_k2:
    flags &= ~cv2.CALIB_FIX_K2
  if args.fit_tangential:
    flags &= ~cv2.CALIB_ZERO_TANGENT_DIST
  if args.fit_k3:
    flags &= ~cv2.CALIB_FIX_K3

  # OpenCV holds whatever the seed matrix carries for the parameters these
  # flags fix, so seed the centre/square-pixel assumptions rather than the
  # camera's existing (possibly wrong) values.
  seed = matrix.copy()
  if flags & cv2.CALIB_FIX_PRINCIPAL_POINT:
    seed[0, 2], seed[1, 2] = width / 2.0, height / 2.0
  if flags & cv2.CALIB_FIX_ASPECT_RATIO:
    seed[0, 0] = seed[1, 1] = (seed[0, 0] + seed[1, 1]) / 2.0

  rms, matrix, distortion, _, _ = cv2.calibrateCamera(
      object_points, image_points, (width, height), seed, distortion.copy(),
      flags=flags)
  distortion = distortion.ravel()[:5]

  after = reprojection_error(object_points, image_points, matrix, distortion)
  fitted = {"fx": float(matrix[0, 0]), "fy": float(matrix[1, 1]),
            "cx": float(matrix[0, 2]), "cy": float(matrix[1, 2])}
  keys = ("k1", "k2", "p1", "p2", "k3")
  fitted_distortion = {k: float(v) for k, v in zip(keys, distortion)}

  print(f"\nFitted   fx={fitted['fx']:.2f} fy={fitted['fy']:.2f} "
        f"cx={fitted['cx']:.2f} cy={fitted['cy']:.2f}")
  print("         distortion " + "  ".join(f"{k}={v:+.5f}" for k, v in fitted_distortion.items()))
  print(f"         reprojection error: mean {after[0]:.2f}px  max {after[1]:.2f}px  (RMS {rms:.2f})")
  improvement = (1 - after[0] / before[0]) * 100 if before[0] else 0.0
  print(f"\nMean error improved by {improvement:.1f}%")

  config_block = {"resolution": [width, height],
                  "intrinsics": {k: round(v, 4) for k, v in fitted.items()},
                  "distortion": {k: round(v, 6) for k, v in fitted_distortion.items()}}
  print("\nAdd to this camera's entry in ptz_pose_service/config/cameras.json:\n")
  print(",\n".join(f'  "{k}": {json.dumps(v)}' for k, v in config_block.items()))

  if args.apply:
    update = dict(config_block)
    update["name"] = camera["name"]
    result = rest.updateCamera(args.camera_uid, update)
    if result.errors:
      print(f"\nFailed to apply: {result.errors}")
      return 1
    print(f"\nApplied to {args.camera_uid}")

  return 0


if __name__ == "__main__":
  exit(main())
