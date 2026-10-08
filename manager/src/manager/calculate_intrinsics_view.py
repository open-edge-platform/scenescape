# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import numpy as np
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from scipy.spatial.transform import Rotation

from manager.api import IsAdminOrReadOnly

from scene_common import log

# Minimum correspondences needed for a PnP-based pose estimate (and hence for
# RANSAC-based outlier rejection and for cv2.calibrateCamera).
MIN_POINTS_FOR_FIT = 4
# Default RANSAC reprojection threshold (pixels) used to flag bad
# map-point/camera-point correspondences as outliers.
DEFAULT_OUTLIER_THRESHOLD_PX = 5.0

def y_up_to_y_down(rotation_matrix):
  rotate_y = Rotation.from_euler('Y', np.pi).as_matrix()
  rotate_z = Rotation.from_euler('Z', np.pi).as_matrix()
  return rotation_matrix @ rotate_y @ rotate_z

def calculate_pose(rvec, tvec):
  R, _ = cv2.Rodrigues(rvec)
  T = np.array([
    [R[0, 0], R[0, 1], R[0, 2], tvec[0, 0]],
    [-R[1, 0], -R[1, 1], -R[1, 2], -tvec[1, 0]],
    [-R[2, 0], -R[2, 1], -R[2, 2], -tvec[2, 0]],
    [0, 0, 0, 1]
  ])
  T_inv = np.linalg.inv(T)

  euler = Rotation.from_matrix(y_up_to_y_down(T_inv[:3, :3])).as_euler('XYZ', degrees=False)

  position = T_inv[:3, 3]

  return euler, position

def find_inlier_mask(obj_points, img_points, intrinsics, distortion,
                     reprojection_threshold_px):
  """Use RANSAC PnP to identify outlier correspondences.

  Returns a boolean mask (True = inlier) over the correspondences, or None if
  a robust estimate could not be produced (too few points, RANSAC failure).
  """
  if len(obj_points) < MIN_POINTS_FOR_FIT:
    return None
  try:
    _, _, _, inliers = cv2.solvePnPRansac(
      obj_points, img_points, intrinsics, distortion,
      reprojectionError=reprojection_threshold_px,
      confidence=0.99,
      flags=cv2.SOLVEPNP_AP3P)
  except cv2.error as e:
    log.warning(f"RANSAC outlier rejection failed: {e}")
    return None
  if inliers is None or len(inliers) == 0:
    return None
  mask = np.zeros(len(obj_points), dtype=bool)
  mask[inliers.ravel()] = True
  return mask

def per_point_reprojection_errors(obj_points, img_points, rvec, tvec, mtx, dist):
  """Reprojection error (pixels) of every correspondence under the fitted model."""
  projected, _ = cv2.projectPoints(obj_points, rvec, tvec, mtx, dist)
  projected = projected.reshape(-1, 2)
  return np.linalg.norm(img_points - projected, axis=1)

def build_calibrate_flags(fix_intrinsics, num_points):
  # FIXME: Consolidate pose calculation with the one in scene_common/transform.py
  flags = cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_ASPECT_RATIO
  calibrate_flags = [
    (["fx", "fy"], cv2.CALIB_FIX_FOCAL_LENGTH, 6),
    (["cx", "cy"], cv2.CALIB_FIX_PRINCIPAL_POINT, 6),
    (["k1"], cv2.CALIB_FIX_K1, 8),
    (["k2"], cv2.CALIB_FIX_K2, 8),
    (["k3"], cv2.CALIB_FIX_K3, 8),
    (["p1", "p2"], cv2.CALIB_FIX_TANGENT_DIST, 8)
  ]

  for keys, flag, min_points in calibrate_flags:
    if any(fix_intrinsics.get(key, True) for key in keys) or num_points < min_points:
      flags |= flag
  return flags

class CalculateCameraIntrinsics(APIView):
  authentication_classes = [TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def post(self, request):
    log.info(f"Received request to calculate intrinsics with {request.data}")
    try:
      required_fields = ['mapPoints', 'camPoints', 'intrinsics', 'distortion', 'imageSize']
      missing_fields = [field for field in required_fields if field not in request.data]
      if missing_fields:
        return Response({"error": f"Missing required fields: {', '.join(missing_fields)}"},
                        status=status.HTTP_400_BAD_REQUEST)

      if len(request.data['mapPoints']) != len(request.data['camPoints']) \
          or len(request.data['mapPoints']) < MIN_POINTS_FOR_FIT:
        return Response({"error": "Invalid number of points provided for calculation."},
                        status=status.HTTP_400_BAD_REQUEST)

      obj_points = np.array(request.data['mapPoints'], dtype=np.float32)
      img_points = np.array(request.data['camPoints'], dtype=np.float32)
      num_points = len(obj_points)

      intrinsics = np.array(request.data['intrinsics'], dtype=np.float64)
      distortion = np.array(request.data['distortion'], dtype=np.float64)
      distortion = np.nan_to_num(distortion, nan=0.0)
      image_size = tuple(map(int, request.data['imageSize']))

      fix_intrinsics = request.data.get("fixIntrinsics", {})

      # Robust outlier rejection: fit a RANSAC PnP model and keep only the
      # inlier correspondences for the calibration fit. Falls back to using
      # all points if RANSAC cannot find a valid consensus set.
      reject_outliers = request.data.get("rejectOutliers", True)
      outlier_threshold = float(request.data.get("outlierThresholdPx",
                                                 DEFAULT_OUTLIER_THRESHOLD_PX))
      inlier_mask = None
      if reject_outliers:
        inlier_mask = find_inlier_mask(obj_points, img_points, intrinsics,
                                       distortion, outlier_threshold)

      ransac_inlier_count = (int(inlier_mask.sum())
                             if inlier_mask is not None else None)
      rejection_applied = (inlier_mask is not None and
                           ransac_inlier_count >= MIN_POINTS_FOR_FIT)
      if rejection_applied:
        fit_obj_points = obj_points[inlier_mask]
        fit_img_points = img_points[inlier_mask]
        num_rejected = num_points - ransac_inlier_count
        log.info(f"Outlier rejection: kept {ransac_inlier_count} of "
                 f"{num_points} correspondences ({num_rejected} rejected)")
      else:
        if reject_outliers:
          log.warning("Outlier rejection found no usable inlier set; "
                      "fitting with all correspondences")
        inlier_mask = np.ones(num_points, dtype=bool)
        fit_obj_points = obj_points
        fit_img_points = img_points

      flags = build_calibrate_flags(fix_intrinsics, len(fit_obj_points))

      rms_error, mtx, dist, rvecs, tvecs = cv2.calibrateCamera([fit_obj_points],
                                                              [fit_img_points],
                                                              image_size, intrinsics,
                                                              distortion, flags=flags)

      # Per-point reprojection errors of every correspondence (inliers and
      # rejected outliers alike) under the final fitted model, so the caller
      # can surface which points were discarded and why.
      point_errors = per_point_reprojection_errors(obj_points, img_points,
                                                   rvecs[0], tvecs[0], mtx, dist)
      rejected_indices = [int(i) for i in np.where(~inlier_mask)[0]]

      euler, position = calculate_pose(rvecs[0], tvecs[0])
      return Response({"euler": euler, "position": position, "mtx": mtx, "dist": dist,
                       "rmsError": float(rms_error),
                       "rejectionRequested": bool(reject_outliers),
                       "rejectionApplied": bool(rejection_applied),
                       "ransacInlierCount": ransac_inlier_count,
                       "fitPointCount": int(len(fit_obj_points)),
                       "rejectedIndices": rejected_indices,
                       "outlierThresholdPx": outlier_threshold,
                       "perPointErrors": [float(e) for e in point_errors]},
                      status=status.HTTP_200_OK)
    except (cv2.error, TypeError, ValueError, KeyError) as e:
      log.error(f"Error calculating intrinsics: {e}")
      return Response({"error": "Invalid values provided for calculation"},
                      status=status.HTTP_400_BAD_REQUEST)
