#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest

from conftest import GT_CAMERA, INTRINSICS, encode_image

from geospatial_map_calibration_controller import NEEDS_PRIOR, GeospatialMapCalibrationController


def _prior_payload():
  return {"mapPoint": [GT_CAMERA["x"] + 3.0, GT_CAMERA["y"] - 3.0],
          "heading": GT_CAMERA["yaw"] + 3.0, "height": GT_CAMERA["height"]}


@pytest.fixture
def controller(data_interface):
  return GeospatialMapCalibrationController(calibration_data_interface=data_interface)


def test_register_scene_success(controller, data_interface, map_file, scene_factory):
  """! Registering a raster-map scene loads it and marks the map processed. """
  result = controller.process_scene_for_calibration(scene_factory(map_file))
  assert result == {"status": "success"}
  data_interface.update_map_processed.assert_called_once()


def test_register_scene_already_processed(controller, data_interface, map_file, scene_factory):
  result = controller.process_scene_for_calibration(scene_factory(map_file, map_processed="t"))
  assert result["status"] == "success"
  data_interface.update_map_processed.assert_not_called()


def test_register_scene_missing_map(controller, data_interface, tmp_path, scene_factory):
  result = controller.process_scene_for_calibration(scene_factory(str(tmp_path / "missing.png")))
  assert result["status"] == "error"
  assert "not found" in result["message"]
  data_interface.update_map_processed.assert_not_called()


def test_register_scene_non_raster_map(controller, tmp_path, scene_factory):
  result = controller.process_scene_for_calibration(scene_factory(str(tmp_path / "scene.glb")))
  assert result["status"] == "error"


def test_is_map_updated(controller, map_file, scene_factory, tmp_path):
  assert controller.is_map_updated(scene_factory(map_file)) is True
  assert controller.is_map_updated(scene_factory(map_file, map_processed="t")) is False
  assert controller.is_map_updated(scene_factory(str(tmp_path / "scene.glb"))) is False


def test_calibrator_reloads_when_scale_changes(controller, map_file, scene_factory):
  first = controller._get_calibrator(scene_factory(map_file))
  assert controller._get_calibrator(scene_factory(map_file)) is first
  assert controller._get_calibrator(scene_factory(map_file, scale=20.0)) is not first
  controller.reset_scene(scene_factory(map_file))
  assert controller._get_calibrator(scene_factory(map_file)) is not first


def test_generate_calibration_success(controller, map_file, scene_factory, camera_frame,
                                      gt_pose, no_vanishing_point):
  """! A frame with a prior yields a success payload the manager UI can consume. """
  frame_data = {"id": "cam1", "image": encode_image(camera_frame), "prior": _prior_payload()}
  result = controller.generate_calibration(scene_factory(map_file), INTRINSICS, frame_data)

  assert result["status"] == "success"
  assert result["camera_id"] == "cam1"
  assert len(result["quaternion"]) == 4
  assert np.linalg.norm(np.array(result["translation"][:2]) - gt_pose[:2, 3]) < 3.0
  assert len(result["calibration_points_2d"]) >= 4
  assert result["confidence"]["needs_prior"] is False


def test_generate_calibration_needs_prior(controller, uniform_map_file, scene_factory,
                                          camera_frame, no_vanishing_point):
  frame_data = {"id": "cam1", "image": encode_image(camera_frame), "prior": _prior_payload()}
  result = controller.generate_calibration(scene_factory(uniform_map_file), INTRINSICS, frame_data)
  assert result["status"] == NEEDS_PRIOR
  assert "prior" in result["message"]
  assert "quaternion" not in result


def test_generate_calibration_bad_image(controller, map_file, scene_factory):
  frame_data = {"id": "cam1", "image": "bm90IGFuIGltYWdl"}
  result = controller.generate_calibration(scene_factory(map_file), INTRINSICS, frame_data)
  assert result == {"status": "error", "message": "Unable to decode camera image"}


def test_generate_calibration_missing_intrinsics(controller, map_file, scene_factory, camera_frame):
  frame_data = {"id": "cam1", "image": encode_image(camera_frame)}
  result = controller.generate_calibration(scene_factory(map_file), None, frame_data)
  assert result["status"] == "error"
  assert "Intrinsics" in result["message"]
