#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
import pytest

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

def enter_and_validate_parameters(browser, button_id, initial_value, step):
  """! Enters camera intrinsic and distortion parameters into the web UI.
  @param    browser             Object wrapping the Selenium driver.
  @param    button_id           ID of the Save Camera button.
  @param    initial_value       Initial value for camera parameters values.
  @param    step                Step size to increment from the initial value.
  @return   BOOL                Boolean representing successfully entering the camera parameters.
  """
  camera1_element_id = "//a[@href = '/cam/calibrate/1']"
  assert common.wait_for_elements(browser, camera1_element_id)
  assert common.click_when_clickable(browser, (By.XPATH, camera1_element_id)), (
    f"Timed out waiting for camera link {camera1_element_id!r} to become clickable."
  )

  # Enter parameters
  assert common.wait_for_elements(browser, "id_intrinsics_fx", findBy=By.ID)
  parameter_elems = browser.find_elements(By.CSS_SELECTOR, "[id^=id_intrinsics], [id^=id_distortion]")
  value = initial_value
  for elem in parameter_elems:
    readonly = elem.get_attribute("readonly")
    disabled = elem.get_attribute("disabled")
    if not readonly and not disabled:
      elem.clear()
      elem.send_keys('{:.1f}'.format(value))
    value += step

  log.info("Saving changes...")
  assert common.click_when_clickable(browser, (By.ID, button_id)), (
    f"Timed out waiting for button {button_id!r} to become clickable."
  )

  assert common.wait_for_elements(browser, camera1_element_id)
  assert common.click_when_clickable(browser, (By.XPATH, camera1_element_id)), (
    f"Timed out waiting for camera link {camera1_element_id!r} to become clickable."
  )

  # Validate parameters
  assert common.wait_for_elements(browser, "id_intrinsics_fx", findBy=By.ID)
  parameter_elems = browser.find_elements(By.CSS_SELECTOR, "[id^=id_intrinsics], [id^=id_distortion]")
  value = initial_value
  for elem in parameter_elems:
    current_value = elem.get_attribute('value')
    readonly = elem.get_attribute("readonly")
    disabled = elem.get_attribute("disabled")
    if not readonly and not disabled:
      print(f"Expected value: {value}, Current value: {current_value}")
      if current_value != '{:.1f}'.format(value):
        raise RuntimeError(f"Value mismatch: Expected {value}, but current {current_value}.")
      value += step
  return True

@pytest.mark.test_name("NEX-T10415")
def test_camera_intrinsics_main(params, record_xml_attribute):
  """! Checks that the camera parameters in the web UI can be updated and
  that they persist after saving, for both Camera Save buttons.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10415"
  exit_code = 1

  try:
    log.info("Executing: " + TEST_NAME)
    browser = Browser()
    assert common.check_page_login(browser, params)
    buttons = {
      "top_save": 5,
      "bottom_save": 10
    }
    for button_id, initial_value in buttons.items():
      log.info(f"Entering parameters, clicking {button_id} button, and validating parameters...")
      assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
      assert enter_and_validate_parameters(browser, button_id, initial_value, 5)

    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
