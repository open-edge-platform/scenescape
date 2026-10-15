# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import numpy as np
import pytest

import atag_camera_calibration_controller as calibration
from calibration_geometry import (
  MAX_PLANAR_REPROJECTION_ERROR_PX,
  MIN_PNP_SPREAD_RATIO,
  validate_camera_pose,
)
from scene_common.transform import (
  RANSAC_REPROJECTION_THRESHOLD_PX,
  scaled_reprojection_threshold_px,
)

INTRINSICS = np.array([[500., 0., 320.], [0., 500., 240.], [0., 0., 1.]])
PLANAR_POINTS = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]


def _validate(points_3d, camera_position=(0, 0, 2), planar_map=True, pixel_offset=0,
              tag_size=0.2, max_reprojection_error_px=None):
  points_3d = np.asarray(points_3d, dtype=float)
  camera_pose = np.eye(4)
  camera_pose[2, 3] = -2
  points_2d, _ = cv2.projectPoints(points_3d, np.zeros(3), np.array([0., 0., 2.]),
                                   INTRINSICS, None)
  # Shift only X so RMS reprojection error equals |pixel_offset|.
  points_2d = points_2d.reshape(-1, 2) + np.array([pixel_offset, 0.0])
  return validate_camera_pose(points_3d, points_3d.tolist(), points_2d, camera_pose,
                              np.asarray(camera_position, dtype=float), INTRINSICS,
                              tag_size, planar_map,
                              max_reprojection_error_px=max_reprojection_error_px)


def test_accepts_well_spread_tags():
  result = _validate([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], planar_map=False)
  assert result.accepted
  assert result.spread_ratio >= MIN_PNP_SPREAD_RATIO


def test_accepts_planar_tags_on_image_map():
  result = _validate(PLANAR_POINTS)
  assert result.accepted
  assert result.spread_ratio < MIN_PNP_SPREAD_RATIO


def test_planar_gate_matches_ransac_default():
  assert MAX_PLANAR_REPROJECTION_ERROR_PX == RANSAC_REPROJECTION_THRESHOLD_PX


@pytest.mark.parametrize("points, planar_map, offset, expected", [
    (PLANAR_POINTS, False, 0, "coplanar"),
    ([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], True, 0, "collinear"),
    # Default gate is RANSAC_REPROJECTION_THRESHOLD_PX (10); exceed it.
    (PLANAR_POINTS, True, RANSAC_REPROJECTION_THRESHOLD_PX + 5, "reprojection error"),
])
def test_rejects_degenerate_geometry(points, planar_map, offset, expected):
  result = _validate(points, planar_map=planar_map, pixel_offset=offset)
  assert not result.accepted
  assert expected in result.message


def test_custom_planar_reprojection_gate():
  # Offset equal to the default gate is accepted (strict greater-than), but a
  # tighter caller-supplied gate rejects the same correspondences.
  offset = RANSAC_REPROJECTION_THRESHOLD_PX
  assert _validate(PLANAR_POINTS, pixel_offset=offset).accepted
  assert not _validate(PLANAR_POINTS, pixel_offset=offset,
                       max_reprojection_error_px=offset - 1).accepted


def test_scaled_scene_gate_accepts_larger_reprojection():
  # Low-ppm scenes tighten the gate; high-ppm scenes relax it (clamped).
  low_ppm_gate = scaled_reprojection_threshold_px(50)
  high_ppm_gate = scaled_reprojection_threshold_px(200)
  assert low_ppm_gate < RANSAC_REPROJECTION_THRESHOLD_PX
  assert high_ppm_gate > RANSAC_REPROJECTION_THRESHOLD_PX

  offset = RANSAC_REPROJECTION_THRESHOLD_PX + 1
  assert not _validate(PLANAR_POINTS, pixel_offset=offset,
                       max_reprojection_error_px=low_ppm_gate).accepted
  assert _validate(PLANAR_POINTS, pixel_offset=offset,
                   max_reprojection_error_px=high_ppm_gate).accepted


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
