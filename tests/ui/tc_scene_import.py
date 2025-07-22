#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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

from selenium.webdriver.support.ui import WebDriverWait

from scene_common.mqtt import PubSub

import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest

MAX_CONTROLLER_WAIT = 30  # seconds
TEST_WAIT_TIME = 10
TEST_NAME = "scene import"

class WillOurShipGo(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.sceneUID = self.params['scene_id']
    self.zipFile = os.path.join(common.TEST_MEDIA_PATH, self.params['zip_file'])
    self.pubsub = PubSub(
      self.params['auth'],
      None,
      self.params['rootcert'],
      self.params['broker_url'],
      int(self.params['broker_port'])
    )
    self.sceneData = self.readJSONFromZip()
    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def getThingTabCount(self, thing):
    count_element = self.findElement(self.By.CSS_SELECTOR, f"#{thing}-tab .show-count")
    count_text = count_element.text.strip("()")
    count = int(count_text)
    return count

  def readJSONFromZip(self):
    with zipfile.ZipFile(self.zipFile, 'r') as zip_ref:
      json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
      if not json_files:
        raise FileNotFoundError("No JSON file found inside the zip archive.")
      with zip_ref.open(json_files[0]) as json_file:
        data = json.load(json_file)
    return data

  def buildArgparser(self):
    parser = super().buildArgparser()
    parser.add_argument("--zip_file", required=True, help="path to zip file to upload", default='Retail.zip')
    return parser

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
      time.sleep(1)

      self.findElement(self.By.ID, "id_zipFile").send_keys(self.zipFile)
      warning_list = self.findElement(self.By.ID, "global-warning-list")
      importButton = self.findElement(self.By.ID, "scene-import")
      importButton.click()

      try:
        WebDriverWait(self.browser, MAX_CONTROLLER_WAIT).until(
          lambda d: warning_list.text.strip() != ""
        )
        print("Warnings detected in the list!")
        print(warning_list.text.strip())
        self.exitCode = 0
      except:
        print("No warnings detected.")
        print(f"Scene data loaded: {self.sceneData}")
        assert self.navigateToScene(self.sceneData['name'])

        cameras = len(self.sceneData.get('cameras', []))
        tripwires = len(self.sceneData.get('tripwires', []))
        regions = len(self.sceneData.get('regions', []))
        sensors = len(self.sceneData.get('sensors', []))

        cameraCount = self.getThingTabCount("cameras")
        tripwireCount = self.getThingTabCount("tripwires")
        regionCount = self.getThingTabCount("regions")
        sensorCount = self.getThingTabCount("sensors")

        assert cameras == cameraCount
        assert tripwires == tripwireCount
        assert regions == regionCount
        assert sensors == sensorCount

      self.exitCode = 0

    finally:
      self.recordTestResult()
    return

def test_scene_import(request, record_xml_attribute):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return

def main():
  return test_scene_import(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
