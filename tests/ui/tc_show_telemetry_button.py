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
import os
import time

from scene_common.mqtt import PubSub

MAX_CONTROLLER_WAIT = 30 # seconds
TEST_WAIT_TIME = 10
TEST_NAME = "NEX-T10435"
NO_FPS_STATUS = "--"

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
      assert self.navigateToScene(self.sceneName)
      telemetry_toggle = self.findElement(self.By.ID, "show-telemetry")
      assert not telemetry_toggle.is_selected(), "Show Telemetry is already on"
      fps_check1 = self.findElement(self.By.ID, "rate-camera1").text
      assert fps_check1 == NO_FPS_STATUS

      #enable "Show Telemetry" toggle
      self.executeScript("arguments[0].click();", telemetry_toggle)

      wait_time = 0
      while wait_time < TEST_WAIT_TIME:
        fps_check2 = self.findElement(self.By.ID, "rate-camera1").text
        print(f"Check {wait_time}: {fps_check2}")
        if fps_check2 != NO_FPS_STATUS:
          break
        time.sleep(1)
        wait_time += 1

      print(f"rate '{fps_check1}' updated to '{fps_check2}'")
      assert fps_check1 != fps_check2

      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

def test_telemetry_button(request, record_xml_attribute):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return

def main():
  return test_telemetry_button(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
