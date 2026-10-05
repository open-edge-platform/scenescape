# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from scene_common.ptz_pose import (
    apply_backlash,
    axis_angle_degrees,
    backlash_degrees_at,
    compose_ptz_rotation,
    compose_ptz_transform,
    rotation_from_ptz_delta,
    scale_from_fov,
)

TEST_NAME = "NEX-T28222"


class TestPTZPoseMath:
  def test_axis_angle_uses_curve_and_inversion(self):
    assert axis_angle_degrees(2.0, 10.0, [1.0, 3.0], invert=True) == -7.0

  def test_backlash_limits_physical_motion(self):
    assert apply_backlash(0.0, 4.0, 2.0) == 3.0
    assert apply_backlash(0.0, -4.0, 2.0) == -3.0
    assert apply_backlash(None, 4.0, 2.0) == 4.0

  def test_backlash_curve_interpolates_and_clamps(self):
    backlash = [[-1.0, 1.0], [1.0, 3.0]]
    assert backlash_degrees_at(backlash, 0.0) == 2.0
    assert backlash_degrees_at(backlash, 2.0) == 3.0
    assert backlash_degrees_at([], 0.0) == 0.0

  def test_backlash_curve_rejects_duplicate_positions(self):
    with pytest.raises(ValueError, match="unique"):
      backlash_degrees_at([[0.0, 1.0], [0.0, 2.0]], 0.0)

  def test_rotation_composition_matches_independent_matrix_product(self):
    home = [15.0, -20.0, 35.0]
    pan_axis = [0.1, -0.2, 1.0]
    actual = compose_ptz_rotation(home, 23.0, -8.0, pan_axis)
    expected = (
        Rotation.from_rotvec(np.asarray(pan_axis) / np.linalg.norm(pan_axis) *
                              math.radians(23.0)) *
        Rotation.from_euler("XYZ", home, degrees=True) *
        Rotation.from_rotvec([math.radians(-8.0), 0.0, 0.0])
    )
    actual_matrix = Rotation.from_euler("XYZ", actual, degrees=True).as_matrix()
    np.testing.assert_allclose(actual_matrix, expected.as_matrix(), atol=1e-12)
    assert not np.allclose(actual, [home[0], home[1], home[2] + 23.0])

  def test_home_pose_and_translation_are_preserved(self):
    home = [10.0, -5.0, 30.0]
    translation = [1.2, -3.4, 5.6]
    transform = compose_ptz_transform(home, translation, 0.0, 0.0)
    expected_rotation = Rotation.from_euler("XYZ", home, degrees=True).as_matrix()
    np.testing.assert_allclose(np.asarray(transform)[:3, :3], expected_rotation)
    assert [row[3] for row in transform[:3]] == translation
    assert transform[3] == [0.0, 0.0, 0.0, 1.0]

  def test_rotation_from_ptz_delta_applies_curves_and_pan_axis(self):
    rotation, delta_pan, delta_tilt = rotation_from_ptz_delta(
        [0.0, 0.0, 0.0], 0.0, 0.0, 1.0, 2.0,
        pan_curve=[0.0, 10.0, 2.0], tilt_scale=5.0, pan_axis=[0.0, 0.0, 1.0])
    assert delta_pan == 12.0
    assert delta_tilt == 10.0
    np.testing.assert_allclose(
        Rotation.from_euler("XYZ", rotation, degrees=True).as_matrix(),
        Rotation.from_euler("XYZ", [0.0, 0.0, 12.0], degrees=True).as_matrix() @
        Rotation.from_euler("XYZ", [10.0, 0.0, 0.0], degrees=True).as_matrix(),
        atol=1e-12,
    )

  def test_scale_from_fov_rejects_invalid_ranges(self):
    assert scale_from_fov(-1.0, 1.0, 180.0) == 90.0
    with pytest.raises(ValueError, match="range"):
      scale_from_fov(1.0, 1.0, 180.0)
    with pytest.raises(ValueError, match="field of view"):
      scale_from_fov(-1.0, 1.0, 0.0)

  def test_zero_pan_axis_is_rejected(self):
    with pytest.raises(ValueError, match="non-zero"):
      compose_ptz_rotation([0.0, 0.0, 0.0], 1.0, 0.0, [0.0, 0.0, 0.0])
