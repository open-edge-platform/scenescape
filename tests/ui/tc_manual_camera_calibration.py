#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common import log
import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

TEST_WAIT_TIME = 5
TEST_NAME = "NEX-T10426"
TEST_IMAGE_THRESHOLD_1 = 10
TEST_IMAGE_THRESHOLD_2 = 1.5

@common.mock_display
def test_manual_camera_calibration(params, record_xml_attribute):
  """! Checks that the camera calibration can be set manually and saved.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  if record_xml_attribute is not None:
    record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    log.info("Executing: " + TEST_NAME)
    log.info("Test that camera pose can be be set manually")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    viewport_dimensions = browser.execute_script("return [window.innerWidth, window.innerHeight];")
    browser.setViewportSize(viewport_dimensions[0], 2000)
    overlay_opacity = browser.find_element(By.ID, 'overlay_opacity')
    slider_action = browser.actionChains()
    slider_action.click_and_hold(overlay_opacity).move_by_offset(99, 0).release().perform()
    cam_values_init = common.get_calibration_points(browser, 'camera')
    map_values_init = common.get_calibration_points(browser, 'map')

    log.info("Take_screenshot before manual calibration")
    camera_view_before = browser.find_element(By.ID, 'camera')
    map_view_before = browser.find_element(By.ID, 'map')
    cam_pic_before = common.get_element_screenshot(camera_view_before)
    map_pic_before = common.get_element_screenshot(map_view_before)
    log.info("Screenshot taken before manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Change calibration settings")
    assert common.change_cam_calibration(browser,[10,80],[0,350])
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_cam_calibration(browser, cam_values_init[0], map_values_init[0])
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after saving manual calibration")
    camera_view_after = browser.find_element(By.ID, 'camera')
    map_view_after = browser.find_element(By.ID, 'map')
    cam_pic_after = common.get_element_screenshot(camera_view_after)
    map_pic_after = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after saving manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Revert to initial calibration settings")
    assert common.change_cam_calibration(browser,[-10,-80],[0,350])
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_calibration_initialization(browser, cam_values_init, map_values_init)
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after reverting to the previous calibration settings")
    camera_view_after = browser.find_element(By.ID, 'camera')
    map_view_after = browser.find_element(By.ID, 'map')
    cam_pic_after_revert = common.get_element_screenshot(camera_view_after)
    map_pic_after_revert = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after reverting to the previous calibration setting")

    log.info("Validating of difference in screenshots after calibration")
    assert common.compare_images(cam_pic_before, cam_pic_after, TEST_IMAGE_THRESHOLD_1)
    log.info("cam_pic_before and cam_pic_after are not equal.")
    assert common.compare_images(map_pic_before, map_pic_after, TEST_IMAGE_THRESHOLD_2)
    log.info("map_pic_before and map_pic_after are not equal.")

    log.info("Validating the similarity in screenshots after reverting calibration settings")
    assert common.get_images_difference(cam_pic_before, cam_pic_after_revert) == 0
    log.info("cam_pic_before and cam_pic_after_revert are equal.")
    assert common.get_images_difference(map_pic_before, map_pic_after_revert) == 0
    log.info("map_pic_before and map_pic_after_revert are equal.")

    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
