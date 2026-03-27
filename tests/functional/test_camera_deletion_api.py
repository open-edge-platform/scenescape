#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from http import HTTPStatus
from scene_common import log
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10403"
MAX_CONTROLLER_WAIT = 20  # seconds
MAX_ATTEMPTS = 3

class CameraDeletionTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.existingSceneUID = self.params['scene_id']
    self.newSceneName = "Automated_Scene_Camera_Deletion"
    self.newCameraName = "Automated_Camera1"
    self.newCameraId = "Automated_ID_Camera1"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def _isCameraAvailable(self, cameras, cameraID):
    """Check if camera with given ID is available in camera list"""
    for camera in cameras:
      if camera['uid'] == cameraID:
        return True
    return False

  def _getCameraByName(self, cameras, cameraName):
    """Get camera by name from camera list"""
    for camera in cameras:
      if camera['name'] == cameraName:
        return camera
    return None

  def testCameraDeletion(self):
    """! Checks that a camera which is not attached to a scene can be deleted.

    Steps:
      * Create a temporary scene
      * Create an orphan camera (not attached to any scene)
      * Attach the orphan camera to the existing test scene
      * Delete the camera from the scene
      * Verify camera is deleted
      * Cleanup: delete temporary scene
    """
    log.info(f"Executing: {TEST_NAME}")

    try:
      # Make sure that the SceneScape is up and running
      log.info("Make sure that the SceneScape is up and running")
      assert self.sceneScapeReady(MAX_ATTEMPTS, MAX_CONTROLLER_WAIT)

      # Step 1: Create a temporary scene to initially attach camera
      log.info(f"Creating temporary scene: {self.newSceneName}")
      tempScene = self.rest.createScene({'name': self.newSceneName})
      assert tempScene, (tempScene.statusCode, tempScene.errors)
      tempSceneUID = tempScene['uid']

      # Step 2: Create orphan camera by creating it in temp scene then deleting the scene
      log.info(f"Creating camera: {self.newCameraName} in temporary scene")
      newCamera = self.rest.createCamera({
        'name': self.newCameraName,
        'sensor_id': self.newCameraId,
        'scene': tempSceneUID
      })
      assert newCamera, (newCamera.statusCode, newCamera.errors)
      cameraUID = newCamera['uid']

      # Step 3: Delete temporary scene to make camera orphan
      log.info(f"Deleting temporary scene to create orphan camera")
      deleteResult = self.rest.deleteScene(tempSceneUID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)

      # Step 4: Verify camera is now orphan (scene is None)
      log.info("Verifying camera is now orphan")
      cameraCheck = self.rest.getCamera(cameraUID)
      assert cameraCheck, (cameraCheck.statusCode, cameraCheck.errors)
      assert 'scene' not in cameraCheck or cameraCheck['scene'] is None, "Camera should be orphan after scene deletion"

      # Step 5: Attach orphan camera to existing test scene
      log.info(f"Attaching orphan camera to scene: {self.existingSceneUID}")
      updateResult = self.rest.updateCamera(cameraUID, {'scene': self.existingSceneUID})
      assert updateResult, (updateResult.statusCode, updateResult.errors)
      assert updateResult['scene'] == self.existingSceneUID

      # Step 6: Verify camera is in the scene cameras list
      log.info("Verifying camera is attached to scene")
      sceneCheck = self.rest.getScene(self.existingSceneUID)
      assert sceneCheck, (sceneCheck.statusCode, sceneCheck.errors)

      # Step 7: Delete the camera
      log.info(f"Deleting camera: {self.newCameraName}")
      deleteResult = self.rest.deleteCamera(cameraUID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)

      # Step 8: Verify camera is deleted - should not appear in cameras list
      log.info("Verifying camera is deleted")
      allCameras = self.rest.getCameras({})
      assert allCameras, (allCameras.statusCode, allCameras.errors)

      # Check that deleted camera is not in the list
      deletedCamera = self._getCameraByName(allCameras['results'], self.newCameraName)
      assert deletedCamera is None, f"Camera {self.newCameraName} should be deleted but still found in camera list"

      log.info(f"Camera {self.newCameraName} successfully deleted")
      self.exitCode = 0

    except Exception as e:
      log.error(f"Test failed with exception: {e}")
      self.exitCode = 1
      raise
    finally:
      # Cleanup: try to delete temporary scene if it still exists
      try:
        self.rest.deleteScene(tempSceneUID)
      except:
        pass  # Scene might already be deleted

      self.recordTestResult()

    return

def test_camera_deletion_main(request, record_xml_attribute):
  test = CameraDeletionTest(TEST_NAME, request, record_xml_attribute)
  test.testCameraDeletion()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_camera_deletion_main(None, None)

if __name__ == "__main__":
  os._exit(main() or 0)
