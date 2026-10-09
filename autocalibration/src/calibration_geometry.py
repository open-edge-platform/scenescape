# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Acceptance checks for 3D-2D correspondence geometry used in AprilTag calibration."""

import cv2
import numpy as np

# Below this ratio, a point set's smallest principal-axis spread is negligible
# relative to its largest and is poorly conditioned for solvePnP.
MIN_PNP_SPREAD_RATIO = 0.05
MAX_PLANAR_REPROJECTION_ERROR_PX = 5.0


def points_spread_ratio(points_3d):
  """Return the smallest-to-largest principal-axis spread ratio for 3D points.

  A value near zero indicates that the points are coplanar or have negligible
  spread along one axis. Fewer than four points or a collapsed point cloud
  returns 0.0.
  """
  points = np.asarray(points_3d, dtype=float)
  if len(points) < 4:
    return 0.0
  singular_values = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
  if singular_values[0] <= 1e-9:
    return 0.0
  return float(singular_values[-1] / singular_values[0])


def validate_correspondence_geometry(map_points_3d, points_2d, camera_pose,
                                     intrinsics, planar_map):
  """Check whether matched tag geometry supports a reliable pose.

  @param   map_points_3d  Matched tag centers in map coordinates (Nx3)
  @param   points_2d      Matched tag centers in image pixels (Nx2)
  @param   camera_pose    4x4 camera-to-map pose from solvePnP
  @param   intrinsics     3x3 camera matrix
  @param   planar_map     True for image floor plans, whose tag centers are planar by design

  @return  (spread_ratio, message) where message is None when the geometry is accepted
  """
  map_points_3d = np.asarray(map_points_3d, dtype=float)
  spread_ratio = points_spread_ratio(map_points_3d)
  if spread_ratio >= MIN_PNP_SPREAD_RATIO:
    return spread_ratio, None

  if not planar_map:
    return spread_ratio, (
        f"Matched AprilTags are too close to coplanar for a reliable pose solve "
        f"(spread ratio={spread_ratio:.3f}, minimum {MIN_PNP_SPREAD_RATIO}); "
        "use tags with more depth/height variation from this viewpoint.")

  singular_values = np.linalg.svd(map_points_3d - map_points_3d.mean(axis=0),
                                  compute_uv=False)
  if singular_values[0] <= 1e-9 or singular_values[1] / singular_values[0] < MIN_PNP_SPREAD_RATIO:
    return spread_ratio, "Matched AprilTags are too close to collinear for a reliable planar pose solve."

  world_to_camera = np.linalg.inv(camera_pose)
  rvec = cv2.Rodrigues(world_to_camera[:3, :3])[0]
  projected, _ = cv2.projectPoints(map_points_3d, rvec, world_to_camera[:3, 3],
                                   intrinsics, None)
  reprojection_error = np.sqrt(np.mean(np.sum(
      (projected.reshape(-1, 2) - np.asarray(points_2d)) ** 2, axis=1)))
  if not np.isfinite(reprojection_error) or reprojection_error > MAX_PLANAR_REPROJECTION_ERROR_PX:
    return spread_ratio, (
        f"Planar AprilTag pose reprojection error is too high "
        f"({reprojection_error:.1f} px, maximum {MAX_PLANAR_REPROJECTION_ERROR_PX} px).")
  return spread_ratio, None
