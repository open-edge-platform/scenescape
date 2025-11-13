#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from http import HTTPStatus
from scene_common import log
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10397"
MAX_CONTROLLER_WAIT = 20  # seconds
MAX_ATTEMPTS = 3

class DeleteSensorSceneTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.testSceneName = "Test_Scene_For_Sensor_Deletion"
    self.testSensorName = "Sensor_0"
    self.testSensorId = "test_sensor"

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])
    return

  def _createTestScene(self):
    """Create a test scene for sensor testing"""
    log.info(f"Creating test scene: {self.testSceneName}")

    sceneData = {
      'name': self.testSceneName,
      'scale': 1000  # pixels per meter
    }

    scene = self.rest.createScene(sceneData)
    assert scene, (scene.statusCode, scene.errors)
    return scene['uid']

  def _createTestSensor(self, sceneUID):
    """Create a test sensor in the given scene"""
    log.info(f"Creating test sensor: {self.testSensorName} in scene: {sceneUID}")

    # Create a simple rectangular sensor covering some area
    sensorData = {
      'scene': sceneUID,
      'name': self.testSensorName,
      'sensor_id': self.testSensorId,
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

  def testDeleteSensorScene(self):
    """! Test that sensor can still be deleted after the scene the sensor was attached to is deleted.

    Steps:
      * Create a test scene
      * Create a sensor in that scene
      * Delete the scene
      * Verify sensor still exists but is orphaned
      * Delete the orphaned sensor
      * Verify sensor is completely removed
    """
    log.info(f"Executing: {TEST_NAME}")
    log.info("Test that sensors are not deleted when the parent scene is deleted")

    sceneUID = None
    sensorUID = None

    try:
      # Make sure that the SceneScape is up and running
      log.info("Make sure that the SceneScape is up and running")
      assert self.sceneScapeReady(MAX_ATTEMPTS, MAX_CONTROLLER_WAIT)

      # Step 1: Create test scene
      sceneUID = self._createTestScene()

      # Step 2: Create sensor in the scene
      sensorUID = self._createTestSensor(sceneUID)

      # Step 3: Delete the scene
      log.info(f"Deleting scene: {sceneUID}")
      deleteResult = self.rest.deleteScene(sceneUID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)
      sceneUID = None  # Mark as deleted

      # Wait a moment for changes to propagate
      time.sleep(1)

      # Step 4: Verify sensor still exists but is orphaned
      log.info("Verifying sensor still exists after scene deletion")
      sensorExists, foundSensorUID = self._verifySensorExists(self.testSensorName)
      assert sensorExists, f"Sensor {self.testSensorName} should still exist after scene deletion"
      assert foundSensorUID == sensorUID, "Sensor UID mismatch"

      # Verify sensor is orphaned (scene is None)
      log.info("Verifying sensor is orphaned")
      assert self._verifySensorOrphaned(sensorUID), "Sensor should be orphaned after scene deletion"

      # Step 5: Delete the orphaned sensor
      log.info(f"Deleting orphaned sensor: {sensorUID}")
      deleteResult = self.rest.deleteSensor(sensorUID)
      assert deleteResult.statusCode == HTTPStatus.OK, (deleteResult.statusCode, deleteResult.errors)
      sensorUID = None  # Mark as deleted

      # Step 6: Verify sensor is completely removed
      log.info("Verifying sensor is completely removed")
      sensorExists, _ = self._verifySensorExists(self.testSensorName)
      assert not sensorExists, f"Sensor {self.testSensorName} should be completely removed"

      log.info("Delete sensor after scene deletion test completed successfully")
      self.exitCode = 0

    except Exception as e:
      log.error(f"Test failed with exception: {e}")
      self.exitCode = 1
      raise
    finally:
      # Cleanup
      self._cleanupTestSensor(sensorUID)
      self._cleanupTestScene(sceneUID)
      self.recordTestResult()

    return

def test_del_sensor_scene(request, record_xml_attribute):
  test = DeleteSensorSceneTest(TEST_NAME, request, record_xml_attribute)
  test.testDeleteSensorScene()
  assert test.exitCode == 0
