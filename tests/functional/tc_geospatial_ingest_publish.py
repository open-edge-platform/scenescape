#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
import time
import numpy as np

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from scene_common.earth_lla import calculateTRSLocal2LLAFromSurfacePoints, convertXYZToLLA
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10490"
CHILD_NAME = "Child"
THING_TYPE = "person"
CAMERA_ID = "camera1"
FRAMES_PER_SECOND = 10
MAX_WAIT_TIMEOUT = 30
LLA_VALUE = [50, 0, -6.37813751e+06]
TRANSLATION_VALUE = [-0.3278, -0.3907, 0]
BOUNDING_BOX = {'x': 0.56, 'y': 0.0, 'width': 0.24, 'height': 0.49}
# the following constants are used to verify that the LLA coordinates of the detected object are correct
DETECTION_XYZ = [3.8679791719486474, 2.7517397452609087, 1.1225254457301852e-19]
EXPECTED_DETECTION_LLA = [37.38688947231117, -121.96410520894621, 8.068826778282563]
# the following values are stored in the test database
MAP_CORNERS_LLA = [[ 37.38685435, -121.96408120, 8.0], [ 37.38693520, -121.96408120, 8.0],
      [ 37.38693520, -121.96413896, 8.0], [ 37.38685435, -121.96413896, 8.0]]
MAP_RESOLUTION = [900, 643]
MAP_SCALE = 100.0

class GeospatialIngestPublish(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.exitCode = 1
    self.outputLLA = False
    self.outputReceived = False
    self.sceneUID = self.params['scene_id']

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'])
    self.topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.sceneUID)
    self.pubsub.onConnect = self.pubsubConnected
    self.pubsub.addCallback(self.topic, self.eventReceived)
    self.pubsub.connect()
    self.pubsub.loopStart()
    self.detectionValidator = None
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    self.pubsub.subscribe(self.topic)
    return

  # TODO: refactor this function: we should not use exceptions to control the flow
  def eventReceived(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    detectionData = json.loads(data)
    try:
      self.verifyDetection(detectionData)
      self.outputReceived = True
    except AssertionError:
      pass
    return

  def verifyDetection(self, detectionData):
    assert "objects" in detectionData
    assert len(detectionData['objects']) > 0
    for object in detectionData['objects']:
      assert "translation" in object
      if self.outputLLA:
        assert "lat_long_alt" in object
        if self.detectionValidator:
          try:
            self.detectionValidator(object)
          except ValueError as e:
            print(e)
            raise AssertionError(f"Detection validation failed: {e}")
      else:
        assert "lat_long_alt" not in object
    return

  def formatDetection(self, timestamp, velocity=[1, 1, 1], lla=None, translation=None):
    detection = {
      'id': CHILD_NAME,
      'timestamp': timestamp,
      'objects': [
        {
          'id': 1,
          'category': THING_TYPE,
          'velocity': velocity,
          'size': [1.5, 1.5, 1.5]
        },
      ],
    }
    if translation:
      detection['objects'][0]['translation'] = translation
    if lla:
      detection['objects'][0]['lat_long_alt'] = lla
    return detection

  def prepareScene(self):
    res = self.rest.getScenes({'id': self.sceneUID})
    assert res and res['count'] >= 1, (res.statusCode, res.errors)
    parent_id = res['results'][0]['uid']
    self.childName = CHILD_NAME
    res = self.rest.createScene({'name': self.childName, 'parent': parent_id})
    self.childId = res['uid']
    assert res, (res.statusCode, res.errors)

    sensor = {'name': 'scene_sensor', 'scene': parent_id, 'area': 'scene'}
    res = self.rest.createSensor(sensor)
    assert res, (res.statusCode, res.errors)

  def verifyIngest(self):
    detection = self.formatDetection(get_iso_time(), translation=TRANSLATION_VALUE)
    topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                               scene_id=self.childId,
                               thing_type=THING_TYPE)
    waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                   scene_id=self.sceneUID,
                                   thing_type=THING_TYPE)
    count = self.sceneControllerReady(waitTopic, topic, MAX_WAIT_TIMEOUT,
                                      time.time(), 1 / FRAMES_PER_SECOND, detection)
    assert count, "Scene controller not ready"

    print("Checking scene ignores lat_long_alt + translation data")
    self.outputReceived = False
    for v in [i * 0.5 for i in range(0, 20)]:
      detection = self.formatDetection(
        get_iso_time(), [v, v, v], lla=LLA_VALUE, translation=TRANSLATION_VALUE)
      self.pubsub.publish(topic, json.dumps(detection))
      time.sleep(1 / FRAMES_PER_SECOND)
      if self.outputReceived is True:
        break
    assert self.outputReceived is not True

    print("\nChecking scene can accept lat_long_alt data")
    for v in [i * 0.5 for i in range(0, 20)]:
      detection = self.formatDetection(get_iso_time(), [v, v, v], lla=LLA_VALUE)
      self.pubsub.publish(topic, json.dumps(detection))
      time.sleep(1 / FRAMES_PER_SECOND)
      if self.outputReceived is True:
        break
    assert self.outputReceived is True
    return

  def sendDetection(self):
    objData = {
      'id': CAMERA_ID,
      'objects': {
        THING_TYPE:[
          {
            'id': 1,
            'category': THING_TYPE,
            'bounding_box': BOUNDING_BOX
          },
        ],
      },
      'rate': FRAMES_PER_SECOND,
    }
    objData["timestamp"] = get_iso_time()
    detection = json.dumps(objData)
    self.pubsub.publish(PubSub.formatTopic(PubSub.DATA_CAMERA,
                                           camera_id=CAMERA_ID), detection)
    return

  def waitForUpdate(self, outputLLA, timeout=MAX_WAIT_TIMEOUT):
    self.outputLLA = outputLLA
    self.outputReceived = False
    start_time = time.time()

    while self.outputReceived is False:
      self.sendDetection()
      time.sleep(1 / FRAMES_PER_SECOND)
      if time.time() - start_time > timeout:
        break

    assert self.outputReceived is True
    print(f"Time taken for data format update: {time.time() - start_time}")
    return

  def verifyPublish(self):
    print("Verifying base output has no lat_long_alt")
    self.waitForUpdate(False)
    print("Enabling lat_long_alt output")
    self.rest.updateScene(self.sceneUID, {'output_lla': True})
    self.detectionValidator = _verifyLLA
    self.waitForUpdate(True)
    print("Disabling lat_long_alt output")
    self.rest.updateScene(self.sceneUID, {'output_lla': False})
    self.detectionValidator = None
    self.waitForUpdate(False)
    return

  def verifyFunction(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      self.check_geospatial_constants()
      self.prepareScene()
      self.verifyIngest()
      self.verifyPublish()
      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

  def check_geospatial_constants(self):
    """! Verify geospatial constants."""
    map_corners = [ [0, 0, 0],
          [MAP_RESOLUTION[0] / MAP_SCALE, 0, 0],
          [MAP_RESOLUTION[0] / MAP_SCALE, MAP_RESOLUTION[1] / MAP_SCALE, 0],
          [0, MAP_RESOLUTION[1] / MAP_SCALE, 0] ]
    trs = calculateTRSLocal2LLAFromSurfacePoints(map_corners, MAP_CORNERS_LLA)
    lla = convertXYZToLLA(trs, DETECTION_XYZ)
    if not np.allclose(lla, EXPECTED_DETECTION_LLA, rtol=1e-8):
      raise ValueError(f"Constants verification failed! Expected LLA: {EXPECTED_DETECTION_LLA}, got: {lla}")

def _verifyLLA(detected_object):
  '''
  Verify the LLA coordinates of the detected object, assuming that:
  - The LLA coordinates of four map corners are:
    [[ 37.38685435, -121.96408120, 8.0], [ 37.38693520, -121.96408120, 8.0],
    [ 37.38693520, -121.96413896, 8.0], [ 37.38685435, -121.96413896, 8.0]]
    (the coordinates are loaded from the test database)
  - The scene dimensions are:
    x=0.24, y=0.49
  - The translation of the detected object is:
    [3.8679791719486474, 2.7517397452609087, 1.1225254457301852e-19]
  '''
  if not np.allclose(detected_object['lat_long_alt'], EXPECTED_DETECTION_LLA, rtol=1e-8):
    raise ValueError(f"LLA verification failed! Expected LLA: {EXPECTED_DETECTION_LLA}, got: {detected_object['lat_long_alt']}")

def test_geospatial_ingest_publish(request, record_xml_attribute):
  test = GeospatialIngestPublish(TEST_NAME, request, record_xml_attribute)
  test.verifyFunction()
  assert test.exitCode == 0
  return

def main():
  return test_geospatial_ingest_publish(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
