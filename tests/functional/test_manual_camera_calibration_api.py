#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
import pytest

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = 'NEX-T15280'

@pytest.mark.test_name("NEX-T15280")
def test_manual_camera_calibration_api(rest, result_recorder):
  """Checks that camera calibration points can be modified through API.

    Steps:
      * Verify that Rest is authenticated
      * Get cameras' UIDs and Transforms. Generate modified data.
      * Modify calibration points
      * Check if data is saved
      * Return to original values (also counts as a cleanup)
  """
  log.info(f"Executing test {TEST_NAME}")
  log.info("Step 1. Verify that Rest is authenticated")
  assert rest.isAuthenticated, "Lacking Rest token."

  log.info("Step 2. Get cameras' UIDs and Transforms. Generate modified data.")
  cameras = rest.getCameras('')
  # CamSerializer requires name on every non-relink update (ITEP-94755).
  original_camera_data = {}  # uid -> (name, transforms)
  for camera in cameras["results"]:
    original_camera_data[camera["uid"]] = (camera["name"], camera["transforms"])
  modified_camera_data = {
    uid: (name, [x * 1.05 for x in transforms])
    for uid, (name, transforms) in original_camera_data.items()
  }
  assert {
    uid: transforms for uid, (_, transforms) in original_camera_data.items()
  } != {
    uid: transforms for uid, (_, transforms) in modified_camera_data.items()
  }, "Original and Modified data is the same"

  log.info("Step 3. Modify calibration points")
  for uid, (name, transforms) in modified_camera_data.items():
    log.info(f"Modifying for UID:{uid}")
    result = rest.updateCamera(uid, {
      "name": name,
      "transform_type": "3d-2d point correspondence",
      "transforms": transforms,
    })
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points not modified"

  log.info("Step 4. Check if data is saved")
  for uid, (name, transforms) in modified_camera_data.items():
    log.info(f"Checking for UID:{uid}")
    result = rest.updateCamera(uid, {"name": name, "transforms": transforms})
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points did not save"

  log.info("Step 5. Return to original values")
  for uid, (name, transforms) in original_camera_data.items():
    log.info(f"Modifying for UID:{uid}")
    result = rest.updateCamera(uid, {
      "name": name,
      "transform_type": "3d-2d point correspondence",
      "transforms": transforms,
    })
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points did not revert to original values"

  result_recorder.success()
