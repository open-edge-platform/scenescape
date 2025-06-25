#!/usr/bin/env python3

# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import json
import os
import time

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_epoch_time

from tests.functional import FunctionalTest

TEST_NAME = 'NEX-T10507'
FRAMES_PER_SECOND = 10
PERSON = "person"
CAMERA_ID = "camera1"
MAX_CONTROLLER_WAIT = 30 # seconds
DETECTION_WAIT = 10

class Percebro3DMsgs(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.passed = False
    self.sceneUID = self.params['scene_id']
    self.frameRate = FRAMES_PER_SECOND
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, (res.errors)

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'])

    self.topics = [PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)]
    self.pubsub.onConnect = self.pubsubConnected
    self.pubsub.addCallback(self.topics[0], self.detectionReceived)
    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    for topic in self.topics:
      self.pubsub.subscribe(topic)
    return

  def detectionReceived(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    detectionData = json.loads(data)
    self.verifyDetectionData(detectionData)
    return

  def dictContains(self, keys, dictionary):
    for key in keys:
      assert key in dictionary
    return

  def checkType(self, ele_type, data):
    assert all(isinstance(x, ele_type) for x in data)
    return

  def checkDictValType(self, ele_type, keys, dictionary):
    for key in keys:
      assert isinstance(dictionary[key], ele_type)
    return

  def checkDictValPos(self, keys, dictionary):
    for key in keys:
      assert dictionary[key] >= 0
    return

  def verifyDetectionData(self, detectionData):
    if PERSON in detectionData['objects'] and \
       len(detectionData["objects"][PERSON]) > 0 and len(detectionData["objects"][PERSON][0]) > 0:
      object_1 = detectionData["objects"][PERSON][0]
      assert object_1["id"] == 1
      assert object_1["category"] == "person"

      assert isinstance(object_1["confidence"], float)
      assert object_1["confidence"] >= 0.0
      assert object_1["confidence"] <= 1.0

      assert len(object_1["translation"]) == 3
      self.checkType(float, object_1["translation"])
      assert len(object_1["size"]) == 3
      self.checkType(float, object_1["size"])

      dict_keys = ["x","y","z","width","height","depth"]
      dimensions = ["width","height","depth"]
      self.dictContains(dict_keys, object_1["center_of_mass"])
      self.checkDictValType((float, int), dict_keys, object_1["center_of_mass"])
      self.checkDictValPos(dimensions, object_1["center_of_mass"])

      self.passed = True
    return

  def getScene(self):
    res = self.rest.getScenes({'id': self.sceneUID})
    assert res['results'], ("Scene does not exist", self.sceneUID, res.statusCode, res.errors)
    return

  def objData(self):
    jdata = {"id": "camera2", "objects": {}, "rate": 9.8}
    obj = {"id": 1, "category": "person",
           "bounding_box": { "x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49}}
    jdata['objects']['person'] = obj
    return jdata

  def setupTest(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)
    return

  def prepareTest(self):
    objData = self.objData()
    waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                   scene_id=self.sceneUID, thing_type=PERSON)
    publishTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=objData['id'])
    begin = get_epoch_time()
    count = self.sceneControllerReady(waitTopic, publishTopic, MAX_CONTROLLER_WAIT,
                                      begin, 1 / self.frameRate, objData)
    assert count is not None
    self.getScene()
    return

  def executeTest(self):
    time.sleep(DETECTION_WAIT)
    return

  def teardownTest(self):
    self.pubsub.loopStop()
    self.recordTestResult()
    return

  def runTest(self):
    self.exitCode = 1
    self.setupTest()
    try:
      self.prepareTest()
      self.executeTest()
      if self.passed:
        self.exitCode = 0
    finally:
      self.teardownTest()
    return

def test_3D_percebro_msgs(request, record_xml_attribute):
  test = Percebro3DMsgs(TEST_NAME, request, record_xml_attribute)
  test.runTest()
  assert test.exitCode == 0
  return

def main():
  return test_3D_percebro_msgs(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
