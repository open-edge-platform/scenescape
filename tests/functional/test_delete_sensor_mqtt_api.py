#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import os
from http import HTTPStatus
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from tests.functional.common_scene_obj import SceneObjectMqtt
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
from tests.utils.log import get_logger
import pytest

log = get_logger(__name__)


SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T21778"
SENSOR_NAME = "temp1"
SENSOR_DELAY = 0.5
SENSOR_PROC_DELAY = 0.001

class SensorDeleteMqtt(SceneObjectMqtt):
  def __init__(self, testName, request, record_xml_attribute):
    super().__init__(testName, request, record_xml_attribute)
    self.sensorValue = 100
    self.sensor_deleted = False
    self.sensor_message_received_after_delete = False
    self.roiPoints = [[-16288968.259278879, -21357971.013039112], [83378856.7842749, 77344998.33741632]]

  def eventReceived(self, pahoClient, userdata, message):
    """Callback for sensor MQTT messages."""
    if self.sensor_deleted:
      # If messages arrive after deletion, mark failure
      self.sensor_message_received_after_delete = True
    return

  def runSceneObjMqttPrepareExtra(self):
    """Prepare: subscribe and create sensor."""
    topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=self.roiName)
    self.pubsub.addCallback(topic, self.eventReceived)

    sensor = {
      "scene": self.sceneUID,
      "name": self.roiName,
      "area": "poly",
      "points": self.roiPoints,
    }
    res = self.rest.createSensor(sensor)
    assert res.statusCode == HTTPStatus.CREATED, (res.statusCode, res.errors)
    self.sensor_uid = res["uid"]

    # Send initial sensor value to confirm publishing works
    assert self.pushSensorValue(self.roiName, self.sensorValue)
    time.sleep(2)

  def runSensorMqttDelete(self):
    """Main workflow for delete sensor test."""
    self.exitCode = 1
    try:
      self.runSceneObjMqttPrepareExtra()

      # Delete the sensor
      res = self.rest.deleteSensor(self.sensor_uid)
      assert res.statusCode == HTTPStatus.OK, (res.statusCode, res.errors)
      time.sleep(2)

      # Unsubscribe before publishing post-delete to prevent MQTT loopback
      topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=self.roiName)
      self.pubsub.removeCallback(topic)
      self.sensor_deleted = True

      # Try publishing again, should NOT be received or processed
      self.sensorValue += 1
      self.pushSensorValue(self.roiName, self.sensorValue)
      time.sleep(2)

      self.runSceneObjMqttVerifyPassedExtra()
      self.exitCode = 0
    finally:
      self.runSceneObjMqttFinally()
    return

  def runSceneObjMqttVerifyPassedExtra(self):
    """Verify that the sensor is gone and MQTT publishes don't resurrect it."""
    res = self.rest.getSensor(self.sensor_uid)
    assert res.statusCode == HTTPStatus.NOT_FOUND, \
      f"Sensor should not exist after deletion, got: {res.statusCode}"
    return True

  def pushSensorValue(self, sensor_name, value):
    """Helper to publish sensor values."""
    message_dict = {
      "timestamp": get_iso_time(),
      "id": sensor_name,
      "value": value,
    }
    result = self.pubsub.publish(
      PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor_name),
      json.dumps(message_dict),
    )
    error_code = result[0]
    if error_code != 0:
      log.info(f"Failed to send sensor {sensor_name} value!")
      log.info(result.is_published())
    return error_code == 0

@pytest.mark.test_name("NEX-T21778")
def test_sensor_delete_mqtt(scenescape_env, demo_scene, request, record_xml_attribute):
  test = SensorDeleteMqtt(TEST_NAME, request, record_xml_attribute)
  test.runSensorMqttDelete()
  assert test.exitCode == 0
