#!/usr/bin/env python3

# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

from tests.functional import FunctionalTest
from scene_common.mqtt import PubSub
from scene_common import log
import time
import os
import json

TEST_NAME = "NEX-T10405"
MAX_CONTROLLER_WAIT = 30 # seconds
NUM_MSGS = 100

class AutoCalibration(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.scene_name = "Queuing"
    self.test_camera = "atag-qcam1"
    self.received_response = False
    self.initial_cam_points = [[119.0, 622.0], [257.0, 561.0], [978.0, 580.0], [628.0, 312.0]]
    self.initial_map_points = [[1.685, 2.533], [2.188, 2.578], [4.449, 1.412], [3.94, 3.228]]
    self.updated_cam_points = None
    self.updated_map_points = None
    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'], int(self.params['broker_port']))

    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def collectPoseResults(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    data = json.loads(data)
    if data['error'] == 'False':
      self.updated_cam_points = data['calibration_points_2d']
      self.updated_map_points = data['calibration_points_3d']
    return

  def autoCalibrationStatus(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=self.test_camera)
    if data == 'running' and self.received_response == False:
      log.info('camcalibration status: ', data)
      log.info('sending localize comand...')
      self.pubsub.publish(topic, 'localize')
      self.received_response = True
    return

  def runMqttPrepare(self):
    topic_auto_calib_status = PubSub.formatTopic(PubSub.SYS_AUTOCALIB_STATUS)
    topic_data_autocalib_cam_pose = PubSub.formatTopic(PubSub.DATA_AUTOCALIB_CAM_POSE, camera_id=self.test_camera)
    self.pubsub.addCallback(topic_data_autocalib_cam_pose, self.collectPoseResults)
    self.pubsub.addCallback(topic_auto_calib_status, self.autoCalibrationStatus)
    for i in range(NUM_MSGS):
      self.pubsub.publish(topic_auto_calib_status, "isAlive")
      time.sleep(1)
    return

  def runMqttFinally(self):
    self.pubsub.loopStop()
    self.recordTestResult()
    return

  def runAutoCalibration(self):
    self.exitCode = 1
    try:
      time.sleep(MAX_CONTROLLER_WAIT)
      self.runMqttPrepare()
      log.info('initial camera points: ', self.initial_cam_points)
      log.info('updated camera points: ', self.updated_cam_points)
      log.info('initial map points: ', self.initial_map_points)
      log.info('updated map points: ', self.updated_map_points)

      if self.updated_map_points != None and self.updated_cam_points != None:
        if self.initial_cam_points != self.updated_cam_points \
            and self.initial_map_points != self.updated_map_points:
          self.exitCode = 0

    finally:
      self.runMqttFinally()
    return

def test_auto_calibration(request, record_xml_attribute):
  test = AutoCalibration(TEST_NAME, request, record_xml_attribute)
  test.runAutoCalibration()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_auto_calibration(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
