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
  points_are_coplanar,
  scaled_reprojection_threshold_px,
  solve_pnpransac,
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
# Match manager/static/js/constants.js MAX_CALIBRATION_POINTS — caps OpenCV work.
MAX_CALIBRATION_CORRESPONDENCES = 50
# OpenCV calibrateCamera accepted distortion lengths.
SUPPORTED_DISTORTION_LENGTHS = (4, 5, 8, 12, 14)
# Reject absurd image sizes that would allocate huge OpenCV buffers.
MAX_IMAGE_DIMENSION_PX = 16384

def y_up_to_y_down(rotation_matrix):
  rotate_y = Rotation.from_euler('Y', np.pi).as_matrix()
  rotate_z = Rotation.from_euler('Z', np.pi).as_matrix()
  return rotation_matrix @ rotate_y @ rotate_z

def calculate_pose(rvec, tvec):
  """Return scene-frame euler (rad), position, and 4x4 camera pose matrix.

  pose_matrix matches the inverted OpenCV→scene transform used by the
  calibration UI preview (setCameraPose), so clients can apply one fitted pose.
  """
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

  return euler, position, T_inv

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


def needs_pose_only_fit(obj_points):
  """True when calibrateCamera cannot initialize extrinsics for this set.

  OpenCV's calibrateCamera uses iterative PnP/DLT that requires at least six
  non-coplanar points. Smaller non-coplanar sets (typical of 3D map cal or
  RANSAC-reduced inliers) must use a pose-only SQPNP path instead. Planar
  floor-plan layouts still work with calibrateCamera.
  """
  return (len(obj_points) < 6 and not points_are_coplanar(obj_points))


def as_distortion_column(distortion):
  """Normalize distortion coefficients to an OpenCV-style column vector (N, 1)."""
  return np.asarray(distortion, dtype=np.float64).reshape(-1, 1)


def validate_correspondence_arrays(map_points, cam_points):
  """Validate and coerce correspondence arrays to float32 Nx3 / Nx2.

  @return  (obj_points, img_points, error_message). error_message is None on success.
  """
  try:
    obj_points = np.asarray(map_points, dtype=np.float32)
    img_points = np.asarray(cam_points, dtype=np.float32)
  except (TypeError, ValueError):
    return None, None, "mapPoints and camPoints must be numeric arrays"

  if obj_points.ndim != 2 or obj_points.shape[1] not in (2, 3):
    return None, None, "mapPoints must be an array of 2D or 3D points"
  if img_points.ndim != 2 or img_points.shape[1] != 2:
    return None, None, "camPoints must be an array of 2D image points"
  if len(obj_points) != len(img_points):
    return None, None, "mapPoints and camPoints must have the same length"
  if len(obj_points) > MAX_CALIBRATION_CORRESPONDENCES:
    return None, None, (
      f"At most {MAX_CALIBRATION_CORRESPONDENCES} correspondence pairs are supported")
  if not (np.isfinite(obj_points).all() and np.isfinite(img_points).all()):
    return None, None, "mapPoints and camPoints must contain finite values"

  if obj_points.shape[1] == 2:
    obj_points = np.hstack(
      (obj_points, np.zeros((obj_points.shape[0], 1), dtype=np.float32)))
  return obj_points, img_points, None


def validate_intrinsics_matrix(intrinsics):
  """Validate and coerce a 3x3 camera matrix.

  @return  (matrix, error_message). error_message is None on success.
  """
  try:
    matrix = np.asarray(intrinsics, dtype=np.float64)
  except (TypeError, ValueError):
    return None, "intrinsics must be a 3x3 numeric matrix"
  if matrix.shape != (3, 3):
    return None, "intrinsics must be a 3x3 matrix"
  if not np.isfinite(matrix).all():
    return None, "intrinsics must contain finite values"
  if matrix[0, 0] <= 0 or matrix[1, 1] <= 0:
    return None, "intrinsics fx and fy must be positive"
  return matrix, None


def validate_distortion_coefficients(distortion):
  """Validate distortion coeffs; NaN becomes 0.0 like prior calibrate path.

  @return  (column_vector, error_message). error_message is None on success.
  """
  try:
    coeffs = np.asarray(distortion, dtype=np.float64).reshape(-1)
  except (TypeError, ValueError):
    return None, "distortion must be a numeric array"
  if coeffs.size not in SUPPORTED_DISTORTION_LENGTHS:
    return None, (
      "distortion must have 4, 5, 8, 12, or 14 coefficients")
  if np.isinf(coeffs).any():
    return None, "distortion must contain finite values"
  # Preserve historical NaN→0 behavior for unlocked/empty coeff fields.
  coeffs = np.nan_to_num(coeffs, nan=0.0, posinf=0.0, neginf=0.0)
  return as_distortion_column(coeffs), None


def validate_image_size(image_size):
  """Validate image width/height as positive ints within a safe bound.

  @return  ((width, height), error_message). error_message is None on success.
  """
  try:
    if not isinstance(image_size, (list, tuple)) or len(image_size) != 2:
      return None, "imageSize must be [width, height]"
    width, height = int(image_size[0]), int(image_size[1])
  except (TypeError, ValueError):
    return None, "imageSize must be [width, height] integers"
  if width <= 0 or height <= 0:
    return None, "imageSize width and height must be positive"
  if width > MAX_IMAGE_DIMENSION_PX or height > MAX_IMAGE_DIMENSION_PX:
    return None, (
      f"imageSize dimensions must be at most {MAX_IMAGE_DIMENSION_PX} pixels")
  return (width, height), None


def fit_pose_fixed_intrinsics(obj_points, img_points, intrinsics, distortion):
  """Pose-only SQPNP fit that keeps the supplied intrinsics and distortion fixed.

  Used when lens parameters are locked, or sparse non-coplanar correspondences
  prevent calibrateCamera from initializing.
  """
  ok, rvec, tvec = cv2.solvePnP(
    obj_points, img_points, intrinsics, distortion, flags=cv2.SOLVEPNP_SQPNP)
  if not ok:
    raise cv2.error("solvePnP failed for pose-only calibration fit")
  errors = per_point_reprojection_errors(
    obj_points, img_points, rvec, tvec, intrinsics, distortion)
  rms_error = float(np.sqrt(np.mean(np.square(errors))))
  return (rms_error, np.asarray(intrinsics, dtype=np.float64).copy(),
          as_distortion_column(distortion), [rvec], [tvec])

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

def parse_reject_outliers(data):
  """Return rejectOutliers as a real JSON boolean, or an error message."""
  if "rejectOutliers" not in data:
    return True, None
  value = data["rejectOutliers"]
  # Reject truthy non-booleans (e.g. "false", 1) that would mislead OpenCV paths.
  if not isinstance(value, bool):
    return None, "rejectOutliers must be a boolean"
  return value, None

def parse_pixels_per_meter(data):
  """Return scene map scale (pixels/meter), or None when omitted / invalid-empty.

  Explicit invalid values (non-positive, non-finite, wrong type) return an error.
  Omitted or null means "use the reference default threshold".
  """
  if "pixelsPerMeter" not in data or data["pixelsPerMeter"] is None:
    return None, None
  value = data["pixelsPerMeter"]
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None, "pixelsPerMeter must be a positive finite number"
  ppm = float(value)
  if not np.isfinite(ppm) or ppm <= 0:
    return None, "pixelsPerMeter must be a positive finite number"
  return ppm, None

def parse_outlier_threshold_px(data):
  """Return a positive finite outlier threshold in camera-image pixels.

  Explicit outlierThresholdPx wins (true image-space gate). Otherwise the
  threshold is derived from scene map pixelsPerMeter via
  scaled_reprojection_threshold_px — a map-resolution heuristic, not camera
  resolution or focal-length scaling.
  """
  if "outlierThresholdPx" in data:
    value = data["outlierThresholdPx"]
    # bool is a subclass of int; reject it so true/false cannot become 1.0/0.0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
      return None, "outlierThresholdPx must be a positive finite number"
    threshold = float(value)
    if not np.isfinite(threshold) or threshold <= 0:
      return None, "outlierThresholdPx must be a positive finite number"
    return threshold, None

  ppm, ppm_error = parse_pixels_per_meter(data)
  if ppm_error:
    return None, ppm_error
  if ppm is None:
    return float(RANSAC_REPROJECTION_THRESHOLD_PX), None
  return scaled_reprojection_threshold_px(ppm), None

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
          or len(request.data['mapPoints']) < MIN_POINTS_FOR_RANSAC \
          or len(request.data['mapPoints']) > MAX_CALIBRATION_CORRESPONDENCES:
        return Response({"error": "Invalid number of points provided for calculation."},
                        status=status.HTTP_400_BAD_REQUEST)

      reject_outliers, reject_error = parse_reject_outliers(request.data)
      if reject_error:
        return Response({"error": reject_error}, status=status.HTTP_400_BAD_REQUEST)
      outlier_threshold, threshold_error = parse_outlier_threshold_px(request.data)
      if threshold_error:
        return Response({"error": threshold_error},
                        status=status.HTTP_400_BAD_REQUEST)

      obj_points, img_points, points_error = validate_correspondence_arrays(
        request.data['mapPoints'], request.data['camPoints'])
      if points_error:
        return Response({"error": points_error},
                        status=status.HTTP_400_BAD_REQUEST)
      num_points = len(obj_points)

      intrinsics, intrinsics_error = validate_intrinsics_matrix(
        request.data['intrinsics'])
      if intrinsics_error:
        return Response({"error": intrinsics_error},
                        status=status.HTTP_400_BAD_REQUEST)
      distortion, distortion_error = validate_distortion_coefficients(
        request.data['distortion'])
      if distortion_error:
        return Response({"error": distortion_error},
                        status=status.HTTP_400_BAD_REQUEST)
      image_size, image_size_error = validate_image_size(request.data['imageSize'])
      if image_size_error:
        return Response({"error": image_size_error},
                        status=status.HTTP_400_BAD_REQUEST)

      fix_intrinsics = request.data.get("fixIntrinsics", {})

      # Robust outlier rejection: fit a RANSAC PnP model and keep only the
      # inlier correspondences for the calibration fit. Falls back to using
      # all points if RANSAC cannot find a valid consensus set.
      # RANSAC uses the request intrinsics/distortion as a fixed model; unlocked
      # lens parameters are refined afterward by calibrateCamera on inliers.
      inlier_mask = None
      if reject_outliers:
        _, _, inlier_mask = solve_pnpransac(
          obj_points, img_points, intrinsics, distortion,
          reprojection_threshold_px=outlier_threshold)

      ransac_inlier_count = (int(inlier_mask.sum())
                             if inlier_mask is not None else None)
      rejection_applied = (inlier_mask is not None and
                           ransac_inlier_count >= MIN_POINTS_FOR_RANSAC)
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
        fit_obj_points = obj_points
        fit_img_points = img_points

      lens_locked = all(fix_intrinsics.get(key, True) for key in
                        ("fx", "fy", "cx", "cy", "k1", "k2", "k3", "p1", "p2"))
      if lens_locked or needs_pose_only_fit(fit_obj_points):
        # Intrinsics/distortion stay at the request values.
        log.info("Using pose-only SQPNP fit for "
                 f"{len(fit_obj_points)} correspondences")
        rms_error, mtx, dist, rvecs, tvecs = fit_pose_fixed_intrinsics(
          fit_obj_points, fit_img_points, intrinsics, distortion)
      else:
        flags = build_calibrate_flags(fix_intrinsics, len(fit_obj_points))
        rms_error, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
          [fit_obj_points], [fit_img_points], image_size, intrinsics,
          distortion, flags=flags)
        dist = as_distortion_column(dist)

      # Per-point reprojection errors of every correspondence (inliers and
      # rejected outliers alike) under the final fitted model, so the caller
      # can surface which points were discarded and why.
      point_errors = per_point_reprojection_errors(obj_points, img_points,
                                                   rvecs[0], tvecs[0], mtx, dist)
      # Preserve RANSAC-flagged outliers even when the fit fell back to all
      # points, so the UI can still highlight which pairs RANSAC rejected.
      rejected_indices = ([int(i) for i in np.where(~inlier_mask)[0]]
                          if inlier_mask is not None else [])

      euler, position, pose_matrix = calculate_pose(rvecs[0], tvecs[0])
      geometry = assess_calibration_geometry(
        fit_obj_points, fit_img_points, image_size, rvecs[0], tvecs[0])
      if geometry["geometryWarnings"]:
        log.info("Calibration geometry warnings: " +
                 "; ".join(geometry["geometryWarnings"]))
      return Response({
                       "euler": np.asarray(euler, dtype=np.float64).reshape(-1).tolist(),
                       "position": np.asarray(position, dtype=np.float64).reshape(-1).tolist(),
                       "poseMatrix": np.asarray(pose_matrix, dtype=np.float64).tolist(),
                       "mtx": mtx, "dist": dist,
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
