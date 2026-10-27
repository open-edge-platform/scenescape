# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""AprilTag-specific camera pose acceptance checks."""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from scene_common.transform import RANSAC_REPROJECTION_THRESHOLD_PX

# Below this ratio, a point set's smallest principal-axis spread is negligible
# relative to its largest and is poorly conditioned for solvePnP.
MIN_PNP_SPREAD_RATIO = 0.05
# Fraction of the tag size the camera may sit below the lowest matched tag.
CAMERA_BELOW_TAG_TOLERANCE_TAG_FRACTION = 0.5


@dataclass(frozen=True)
class PoseValidation:
  spread_ratio: float
  message: Optional[str] = None

  @property
  def accepted(self):
    return self.message is None


def _points_spread_ratio(points_3d):
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


def _validate_correspondence_geometry(map_points_3d, points_2d, camera_pose,
                                      intrinsics, max_reprojection_error_px=None):
  """Check whether matched tag geometry supports a reliable pose.

  Well-spread 3D layouts are accepted on spread alone. Near-coplanar layouts
  (common for floor tags on both image maps and GLB scenes) are accepted when
  they are not collinear and the pose reprojects within the pixel gate. Map
  file type does not change these rules.
  """
  map_points_3d = np.asarray(map_points_3d, dtype=float)
  # Default planar gate matches the RANSAC inlier threshold so acceptance is
  # not stricter than the pose solve. Callers may pass a scene-scale-adjusted
  # value instead.
  max_error_px = (RANSAC_REPROJECTION_THRESHOLD_PX
                  if max_reprojection_error_px is None
                  else float(max_reprojection_error_px))
  spread_ratio = _points_spread_ratio(map_points_3d)
  if spread_ratio >= MIN_PNP_SPREAD_RATIO:
    return spread_ratio, None

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
  if not np.isfinite(reprojection_error) or reprojection_error > max_error_px:
    return spread_ratio, (
        f"Planar AprilTag pose reprojection error is too high "
        f"({reprojection_error:.1f} px, maximum {max_error_px} px).")
  return spread_ratio, None


def validate_camera_pose(map_points_3d, scene_points_3d, points_2d, camera_pose,
                         camera_position, intrinsics, tag_size,
                         max_reprojection_error_px=None):
  """Decide whether a solved AprilTag camera pose can be accepted.

  @param   map_points_3d    Matched tag centers in map coordinates (Nx3)
  @param   scene_points_3d  Matched tag centers in scene coordinates (Nx3)
  @param   points_2d        Matched tag centers in image pixels (Nx2)
  @param   camera_pose      4x4 camera-to-map pose from solvePnP
  @param   camera_position  Camera translation in scene coordinates
  @param   intrinsics       3x3 camera matrix
  @param   tag_size         AprilTag edge length in scene units
  @param   max_reprojection_error_px  Optional planar RMS gate (defaults to
                            RANSAC_REPROJECTION_THRESHOLD_PX). Prefer the
                            scene-scale-adjusted RANSAC threshold.

  @return  PoseValidation
  """
  spread_ratio, message = _validate_correspondence_geometry(
      map_points_3d, points_2d, camera_pose, intrinsics,
      max_reprojection_error_px=max_reprojection_error_px)
  if message:
    return PoseValidation(spread_ratio, message)

  min_tag_z = min(point[2] for point in scene_points_3d)
  if camera_position[2] < min_tag_z - tag_size * CAMERA_BELOW_TAG_TOLERANCE_TAG_FRACTION:
    return PoseValidation(spread_ratio, (
        f"Computed camera position (z={camera_position[2]:.2f}) is implausibly below the "
        f"AprilTags it observed (lowest tag z={min_tag_z:.2f}); the matched tags "
        "likely don't provide enough depth/height spread for a reliable pose solve. "
        "Try recalibrating from a view with tags at more varied distances/heights."))
  return PoseValidation(spread_ratio)
