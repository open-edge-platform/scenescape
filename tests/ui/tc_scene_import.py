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

from tests.ui import UserInterfaceTest
import tests.ui.common_ui_test_utils as common
import os
import time

from scene_common.mqtt import PubSub

MAX_CONTROLLER_WAIT = 30 # seconds
TEST_WAIT_TIME = 10
TEST_NAME = "scene import"
class WillOurShipGo(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.sceneUID = self.params['scene_id']

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'], int(self.params['broker_port']))

    self.pubsub.connect()
    self.pubsub.loopStart()
    return

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      waitTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id="+")
      assert self.waitForTopic(waitTopic, MAX_CONTROLLER_WAIT), "Percebro not ready"

      waitTopic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.sceneUID)
      assert self.waitForTopic(waitTopic, MAX_CONTROLLER_WAIT), "Scene controller not ready"

      assert self.login()
      time.sleep(5)

      zipFile = os.path.join(common.TEST_MEDIA_PATH, "Test.zip")
      importSceneButton = self.findElement(self.By.ID, "import_scene")
      importSceneButton.click()
      time.sleep(1)

      self.findElement(self.By.ID, "id_zipFile").send_keys(zipFile)
      importButton = self.findElement(self.By.ID, "scene_import")
      importButton.click()
      time.sleep(30)

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
