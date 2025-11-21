#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from scene_common import log
from tests.functional.common_scene_obj import SceneObjectMqtt

TEST_NAME = "NEX-T15347"

class SceneControllerImportJSON(SceneObjectMqtt):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.jsonPath = "./sample_data/Retail.json"
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
    self.runSceneObjMqttInitialize()
    try:
      log.info(f"Executing test {TEST_NAME}")
      log.info("Step 1. Verify JSON file exists")
      assert os.path.exists(self.jsonPath), "JSON file does not exist"
      log.info("JSON file present")

      log.info("Step 2. Check for regulated messages")
      log.info("Sending detections for regulated messages to appear.")
      self.runSceneObjMqttPrepare()
      objLocation = self.getLocations()
      self.sendDetections(objLocation, self.frameRate)

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
