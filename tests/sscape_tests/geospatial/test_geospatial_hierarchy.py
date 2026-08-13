# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for geospatial child-to-parent pose estimation."""

import numpy as np
import pytest

from scene_common.earth_lla import calculateTRSLocal2LLAFromSurfacePoints, convertXYZToLLA
from scene_common.geospatial_hierarchy import (
    DEFAULT_RESIDUAL_THRESHOLD_M,
    GeospatialHierarchyError,
    compute_child_to_parent_pose,
    local_xyz_corners_from_extents,
    local_xyz_corners_from_image_size,
    scene_is_georeferenced,
)
from scene_common.transform import CameraPose

TEST_NAME = "NEX-T22110"

# Same 4-corner fixture style as test_geospatial_ingest_publish / test_external_source.
PARENT_XYZ = local_xyz_corners_from_image_size(900, 643, 100.0)
PARENT_LLA = [
    [37.38685435, -121.96408120, 8.0],
    [37.38693520, -121.96408120, 8.0],
    [37.38693520, -121.96413896, 8.0],
    [37.38685435, -121.96413896, 8.0],
]


def _child_lla_from_pose(translation, rotation_deg, scale, child_xyz):
  """Ground-truth child LLA by placing the child in the parent with a known pose."""
  parent_trs = calculateTRSLocal2LLAFromSurfacePoints(PARENT_XYZ, PARENT_LLA)
  pose = CameraPose({
      'translation': translation,
      'rotation': rotation_deg,
      'scale': scale,
  }, None)
  child_lla = []
  for xyz in child_xyz:
    parent_pt = np.matmul(pose.pose_mat, np.hstack([xyz, 1.0]))[:3]
    child_lla.append(convertXYZToLLA(parent_trs, parent_pt).tolist())
  return child_lla


def _assert_pose_close(result, translation, rotation_deg, scale, atol_t=0.15, atol_r=1.0, atol_s=0.05):
  np.testing.assert_allclose(result['translation'], translation, atol=atol_t)
  np.testing.assert_allclose(result['rotation'], rotation_deg, atol=atol_r)
  np.testing.assert_allclose(result['scale'], scale, atol=atol_s)
  assert result['residual_m'] < DEFAULT_RESIDUAL_THRESHOLD_M


class TestLocalXyzCorners:
  def test_extents_ccw_from_lower_left(self):
    corners = local_xyz_corners_from_extents(10.0, 4.0)
    np.testing.assert_array_equal(
        corners,
        [[0, 0, 0], [10, 0, 0], [10, 4, 0], [0, 4, 0]])

  def test_image_size_divides_by_scale(self):
    corners = local_xyz_corners_from_image_size(200, 100, 20.0)
    np.testing.assert_allclose(corners[2], [10.0, 5.0, 0.0])

  def test_rejects_non_positive_extents(self):
    with pytest.raises(GeospatialHierarchyError, match="positive"):
      local_xyz_corners_from_extents(0, 5)
    with pytest.raises(GeospatialHierarchyError, match="positive"):
      local_xyz_corners_from_image_size(100, 100, 0)


class TestSceneIsGeoreferenced:
  def test_true_when_output_and_four_corners(self):
    assert scene_is_georeferenced(True, PARENT_LLA)

  def test_false_when_disabled_or_incomplete(self):
    assert not scene_is_georeferenced(False, PARENT_LLA)
    assert not scene_is_georeferenced(True, None)
    assert not scene_is_georeferenced(True, PARENT_LLA[:3])


class TestComputeChildToParentPose:
  def test_identity_when_corners_match(self):
    result = compute_child_to_parent_pose(
        PARENT_XYZ, PARENT_LLA, PARENT_XYZ, PARENT_LLA)
    _assert_pose_close(result, [0, 0, 0], [0, 0, 0], [1, 1, 1], atol_t=0.05, atol_r=0.5)

  def test_translated_child(self):
    child_xyz = local_xyz_corners_from_extents(3.0, 2.0)
    translation = [1.5, 0.8, 0.0]
    child_lla = _child_lla_from_pose(translation, [0, 0, 0], [1, 1, 1], child_xyz)
    result = compute_child_to_parent_pose(
        PARENT_XYZ, PARENT_LLA, child_xyz, child_lla)
    _assert_pose_close(result, translation, [0, 0, 0], [1, 1, 1])

  def test_yaw_rotated_child(self):
    child_xyz = local_xyz_corners_from_extents(3.0, 2.0)
    translation = [2.0, 1.0, 0.0]
    rotation = [0.0, 0.0, 25.0]
    child_lla = _child_lla_from_pose(translation, rotation, [1, 1, 1], child_xyz)
    result = compute_child_to_parent_pose(
        PARENT_XYZ, PARENT_LLA, child_xyz, child_lla)
    _assert_pose_close(result, translation, rotation, [1, 1, 1], atol_t=0.25, atol_r=2.0)

  def test_nested_building_in_campus(self):
    """Child footprint is a subset of the parent, offset inside the campus."""
    child_xyz = local_xyz_corners_from_extents(2.0, 1.5)
    translation = [3.0, 2.0, 0.0]
    child_lla = _child_lla_from_pose(translation, [0, 0, 0], [1, 1, 1], child_xyz)
    result = compute_child_to_parent_pose(
        PARENT_XYZ, PARENT_LLA, child_xyz, child_lla)
    _assert_pose_close(result, translation, [0, 0, 0], [1, 1, 1])
    # Origin of the child should land at the translation in parent meters.
    pose = CameraPose({
        'translation': result['translation'],
        'rotation': result['rotation'],
        'scale': result['scale'],
    }, None)
    origin_in_parent = np.matmul(pose.pose_mat, [0, 0, 0, 1])[:3]
    np.testing.assert_allclose(origin_in_parent, translation, atol=0.15)

  def test_rejects_three_corners(self):
    with pytest.raises(GeospatialHierarchyError, match="exactly 4"):
      compute_child_to_parent_pose(
          PARENT_XYZ[:3], PARENT_LLA[:3], PARENT_XYZ[:3], PARENT_LLA[:3])

  def test_rejects_mismatched_xyz_lla_counts_via_fit(self):
    with pytest.raises(GeospatialHierarchyError, match="exactly 4"):
      compute_child_to_parent_pose(
          PARENT_XYZ, PARENT_LLA, PARENT_XYZ[:3], PARENT_LLA)

  def test_rejects_off_surface_xyz(self):
    lifted = PARENT_XYZ.copy()
    lifted[0, 2] = 1.0
    with pytest.raises(GeospatialHierarchyError, match="surface"):
      compute_child_to_parent_pose(lifted, PARENT_LLA, PARENT_XYZ, PARENT_LLA)

  def test_rejects_tight_residual_threshold(self):
    child_xyz = local_xyz_corners_from_extents(3.0, 2.0)
    child_lla = _child_lla_from_pose([1.0, 0.5, 0.0], [0, 0, 0], [1, 1, 1], child_xyz)
    with pytest.raises(GeospatialHierarchyError, match="residual"):
      compute_child_to_parent_pose(
          PARENT_XYZ, PARENT_LLA, child_xyz, child_lla,
          residual_threshold_m=1e-12)
