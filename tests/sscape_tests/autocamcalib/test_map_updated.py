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


def test_invalidated_source_rebuilds_cached_mesh_and_replaces_markers():
  data_iface = MagicMock()
  old_markers = {"1": [0, 0, 0], "2": [1, 0, 0]}
  new_markers = {"9": [4, 5, 6]}
  stored_markers = old_markers.copy()
  data_iface.delete_calibration_markers_for_scene.side_effect = (
    lambda scene_id: stored_markers.clear() or True)
  data_iface.update_or_create_calibration_marker.side_effect = (
    lambda scene_id, data: stored_markers.update({data["apriltag_id"]: data["dims"]}) or True)
  data_iface.calibration_markers_with_scene_id.side_effect = lambda scene_id: {
    "results": [{"apriltag_id": tag, "dims": dims} for tag, dims in stored_markers.items()]}
  controller = ApriltagCameraCalibrationController(calibration_data_interface=data_iface)
  controller.notify_scene_registration = MagicMock()
  scene = MagicMock(id="scene-1", map="/media/activated.glb", map_processed=None)
  previous = MagicMock(result_data_3d=old_markers)
  controller.cam_calib_objs[scene.id] = previous
  replacement = MagicMock(result_data_3d=new_markers)
  with patch("atag_camera_calibration_controller.CameraCalibrationApriltag",
             return_value=replacement) as factory:
    controller.process_scene_for_calibration(scene, map_update=controller.is_map_updated(scene))
  assert controller.cam_calib_objs[scene.id] is replacement
  assert factory.call_args.args[0] == scene.map
  previous.identify_apriltags_in_scene.assert_not_called()
  replacement.identify_apriltags_in_scene.assert_called_once()
  assert stored_markers == new_markers
  data_iface.delete_calibration_markers_for_scene.assert_called_once_with(scene.id)
  data_iface.update_map_processed.assert_called_once()
  calls = [call[0] for call in data_iface.mock_calls]
  assert calls.index("delete_calibration_markers_for_scene") < calls.index(
    "update_or_create_calibration_marker") < calls.index("update_map_processed")


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
