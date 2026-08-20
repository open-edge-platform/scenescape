#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import os
from http import HTTPStatus
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time, get_epoch_time
from tests.functional.common_scene_obj import SceneObjectMqtt
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
from tests.utils.log import get_logger

log = get_logger(__name__)


SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T10460"
SENSOR_DELAY = 0.5
SENSOR_PROC_DELAY = 0.001
SENSOR_NAME = "TestSensor1"
PERSON = "person"
REGION = "region"
FRAME_RATE = 10
MAX_DELAYS = 100

class SensorMqttRoi(SceneObjectMqtt):
  def __init__(self, testName, request, sensor_delay, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sensorHistory = []
    self.sensorDelay = sensor_delay
    self.foundValid = 0
    self.sensorValue = 100
    self.missedValues = 0
    self.errorInSensor = False
    self.checkedValues = 0
    self.checkedEntered = 0
    self.checkedExited = 0
    self.enteredDetected = True
    self.exitedDetected = True
    self.exitedTimestamp = None
    self.enteredTimestamp = None
    return

  def createSensor(self, sensorData):
    res = self.rest.createSensor(sensorData)
    assert res.statusCode == HTTPStatus.CREATED, (res.statusCode, res.errors)
    return

  def runSceneObjMqttPrepareExtra(self):
    topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=self.roiName)
    self.pubsub.addCallback(topic, self.sensorDataReceived)

    sensor = {
      'scene': self.sceneUID,
      'name': self.roiName,
      'area': "poly",
      'points': self.roiPoints
    }

    self.createSensor(sensor)

    time.sleep(1)
    assert self.pushSensorValue(self.roiName, self.sensorValue)
    time.sleep(3)

    return

  def runSceneObjMqttVerifyPassedExtra(self):
    log.info("Verifying test parameters")
    assert not self.errorInSensor
    assert self.enteredDetected
    assert self.exitedDetected
    assert self.foundValid > 0
    assert self.checkedEntered > 0
    assert self.checkedExited > 0
    assert self.checkedValues > 0
    # Verify dwell window calculation is sensible
    self.verifyDwellWindowExists()
    return True

  def verifyDwellWindowExists(self):
    """Verify dwell window metadata exists for integration validation.

    This validates integration aspects only - that entry/exit times were properly
    captured. The actual dwell calculation formulas are already tested by unit tests.
    """
    if self.enteredTimestamp is None:
      return  # No entry detected, nothing to verify

    if self.exitedTimestamp is not None:
      dwell_window = self.exitedTimestamp - self.enteredTimestamp
      assert dwell_window >= 0, f"Invalid dwell window: exit before entry"
      log.info(f"Dwell window validated: {dwell_window:.2f}s from entry to exit")
    else:
      log.info("Object still in region - no exit timestamp to validate")
    return

  def sendDetections(self, objLocation, frame_rate):
    jdata = self.objData()
    start_time = get_epoch_time()
    for location in objLocation:
      now = time.time()
      camera_id = jdata['id']
      jdata['timestamp'] = get_iso_time(now)
      jdata['objects'][PERSON][0]['bounding_box']['y'] = location
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / frame_rate)
      if now - start_time > self.sensorDelay:
        start_time = now
        self.sensorValue += 1
        assert self.pushSensorValue(self.roiName, self.sensorValue)
        time.sleep(SENSOR_PROC_DELAY)
    return

  def eventReceived(self, pahoClient, userdata, message):
    region_data = json.loads(message.payload.decode("utf-8"))
    has_objects = len(region_data.get('objects', [])) > 0
    has_region_transitions = (
      len(region_data.get('entered', [])) > 0
      or len(region_data.get('exited', [])) > 0
    )
    if has_objects or has_region_transitions:
      self.handleRegionData(region_data)

    return

  def regulatedReceived(self, pahoClient, userdata, message):
    if self.entered:
      scene_data = json.loads(message.payload.decode("utf-8"))

      for obj in scene_data['objects']:
        current_point = obj['translation']
        scene_message_ts = get_epoch_time(scene_data['timestamp'])
        if not self.isWithinRectangle(
          self.roiPoints[1], self.roiPoints[3],
          (current_point[0], current_point[1])
        ):
          self.exited = True
          self.entered = False
          self.exitedDetected = True
          self.exitedTimestamp = scene_message_ts
          log.info('object exited region')
        self.handleSceneSensorData(obj, scene_message_ts, self.exitedTimestamp)
        if self.exited:
          self.exitedTimestamp = None
          self.enteredTimestamp = None
        if self.errorInSensor:
          break
    return

  def sensorDataReceived(self, pahoClient, userdata, message):
    sensor_data = json.loads(message.payload.decode("utf-8"))
    self.sensorHistory.append(sensor_data)
    return

  def pushSensorValue(self, sensor_name, value):
    message_dict = {
      'timestamp': get_iso_time(),
      'id': sensor_name,
      'value': value
    }

    # Publish the message to the sensor topic
    result = self.pubsub.publish(
      PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor_name),
      json.dumps(message_dict)
    )
    error_code = result[0]
    if error_code != 0:
      log.info(f"Failed to send sensor {sensor_name} value!")
      log.info(result.is_published())
    return error_code == 0

  def runROIMqtt(self):
    self.exitCode = 1
    self.runSceneObjMqttInitialize()
    try:
      self.runSceneObjMqttPrepare()
      self.runSceneObjMqttPrepareExtra()
      self.runROIMqttExecute()
      passed = self.runROIMqttVerifyPassed()
      passed_extra = self.runSceneObjMqttVerifyPassedExtra()
      if (passed and passed_extra):
        self.exitCode = 0
    finally:
      self.runSceneObjMqttFinally()
    return

  def handleEnteredExitedObjects(self, object_list, sensor_history_list):
    found_error = False
    for obj in object_list:
      if not self.findAllSensorsInRange(obj, sensor_history_list):
        found_error = True
        break
    return found_error is False

  def handleRegionData(self, region_data):
    objects = region_data.get('objects', [])
    if len(objects) == 0:
      log.info("No objects in region!")

    region_message_ts = get_epoch_time(region_data['timestamp'])
    if len(objects) > 0:
      current_point = objects[0]['translation']
      if self.isWithinRectangle(self.roiPoints[1], self.roiPoints[3], (current_point[0], current_point[1])):
        self.entered = True
        self.enteredDetected = True
        self.object_in_region = True  # Critical: update flag for regionDataReceived callback
        log.info('object entered region')
        if self.enteredTimestamp is None:
          self.enteredTimestamp = region_message_ts

    # Check for exit events to clear object_in_region flag
    exited_objects = region_data.get('exited', [])
    if len(exited_objects) > 0:
      self.object_in_region = False  # Critical: update flag when object exits
      log.info('object exited region')

    entered_objects = region_data.get('entered', [])
    # Exited objects arrive wrapped as {'object': ..., 'dwell': N}; unwrap for sensor checks.
    unwrapped_exited = [
      item['object'] if isinstance(item, dict) and 'object' in item else item
      for item in exited_objects
    ]
    if self.entered and self.enteredTimestamp is not None and len(self.sensorHistory) > 0:
      start_idx, end_idx = self.findSensorIndexes(
        self.enteredTimestamp, region_message_ts, self.exitedTimestamp)
      if not self.handleEnteredExitedObjects(entered_objects,
                                             self.sensorHistory[start_idx:end_idx]):
        log.info("Found error in 'entered' objects!")
        self.errorInSensor = True
      else:
        self.checkedEntered += 1

      if not self.handleEnteredExitedObjects(unwrapped_exited,
                                             self.sensorHistory[start_idx:end_idx]):
        log.info("Found error in 'exited' objects!")
        self.errorInSensor = True
      else:
        self.checkedExited += 1
    return

  def findAllSensorsInRange(self, obj, sensor_list):
    found_all = True
    for cur_sensor in sensor_list:
      found = self.findSensorInObj(obj, cur_sensor, self.roiName)
      if not found:
        log.info(
          f"Warning: failed to find expected sensor value {cur_sensor['value']} "
          f"(TS {cur_sensor['timestamp']})"
        )
        found_all = False
      else:
        self.foundValid += 1
    return found_all

  def findSensorInObj(self, obj, sensor_entry, sensor_name):
    found = False
    expected_sensor_ts = get_epoch_time(sensor_entry['timestamp'])
    expected_sensor_value = sensor_entry['value']

    if not 'sensors' in obj:
      log.info(f"Object missing sensor data {obj}")
      return False

    sensor_payload = obj['sensors'].get(sensor_name)
    if sensor_payload is None:
      log.info(f"Object missing expected sensor '{sensor_name}' data {obj}")
      return False

    if isinstance(sensor_payload, dict):
      sensor_values = sensor_payload.get('values', [])
    else:
      sensor_values = sensor_payload

    for sensor_info in sensor_values:
      if get_epoch_time(sensor_info[0]) == expected_sensor_ts \
              and sensor_info[1] == expected_sensor_value:
        found = True
        break
    return found

  def handleSceneSensorData(self, obj, scene_message_ts, exited_timestamp):
    if self.enteredTimestamp is None:
      return

    if self.entered and len(self.sensorHistory) > 0:
      start_idx, end_idx = self.findSensorIndexes(
        self.enteredTimestamp, scene_message_ts, exited_timestamp)
      found_all = self.findAllSensorsInRange(obj, self.sensorHistory[start_idx:end_idx])

      if found_all:
        self.missedValues = 0
      else:
        # Sometimes the scene controller hasn't updated the last sensor value,
        # but it will on subsequent messages, so allow to check it later
        if self.missedValues:
          self.errorInSensor = True
          log.info("Had previously Failed to find some expected sensor values!")
        else:
          self.missedValues += 1

      self.checkedValues += end_idx - start_idx
    return

  def findSensorIndexes(self, entered_ts, cur_scene_ts, exited_ts):
    global SENSOR_PROC_DELAY
    start_idx = 0
    end_idx = len(self.sensorHistory) - 1

    for cur_idx, sensor in enumerate(self.sensorHistory):
      cur_sensor_ts = get_epoch_time(sensor['timestamp'])
      if (cur_sensor_ts - SENSOR_PROC_DELAY) <= entered_ts:
        start_idx = cur_idx
      if exited_ts is not None:
        # Give the scene controller a grace period to process the sensor sensor data.
        if (cur_sensor_ts - SENSOR_PROC_DELAY) < exited_ts:
          end_idx = max(0, cur_idx - 1)
      else:
        if (cur_sensor_ts - SENSOR_PROC_DELAY) < cur_scene_ts:
          end_idx = cur_idx
    if end_idx == start_idx:
      end_idx += 1
    return start_idx, end_idx

def test_sensor_roi_mqtt(scenescape_env, demo_scene, request, record_xml_attribute):
  test = SensorMqttRoi(TEST_NAME, request, SENSOR_DELAY, record_xml_attribute)
  test.sceneUID = demo_scene
  test.runROIMqtt()
  assert test.exitCode == 0
