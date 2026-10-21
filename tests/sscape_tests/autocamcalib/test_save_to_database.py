# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""AprilTag save_to_database must replace the stored marker set atomically."""

from unittest.mock import MagicMock, call, patch

import pytest

from atag_camera_calibration_controller import ApriltagCameraCalibrationController


def _controller_with_iface():
  data_iface = MagicMock()
  data_iface.delete_calibration_markers_for_scene.return_value = True
  data_iface.update_or_create_calibration_marker.return_value = {"ok": True}
  data_iface.update_map_processed.return_value = {"ok": True}
  controller = ApriltagCameraCalibrationController(calibration_data_interface=data_iface)
  return controller, data_iface


def test_save_to_database_replaces_smaller_and_stale_marker_sets():
  """Fewer or different detected tags must still persist the new set."""
  controller, data_iface = _controller_with_iface()
  scene = MagicMock()
  scene.id = "scene-1"
  detected = {
      "1": [0.0, 0.0, 0.0],
      "2": [1.0, 0.0, 0.0],
  }

  with patch(
      "atag_camera_calibration_controller.get_iso_time",
      return_value="2026-01-01T00:00:00Z",
  ):
    controller.save_to_database(scene, detected)

  data_iface.delete_calibration_markers_for_scene.assert_called_once_with(scene.id)
  assert data_iface.update_or_create_calibration_marker.call_count == 2
  data_iface.update_or_create_calibration_marker.assert_has_calls(
      [
          call(
              scene.id,
              {
                  "marker_id": "scene-1_1",
                  "apriltag_id": "1",
                  "dims": [0.0, 0.0, 0.0],
                  "scene": scene.id,
              },
          ),
          call(
              scene.id,
              {
                  "marker_id": "scene-1_2",
                  "apriltag_id": "2",
                  "dims": [1.0, 0.0, 0.0],
                  "scene": scene.id,
              },
          ),
      ],
      any_order=True,
  )
  data_iface.update_map_processed.assert_called_once_with(
      scene.id, "2026-01-01T00:00:00Z"
  )


def test_save_to_database_does_not_read_prior_markers_before_replace():
  """Replacement must not branch on prior DB count (old delete-only path)."""
  controller, data_iface = _controller_with_iface()
  scene = MagicMock()
  scene.id = "scene-2"

  with patch(
      "atag_camera_calibration_controller.get_iso_time",
      return_value="2026-01-01T00:00:00Z",
  ):
    controller.save_to_database(scene, {"7": [2.0, 2.0, 0.0]})

  data_iface.calibration_markers_with_scene_id.assert_not_called()
  data_iface.delete_calibration_markers_for_scene.assert_called_once_with(scene.id)
  data_iface.update_or_create_calibration_marker.assert_called_once()


def test_save_to_database_skips_map_processed_when_delete_fails():
  controller, data_iface = _controller_with_iface()
  data_iface.delete_calibration_markers_for_scene.return_value = False
  scene = MagicMock()
  scene.id = "scene-3"

  with pytest.raises(RuntimeError, match="Failed to clear calibration markers"):
    controller.save_to_database(scene, {"1": [0.0, 0.0, 0.0]})

  data_iface.update_or_create_calibration_marker.assert_not_called()
  data_iface.update_map_processed.assert_not_called()


def test_save_to_database_skips_map_processed_when_create_fails():
  controller, data_iface = _controller_with_iface()
  data_iface.update_or_create_calibration_marker.return_value = None
  scene = MagicMock()
  scene.id = "scene-4"

  with pytest.raises(RuntimeError, match="Failed to persist calibration marker"):
    controller.save_to_database(scene, {"1": [0.0, 0.0, 0.0]})

  data_iface.update_map_processed.assert_not_called()
