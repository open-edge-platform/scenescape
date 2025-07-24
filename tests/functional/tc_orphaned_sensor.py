#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from scene_common import log
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest
from tests.functional.rest_test_cases import testCases

TEST_NAME = "NEX-T10398"
MAX_CONTROLLER_WAIT = 30 # seconds
MAX_ATTEMPTS = 3

class OrphanedSensorTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.existingSceneUID = self.params['scene_id']
    self.newSceneName = "automated-scene1"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def _isSensorAvailable(self, sensorID):
    getAllSensors = self.rest.getSensors({})

    for sensor in getAllSensors['results']:
      if sensor['uid'] == sensorID:
        return True

    return False

  def verifyOrphanedSensors(self):
    """ Verifies that sensor can exist even if the scene associated with it is deleted.
    Also verifies that the orphaned sensor can be assigned to another scene.

    Steps:
      * Create new scene
      * Create new sensor and assign to the new scene
      * Delete the new scene
      * Check the orphaned sensor still exists in all sensor list
      * Add orphaned sensor to another scene
      * Get the entire list of sensors and verify that the new sensor has the new scene ID
    """

    log.info("Make sure that the SceneScape is up and running")
    assert self.sceneScapeReady(MAX_ATTEMPTS, MAX_CONTROLLER_WAIT)

    try:
      log.info(f"Generating a new scene: {self.newSceneName}")
      newScene = self.rest.createScene({'name': self.newSceneName})
      assert newScene, (newScene.statusCode, newScene.errors)

      sensorData = testCases['Sensor']['create'][0][0]
      log.info(f"Generating a new sensor with the following data: {sensorData}")
      sensorData['scene'] = newScene['uid']
      newSensor = self.rest.createSensor(sensorData)
      assert newSensor, (newSensor.statusCode, newSensor.errors)

      log.info(f"Make sure the sensor is available in the sensor list after deleting associated scene")
      assert self.rest.deleteScene(newScene['uid'])
      assert self._isSensorAvailable(newSensor['uid'])

      log.info(f"Assign the orphaned sensor to an existing scene")
      existingScene = self.rest.getScenes({'id': self.existingSceneUID})
      assert existingScene['results'], (existingScene.statusCode, existingScene.errors)
      sceneID = existingScene['results'][0]['uid']

      sensorData['scene'] = sceneID
      updateNewSensor = self.rest.updateSensor(newSensor['uid'], sensorData)
      assert updateNewSensor and updateNewSensor['scene'] == sceneID, \
        (updateNewSensor.statusCode, updateNewSensor.errors)

      log.info("Make sure that the sensor is still available")
      assert self._isSensorAvailable(newSensor['uid'])

      self.exitCode = 0

    finally:
      self.recordTestResult()

    return

def test_orphaned_sensors(request, record_xml_attribute):
  test = OrphanedSensorTest(TEST_NAME, request, record_xml_attribute)
  test.verifyOrphanedSensors()
  assert test.exitCode == 0
  return

def main():
  return test_orphaned_sensors(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
