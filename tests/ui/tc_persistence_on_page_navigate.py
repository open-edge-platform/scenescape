#!/usr/bin/env python3

# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import os, time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

def test_page_persistence_main(params, record_xml_attribute):
  """! Checks that a scene can be created and a camera added.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10393_PERSISTENCE"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test that the system saves scene floor plan, name, and scale")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    scene_name = "Selenium Sample Scene"
    camera_id = "selenium_cam_test_1"
    camera_name = "selenium_cam_test1"
    scale = 1000
    sensor_count_loc = "[name='" + scene_name + "'] .sensor-count"
    print("Creating Scene " + scene_name)
    map_image = os.path.join(common.TEST_MEDIA_PATH, "HazardZoneScene.png")
    assert common.create_scene(browser, scene_name, scale, map_image)
    assert scene_name in browser.page_source

    camera_count = browser.find_element(By.CSS_SELECTOR, sensor_count_loc).text
    print("Editing scene by adding camera " + scene_name)
    assert common.add_camera_to_scene(browser, scene_name, camera_id, camera_name)
    browser.find_element(By.ID, "home").click()
    changed_camera_count = browser.find_element(By.CSS_SELECTOR, sensor_count_loc).text

    assert int(changed_camera_count) == int(camera_count) + 1
    print("Edited info (camera addition to scene) persists on page navigation, camera count: " + str(changed_camera_count))
    assert common.validate_scene_data(browser, scene_name, scale, map_image)
    print("Scene data persist on page navigation")
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
