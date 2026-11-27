# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""AprilTag and point-cloud map_processed stamps must be the run start time.

A stamp taken when a run ends is newer than a map uploaded during that run, so
the upload would be treated as already processed and lost.
"""

import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from atag_camera_calibration_controller import ApriltagCameraCalibrationController
from point_cloud_calibration_controller import PointCloudCalibrationController
from scene_common.timestamp import get_datetime_from_string
from scene_common.timestamp import get_iso_time as real_get_iso_time


class FakeClock:
  """! Deterministic stand-in for get_iso_time: each call advances one second. """

  def __init__(self):
    self.now = time.time() - 600

  def get_iso_time(self, timestamp=None):
    if timestamp is not None:
      return real_get_iso_time(timestamp)
    self.now += 1
    return real_get_iso_time(self.now)

  def between_ticks(self):
    """! A moment after the last stamp handed out and before the next one. """
    return self.now + 0.5


def make_scene(tmp_path, clock):
  """! Scene whose map was last written before the run. """
  map_path = tmp_path / "scene.glb"
  map_path.write_bytes(b"old")
  os.utime(map_path, (clock.now - 100, clock.now - 100))
  return SimpleNamespace(id="scene-1", name="lab", map=str(map_path), scale=1.0,
                         apriltag_size=0.1, map_processed=None)


def make_data_interface(scene):
  data_interface = MagicMock()

  def save_stamp(scene_id, stamp):
    scene.map_processed = get_datetime_from_string(stamp)
    return True

  data_interface.update_map_processed.side_effect = save_stamp
  return data_interface


def upload_map(scene, clock):
  uploaded_at = clock.between_ticks()
  os.utime(scene.map, (uploaded_at, uploaded_at))


def run_apriltag(scene, clock, on_identify):
  controller = ApriltagCameraCalibrationController(
      calibration_data_interface=make_data_interface(scene))
  controller.notify_scene_registration = MagicMock()
  cam_calib = MagicMock(result_data_3d={"1": [0.0, 0.0, 0.0]})
  cam_calib.identify_apriltags_in_scene.side_effect = lambda *_args: on_identify()
  with patch("atag_camera_calibration_controller.CameraCalibrationApriltag", return_value=cam_calib), \
          patch("atag_camera_calibration_controller.get_iso_time", clock.get_iso_time):
    controller.process_scene_for_calibration(scene, map_update=True)
  return controller


def test_apriltag_map_uploaded_during_run_stays_pending(tmp_path):
  """! Positive: a map uploaded while apriltags are being identified is still pending after the run. """
  clock = FakeClock()
  scene = make_scene(tmp_path, clock)

  controller = run_apriltag(scene, clock, lambda: upload_map(scene, clock))

  assert scene.map_processed is not None
  assert controller.is_map_updated(scene), "upload made during the run was marked processed by that run"


def test_apriltag_map_written_before_run_is_not_pending(tmp_path):
  """! Negative: a map written before the run started is processed once the run has saved. """
  clock = FakeClock()
  scene = make_scene(tmp_path, clock)

  controller = run_apriltag(scene, clock, lambda: None)

  assert scene.map_processed is not None
  assert not controller.is_map_updated(scene)


def run_point_cloud(scene, clock, on_read):
  data_interface = make_data_interface(scene)
  controller = PointCloudCalibrationController(calibration_data_interface=data_interface)
  controller.notify_scene_registration = MagicMock()
  controller._ensure_scene_cloud = MagicMock(side_effect=lambda *_args: on_read())
  with patch("point_cloud_calibration_controller.get_iso_time", clock.get_iso_time):
    controller.process_scene_for_calibration(scene, map_update=True)
  return data_interface


def test_point_cloud_stamp_is_taken_before_the_scene_is_read(tmp_path):
  """! Positive: the saved stamp predates a map upload that lands while the scene cloud is built. """
  clock = FakeClock()
  scene = make_scene(tmp_path, clock)

  run_point_cloud(scene, clock, lambda: upload_map(scene, clock))

  assert scene.map_processed.timestamp() < os.path.getmtime(scene.map)


def test_point_cloud_failed_run_does_not_stamp(tmp_path):
  """! Negative: a scene that cannot be read is not stamped as processed. """
  clock = FakeClock()
  scene = make_scene(tmp_path, clock)
  data_interface = make_data_interface(scene)
  controller = PointCloudCalibrationController(calibration_data_interface=data_interface)
  controller._ensure_scene_cloud = MagicMock(side_effect=FileNotFoundError("missing mesh"))

  result = controller.process_scene_for_calibration(scene, map_update=True)

  assert result["status"] == "Error: missing mesh"
  data_interface.update_map_processed.assert_not_called()


def test_apriltag_is_map_stale_does_not_reset_scene_without_a_map():
  """! is_map_stale only reports; is_map_updated still resets a scene whose map was removed. """
  data_interface = MagicMock()
  controller = ApriltagCameraCalibrationController(calibration_data_interface=data_interface)
  scene = SimpleNamespace(id="scene-1", map=None, map_processed=None)

  assert controller.is_map_stale(scene) is False
  data_interface.delete_calibration_markers_for_scene.assert_not_called()

  assert controller.is_map_updated(scene) is False
  data_interface.delete_calibration_markers_for_scene.assert_called_once_with("scene-1")


def test_apriltag_is_map_stale_matches_is_map_updated_with_a_map(tmp_path):
  """! With a map, is_map_stale answers like is_map_updated: unprocessed or newer map is stale. """
  clock = FakeClock()
  scene = make_scene(tmp_path, clock)
  controller = ApriltagCameraCalibrationController(calibration_data_interface=MagicMock())

  assert controller.is_map_stale(scene) is True
  scene.map_processed = get_datetime_from_string(real_get_iso_time(clock.now))
  assert controller.is_map_stale(scene) is False
  os.utime(scene.map, (clock.now + 10, clock.now + 10))
  assert controller.is_map_stale(scene) is True


def test_point_cloud_is_map_stale_does_not_reset_scene_without_a_map():
  """! is_map_stale only reports; is_map_updated still drops the cached scene cloud. """
  controller = PointCloudCalibrationController(calibration_data_interface=MagicMock())
  controller.scene_clouds["scene-1"] = object()
  scene = SimpleNamespace(id="scene-1", map=None, map_processed=None)

  assert controller.is_map_stale(scene) is False
  assert "scene-1" in controller.scene_clouds

  assert controller.is_map_updated(scene) is False
  assert "scene-1" not in controller.scene_clouds


def test_point_cloud_is_map_stale_until_processed():
  """! A scene with a map is stale until its map_processed stamp is saved. """
  controller = PointCloudCalibrationController(calibration_data_interface=MagicMock())
  scene = SimpleNamespace(id="scene-1", map="/media/scene.glb", map_processed=None)

  assert controller.is_map_stale(scene) is True
  scene.map_processed = get_datetime_from_string(real_get_iso_time())
  assert controller.is_map_stale(scene) is False
