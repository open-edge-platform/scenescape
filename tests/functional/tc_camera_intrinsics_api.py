#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from scene_common import log
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10415"
MAX_CONTROLLER_WAIT = 20  # seconds
MAX_ATTEMPTS = 3

class CameraIntrinsicsTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.existingSceneUID = self.params['scene_id']
    self.testCameraName = "Camera_Intrinsics"
    self.testCameraId = "Camera_Intrinsics"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    # Initialize MQTT for camera intrinsics updates
    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'], int(self.params['broker_port']))
    self.pubsub.connect()
    self.pubsub.loopStart()

    self.intrinsics_updated = False
    return

  def _setupTestCamera(self):
    """Create a test camera for intrinsics testing"""
    log.info(f"Creating test camera: {self.testCameraName}")

    cameraData = {
      'name': self.testCameraName,
      'sensor_id': self.testCameraId,
      'scene': self.existingSceneUID,
      'intrinsics': {
        'fx': 800.0,
        'fy': 800.0,
        'cx': 320.0,
        'cy': 240.0
      }
    }

    camera = self.rest.createCamera(cameraData)
    assert camera, (camera.statusCode, camera.errors)
    return camera['uid']

  def _cleanupTestCamera(self, cameraUID):
    """Delete the test camera"""
    try:
      if cameraUID:
        log.info(f"Cleaning up test camera: {cameraUID}")
        self.rest.deleteCamera(cameraUID)
    except:
      pass  # Camera might already be deleted

  def _validateIntrinsics(self, camera, expectedIntrinsics, expectedDistortion):
    """Validate that camera has expected intrinsics and distortion values"""
    actualIntrinsics = camera.get('intrinsics', {})
    actualDistortion = camera.get('distortion', {})

    # Check intrinsics
    for key, expectedValue in expectedIntrinsics.items():
      actualValue = actualIntrinsics.get(key)
      assert actualValue is not None, f"Intrinsics {key} not found in camera"
      assert abs(float(actualValue) - float(expectedValue)) < 0.1, \
        f"Intrinsics {key}: expected {expectedValue}, got {actualValue}"

    # Check distortion
    for key, expectedValue in expectedDistortion.items():
      actualValue = actualDistortion.get(key)
      assert actualValue is not None, f"Distortion {key} not found in camera"
      assert abs(float(actualValue) - float(expectedValue)) < 0.1, \
        f"Distortion {key}: expected {expectedValue}, got {actualValue}"

    return True

  def _updateAndValidateIntrinsics(self, cameraUID, initialValue, step):
    """Update camera intrinsics and validate they persist after saving"""
    log.info(f"Updating camera intrinsics with initial value {initialValue} and step {step}")

    # Prepare new intrinsics and distortion values
    newIntrinsics = {
      'fx': float(initialValue),
      'fy': float(initialValue + step),
      'cx': float(initialValue + 2 * step),
      'cy': float(initialValue + 3 * step)
    }

    newDistortion = {
      'k1': float(initialValue + 4 * step),
      'k2': float(initialValue + 5 * step),
      'p1': float(initialValue + 6 * step),
      'p2': float(initialValue + 7 * step),
      'k3': float(initialValue + 8 * step)
    }

    # Update camera with new intrinsics
    updateData = {
      'intrinsics': newIntrinsics,
      'distortion': newDistortion
    }

    log.info("Saving camera intrinsics changes...")
    updateResult = self.rest.updateCamera(cameraUID, updateData)
    assert updateResult, (updateResult.statusCode, updateResult.errors)

    # Wait a moment for changes to propagate
    time.sleep(1)

    # Retrieve camera and validate the changes persisted
    log.info("Validating that intrinsics changes persisted...")
    updatedCamera = self.rest.getCamera(cameraUID)
    assert updatedCamera, (updatedCamera.statusCode, updatedCamera.errors)

    # Validate the intrinsics and distortion values
    self._validateIntrinsics(updatedCamera, newIntrinsics, newDistortion)

    log.info("Camera intrinsics successfully updated and validated")
    return True

  def testCameraIntrinsics(self):
    """! Test that camera parameters can be updated via REST API and persist after saving.

    Steps:
      * Create a test camera
      * Update intrinsics with first set of values and validate persistence
      * Update intrinsics with second set of values and validate persistence
      * Cleanup test camera
    """
    log.info(f"Executing: {TEST_NAME}")
    cameraUID = None

    try:
      # Make sure that the SceneScape is up and running
      log.info("Make sure that the SceneScape is up and running")
      assert self.sceneScapeReady(MAX_ATTEMPTS, MAX_CONTROLLER_WAIT)

      # Step 1: Create test camera
      log.info("Creating test camera for intrinsics testing")
      cameraUID = self._setupTestCamera()

      # Step 2: Test first set of parameter updates (similar to "top_save" button)
      log.info("Testing first set of intrinsics parameter updates")
      assert self._updateAndValidateIntrinsics(cameraUID, 5.0, 5.0)

      # Step 3: Test second set of parameter updates (similar to "bottom_save" button)
      log.info("Testing second set of intrinsics parameter updates")
      assert self._updateAndValidateIntrinsics(cameraUID, 10.0, 5.0)

      log.info("Camera intrinsics test completed successfully")
      self.exitCode = 0

    except Exception as e:
      log.error(f"Test failed with exception: {e}")
      self.exitCode = 1
      raise
    finally:
      # Cleanup
      self._cleanupTestCamera(cameraUID)
      self.pubsub.loopStop()
      self.recordTestResult()

    return

def test_camera_intrinsics(request, record_xml_attribute):
  test = CameraIntrinsicsTest(TEST_NAME, request, record_xml_attribute)
  test.testCameraIntrinsics()
  assert test.exitCode == 0
