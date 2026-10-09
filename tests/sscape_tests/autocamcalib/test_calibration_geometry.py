# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import numpy as np
import pytest

import atag_camera_calibration_controller as calibration
from calibration_geometry import MIN_PNP_SPREAD_RATIO, validate_camera_pose

INTRINSICS = np.array([[500., 0., 320.], [0., 500., 240.], [0., 0., 1.]])


def _validate(points_3d, camera_position=(0, 0, 2), planar_map=True, pixel_offset=0,
              tag_size=0.2):
  points_3d = np.asarray(points_3d, dtype=float)
  camera_pose = np.eye(4)
  camera_pose[2, 3] = -2
  points_2d, _ = cv2.projectPoints(points_3d, np.zeros(3), np.array([0., 0., 2.]),
                                   INTRINSICS, None)
  points_2d = points_2d.reshape(-1, 2) + pixel_offset
  return validate_camera_pose(points_3d, points_3d.tolist(), points_2d, camera_pose,
                              np.asarray(camera_position, dtype=float), INTRINSICS,
                              tag_size, planar_map)


def test_accepts_well_spread_tags():
  result = _validate([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], planar_map=False)
  assert result.accepted
  assert result.spread_ratio >= MIN_PNP_SPREAD_RATIO


def test_accepts_planar_tags_on_image_map():
  result = _validate([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
  assert result.accepted
  assert result.spread_ratio < MIN_PNP_SPREAD_RATIO


@pytest.mark.parametrize("points, planar_map, offset, expected", [
    ([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], False, 0, "coplanar"),
    ([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], True, 0, "collinear"),
    ([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], True, 10, "reprojection error"),
])
def test_rejects_degenerate_geometry(points, planar_map, offset, expected):
  result = _validate(points, planar_map=planar_map, pixel_offset=offset)
  assert not result.accepted
  assert expected in result.message


def test_rejects_camera_below_tags_beyond_tag_scaled_tolerance():
  points = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
  assert not _validate(points, camera_position=(0, 0, -0.2), planar_map=False).accepted
  assert _validate(points, camera_position=(0, 0, -0.15), planar_map=False,
                   tag_size=0.4).accepted


def test_pending_response_counts_frames_then_fails():
  controller = object.__new__(calibration.ApriltagCameraCalibrationController)
  controller.frame_count = {}
  for _ in range(calibration.MAX_WAIT_FRAME_COUNT):
    assert controller._pending_response("cam")["status"] == "pending"
  with pytest.raises(TypeError, match="Fewer than"):
    controller._pending_response("cam")