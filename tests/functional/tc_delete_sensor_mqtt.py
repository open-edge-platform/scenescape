#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import os
from http import HTTPStatus
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from tests.functional.common_scene_obj import SceneObjectMqtt

TEST_NAME = "NEX-T10399"   # replace with your test case ID
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

    # Send initial sensor value to confirm publishing works
    assert self.pushSensorValue(self.roiName, self.sensorValue)
    time.sleep(2)

  def runSensorMqttDelete(self):
    """Main workflow for delete sensor test."""
    self.exitCode = 1
    try:
      self.runSceneObjMqttPrepareExtra()

      # Delete the sensor
      res = self.rest.deleteSensor(self.roiName)
      assert res.statusCode == HTTPStatus.OK, (res.statusCode, res.errors)
      time.sleep(2)
      self.sensor_deleted = True

      # Try publishing again, should NOT be received
      self.sensorValue += 1
      self.pushSensorValue(self.roiName, self.sensorValue)
      time.sleep(2)

      self.runSceneObjMqttVerifyPassedExtra()
    finally:
      self.runSceneObjMqttFinally()
    return

  def runSceneObjMqttVerifyPassedExtra(self):
    """Verify that no MQTT messages were received after deletion."""
    assert (
      self.sensor_message_received_after_delete is False
    ), "MQTT messages were still received after sensor deletion"
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
      print(f"Failed to send sensor {sensor_name} value!")
      print(result.is_published())
    return error_code == 0

def test_sensor_delete_mqtt(request, record_xml_attribute):
  test = SensorDeleteMqtt(TEST_NAME, request, record_xml_attribute)
  test.runSensorMqttDelete()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_sensor_delete_mqtt(None, None)

if __name__ == "__main__":
  os._exit(main() or 0)
