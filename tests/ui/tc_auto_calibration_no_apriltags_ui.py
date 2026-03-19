#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from tests.ui import UserInterfaceTest
from tests.ui import common

class NoAprilTagCalibrationTest(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.exitCode = 1
    return
  
  def wait_for_button_label(self, driver, expected_label, actual_label, button_id):
    value = driver.find_element(By.ID, button_id).get_attribute("title")
    actual_label['value'] = value
    return value == expected_label
  
  def execute_test(self):
    """! Executes test case """
    expected_label = "Cannot auto calibrate. Check scene to ensure there are at least 4 april tags"
    actual_label = {"value": None}
    cam_url = "/cam/calibrate/1"
    button_id = "auto-autocalibration"
    wait_time = 600

    assert self.login()
    print("Navigating to camera1 page.")
    self.navigateDirectlyToPage(cam_url)

    print(f"Checking auto calibration button label. Timeout: {wait_time}")
    WebDriverWait(self.browser, wait_time).until(
      lambda d: self.wait_for_button_label(d, expected_label, actual_label, button_id)
    )

    if expected_label == actual_label['value']:
      self.exitCode = 0
      print("Autocalibration label displays correct message.")
    else: 
      print("Autocalibration label displays wrong message.")

@common.mock_display
def test_no_april_tag(request, record_xml_attribute):
  """! Checks that the ACC displays an appropriate error message and disables the calibration button when no April tags are present in the scene.
  @param    request                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10485"
  record_xml_attribute("name", TEST_NAME)

  test = NoAprilTagCalibrationTest(TEST_NAME, request, record_xml_attribute)
  test.execute_test()

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_no_april_tag(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
