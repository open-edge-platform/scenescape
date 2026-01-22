#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import json
import time
from scene_common import log
from scene_common.mqtt import PubSub
from tests.functional import FunctionalTest
from scene_common.timestamp import get_iso_time

TEST_NAME = "NEX-T15347"
FRAMES_PER_SECOND = 10
PERSON = "person"

class SceneControllerImportJSON(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneUID = self.params['scene_id']
    self.frameRate = FRAMES_PER_SECOND
    self.sceneData = None
    self.jsonPath = "./sample_data/Retail.json"

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'], int(self.params['broker_port']))

    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def regulatedReceived(self, pahoClient, userdata, message):
    data = message.payload.decode("utf-8")
    self.sceneData = json.loads(data)
    return

  def runTest(self):
    """Checks that JSON file is a valid data source when database is inaccessible

    Steps:
      * Get scene JSON file
      * Subscribe to regulated scene MQTT topic and verify messages are present

    Notes:
      * This test requires to be run using scene_no_db.yml present in tests/compose folder
      * This compose file removes --restauth option from scene service and replaces it with --data_source pointing to JSON.
    """

    self.exitCode = 1

    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)
    try:
      log.info(f"Executing test {TEST_NAME}")
      log.info("Step 1. Verify JSON file exists")
      assert os.path.exists(self.jsonPath), "JSON file does not exist"
      log.info("JSON file present")

      log.info("Step 2. Check for regulated messages")
      log.info("Adding callback to check for regulated messages.")
      topic_regulated = self.pubsub.formatTopic(self.pubsub.DATA_REGULATED, scene_id=self.sceneUID)
      self.pubsub.addCallback(topic_regulated, self.regulatedReceived)

      log.info("Sending detections for regulated messages to appear.")
      objLocation = self.getLocations()
      jdata = self.objData()
      for location in objLocation:
        camera_id = jdata['id']
        jdata['timestamp'] = get_iso_time()
        jdata['objects'][PERSON][0]['bounding_box']['y'] = location
        detection = json.dumps(jdata)
        self.pubsub.publish(PubSub.formatTopic(PubSub.DATA_CAMERA,
                                         camera_id=camera_id), detection)
        time.sleep(1 / self.frameRate)

      log.info("Verifying if regulated messages appeared")
      assert self.sceneData != None, "No regulated message received."

      log.info(f"Regulated message received. Contents:\n{self.sceneData}")
      self.exitCode = 0

    except Exception as e:
      log.error(f"Test failed with exception: {e}")
      self.exitCode = 1

    finally:
      self.pubsub.loopStop()

    return self.exitCode

def test_scene_controller_import_json(request, record_xml_attribute):
  test = SceneControllerImportJSON(TEST_NAME, request, record_xml_attribute)
  assert test.runTest() == 0
