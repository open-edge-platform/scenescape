# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The markerless map_processed stamp must be the registration start time.

A stamp taken when a run ends is newer than a map uploaded during that run, so
is_map_updated() would treat the upload as already processed and drop it.
"""

import os
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from markerless_camera_calibration_controller import MarkerlessCameraCalibrationController
from scene_common.timestamp import get_datetime_from_string
from scene_common.timestamp import get_iso_time as real_get_iso_time


def make_scene():
  return SimpleNamespace(id="scene-1", name="lab", camera_calibration="Markerless",
                         map="/tmp/box.glb", polycam_data="/tmp/poly.zip",
                         map_processed=None, output_dir="/tmp/out")


def test_map_processed_stamp_is_run_start_not_run_end():
  """! Positive: the stamp saved after a map-update run is no later than the run start. """
  data_interface = MagicMock()
  controller = MarkerlessCameraCalibrationController(calibration_data_interface=data_interface)
  controller.preprocess_polycam_dataset = MagicMock(
      return_value={"status": "success", "dataset_dir": "/tmp/ds", "output_dir": "/tmp/out"})
  controller.notify_scene_registration = MagicMock()

  register_entered = {}
  scene = make_scene()

  def register_dataset(sceneobj):
    register_entered["at"] = datetime.now(timezone.utc)
    time.sleep(0.2)
    return sceneobj

  pose_estimate = MagicMock()
  pose_estimate.register_dataset.side_effect = register_dataset
  fake_module = MagicMock(CameraCalibrationMonocularPoseEstimate=MagicMock(return_value=pose_estimate))

  with patch.dict(sys.modules, {"markerless_camera_calibration": fake_module}):
    controller.process_scene_for_calibration(scene, map_update=True)

  data_interface.update_map_processed.assert_called_once()
  stamp_arg = data_interface.update_map_processed.call_args.args[1]
  stamp = get_datetime_from_string(stamp_arg)
  assert stamp <= register_entered["at"], \
      f"stamp {stamp_arg} is later than registration start {register_entered['at'].isoformat()}"


def test_failed_registration_does_not_stamp_map_processed():
  """! Negative: a run that fails must not save map_processed, so the map stays pending. """
  data_interface = MagicMock()
  controller = MarkerlessCameraCalibrationController(calibration_data_interface=data_interface)
  controller.preprocess_polycam_dataset = MagicMock(
      return_value={"status": "success", "dataset_dir": "/tmp/ds", "output_dir": "/tmp/out"})
  controller.notify_scene_registration = MagicMock()

  pose_estimate = MagicMock()
  pose_estimate.register_dataset.side_effect = FileNotFoundError("missing features file")
  fake_module = MagicMock(CameraCalibrationMonocularPoseEstimate=MagicMock(return_value=pose_estimate))

  with patch.dict(sys.modules, {"markerless_camera_calibration": fake_module}):
    response = controller.process_scene_for_calibration(make_scene(), map_update=True)

  data_interface.update_map_processed.assert_not_called()
  assert response["status"] == "missing features file"


def test_map_uploaded_during_run_stays_unprocessed_after_run_saves(tmp_path):
  """! Positive: a box map uploaded mid-run is still pending once the run has saved its stamp. """
  map_path = tmp_path / "box.glb"
  polycam_path = tmp_path / "poly.zip"
  map_path.write_bytes(b"old")
  polycam_path.write_bytes(b"old")
  old = time.time() - 600
  os.utime(map_path, (old, old))
  os.utime(polycam_path, (old, old))

  scene = make_scene()
  scene.map = str(map_path)
  scene.polycam_data = str(polycam_path)
  scene.map_processed = None

  data_interface = MagicMock()

  def save_stamp(scene_id, stamp):
    scene.map_processed = get_datetime_from_string(stamp)

  data_interface.update_map_processed.side_effect = save_stamp
  controller = MarkerlessCameraCalibrationController(calibration_data_interface=data_interface)
  controller.preprocess_polycam_dataset = MagicMock(
      return_value={"status": "success", "dataset_dir": "/tmp/ds", "output_dir": "/tmp/out"})
  controller.notify_scene_registration = MagicMock()

  def register_dataset(sceneobj):
    uploaded_at = time.time()  # box uploaded while the run is in progress
    os.utime(map_path, (uploaded_at, uploaded_at))
    return sceneobj

  pose_estimate = MagicMock()
  pose_estimate.register_dataset.side_effect = register_dataset
  fake_module = MagicMock(CameraCalibrationMonocularPoseEstimate=MagicMock(return_value=pose_estimate))

  with patch.dict(sys.modules, {"markerless_camera_calibration": fake_module}):
    controller.process_scene_for_calibration(scene, map_update=True)

  assert scene.map_processed is not None
  assert controller.is_map_updated(scene), "upload made during the run was marked processed by that run"


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


def make_scene_with_files(tmp_path, clock):
  """! Scene whose map and polycam files were both last written before the run. """
  scene = make_scene()
  for attr, name in (("map", "box.glb"), ("polycam_data", "poly.zip")):
    path = tmp_path / name
    path.write_bytes(b"old")
    os.utime(path, (clock.now - 100, clock.now - 100))
    setattr(scene, attr, str(path))
  return scene


def make_stamping_controller(scene):
  data_interface = MagicMock()

  def save_stamp(scene_id, stamp):
    scene.map_processed = get_datetime_from_string(stamp)

  data_interface.update_map_processed.side_effect = save_stamp
  controller = MarkerlessCameraCalibrationController(calibration_data_interface=data_interface)
  controller.notify_scene_registration = MagicMock()
  return controller


def run_markerless(controller, scene, clock, preprocess):
  controller.preprocess_polycam_dataset = MagicMock(side_effect=preprocess)
  fake_module = MagicMock(CameraCalibrationMonocularPoseEstimate=MagicMock())
  with patch.dict(sys.modules, {"markerless_camera_calibration": fake_module}), \
          patch("markerless_camera_calibration_controller.get_iso_time", clock.get_iso_time):
    controller.process_scene_for_calibration(scene, map_update=True)


def test_upload_between_preprocess_read_and_stamp_stays_pending(tmp_path):
  """! Positive: a polycam upload landing right after the zip was read is still pending after the run. """
  clock = FakeClock()
  scene = make_scene_with_files(tmp_path, clock)
  controller = make_stamping_controller(scene)

  def preprocess(_scene):
    uploaded_at = clock.between_ticks()  # upload lands after the zip was read
    os.utime(scene.polycam_data, (uploaded_at, uploaded_at))
    return {"status": "success", "dataset_dir": "/tmp/ds", "output_dir": "/tmp/out"}

  run_markerless(controller, scene, clock, preprocess)

  assert scene.map_processed is not None
  assert controller.is_map_updated(scene), "upload after the zip was read was marked processed"


def test_upload_consumed_by_the_run_is_not_pending_again(tmp_path):
  """! Negative: a polycam file written before the run started is processed, so no re-run is needed. """
  clock = FakeClock()
  scene = make_scene_with_files(tmp_path, clock)
  controller = make_stamping_controller(scene)

  def preprocess(_scene):
    return {"status": "success", "dataset_dir": "/tmp/ds", "output_dir": "/tmp/out"}

  run_markerless(controller, scene, clock, preprocess)

  assert scene.map_processed is not None
  assert not controller.is_map_updated(scene), "an upload the run consumed was left pending"


def test_markerless_is_map_stale_returns_bool_and_does_not_reset(tmp_path):
  """! The markerless check returns a real boolean and never touches the scene's output. """
  clock = FakeClock()
  scene = make_scene_with_files(tmp_path, clock)
  controller = make_stamping_controller(scene)
  controller.reset_scene = MagicMock()

  assert controller.is_map_stale(scene) is True
  scene.map_processed = get_datetime_from_string(real_get_iso_time(clock.now))
  assert controller.is_map_stale(scene) is False
  assert controller.is_map_updated(scene) is False
  scene.polycam_data = None
  assert controller.is_map_stale(scene) is False
  controller.reset_scene.assert_not_called()
