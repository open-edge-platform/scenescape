#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
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
    timeout = 120

    assert self.login()
    print("Navigating to camera1 page.")
    self.navigateDirectlyToPage(cam_url)

    print(f"Checking auto calibration button label. Timeout: {timeout}")
    try:
      WebDriverWait(self.browser, timeout).until(
        lambda d: self.wait_for_button_label(d, expected_label, actual_label, button_id)
      )
      print("Autocalibration label displays correct message.")
    except TimeoutException:
      print(
        f"Autocalibration label did not display expected message within {timeout} seconds. "
        f"Last observed label: {actual_label['value']!r}, expected: {expected_label!r}."
      )

    print("Checking button state is disabled.")
    button_element = self.browser.find_element(By.ID, button_id)
    button_is_disabled = not button_element.is_enabled()

    if actual_label['value'] == expected_label and button_is_disabled:
      self.exitCode = 0
      print("Button state is correct and label displays correct message.")
    else:
      print("Autocalibration label or button state is incorrect.")

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

  common.record_test_result(TEST_NAME, test.exitCode)

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_no_april_tag(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
