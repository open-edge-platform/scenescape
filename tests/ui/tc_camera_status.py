#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import time
from tests.ui.browser import Browser, By
from tests.mqtt_helper import mqtt_wait_for_detections
import tests.ui.common_ui_test_utils as common

def test_camera_status_main(params, record_xml_attribute):
  """! Checks that the camera streams on the WebUI are updated, reporting success
  if camera 1 and 2 streams are updated, and camera 3 is offline.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10416"
  record_xml_attribute("name", TEST_NAME)
  cameraNumber = 3
  exit_code = 1

  try:
    print("Executing: " + TEST_NAME)
    print("Test that cameras identify as offline until data is received")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    print("Waiting for the cameras to send the data...")
    assert mqtt_wait_for_detections(params['broker_url'], params['broker_port'], params['rootcert'],
                                    params['auth'], waitOnPercebro=True, waitOnScene=False)
    statusCamera = [False] * cameraNumber
    foundCameras = 0
    assert common.wait_for_elements(browser, "#camera1", findBy=By.CSS_SELECTOR)

    camerasOnline = False
    currWait = 0
    maxWait = 30
    while not camerasOnline:
      currWait += 1
      if currWait < maxWait:
        time.sleep(1)
      else:
        print("Camera1 failed to come online...")
        break
      camerasOnline = browser.find_element(By.CSS_SELECTOR, "#camera1").is_displayed()

    assert camerasOnline
    for i in range(cameraNumber):
      statusCamera[i] = browser.find_element(By.CSS_SELECTOR, "#camera{}".format(i+1)).is_displayed()
      foundCameras += 1

    assert foundCameras == cameraNumber
    label_cam_offline = browser.find_element(By.CLASS_NAME, "cam-offline").get_attribute("textContent")
    assert statusCamera[0] and statusCamera[1] and not statusCamera[2]
    print("Camera1 & Camera2 are visible and show a snapshot!")
    print("Camera3 does not sending data and displays the label: " + label_cam_offline)
    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
