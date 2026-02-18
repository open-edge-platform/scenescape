#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Functional tests for singleton sensor tagging on tracked objects.
Tests environmental and attribute sensors with entry/exit events.
"""

import json
import time
import os
from http import HTTPStatus
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time, get_epoch_time
from tests.functional.common_scene_obj import SceneObjectMqtt

TEST_NAME = "singleton-sensor-tagging"
SENSOR_DELAY = 0.5
SENSOR_PROC_DELAY = 0.1
TEMP_SENSOR_NAME = "temp"
BADGE_SENSOR_NAME = "badge"
PERSON = "person"
REGION = "region"
FRAME_RATE = 10
MAX_DELAYS = 100


class SingletonSensorTagging(SceneObjectMqtt):
  """Test singleton sensor tagging for environmental and attribute sensors."""

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.tempSensorHistory = []
    self.badgeSensorHistory = []
    self.tempValue = 20.5
    self.badgeValue = "BADGE-1002"
    self.errorInSensor = False
    
    # Test state tracking
    self.test1_passed = False  # Entry with temp reading
    self.test2_passed = False  # Exit with temp reading, removed from object
    self.test3_passed = False  # Re-entry with cached temp reading
    self.test4_passed = False  # Badge entry and exit persistence
    self.test5_passed = False  # Badge re-entry without previous value
    
    # Event tracking
    self.temp_sensor_uid = None
    self.badge_sensor_uid = None
    self.entered_events = []
    self.exited_events = []
    self.regulated_messages = []
    
    return

  def createSensor(self, sensorData):
    """Create a sensor via REST API."""
    res = self.rest.createSensor(sensorData)
    assert res.statusCode == HTTPStatus.CREATED, (res.statusCode, res.errors)
    return res['uid']

  def runSceneObjMqttPrepareExtra(self):
    """Create sensors and subscribe to events."""
    # Pre-cleanup: Delete any existing temp/badge sensors from previous runs
    try:
      sensors = self.rest.getSensors(self.sceneUID)
      for sensor in sensors:
        if sensor.get('sensor_id') in [TEMP_SENSOR_NAME, BADGE_SENSOR_NAME]:
          print(f"Deleting existing sensor: {sensor.get('sensor_id')} (uid: {sensor.get('uid')})")
          self.rest.deleteSensor(sensor['uid'])
    except Exception as e:
      print(f"Pre-cleanup warning: {e}")

    # Subscribe to temp sensor data
    topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=TEMP_SENSOR_NAME)
    self.pubsub.addCallback(topic, self.tempSensorDataReceived)

    # Subscribe to badge sensor data
    topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=BADGE_SENSOR_NAME)
    self.pubsub.addCallback(topic, self.badgeSensorDataReceived)

    # Create environmental sensor (temp) - circular region
    temp_sensor = {
      'scene': self.sceneUID,
      'sensor_id': TEMP_SENSOR_NAME,
      'name': TEMP_SENSOR_NAME,
      'area': 'circle',
      'radius': 1.464968152866242,
      'center': [3.8535031847133756, 2.4585987261146496],
      'translation': [3.8535031847133756, 2.4585987261146496, 0],
      'singleton_type': 'environmental'
    }
    self.temp_sensor_uid = self.createSensor(temp_sensor)
    print(f"Created temp sensor: {self.temp_sensor_uid}")

    # Subscribe to temp sensor count events
    topic = PubSub.formatTopic(PubSub.EVENT, event_type="count", 
                               scene_id=self.sceneUID,
                               region_id=self.temp_sensor_uid, 
                               region_type=REGION)
    self.pubsub.addCallback(topic, self.tempEventReceived)

    # Create attribute sensor (badge) - polygon region
    badge_sensor = {
      'scene': self.sceneUID,
      'sensor_id': BADGE_SENSOR_NAME,
      'name': BADGE_SENSOR_NAME,
      'area': 'poly',
      'points': [
        [1.732484076433121, 5.738853503184713],
        [0.7834394904458599, 4.732484076433121],
        [1.872611464968153, 3.611464968152866],
        [3.0127388535031847, 4.617834394904459]
      ],
      'radius': 3.6305732484076434,
      'center': [2.0127388535031847, 4.484076433121019],
      'translation': [2.0127388535031847, 4.484076433121019, 0],
      'singleton_type': 'attribute'
    }
    self.badge_sensor_uid = self.createSensor(badge_sensor)
    print(f"Created badge sensor: {self.badge_sensor_uid}")

    # Subscribe to badge sensor count events
    topic = PubSub.formatTopic(PubSub.EVENT, event_type="count",
                               scene_id=self.sceneUID,
                               region_id=self.badge_sensor_uid,
                               region_type=REGION)
    self.pubsub.addCallback(topic, self.badgeEventReceived)

    # Subscribe to regulated topic to verify sensor data on objects
    topic = PubSub.formatTopic(PubSub.REGULATED, scene_id=self.sceneUID,
                               detection_type=PERSON)
    self.pubsub.addCallback(topic, self.regulatedReceived)

    time.sleep(2)
    return

  def tempSensorDataReceived(self, pahoClient, userdata, message):
    """Callback for temperature sensor data."""
    sensor_data = json.loads(message.payload.decode("utf-8"))
    self.tempSensorHistory.append(sensor_data)
    print(f"Temp sensor data received: {sensor_data}")
    return

  def badgeSensorDataReceived(self, pahoClient, userdata, message):
    """Callback for badge sensor data."""
    sensor_data = json.loads(message.payload.decode("utf-8"))
    self.badgeSensorHistory.append(sensor_data)
    print(f"Badge sensor data received: {sensor_data}")
    return

  def tempEventReceived(self, pahoClient, userdata, message):
    """Callback for temp sensor region events."""
    region_data = json.loads(message.payload.decode("utf-8"))
    print(f"Temp event received: entered={len(region_data.get('entered', []))}, "
          f"exited={len(region_data.get('exited', []))}")
    
    # Test 1: Entry with temp reading
    for entered_obj in region_data.get('entered', []):
      if TEMP_SENSOR_NAME in entered_obj.get('sensors', {}):
        sensor_data = entered_obj['sensors'][TEMP_SENSOR_NAME]
        if 'values' in sensor_data and len(sensor_data['values']) > 0:
          print(f"✓ Test 1: Object entered temp region with reading: {sensor_data['values']}")
          self.test1_passed = True
    
    # Test 2 & 3: Exit and re-entry
    for exited_data in region_data.get('exited', []):
      exited_obj = exited_data.get('object', {})
      if TEMP_SENSOR_NAME in exited_obj.get('sensors', {}):
        sensor_data = exited_obj['sensors'][TEMP_SENSOR_NAME]
        if 'values' in sensor_data and len(sensor_data['values']) > 0:
          print(f"✓ Test 2: Object exited temp region with reading: {sensor_data['values']}")
          self.test2_passed = True
    
    self.entered_events.extend(region_data.get('entered', []))
    self.exited_events.extend(region_data.get('exited', []))
    return

  def badgeEventReceived(self, pahoClient, userdata, message):
    """Callback for badge sensor region events."""
    region_data = json.loads(message.payload.decode("utf-8"))
    print(f"Badge event received: entered={len(region_data.get('entered', []))}, "
          f"exited={len(region_data.get('exited', []))}")
    
    # Test 4: Badge entry and persistence on exit
    for entered_obj in region_data.get('entered', []):
      if BADGE_SENSOR_NAME in entered_obj.get('sensors', {}):
        sensor_data = entered_obj['sensors'][BADGE_SENSOR_NAME]
        if 'values' in sensor_data and len(sensor_data['values']) > 0:
          print(f"✓ Test 4a: Object entered badge region with value: {sensor_data['values']}")
    
    for exited_data in region_data.get('exited', []):
      exited_obj = exited_data.get('object', {})
      if BADGE_SENSOR_NAME in exited_obj.get('sensors', {}):
        sensor_data = exited_obj['sensors'][BADGE_SENSOR_NAME]
        if 'values' in sensor_data and len(sensor_data['values']) > 0:
          print(f"✓ Test 4b: Object exited badge region with persisted value: {sensor_data['values']}")
          self.test4_passed = True
    
    # Test 5: Re-entry should NOT have old badge value (attribute sensors don't cache)
    # This will be verified by checking that re-entry doesn't have old values
    
    self.entered_events.extend(region_data.get('entered', []))
    self.exited_events.extend(region_data.get('exited', []))
    return

  def regulatedReceived(self, pahoClient, userdata, message):
    """Callback for regulated messages to track sensor data on objects."""
    scene_data = json.loads(message.payload.decode("utf-8"))
    self.regulated_messages.append(scene_data)
    
    # Verify objects outside temp region don't have temp sensor data
    for obj in scene_data.get('objects', []):
      if TEMP_SENSOR_NAME not in obj.get('regions', {}):
        # Object not in temp region
        if TEMP_SENSOR_NAME in obj.get('sensors', {}):
          print(f"✗ ERROR: Object outside temp region has sensor data!")
          self.errorInSensor = True
    
    return

  def pushTempValue(self, value):
    """Publish temperature sensor reading."""
    message_dict = {
      'timestamp': get_iso_time(),
      'id': TEMP_SENSOR_NAME,
      'value': value
    }
    result = self.pubsub.publish(
      PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=TEMP_SENSOR_NAME),
      json.dumps(message_dict)
    )
    error_code = result[0]
    if error_code != 0:
      print(f"Failed to send temp sensor value!")
    else:
      print(f"Published temp value: {value}")
    return error_code == 0

  def pushBadgeValue(self, value):
    """Publish badge sensor reading."""
    message_dict = {
      'timestamp': get_iso_time(),
      'id': BADGE_SENSOR_NAME,
      'value': value
    }
    result = self.pubsub.publish(
      PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=BADGE_SENSOR_NAME),
      json.dumps(message_dict)
    )
    error_code = result[0]
    if error_code != 0:
      print(f"Failed to send badge sensor value!")
    else:
      print(f"Published badge value: {value}")
    return error_code == 0

  def sendDetectionSequence(self):
    """
    Send detection sequence to test all scenarios:
    1. Object moves into temp region (test 1)
    2. Object exits temp region (test 2)
    3. Object re-enters temp region (test 3)
    4. Object moves into badge region, gets badge, exits (test 4)
    5. Object re-enters badge region without badge published (test 5)
    """
    jdata = self.objData()
    camera_id = jdata['id']
    
    # Publish initial temp reading before object enters
    print("\n=== Publishing initial temp reading ===")
    assert self.pushTempValue(self.tempValue)
    time.sleep(1)
    
    # Move object into temp sensor region (center at ~3.85, 2.46)
    print("\n=== Test 1: Object entering temp region ===")
    locations = [
      {'x': 3.8, 'y': 2.4},  # Inside temp region
      {'x': 3.9, 'y': 2.5},
    ]
    for loc in locations:
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['x'] = loc['x'] * 100
      jdata['objects'][PERSON][0]['bounding_box']['y'] = loc['y'] * 100
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / FRAME_RATE * 2)
    
    time.sleep(2)
    
    # Move object out of temp region
    print("\n=== Test 2: Object exiting temp region ===")
    locations = [
      {'x': 5.5, 'y': 2.5},  # Outside temp region
      {'x': 6.0, 'y': 2.5},
    ]
    for loc in locations:
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['x'] = loc['x'] * 100
      jdata['objects'][PERSON][0]['bounding_box']['y'] = loc['y'] * 100
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / FRAME_RATE * 2)
    
    time.sleep(2)
    
    # Update temp value and move object back into temp region
    print("\n=== Test 3: Object re-entering temp region with cached value ===")
    self.tempValue = 21.8
    assert self.pushTempValue(self.tempValue)
    time.sleep(0.5)
    
    locations = [
      {'x': 4.0, 'y': 2.5},  # Back inside temp region
      {'x': 3.8, 'y': 2.4},
    ]
    for loc in locations:
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['x'] = loc['x'] * 100
      jdata['objects'][PERSON][0]['bounding_box']['y'] = loc['y'] * 100
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / FRAME_RATE * 2)
    
    # Verify test 3 - object should have cached reading
    if len(self.entered_events) >= 2:
      second_entry = self.entered_events[-1]
      if TEMP_SENSOR_NAME in second_entry.get('sensors', {}):
        sensor_data = second_entry['sensors'][TEMP_SENSOR_NAME]
        if 'values' in sensor_data and len(sensor_data['values']) > 0:
          print(f"✓ Test 3: Object re-entered with cached reading: {sensor_data['values']}")
          self.test3_passed = True
    
    time.sleep(2)
    
    # Move to badge region (center at ~2.01, 4.48)
    print("\n=== Test 4: Object entering badge region ===")
    assert self.pushBadgeValue(self.badgeValue)
    time.sleep(0.5)
    
    locations = [
      {'x': 2.0, 'y': 4.5},  # Inside badge region
      {'x': 1.9, 'y': 4.4},
    ]
    for loc in locations:
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['x'] = loc['x'] * 100
      jdata['objects'][PERSON][0]['bounding_box']['y'] = loc['y'] * 100
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / FRAME_RATE * 2)
    
    time.sleep(2)
    
    # Exit badge region
    print("\n=== Test 4: Object exiting badge region ===")
    locations = [
      {'x': 3.5, 'y': 5.0},  # Outside badge region
      {'x': 4.0, 'y': 5.5},
    ]
    for loc in locations:
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['x'] = loc['x'] * 100
      jdata['objects'][PERSON][0]['bounding_box']['y'] = loc['y'] * 100
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / FRAME_RATE * 2)
    
    time.sleep(2)
    
    # Re-enter badge region WITHOUT publishing new badge value
    print("\n=== Test 5: Object re-entering badge region without new value ===")
    # DO NOT publish badge value - test that attribute sensors don't cache
    
    locations = [
      {'x': 2.0, 'y': 4.5},  # Back inside badge region
      {'x': 1.8, 'y': 4.6},
    ]
    for loc in locations:
      jdata['timestamp'] = get_iso_time()
      jdata['objects'][PERSON][0]['bounding_box']['x'] = loc['x'] * 100
      jdata['objects'][PERSON][0]['bounding_box']['y'] = loc['y'] * 100
      detection = json.dumps(jdata)
      self.pubsub.publish(
        PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
        detection
      )
      time.sleep(1 / FRAME_RATE * 2)
    
    time.sleep(2)
    
    # Verify test 5 - check that re-entry doesn't have old badge values
    # Count entries in badge region
    badge_entries = [e for e in self.entered_events 
                    if BADGE_SENSOR_NAME in e.get('regions', {})]
    if len(badge_entries) >= 2:
      second_badge_entry = badge_entries[-1]
      if BADGE_SENSOR_NAME in second_badge_entry.get('sensors', {}):
        sensor_data = second_badge_entry['sensors'][BADGE_SENSOR_NAME]
        # Should NOT have values from previous entry
        if 'values' not in sensor_data or len(sensor_data['values']) == 0:
          print(f"✓ Test 5: Object re-entered badge region without old value (correct!)")
          self.test5_passed = True
        else:
          print(f"✗ Test 5: Object re-entered badge region with old value (wrong!): {sensor_data['values']}")
      else:
        print(f"✓ Test 5: Object re-entered badge region without sensor data (correct!)")
        self.test5_passed = True
    
    return

  def runSceneObjMqttVerifyPassedExtra(self):
    """Verify all test conditions passed."""
    print("\n=== Test Results ===")
    print(f"Test 1 (Temp entry with reading): {'PASS' if self.test1_passed else 'FAIL'}")
    print(f"Test 2 (Temp exit with reading): {'PASS' if self.test2_passed else 'FAIL'}")
    print(f"Test 3 (Temp re-entry cached): {'PASS' if self.test3_passed else 'FAIL'}")
    print(f"Test 4 (Badge exit persistence): {'PASS' if self.test4_passed else 'FAIL'}")
    print(f"Test 5 (Badge re-entry no cache): {'PASS' if self.test5_passed else 'FAIL'}")
    print(f"Error in sensor: {self.errorInSensor}")
    
    assert not self.errorInSensor, "Sensor data errors detected"
    assert self.test1_passed, "Test 1 failed: Object entry with temp reading"
    assert self.test2_passed, "Test 2 failed: Object exit with temp reading"
    assert self.test3_passed, "Test 3 failed: Object re-entry with cached temp"
    assert self.test4_passed, "Test 4 failed: Badge persistence on exit"
    assert self.test5_passed, "Test 5 failed: Badge re-entry without cache"
    
    return True

  def runSingletonSensorTest(self):
    """Main test execution."""
    self.exitCode = 1
    self.runSceneObjMqttInitialize()
    try:
      self.runSceneObjMqttPrepare()
      self.runSceneObjMqttPrepareExtra()
      self.sendDetectionSequence()
      passed = self.runSceneObjMqttVerifyPassedExtra()
      if passed:
        self.exitCode = 0
    finally:
      self.runSceneObjMqttFinally()
      # Clean up sensors
      if self.temp_sensor_uid:
        try:
          self.rest.deleteSensor(self.temp_sensor_uid)
          print(f"Deleted temp sensor: {self.temp_sensor_uid}")
        except:
          pass
      if self.badge_sensor_uid:
        try:
          self.rest.deleteSensor(self.badge_sensor_uid)
          print(f"Deleted badge sensor: {self.badge_sensor_uid}")
        except:
          pass
    return


def test_singleton_sensor_tagging(request, record_xml_attribute):
  """Pytest entry point."""
  test = SingletonSensorTagging(TEST_NAME, request, record_xml_attribute)
  test.runSingletonSensorTest()
  assert test.exitCode == 0
  return test.exitCode


def main():
  """Standalone execution."""
  return test_singleton_sensor_tagging(None, None)


if __name__ == '__main__':
  os._exit(main() or 0)
