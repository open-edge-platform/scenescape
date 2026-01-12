#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from http import HTTPStatus
from scene_common import log
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10399"
MAX_CONTROLLER_WAIT = 20  # seconds
MAX_ATTEMPTS = 3

class DeleteSensorsTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.testScene1Name = "Scene-1"
    self.testScene2Name = "Scene-2"
    self.testSensor1Name = "Sensor_1"
    self.testSensor2Name = "Sensor_2"
    self.testSensor1Id = "Sensor1"
    self.testSensor2Id = "Sensor2"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def _createTestScene(self, sceneName):
    """Create a test scene"""
    log.info(f"Creating test scene: {sceneName}")

    sceneData = {
      'name': sceneName,
      'scale': 1000  # pixels per meter
    }

    scene = self.rest.createScene(sceneData)
    assert scene, (scene.statusCode, scene.errors)
    return scene['uid']

  def _createTestSensor(self, sceneUID, sensorName, sensorId):
    """Create a test sensor in the given scene"""
    log.info(f"Creating test sensor: {sensorName} in scene: {sceneUID}")

    # Create a simple rectangular sensor
    sensorData = {
      'scene': sceneUID,
      'name': sensorName,
      'sensor_id': sensorId,
      'area': 'poly',
      'points': [
        [0.0, 0.0],
        [100.0, 0.0],
        [100.0, 100.0],
        [0.0, 100.0]
      ]
    }

    sensor = self.rest.createSensor(sensorData)
    assert sensor, (sensor.statusCode, sensor.errors)
    return sensor['uid']

  def _verifySensorExists(self, sensorName):
    """Verify that sensor exists in the sensor list"""
    log.info(f"Verifying sensor {sensorName} exists")

    sensors = self.rest.getSensors({})
    assert sensors, (sensors.statusCode, sensors.errors)

    for sensor in sensors['results']:
      if sensor['name'] == sensorName:
        return True, sensor['uid']

    return False, None

  def _verifySensorOrphaned(self, sensorUID):
    """Verify that sensor is orphaned (scene is None)"""
    log.info(f"Verifying sensor {sensorUID} is orphaned")

    sensor = self.rest.getSensor(sensorUID)
    assert sensor, (sensor.statusCode, sensor.errors)

    return 'scene' not in sensor or sensor['scene'] is None

  def _cleanupTestScene(self, sceneUID):
    """Delete the test scene"""
    try:
      if sceneUID:
        log.info(f"Cleaning up test scene: {sceneUID}")
        self.rest.deleteScene(sceneUID)
    except:
      pass  # Scene might already be deleted

  def _cleanupTestSensor(self, sensorUID):
    """Delete the test sensor"""
    try:
      if sensorUID:
        log.info(f"Cleaning up test sensor: {sensorUID}")
        self.rest.deleteSensor(sensorUID)
    except:
      pass  # Sensor might already be deleted

  def testDeleteSensors(self):
    """! Test that sensors can be deleted from scenes, including orphaned sensors.

    Steps:
      * Create two test scenes
      * Create a sensor in each scene
      * Delete one scene (making one sensor orphaned)
      * Delete the sensor that was in the remaining scene
      * Delete the orphaned sensor
      * Verify both sensors are completely removed
      * Cleanup remaining scene
    """
    log.info(f"Executing: {TEST_NAME}")
    log.info("Test deleting sensors")

    scene1UID = None
    scene2UID = None
    sensor1UID = None
    sensor2UID = None

    try:
      # Make sure that the SceneScape is up and running
      log.info("Make sure that the SceneScape is up and running")
      assert self.sceneScapeReady(MAX_ATTEMPTS, MAX_CONTROLLER_WAIT)

      # Step 1: Create two test scenes
      scene1UID = self._createTestScene(self.testScene1Name)
      scene2UID = self._createTestScene(self.testScene2Name)

      # Step 2: Create sensors in each scene
      sensor1UID = self._createTestSensor(scene1UID, self.testSensor1Name, self.testSensor1Id)
      sensor2UID = self._createTestSensor(scene2UID, self.testSensor2Name, self.testSensor2Id)

      # Step 3: Delete Scene-2 (making Sensor_2 orphaned)
      log.info(f"Deleting scene: {self.testScene2Name}")
      deleteResult = self.rest.deleteScene(scene2UID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)
      scene2UID = None  # Mark as deleted

      # Wait a moment for changes to propagate
      time.sleep(1)

      # Step 4: Verify Sensor_2 is now orphaned
      log.info(f"Verifying {self.testSensor2Name} is orphaned")
      assert self._verifySensorOrphaned(sensor2UID), f"{self.testSensor2Name} should be orphaned"

      # Step 5: Delete Sensor_1 (which was assigned to Scene-1)
      log.info(f"Deleting sensor: {self.testSensor1Name} (assigned to {self.testScene1Name})")
      deleteResult = self.rest.deleteSensor(sensor1UID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)

      # Verify Sensor_1 is deleted
      sensorExists, _ = self._verifySensorExists(self.testSensor1Name)
      assert not sensorExists, f"{self.testSensor1Name} should be deleted"
      log.info(f"{self.testSensor1Name} was assigned to {self.testScene1Name} and can be deleted")
      sensor1UID = None  # Mark as deleted

      # Step 6: Delete Sensor_2 (which was orphaned)
      log.info(f"Deleting sensor: {self.testSensor2Name} (orphaned)")
      deleteResult = self.rest.deleteSensor(sensor2UID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)

      # Verify Sensor_2 is deleted
      sensorExists, _ = self._verifySensorExists(self.testSensor2Name)
      assert not sensorExists, f"{self.testSensor2Name} should be deleted"
      log.info(f"{self.testSensor2Name} was orphaned(--) and can be deleted")
      sensor2UID = None  # Mark as deleted

      # Step 7: Delete remaining Scene-1
      log.info(f"Deleting remaining scene: {self.testScene1Name}")
      deleteResult = self.rest.deleteScene(scene1UID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)
      scene1UID = None  # Mark as deleted

      log.info("Delete sensors test completed successfully")
      self.exitCode = 0

    except Exception as e:
      log.error(f"Test failed with exception: {e}")
      self.exitCode = 1
      raise
    finally:
      # Cleanup
      self._cleanupTestSensor(sensor1UID)
      self._cleanupTestSensor(sensor2UID)
      self._cleanupTestScene(scene1UID)
      self._cleanupTestScene(scene2UID)
      self.recordTestResult()

    return

def test_delete_sensor(request, record_xml_attribute):
  test = DeleteSensorsTest(TEST_NAME, request, record_xml_attribute)
  test.testDeleteSensors()
  assert test.exitCode == 0
