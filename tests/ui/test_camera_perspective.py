#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import random
import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from scene_common import log

TEST_WAIT_TIME = 5


def reset_perspective(browser):
  """! Resets the points defining the camera calibration.
  @param    browser       Object wrapping the Selenium driver.
  @ return  BOOL      Boolean representing a successful reset.
  """
  try:
    browser.find_element(By.ID, "reset_points").click()
    time.sleep(TEST_WAIT_TIME)
    browser.find_element(By.NAME, "calibrate_save").click()
    log.info("Perspective has been reset!")
    return True
  except Exception as e:
    log.info("Error while Resetting Perspective: ", e)
    return False


def test_cam_perspective_main(params, record_xml_attribute):
  """! Checks that the camera calibration can be reset.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10410"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  logged_in = False
  changed_perspective = False
  verified_perspective_change = False
  perspective_reset = False
  postreset_saved_perspective = False
  try:
    log.info("Executing: " + TEST_NAME)
    browser = Browser()
    logged_in = common.check_page_login(browser, params)
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)

    browser.find_element(By.ID, 'cam_calibrate_1').click()
    log.info("Resetting Perspective...")
    perspective_reset = reset_perspective(browser)

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info('Get temporary calibration coorinates after reset.')
    cam_values_reset_temp = common.get_calibration_points(browser, 'camera', False)
    map_values_reset_temp = common.get_calibration_points(browser, 'map', False)

    log.info('Get saved calibration coorinates after reset.')
    cam_values_reset_saved = common.get_calibration_points(browser, 'camera')
    map_values_reset_saved = common.get_calibration_points(browser, 'map')

    log.info('Validate if postreset temporary perspective match postreset saved perspective.')
    postreset_saved_perspective = (cam_values_reset_temp == cam_values_reset_saved) and \
                                  (map_values_reset_temp == map_values_reset_saved)
    log.info('Validate if postreset saved perspective match inintial perspective.')
  finally:
    # Split the condition into two parts to avoid having more than 5 boolean expressions in one if statement
    validation = logged_in and perspective_reset and postreset_saved_perspective
    if validation:
      exit_code = 0
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code

if __name__ == '__main__':
  exit(test_cam_perspective_main() or 0)
