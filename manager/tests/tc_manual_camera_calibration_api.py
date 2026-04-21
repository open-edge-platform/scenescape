#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging

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

  logging.info(f"Executing test {TEST_NAME}")
  logging.info("Step 1. Verify that Rest is authenticated")
  assert rest.isAuthenticated, "Lacking Rest token."

  logging.info("Step 2. Get cameras' UIDs and Transforms. Generate modified data.")
  cameras = rest.getCameras('')
  for camera in cameras["results"]:
    original_camera_data.update({camera["uid"]: camera["transforms"]})
    modified_camera_data = {uid: [x*1.05 for x in transforms] for uid, transforms in original_camera_data.items()}
    assert original_camera_data != modified_camera_data, "Original and Modified data is the same"

  logging.info("Step 3. Modify calibration points")
  for uid, transforms in modified_camera_data.items():
    logging.info(f"Modifying for UID:{uid}")
    result = rest.updateCamera(uid, {"transform_type": "3d-2d point correspondence", "transforms":transforms})
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points not modified"

  logging.info("Step 4. Check if data is saved")
  for uid, transforms in modified_camera_data.items():
    logging.info(f"Checking for UID:{uid}")
    result = rest.updateCamera(uid, {"transforms":transforms})
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points did not save"

  logging.info("Step 5. Return to original values")
  for uid, transforms in original_camera_data.items():
    logging.info(f"Modifying for UID:{uid}")
    result = rest.updateCamera(uid, {"transform_type": "3d-2d point correspondence", "transforms":transforms})
    assert result != {}, f"Action failed with {result.errors}"
    assert result["transforms"] == transforms, "Calibration points did not revert to original values"

  result_recorder.success()
