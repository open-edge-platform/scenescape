# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""AprilTag is_map_updated must detect replaced map files."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from atag_camera_calibration_controller import ApriltagCameraCalibrationController


def test_is_map_updated_true_when_map_processed_is_none():
  controller = ApriltagCameraCalibrationController(calibration_data_interface=MagicMock())
  scene = MagicMock()
  scene.map = "/media/scene.png"
  scene.map_processed = None
  assert controller.is_map_updated(scene) is True


def test_is_map_updated_true_when_map_file_is_newer():
  controller = ApriltagCameraCalibrationController(calibration_data_interface=MagicMock())
  scene = MagicMock()
  scene.map = "/media/scene.png"
  scene.map_processed = datetime.now(timezone.utc)
  with patch.object(controller, "is_map_processed", return_value=True):
    assert controller.is_map_updated(scene) is True


def test_is_map_updated_false_when_map_is_current():
  controller = ApriltagCameraCalibrationController(calibration_data_interface=MagicMock())
  scene = MagicMock()
  scene.map = "/media/scene.png"
  scene.map_processed = datetime.now(timezone.utc)
  with patch.object(controller, "is_map_processed", return_value=False):
    assert controller.is_map_updated(scene) is False


def test_is_map_processed_accepts_string_map_path(tmp_path):
  from auto_camera_calibration_controller import CameraCalibrationController

  class _Stub(CameraCalibrationController):
    def process_scene_for_calibration(self, sceneobj, map_update=False):
      return None

    def reset_scene(self, scene):
      return None

    def is_map_updated(self, sceneobj):
      return False

    def generate_calibration(self, sceneobj, camera_intrinsics, msg):
      return None

  map_file = tmp_path / "scene.png"
  map_file.write_bytes(b"png")
  controller = _Stub(calibration_data_interface=MagicMock())
  scene = MagicMock()
  scene.map = str(map_file)
  scene.map_processed = datetime.fromtimestamp(map_file.stat().st_mtime - 10, tz=timezone.utc)
  assert controller.is_map_processed(scene) is True

  scene.map_processed = datetime.fromtimestamp(map_file.stat().st_mtime + 10, tz=timezone.utc)
  assert controller.is_map_processed(scene) is False
