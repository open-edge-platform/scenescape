# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
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
from scene_common.transform import (
  MIN_POINTS_FOR_RANSAC,
  RANSAC_REPROJECTION_THRESHOLD_PX,
)

# Geometry-conditioning thresholds for fit diagnostics. These warn when the
# selected correspondences can still yield a low RMS while leaving pose /
# distortion poorly constrained (clustered or near-collinear layouts).
# Distinct from RANSAC_REPROJECTION_THRESHOLD_PX (outlier rejection) and from
# AprilTag autocalibration pose-acceptance gates.
MIN_INPLANE_SPREAD_RATIO = 0.05
MIN_VOLUME_SPREAD_RATIO = 0.05
# Treat map points as planar when the smallest principal axis is negligible
# relative to the middle one (same idea as coplanarity tests, separate cutoff).
PLANAR_AXIS_RATIO = 0.02
MIN_IMAGE_COVERAGE = 0.12
MIN_IMAGE_AXIS_FRACTION = 0.2
MIN_DEPTH_RANGE_RATIO = 1.5

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
  if len(obj_points) < MIN_POINTS_FOR_RANSAC:
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

def _singular_values_3d(points):
  """Principal-axis lengths (descending) for a 3D point set, padded to 3."""
  points = np.asarray(points, dtype=float).reshape(-1, 3)
  if len(points) == 0:
    return np.zeros(3)
  centered = points - points.mean(axis=0)
  singular_values = np.linalg.svd(centered, compute_uv=False)
  padded = np.zeros(3)
  padded[: min(3, len(singular_values))] = singular_values[:3]
  return padded

def assess_map_point_geometry(map_points):
  """Return spread metrics and warnings for map-side point layout."""
  singular_values = _singular_values_3d(map_points)
  s0, s1, s2 = [float(v) for v in singular_values]
  if s0 <= 1e-9:
    return {
      "mapInPlaneSpreadRatio": 0.0,
      "mapVolumeSpreadRatio": 0.0,
      "mapNearlyPlanar": True,
      "warnings": [
        "Map points are too concentrated for a stable pose. Move them farther "
        "apart across the scene (and in depth on a 3D map) so they form a wide "
        "triangle or rectangle, then recheck the fit."
      ],
    }

  in_plane_ratio = s1 / s0
  volume_ratio = s2 / s0
  nearly_planar = s1 <= 1e-9 or (s2 / s1) < PLANAR_AXIS_RATIO
  warnings = []
  if nearly_planar:
    if in_plane_ratio < MIN_INPLANE_SPREAD_RATIO:
      warnings.append(
        "Map points form a thin line. On the floor plan, drag them into a wide "
        "triangle or rectangle across the visible area — not along one line "
        "near the camera — then recheck the fit.")
  elif volume_ratio < MIN_VOLUME_SPREAD_RATIO:
    warnings.append(
      "Map points lack depth or height variation. On a 3D map, add pairs at "
      "different depths or heights (near and far), then recheck the fit.")

  return {
    "mapInPlaneSpreadRatio": in_plane_ratio,
    "mapVolumeSpreadRatio": volume_ratio,
    "mapNearlyPlanar": bool(nearly_planar),
    "warnings": warnings,
  }

def assess_image_point_coverage(cam_points, image_size):
  """Return image coverage metrics and warnings for camera-side layout."""
  points = np.asarray(cam_points, dtype=float).reshape(-1, 2)
  width, height = float(image_size[0]), float(image_size[1])
  image_area = max(width * height, 1.0)
  if len(points) == 0:
    return {
      "imageCoverage": 0.0,
      "imageWidthFraction": 0.0,
      "imageHeightFraction": 0.0,
      "warnings": [],
    }

  min_xy = points.min(axis=0)
  max_xy = points.max(axis=0)
  span = np.maximum(max_xy - min_xy, 0.0)
  width_fraction = float(span[0] / max(width, 1.0))
  height_fraction = float(span[1] / max(height, 1.0))
  coverage = float((span[0] * span[1]) / image_area)
  warnings = []
  if (coverage < MIN_IMAGE_COVERAGE or
      width_fraction < MIN_IMAGE_AXIS_FRACTION or
      height_fraction < MIN_IMAGE_AXIS_FRACTION):
    warnings.append(
      "Camera points cover too little of the frame. Move pairs toward the "
      "corners and edges (not one small cluster); low RMS on a tight group "
      "can still leave pose and distortion wrong elsewhere.")

  return {
    "imageCoverage": coverage,
    "imageWidthFraction": width_fraction,
    "imageHeightFraction": height_fraction,
    "warnings": warnings,
  }

def assess_point_depth_spread(map_points, rvec, tvec):
  """Warn when fitted correspondences sit at nearly the same camera depth."""
  points = np.asarray(map_points, dtype=float).reshape(-1, 3)
  rotation, _ = cv2.Rodrigues(rvec)
  camera_points = (rotation @ points.T).T + np.asarray(tvec, dtype=float).reshape(1, 3)
  depths = camera_points[:, 2]
  positive = depths[depths > 1e-6]
  if len(positive) < MIN_POINTS_FOR_RANSAC:
    return {"depthRangeRatio": None, "warnings": []}

  depth_range_ratio = float(positive.max() / positive.min())
  warnings = []
  if depth_range_ratio < MIN_DEPTH_RANGE_RATIO:
    warnings.append(
      "Calibration points sit at similar depth from the camera. Add some "
      "farther scene pairs (near and far), then recheck — near-camera "
      "clusters often fit local pixels but fail across the view.")
  return {"depthRangeRatio": depth_range_ratio, "warnings": warnings}

def assess_calibration_geometry(map_points, cam_points, image_size, rvec, tvec):
  """Aggregate geometry-conditioning diagnostics for the fitted correspondences."""
  map_assessment = assess_map_point_geometry(map_points)
  image_assessment = assess_image_point_coverage(cam_points, image_size)
  depth_assessment = assess_point_depth_spread(map_points, rvec, tvec)
  warnings = (map_assessment["warnings"] + image_assessment["warnings"] +
              depth_assessment["warnings"])
  return {
    "mapInPlaneSpreadRatio": map_assessment["mapInPlaneSpreadRatio"],
    "mapVolumeSpreadRatio": map_assessment["mapVolumeSpreadRatio"],
    "mapNearlyPlanar": map_assessment["mapNearlyPlanar"],
    "imageCoverage": image_assessment["imageCoverage"],
    "imageWidthFraction": image_assessment["imageWidthFraction"],
    "imageHeightFraction": image_assessment["imageHeightFraction"],
    "depthRangeRatio": depth_assessment["depthRangeRatio"],
    "geometryWarnings": warnings,
  }

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
          or len(request.data['mapPoints']) < MIN_POINTS_FOR_RANSAC:
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
      outlier_threshold = float(request.data.get(
        "outlierThresholdPx", RANSAC_REPROJECTION_THRESHOLD_PX))
      inlier_mask = None
      if reject_outliers:
        inlier_mask = find_inlier_mask(obj_points, img_points, intrinsics,
                                       distortion, outlier_threshold)

      ransac_mask = inlier_mask
      ransac_inlier_count = (int(ransac_mask.sum())
                             if ransac_mask is not None else None)
      rejection_applied = (ransac_mask is not None and
                           ransac_inlier_count >= MIN_POINTS_FOR_RANSAC)
      if rejection_applied:
        fit_obj_points = obj_points[ransac_mask]
        fit_img_points = img_points[ransac_mask]
        num_rejected = num_points - ransac_inlier_count
        log.info(f"Outlier rejection: kept {ransac_inlier_count} of "
                 f"{num_points} correspondences ({num_rejected} rejected)")
      else:
        if reject_outliers:
          log.warning("Outlier rejection found no usable inlier set; "
                      "fitting with all correspondences")
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
      # Preserve RANSAC-flagged outliers even when the fit fell back to all
      # points, so the UI can still highlight which pairs RANSAC rejected.
      rejected_indices = ([int(i) for i in np.where(~ransac_mask)[0]]
                          if ransac_mask is not None else [])

      euler, position = calculate_pose(rvecs[0], tvecs[0])
      geometry = assess_calibration_geometry(
        fit_obj_points, fit_img_points, image_size, rvecs[0], tvecs[0])
      if geometry["geometryWarnings"]:
        log.info("Calibration geometry warnings: " +
                 "; ".join(geometry["geometryWarnings"]))
      return Response({"euler": euler, "position": position, "mtx": mtx, "dist": dist,
                       "rmsError": float(rms_error),
                       "rejectionRequested": bool(reject_outliers),
                       "rejectionApplied": bool(rejection_applied),
                       "ransacInlierCount": ransac_inlier_count,
                       "fitPointCount": int(len(fit_obj_points)),
                       "rejectedIndices": rejected_indices,
                       "outlierThresholdPx": outlier_threshold,
                       "perPointErrors": [float(e) for e in point_errors],
                       "mapInPlaneSpreadRatio": geometry["mapInPlaneSpreadRatio"],
                       "mapVolumeSpreadRatio": geometry["mapVolumeSpreadRatio"],
                       "mapNearlyPlanar": geometry["mapNearlyPlanar"],
                       "imageCoverage": geometry["imageCoverage"],
                       "imageWidthFraction": geometry["imageWidthFraction"],
                       "imageHeightFraction": geometry["imageHeightFraction"],
                       "depthRangeRatio": geometry["depthRangeRatio"],
                       "geometryWarnings": geometry["geometryWarnings"]},
                      status=status.HTTP_200_OK)
    except (cv2.error, TypeError, ValueError, KeyError) as e:
      log.error(f"Error calculating intrinsics: {e}")
      return Response({"error": "Invalid values provided for calculation"},
                      status=status.HTTP_400_BAD_REQUEST)
