# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""AprilTag-specific camera pose acceptance checks."""

from dataclasses import dataclass
from typing import Optional

from scene_common.calibration_geometry import validate_camera_pose_geometry

# Fraction of the tag size the camera may sit below the lowest matched tag.
CAMERA_BELOW_TAG_TOLERANCE_TAG_FRACTION = 0.5
PLANAR_MAP_EXTENSIONS = ('.png', '.jpg', '.jpeg')


@dataclass(frozen=True)
class PoseValidation:
  spread_ratio: float
  message: Optional[str] = None

  @property
  def accepted(self):
    return self.message is None


def validate_camera_pose(map_points_3d, scene_points_3d, points_2d, camera_pose,
                         camera_position, intrinsics, tag_size, planar_map):
  """Decide whether a solved AprilTag camera pose can be accepted.

  @param   map_points_3d    Matched tag centers in map coordinates (Nx3)
  @param   scene_points_3d  Matched tag centers in scene coordinates (Nx3)
  @param   points_2d        Matched tag centers in image pixels (Nx2)
  @param   camera_pose      4x4 camera-to-map pose from solvePnP
  @param   camera_position  Camera translation in scene coordinates
  @param   intrinsics       3x3 camera matrix
  @param   tag_size         AprilTag edge length in scene units
  @param   planar_map       True for image floor plans

  @return  PoseValidation
  """
  camera_below_tolerance = tag_size * CAMERA_BELOW_TAG_TOLERANCE_TAG_FRACTION
  spread_ratio, message = validate_camera_pose_geometry(
      map_points_3d, scene_points_3d, points_2d, camera_pose, camera_position,
      intrinsics, planar_map, camera_below_tolerance)
  return PoseValidation(spread_ratio, message)
