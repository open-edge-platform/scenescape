#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Offline lens solver ported from the lab calibrate_intrinsics.py."""

import cv2
import numpy as np

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
      where = (f"pan={views[i]['pan']:+.4f} tilt={views[i]['tilt']:+.4f}"
               if views[i].get("pan") is not None else "static")
      print(f"  dropping view {i} ({where}): mean error {m:.1f}px > {threshold:.1f}px")
  return keep


def fit_lens(data, camera):
  """Fit local AprilTag views without changing the Manager camera."""
  views = data["views"]

  object_points = [np.array(v["points_3d"], dtype=np.float32) for v in views]
  image_points = [np.array(v["points_2d"], dtype=np.float32) for v in views]
  total = sum(len(p) for p in image_points)
  print(f"Loaded {len(views)} views / {total} points")

  intrinsics = camera["intrinsics"]
  if not intrinsics or not all(k in intrinsics for k in ("fx", "fy", "cx", "cy")):
    raise ValueError("Set approximate fx, fy, cx, cy intrinsics in Manager before lens fitting")
  width, height = data.get("image_size") or camera["resolution"]
  if list(camera["resolution"]) != [width, height]:
    print(f"Stored resolution {camera['resolution']} doesn't match the camera's frames "
          f"{[width, height]}; fitting {[width, height]} locally")
  matrix = np.array([[intrinsics["fx"], 0, intrinsics["cx"]],
                     [0, intrinsics["fy"], intrinsics["cy"]],
                     [0, 0, 1]], dtype=np.float64)
  distortion = np.zeros(5)

  before = reprojection_error(object_points, image_points, matrix, distortion)
  print(f"\nCurrent  fx={intrinsics['fx']:.2f} fy={intrinsics['fy']:.2f} "
        f"cx={intrinsics['cx']:.2f} cy={intrinsics['cy']:.2f}  no distortion")
  print(f"         reprojection error: mean {before[0]:.2f}px  max {before[1]:.2f}px")

  if len(views) > 2:
    keep = reject_outlier_views(views, object_points, image_points, matrix, distortion)
    if len(keep) < len(views):
      object_points = [object_points[i] for i in keep]
      image_points = [image_points[i] for i in keep]
      print(f"  using {len(keep)}/{len(views)} views")

  flags = DEFAULT_FLAGS

  # OpenCV holds whatever the seed matrix carries for the parameters these
  # flags fix, so seed the centre/square-pixel assumptions rather than the
  # camera's existing (possibly wrong) values.
  seed = matrix.copy()
  if flags & cv2.CALIB_FIX_PRINCIPAL_POINT:
    seed[0, 2], seed[1, 2] = width / 2.0, height / 2.0
  if flags & cv2.CALIB_FIX_ASPECT_RATIO:
    seed[0, 0] = seed[1, 1] = (seed[0, 0] + seed[1, 1]) / 2.0

  rms, matrix, distortion, _, _, std_intrinsics, _, _ = cv2.calibrateCameraExtended(
      object_points, image_points, (width, height), seed, distortion.copy(),
      flags=flags)
  distortion = distortion.ravel()[:5]
  # Order: fx, fy, cx, cy, k1, ...; with a fixed aspect ratio the focal sigma is in fy.
  std = std_intrinsics.ravel()
  if not np.all(np.isfinite(np.concatenate(([rms], matrix.ravel(), distortion, std)))):
    raise ValueError("Lens fit or its uncertainty is non-finite; improve view geometry")
  focal_std = max(std[0], std[1])

  after = reprojection_error(object_points, image_points, matrix, distortion)
  fitted = {"fx": float(matrix[0, 0]), "fy": float(matrix[1, 1]),
            "cx": float(matrix[0, 2]), "cy": float(matrix[1, 2])}
  keys = ("k1", "k2", "p1", "p2", "k3")
  fitted_distortion = {k: float(v) for k, v in zip(keys, distortion)}

  print(f"\nFitted   fx={fitted['fx']:.2f} fy={fitted['fy']:.2f} "
        f"cx={fitted['cx']:.2f} cy={fitted['cy']:.2f}")
  print("         distortion " + "  ".join(f"{k}={v:+.5f}" for k, v in fitted_distortion.items()))
  print(f"         reprojection error: mean {after[0]:.2f}px  max {after[1]:.2f}px  (RMS {rms:.2f})")
  print(f"         uncertainty (1 sigma): f ±{focal_std:.1f}  k1 ±{std[4]:.4f}")
  poorly_constrained = bool(focal_std > 0.05 * fitted["fx"] or std[4] > 0.05)
  if poorly_constrained:
    print("         WARNING: poorly constrained - the tags don't span enough of the frame "
          "or of depth; don't trust this fit")
  improvement = (1 - after[0] / before[0]) * 100 if before[0] else 0.0
  print(f"\nMean error improved by {improvement:.1f}%")

  config_block = {"resolution": [width, height],
                  "intrinsics": {k: round(v, 4) for k, v in fitted.items()},
                  "distortion": {k: round(v, 6) for k, v in fitted_distortion.items()}}
  return {"config": config_block, "poorly_constrained": poorly_constrained,
          "mean_error_before": before[0], "mean_error_after": after[0],
          "rms_px": float(rms)}
