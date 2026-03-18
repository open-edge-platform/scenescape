#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from tests.ui import UserInterfaceTest
from tests.ui import common

class NoAprilTagCalibrationTest(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.exitCode = 1
    return
  
  def execute_test(self):
    """! Executes test case """
    cam_url = "/cam/calibrate/1"

    assert self.login()
    # self.navigateDirectlyToPage("/cam/list/")
    self.navigateDirectlyToPage(cam_url)
    print("Successfully navigated to camera1 page.")

    expected_label = "Cannot auto calibrate. Check scene to ensure there are at least 4 april tags"
    actual_label = self.check_label("auto-autocalibration")
    print(f"Expected label: {expected_label}")
    print(f"Actual label: {actual_label}")

    if expected_label == actual_label:
      self.exitCode = 0
      print("Autocalibration label displays correct message.")
    else: 
      print("Autocalibration label displays wrong message.")
  
  def check_label(self, button_id):
    button = self.browser.find_element(By.ID, button_id)
    label = button.get_attribute("title")
    return label

  # def check_container_logs(self):

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
