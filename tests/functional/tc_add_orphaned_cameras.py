#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from scene_common import log
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10402"
MAX_CONTROLLER_WAIT = 20 # seconds
MAX_ATTEMPTS = 3

class OrphanedCameraTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.existingSceneUID = self.params['scene_id']
    self.newSceneName = "automated-scene1"
    self.newCameraName = "automated-camera1"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def _isCameraAvailable(self, cameras, cameraID):
    for camera in cameras:
      if camera['uid'] == cameraID:
        return True

    return False

  def verifyOrphanedCameras(self):
    """ Verifies that camera can exist even if the scene associated with it is deleted.
    Also verifies that the orphaned camera can be assigned to another scene.

    Steps:
      * Create new scene
      * Create new camera and assign to the new scene
      * Delete the new scene
      * Check the orphaned camera still exists in all camera list
      * Add orphaned camera to another scene
      * Get the entire list of cameras and verify that the new camera is has the new scene ID
    """

    log.info("Make sure that the SceneScape is up and running")
    assert self.sceneScapeReady(MAX_ATTEMPTS, MAX_CONTROLLER_WAIT)

    try:
      log.info(f"Generating a new scene: {self.newSceneName}")
      newScene = self.rest.createScene({'name': self.newSceneName})
      assert newScene, (newScene.statusCode, newScene.errors)

      log.info(f"Generating a new camera: {self.newCameraName} and adding it to scene: {newScene['uid']}")
      newCamera = self.rest.createCamera({'name': self.newCameraName, 'scene': newScene['uid']})
      assert newCamera, (newCamera.statusCode, newCamera.errors)

      log.info(f"Delete the newly created scene: {newScene['uid']}")
      assert self.rest.deleteScene(newScene['uid'])

      log.info("Make sure the camera is available in the camera list after deleting associated scene")
      getAllCameras = self.rest.getCameras({})
      assert len(getAllCameras['results']) >= 1 \
        and self._isCameraAvailable(getAllCameras['results'], newCamera['uid'])

      log.info("Assign the orphaned camera to an existing scene")
      existingScene = self.rest.getScenes({'id': self.existingSceneUID})
      assert existingScene['results'], (existingScene.statusCode, existingScene.errors)
      sceneID = existingScene['results'][0]['uid']
      updateNewCamera = self.rest.updateCamera(newCamera['uid'], {'scene': sceneID})
      assert updateNewCamera and updateNewCamera['scene'] == sceneID, \
        (updateNewCamera.statusCode, updateNewCamera.errors)

      log.info("Make sure that the camera is still available")
      getAllCameras = self.rest.getCameras({})
      assert len(getAllCameras['results']) >= 1 \
        and self._isCameraAvailable(getAllCameras['results'], newCamera['uid'])

      self.exitCode = 0

    finally:
      self.recordTestResult()

    return

def test_orphaned_cameras(request, record_xml_attribute):
  test = OrphanedCameraTest(TEST_NAME, request, record_xml_attribute)
  test.verifyOrphanedCameras()
  assert test.exitCode == 0
  return

def main():
  return test_orphaned_cameras(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
