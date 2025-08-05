#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

import numpy as np

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TEST_WAIT_TIME = 5
TEST_NAME = "NEX-T10426"
TEST_IMAGE_THRESHOLD_1 = 0.01
TEST_IMAGE_THRESHOLD_2 = 2.0

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

    overlay_opacity = browser.find_element(By.ID, 'overlay_opacity')
    location = overlay_opacity.location
    size = overlay_opacity.size
    element_bottom_y = location['y'] + size['height']

    current_viewport_height = 2000
    required_height = element_bottom_y + 50

    if required_height > current_viewport_height:
      browser.setViewportSize(viewport_dimensions[0], required_height)
    else:
      browser.setViewportSize(viewport_dimensions[0], current_viewport_height)

    slider_width = overlay_opacity.size['width']
    desired_offset = int(slider_width * 0.8)

    slider_action = browser.actionChains()
    slider_action.move_to_element_with_offset(overlay_opacity, 1, 1) \
             .click_and_hold() \
             .move_by_offset(desired_offset, 0) \
             .release() \
             .perform()

    cam_values_init = common.get_calibration_points(browser, 'camera')
    map_values_init = common.get_calibration_points(browser, 'map')

    initial_cam_x = cam_values_init[0][0]
    initial_map_x = map_values_init[0][0]
    log.info("Take_screenshot before manual calibration")
    camera_view_before = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_before = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_before = common.get_element_screenshot(camera_view_before)
    map_pic_before = common.get_element_screenshot(map_view_before)
    log.info("Screenshot taken before manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Change calibration settings")
    assert common.change_cam_calibration(browser, initial_cam_x * 2, initial_map_x * 10)
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_cam_calibration(browser, cam_values_init[0], map_values_init[0])
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after saving manual calibration")
    camera_view_after = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_after = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_after = common.get_element_screenshot(camera_view_after)
    map_pic_after = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after saving manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Revert to initial calibration settings")
    assert common.change_cam_calibration(browser, initial_cam_x, initial_map_x)
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_calibration_initialization(browser, [cam_values_init[0]], [map_values_init[0]])
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after reverting to the previous calibration settings")
    camera_view_after = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_after = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_after_revert = common.get_element_screenshot(camera_view_after)
    map_pic_after_revert = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after reverting to the previous calibration setting")

    log.info("Validating of difference in screenshots after calibration")

    assert not np.array_equal(cam_pic_before, cam_pic_after), \
    "Expected camera images to be different, but they are the same"
    assert not np.array_equal(map_pic_before, map_pic_after), \
    "Expected map images to be different, but they are the same"

    cropped_cam_before, cropped_cam_after_revert = common.crop_to_common_shape(cam_pic_before, cam_pic_after_revert)
    cropped_map_before, cropped_map_after_revert = common.crop_to_common_shape(map_pic_before, map_pic_after_revert)

    mse1 = common.get_images_difference(cropped_cam_before, cropped_cam_after_revert)
    mse2 = common.get_images_difference(cropped_map_before, cropped_map_after_revert)

    assert mse1 <= TEST_IMAGE_THRESHOLD_1
    assert mse2 <= TEST_IMAGE_THRESHOLD_2

    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
