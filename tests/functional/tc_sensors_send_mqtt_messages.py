#!/usr/bin/env python3

# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

# Microservices needed for test:
#   * broker
#   * web (REST)
#   * pgserver
#   * scene

from tests.functional import FunctionalTest

import os
import numpy as np
import json
import time

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_epoch_time, get_iso_time
from scene_common.geometry import Point

TEST_NAME = "NEX-T10456"
WALKING_SPEED = 1.2 # meters per second
FRAMES_PER_SECOND = 10
THING_TYPE = "person"
MAX_CONTROLLER_WAIT = 30 # seconds

class WillOurShipGo(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneUID = self.params['scene_id']

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'])

    self.eventTopic = PubSub.formatTopic(PubSub.EVENT, region_type="region", event_type="+",
                                         scene_id="+", region_id="+")
    self.pubsub.onConnect = self.pubsubConnected
    self.pubsub.addCallback(self.eventTopic, self.eventReceived)
    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    self.pubsub.subscribe(self.eventTopic)
    return

  def eventReceived(self, pahoClient, userdata, message):
    topic = PubSub.parseTopic(message.topic)
    self.sensors[topic['region_id']]['received'] = get_epoch_time()
    return

  def prepareScene(self):
    res = self.rest.getScenes({'id': self.sceneUID})
    assert res and res['count'] >= 1, (res.statusCode, res.errors)
    parent_id = res['results'][0]['uid']
    self.childName = "child"
    res = self.rest.createScene({'name': self.childName, 'parent': parent_id})
    self.childId = res['uid']
    assert res, (res.statusCode, res.errors)

    self.sensors = {
      'scene_sensor': {
        'area': "scene",
      },
      'circle_sensor': {
        'area': "circle",
        'radius': 1,
        'center': (0, 0),
      },
      'poly_sensor': {
        'area': "poly",
        'points': ((-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5)),
      }
    }

    for name in self.sensors:
      sensorConfig = {
        'name': name,
        'scene': parent_id,
      }
      sensorConfig.update(self.sensors[name])
      res = self.rest.createSensor(sensorConfig)
      assert res, (res.statusCode, res.errors)

    return

  def plotCourse(self):
    startPosition = (-2, -2, 0)
    endPosition = (2, 2, 0)
    stepDistance = WALKING_SPEED / FRAMES_PER_SECOND

    # FIXME - should probably use whichever dimension results in the
    #         most number of steps, not index 0
    course = [np.arange(startPosition[0], endPosition[0], stepDistance)]
    for idx in range(1, len(startPosition)):
      course.append(np.linspace(startPosition[idx], endPosition[idx], len(course[0])))
    course = np.dstack(course)
    return course[0]

  def createDetection(self, begin, idx, positionNow, positionLast):
    velocity = positionNow - positionLast
    detection = {
      'id': self.childName,
      'timestamp': get_iso_time(begin + idx / FRAMES_PER_SECOND),
      'objects': [
        {
          'id': 1,
          'category': THING_TYPE,
          'translation': positionNow.asNumpyCartesian.tolist(),
          'size': [1.5, 1.5, 1.5],
          'velocity': velocity.asNumpyCartesian.tolist(),
        },
      ],
    }
    return detection

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      self.prepareScene()
      course = self.plotCourse()

      topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                                 scene_id=self.childId, thing_type=THING_TYPE)
      begin = get_epoch_time()
      positionLast = Point(course[0])

      waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                     scene_id=self.sceneUID, thing_type=THING_TYPE)
      positionNow = Point(course[0])
      detection = self.createDetection(begin, 0, positionNow, positionNow)
      count = self.sceneControllerReady(waitTopic, topic, MAX_CONTROLLER_WAIT,
                                        begin, 1 / FRAMES_PER_SECOND, detection)
      assert count, "Scene controller not ready"

      for idx in range(len(course)):
        positionNow = Point(course[idx])
        detection = self.createDetection(begin, idx + count, positionNow, positionLast)
        self.pubsub.publish(topic, json.dumps(detection))
        time.sleep(1 / FRAMES_PER_SECOND)

        sensorsReceived = [name for name in self.sensors if 'received' in self.sensors[name]]
        if len(sensorsReceived) == len(self.sensors):
          self.exitCode = 0
          break

        positionLast = positionNow

      print("Received events from sensors:", sensorsReceived)
    finally:
      self.recordTestResult()
    return

def test_sensor_region_events(request, record_xml_attribute):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_sensor_region_events(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
