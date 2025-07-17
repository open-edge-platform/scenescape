#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

# Microservices needed for test:
#   * broker
#   * ntpserv
#   * pgserver
#   * scene (regulated topic)
#   * video
#   * web (REST)

import os
import time
import zipfile
import json
import pytest
import re

from scene_common.mqtt import PubSub

import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest

MAX_CONTROLLER_WAIT = 30  # seconds
TEST_WAIT_TIME = 10
TEST_NAME = "scene import"

SUCCESS = '0'
EMPTY_ZIP = '1'
INVALID_ZIP = '2'
SCENE_EXISTS = '3'

class WillOurShipGo(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute, zipFile, expected):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.sceneUID = self.params['scene_id']
    self.expected = expected
    self.errors = {
      EMPTY_ZIP: "Cannot find JSON or resource file",
      INVALID_ZIP: "Failed to parse JSON",
      SCENE_EXISTS: "A scene with the name '{}' already exists."
    }
    if self.expected != SUCCESS:
      print('expected error:', self.errors[self.expected])

    self.zipFile = os.path.join(common.TEST_MEDIA_PATH, zipFile)
    print(self.zipFile)
    self.pubsub = PubSub(
      self.params['auth'],
      None,
      self.params['rootcert'],
      self.params['broker_url'],
      int(self.params['broker_port'])
    )
    if self.expected == SUCCESS or self.expected == SCENE_EXISTS:
      self.sceneData = self.readJSONFromZip()
    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def getThingTabCount(self, thing):
    count = 0
    if thing == 'children':
      children_element = self.findElement(self.By.ID, "children-tab")
      text = children_element.text
      match = re.search(r'\((\d+)\)', text)
      if match:
        count = int(match.group(1))
    else:
      count_element = self.findElement(self.By.CSS_SELECTOR, f"#{thing}-tab .show-count")
      count_text = count_element.text.strip("()")
      count = int(count_text)
    return count

  def readJSONFromZip(self):
    data = None
    with zipfile.ZipFile(self.zipFile, 'r') as zip_ref:
      json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
      if not json_files:
        print("No JSON file found inside the zip archive.")
        return data
      with zip_ref.open(json_files[0]) as json_file:
        data = json.load(json_file)
    return data

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      waitTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id="+")
      assert self.waitForTopic(waitTopic, MAX_CONTROLLER_WAIT), "Percebro not ready"

      waitTopic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.sceneUID)
      assert self.waitForTopic(waitTopic, MAX_CONTROLLER_WAIT), "Scene controller not ready"

      assert self.login()
      importSceneButton = self.findElement(self.By.ID, "import-scene")
      importSceneButton.click()
      time.sleep(TEST_WAIT_TIME)

      self.findElement(self.By.ID, "id_zipFile").send_keys(self.zipFile)
      errors_list = self.findElement(self.By.ID, "global-error-list")
      importButton = self.findElement(self.By.ID, "scene-import")
      importButton.click()

      time.sleep(TEST_WAIT_TIME)
      if self.expected == SCENE_EXISTS or self.expected == EMPTY_ZIP or self.expected == INVALID_ZIP:
        errorMessage = self.errors[self.expected]

        if self.expected == SCENE_EXISTS:
          errorMessage = errorMessage.format(self.sceneData['name'])

        errors_list = self.findElement(self.By.ID, "global-error-list")
        assert errors_list
        print("Errors detected")
        print(errors_list.text.strip())
        assert errorMessage == errors_list.text.strip()

      if self.expected == SUCCESS:
        print("No errors detected")
        print('navigating to: ', self.sceneData['name'])
        # img = self.getPageScreenshot()
        # cv2.imwrite("screenshot.png", img)
        assert self.navigateToScene(self.sceneData['name'])
        cameras = len(self.sceneData.get('cameras', []))
        tripwires = len(self.sceneData.get('tripwires', []))
        regions = len(self.sceneData.get('regions', []))
        sensors = len(self.sceneData.get('sensors', []))
        children = len(self.sceneData.get('children', []))

        cameraCount = self.getThingTabCount("cameras")
        tripwireCount = self.getThingTabCount("tripwires")
        regionCount = self.getThingTabCount("regions")
        sensorCount = self.getThingTabCount("sensors")
        childrenCount = self.getThingTabCount("children")

        assert cameras == cameraCount
        assert tripwires == tripwireCount
        assert regions == regionCount
        assert sensors == sensorCount
        assert children == childrenCount

      self.exitCode = 0

    finally:
      self.recordTestResult()
    return

@pytest.mark.parametrize(
  "zipFile, expected",
  [
    ("Retail.zip", '0'), # Standard scene with tripwire, sensor, region and cameras
    ("Empty.zip", '1'), # Empty zip file
    ("Retail.zip", '3'), # Duplicate scene
    ("Parent.zip", '0'), # Local scene hierarchy
    ("Invalid.zip", '2') # Malformed JSON
  ]
)
def test_scene_import(request, record_xml_attribute, zipFile, expected):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute, zipFile, expected)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return

def main():
  return test_scene_import(None, None, None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
