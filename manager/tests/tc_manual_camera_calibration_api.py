#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest

TEST_NAME = 'NEX-T15280'

class ManualCameraCalibrationAPITest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

  def runTest(self):
    """Checks that camera calibration points can be modified through API.

    Steps:
      * Verify that Rest is authenticated
      * Get cameras' UIDs and Transforms. Generate modified data.
      * Modify calibration points
      * Check if data is saved
      * Return to original values (also counts as a cleanup)
    """

    self.exitCode = 1
    original_camera_data = {}  # UID and Transforms pairs for each camera

    try:
      log.info(f"Executing test {TEST_NAME}")
      log.info("Step 1. Verify that Rest is authenticated")
      assert self.rest.isAuthenticated, "Lacking Rest token."

      log.info("Step 2. Get cameras' UIDs and Transforms. Generate modified data.")
      cameras = self.rest.getCameras('')
      for camera in cameras["results"]:
        original_camera_data.update({camera["uid"]: camera["transforms"]})
      modified_camera_data = {uid: [x*1.05 for x in transforms] for uid, transforms in original_camera_data.items()}
      assert original_camera_data != modified_camera_data, "Original and Modified data is the same"

      log.info("Step 3. Modify calibration points")
      for uid, transforms in modified_camera_data.items():
        log.info(f"Modifying for UID:{uid}")
        result = self.rest.updateCamera(uid, {"transform_type": "3d-2d point correspondence", "transforms":transforms})
        assert result != {}, f"Action failed with {result.errors}"
        assert result["transforms"] == transforms, "Calibration points not modified"

      log.info("Step 4. Check if data is saved")
      for uid, transforms in modified_camera_data.items():
        log.info(f"Checking for UID:{uid}")
        result = self.rest.updateCamera(uid, {"transforms":transforms})
        assert result != {}, f"Action failed with {result.errors}"
        assert result["transforms"] == transforms, "Calibration points did not save"

      log.info("Step 5. Return to original values")
      for uid, transforms in original_camera_data.items():
        log.info(f"Modifying for UID:{uid}")
        result = self.rest.updateCamera(uid, {"transform_type": "3d-2d point correspondence", "transforms":transforms})
        assert result != {}, f"Action failed with {result.errors}"
        assert result["transforms"] == transforms, "Calibration points did not revert to original values"

      self.exitCode = 0

    except Exception as e:
      log.error(f"Test failed with exception: {e}")
      self.exitCode = 1

    return self.exitCode

def test_api_camera_calibration(request, record_xml_attribute):
  test = ManualCameraCalibrationAPITest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest() == 0
