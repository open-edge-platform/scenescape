# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generic geometry checks for 3D-2D point correspondences."""

import numpy as np

MIN_PNP_SPREAD_RATIO = 0.05
MAX_PLANAR_REPROJECTION_ERROR_PX = 5.0


def point_spread_ratio(points_3d):
  """Return the smallest-to-largest principal-axis spread ratio.

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
  """Check whether 3D-2D point correspondence geometry supports a pose solve.

  @param   map_points_3d  Matched points in map coordinates (Nx3)
  @param   points_2d      Matched points in image pixels (Nx2)
  @param   camera_pose    4x4 camera-to-map pose
  @param   intrinsics     3x3 camera matrix
  @param   planar_map     True when the map's matched points are planar by design

  @return  (spread_ratio, message) where message is None when geometry is accepted
  """
  map_points_3d = np.asarray(map_points_3d, dtype=float)
  points_2d = np.asarray(points_2d, dtype=float)
  spread_ratio = point_spread_ratio(map_points_3d)
  if spread_ratio >= MIN_PNP_SPREAD_RATIO:
    return spread_ratio, None

  if not planar_map:
    return spread_ratio, (
        f"Matched points are too close to coplanar for a reliable pose solve "
        f"(spread ratio={spread_ratio:.3f}, minimum {MIN_PNP_SPREAD_RATIO}); "
        "use points with more depth/height variation from this viewpoint.")

  singular_values = np.linalg.svd(map_points_3d - map_points_3d.mean(axis=0),
                                  compute_uv=False)
  if singular_values[0] <= 1e-9 or singular_values[1] / singular_values[0] < MIN_PNP_SPREAD_RATIO:
    return spread_ratio, "Matched points are too close to collinear for a reliable planar pose solve."

  world_to_camera = np.linalg.inv(np.asarray(camera_pose, dtype=float))
  camera_points = (map_points_3d @ world_to_camera[:3, :3].T
                   + world_to_camera[:3, 3])
  projected_homogeneous = camera_points @ np.asarray(intrinsics, dtype=float).T
  with np.errstate(divide="ignore", invalid="ignore"):
    projected = projected_homogeneous[:, :2] / projected_homogeneous[:, 2, None]
  reprojection_error = np.sqrt(np.mean(np.sum((projected - points_2d) ** 2, axis=1)))
  if not np.isfinite(reprojection_error) or reprojection_error > MAX_PLANAR_REPROJECTION_ERROR_PX:
    return spread_ratio, (
        f"Planar point correspondence reprojection error is too high "
        f"({reprojection_error:.1f} px, maximum {MAX_PLANAR_REPROJECTION_ERROR_PX} px).")
  return spread_ratio, None


def validate_camera_pose_geometry(map_points_3d, scene_points_3d, points_2d,
                                  camera_pose, camera_position, intrinsics,
                                  planar_map, camera_below_tolerance):
  """Validate correspondence geometry and camera height relative to matched points.

  @param   map_points_3d          Matched points in map coordinates (Nx3)
  @param   scene_points_3d        Matched points in scene coordinates (Nx3)
  @param   points_2d              Matched points in image pixels (Nx2)
  @param   camera_pose            4x4 camera-to-map pose
  @param   camera_position        Camera translation in scene coordinates
  @param   intrinsics             3x3 camera matrix
  @param   planar_map             True when the map's matched points are planar by design
  @param   camera_below_tolerance Maximum distance below the lowest point, in scene units

  @return  (spread_ratio, message) where message is None when the pose is accepted
  """
  spread_ratio, message = validate_correspondence_geometry(
      map_points_3d, points_2d, camera_pose, intrinsics, planar_map)
  if message:
    return spread_ratio, message

  min_point_z = min(point[2] for point in scene_points_3d)
  if camera_position[2] < min_point_z - camera_below_tolerance:
    return spread_ratio, (
        f"Computed camera position (z={camera_position[2]:.2f}) is implausibly below the "
        f"matched points (lowest point z={min_point_z:.2f}); the matched points "
        "likely don't provide enough depth/height spread for a reliable pose solve. "
        "Try recalibrating from a view with points at more varied distances/heights.")
  return spread_ratio, None