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
