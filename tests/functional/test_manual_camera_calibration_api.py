#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = 'NEX-T15280'

def test_manual_camera_calibration_api(rest, result_recorder):
  """Checks that camera calibration points can be modified through API.

    Steps:
      * Verify that Rest is authenticated
      * Get cameras' UIDs and Transforms. Generate modified data.
      * Modify calibration points
      * Check if data is saved
      * Return to original values (also counts as a cleanup)
  """
  original_camera_data = {}  # UID and Transforms pairs for each camera

  log.info(f"Executing test {TEST_NAME}")
  log.info("Step 1. Verify that Rest is authenticated")
  assert rest.isAuthenticated, "Lacking Rest token."

  log.info("Step 2. Get cameras' UIDs and Transforms. Generate modified data.")
  cameras = rest.getCameras('')
  camera_metadata = {}
  for camera in cameras["results"]:
    original_camera_data.update({camera["uid"]: camera["transforms"]})
    camera_metadata[camera["uid"]] = {
      "name": camera["name"],
      "sensor_id": camera.get("sensor_id"),
      "scene": camera.get("scene"),
    }
    modified_camera_data = {uid: [x*1.05 for x in transforms] for uid, transforms in original_camera_data.items()}
    assert original_camera_data != modified_camera_data, "Original and Modified data is the same"

  log.info("Step 3. Modify calibration points")
  for uid, transforms in modified_camera_data.items():
    log.info(f"Modifying for UID:{uid}")
    update_payload = {
      "name": camera_metadata[uid]["name"],
      "transform_type": "3d-2d point correspondence",
      "transforms": transforms,
    }
    if camera_metadata[uid]["sensor_id"] is not None:
      update_payload["sensor_id"] = camera_metadata[uid]["sensor_id"]
    if camera_metadata[uid]["scene"] is not None:
      update_payload["scene"] = camera_metadata[uid]["scene"]
    result = rest.updateCamera(uid, update_payload)
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points not modified"

  log.info("Step 4. Check if data is saved")
  for uid, transforms in modified_camera_data.items():
    log.info(f"Checking for UID:{uid}")
    result = rest.getCamera(uid)
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points did not save"

  log.info("Step 5. Return to original values")
  for uid, transforms in original_camera_data.items():
    log.info(f"Modifying for UID:{uid}")
    update_payload = {
      "name": camera_metadata[uid]["name"],
      "transform_type": "3d-2d point correspondence",
      "transforms": transforms,
    }
    if camera_metadata[uid]["sensor_id"] is not None:
      update_payload["sensor_id"] = camera_metadata[uid]["sensor_id"]
    if camera_metadata[uid]["scene"] is not None:
      update_payload["scene"] = camera_metadata[uid]["scene"]
    result = rest.updateCamera(uid, update_payload)
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points did not revert to original values"

  result_recorder.success()
