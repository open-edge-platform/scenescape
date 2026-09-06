# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from tests.ui import UserInterfaceTest
from tests.ui import common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK_AUTOCALIBRATION_NO_APRILTAGS
import pytest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_AUTOCALIBRATION_NO_APRILTAGS,
  require_password=True, auth="",
)

class RegistrationErrorHandlingTest(UserInterfaceTest):
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

    # First visit takes the async registration path (map not yet processed) and
    # leaves the scene's map marked as processed once it settles.
    print("Navigating to camera1 page to let the first registration settle.")
    self.navigateDirectlyToPage(cam_url)
    WebDriverWait(self.browser, timeout).until(
      lambda d: self.wait_for_button_label(d, expected_label, actual_label, button_id)
    )

    button_element = self.browser.find_element(By.ID, button_id)
    if button_element.is_enabled():
      print("Auto calibration button should be disabled after the async registration error path.")
      return

    # Reloading now hits the synchronous registration-error path, which never emits
    # a "register_result" socket event, previously leaving the button stuck on
    # "Initializing auto camera calibration".
    print("Reloading the page to force a synchronous registration error response.")
    actual_label['value'] = None
    self.browser.refresh()

    print(f"Checking auto calibration button label after reload. Timeout: {timeout}")
    try:
      WebDriverWait(self.browser, timeout).until(
        lambda d: self.wait_for_button_label(d, expected_label, actual_label, button_id)
      )
      print("Autocalibration label displays correct message after reload.")
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
      print("Button state is correct and label displays correct message after a synchronous registration error.")
    else:
      print("Autocalibration label or button state is incorrect after a synchronous registration error.")

@pytest.mark.test_name("NEX-T27164")
@common.mock_display
def test_registration_error_status_handled(request, record_xml_attribute, scenescape_env):
  """! Checks that a synchronous registration-error response (no register_result socket
  event) still updates the Auto Calibrate button/tooltip instead of leaving it stuck on
  "Initializing auto camera calibration".
  @param    request                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T27164"

  test = RegistrationErrorHandlingTest(TEST_NAME, request, record_xml_attribute)
  test.execute_test()

  common.record_test_result(TEST_NAME, test.exitCode)

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_registration_error_status_handled(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
