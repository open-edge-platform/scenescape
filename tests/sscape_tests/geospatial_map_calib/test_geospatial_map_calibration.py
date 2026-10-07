#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest

from conftest import GT_CAMERA, INTRINSICS, MAP_SCALE

from geospatial_map_calibration import (
  GeoMapPrior, GeospatialMapCalibration, angle_diff_deg, is_raster_map, pitch_from_vp,
  pose_from_look)


def _prior_near_gt():
  return GeoMapPrior(map_point=(GT_CAMERA["x"] + 3.0, GT_CAMERA["y"] - 3.0),
                     heading_deg=GT_CAMERA["yaw"] + 3.0, height_m=GT_CAMERA["height"])


def test_calibrate_with_prior_recovers_pose(textured_map, camera_frame, gt_pose, no_vanishing_point):
  """! A nearby map point + heading prior recovers the rendered camera pose. """
  engine = GeospatialMapCalibration(textured_map, MAP_SCALE)
  result = engine.calibrate(camera_frame, INTRINSICS, _prior_near_gt())

  assert result["needs_prior"] is False
  assert np.linalg.norm(result["pose"][:2, 3] - gt_pose[:2, 3]) < 3.0
  assert angle_diff_deg(result["yaw_deg"], GT_CAMERA["yaw"]) <= 5.0
  assert result["translation"][2] > 0
  assert np.isclose(np.linalg.norm(result["quaternion"]), 1.0)
  assert len(result["calibration_points_2d"]) == len(result["calibration_points_3d"]) >= 4
  assert all(p[2] == 0.0 for p in result["calibration_points_3d"])


def test_calibrate_correspondences_reproject(textured_map, camera_frame, no_vanishing_point):
  """! Returned 3D ground points project back onto their 2D image points. """
  engine = GeospatialMapCalibration(textured_map, MAP_SCALE)
  result = engine.calibrate(camera_frame, INTRINSICS, _prior_near_gt())
  cam_from_world = np.linalg.inv(result["pose"])
  K = np.asarray(INTRINSICS)
  for p3, p2 in zip(result["calibration_points_3d"], result["calibration_points_2d"]):
    cam = cam_from_world @ np.array([*p3, 1.0])
    proj = K @ cam[:3]
    assert np.allclose(proj[:2] / proj[2], p2, atol=1e-3)


def test_calibrate_uniform_map_needs_prior(camera_frame, no_vanishing_point):
  """! A textureless map gives no correlation, so the engine asks for a prior. """
  uniform = np.full((1000, 1000, 3), 128, np.uint8)
  engine = GeospatialMapCalibration(uniform, MAP_SCALE)
  result = engine.calibrate(camera_frame, INTRINSICS, _prior_near_gt())
  assert result["needs_prior"] is True


def test_calibrate_prior_outside_map_rejected(textured_map, camera_frame):
  engine = GeospatialMapCalibration(textured_map, MAP_SCALE)
  with pytest.raises(ValueError, match="outside"):
    engine.calibrate(camera_frame, INTRINSICS, GeoMapPrior(map_point=(-500.0, -500.0)))


@pytest.mark.parametrize("intrinsics", [
  [[0.0, 0.0, 320.0], [0.0, 400.0, 180.0], [0.0, 0.0, 1.0]],
  [[np.nan, 0.0, 320.0], [0.0, 400.0, 180.0], [0.0, 0.0, 1.0]],
])
def test_calibrate_invalid_intrinsics_rejected(textured_map, camera_frame, intrinsics):
  engine = GeospatialMapCalibration(textured_map, MAP_SCALE)
  with pytest.raises(ValueError, match="intrinsics"):
    engine.calibrate(camera_frame, intrinsics, _prior_near_gt())


def test_calibrate_invalid_prior_height_rejected(textured_map, camera_frame):
  engine = GeospatialMapCalibration(textured_map, MAP_SCALE)
  with pytest.raises(ValueError, match="height"):
    engine.calibrate(camera_frame, INTRINSICS, GeoMapPrior(height_m=-1.0))


@pytest.mark.parametrize("scale", [0, -1.0, float("nan"), None])
def test_invalid_scale_rejected(textured_map, scale):
  with pytest.raises(ValueError, match="scale"):
    GeospatialMapCalibration(textured_map, scale)


def test_from_file_rejects_non_raster(tmp_path):
  with pytest.raises(ValueError):
    GeospatialMapCalibration.from_file(str(tmp_path / "scene.glb"), MAP_SCALE)


def test_from_file_missing(tmp_path):
  with pytest.raises(FileNotFoundError):
    GeospatialMapCalibration.from_file(str(tmp_path / "missing.png"), MAP_SCALE)


@pytest.mark.parametrize("path,expected", [
  ("/media/map.PNG", True), ("/media/map.jpg", True), ("/media/map.jpeg", True),
  ("/media/map.glb", False), ("/media/map.zip", False), (None, False), ("", False),
])
def test_is_raster_map(path, expected):
  assert is_raster_map(path) is expected


def test_prior_from_request():
  prior = GeoMapPrior.from_request({"mapPoint": [1, 2], "heading": 90, "height": 7})
  assert prior.map_point == (1.0, 2.0)
  assert prior.heading_deg == 90.0
  assert prior.height_m == 7.0
  assert GeoMapPrior.from_request(None) is None
  assert GeoMapPrior.from_request({}) is None


def test_pitch_from_vp():
  K = np.asarray(INTRINSICS)
  pitch, ok = pitch_from_vp(np.array([320.0, 180.0 + 400.0 * np.tan(np.radians(12.0))]), K)
  assert ok and pitch == pytest.approx(12.0)
  assert pitch_from_vp(None, K) == (10.0, False)
  assert pitch_from_vp(np.array([320.0, 0.0]), K)[1] is False


def test_pose_from_look_convention():
  """! Camera z (optical axis) follows yaw/pitch; camera y points downward-ish. """
  pose = pose_from_look(1.0, 2.0, 5.0, 90.0, 30.0)
  look = pose[:3, 2]
  assert np.allclose(look, [0.0, np.cos(np.radians(30)), -np.sin(np.radians(30))], atol=1e-9)
  assert pose[2, 1] < 0
  assert np.allclose(pose[:3, 3], [1.0, 2.0, 5.0])
  with pytest.raises(ValueError):
    pose_from_look(0.0, 0.0, 0.0, 0.0, 10.0)
