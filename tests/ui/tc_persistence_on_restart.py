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

import os
import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

def test_system_persist_main(params, record_xml_attribute):
  """! Checks that the scene constructed in tc_persistence_on_page_navigate.py is
  still in the scenescape database.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10393_RESTART"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME + " with restart")
    print("Test that the system saves scene floor plan, name, and scale - On restart")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    scene_name = "Selenium Sample Scene"
    scale = 1000
    map_image = os.path.join(common.TEST_MEDIA_PATH, "HazardZoneScene.png")
    camera_name = "selenium_cam_test1"
    browser.find_element(By.ID, "nav-scenes").click()
    time.sleep(1)

    sensor_count_loc = "[name='" + scene_name + "'] .sensor-count"
    assert scene_name in browser.page_source
    changed_camera_count = browser.find_element(By.CSS_SELECTOR, sensor_count_loc).text
    assert int(changed_camera_count) == 1
    print("Edited info (camera addition to scene) persists on docker restart, camera count: " + str(changed_camera_count))
    assert common.validate_scene_data(browser, scene_name, scale, map_image)
    print("Scene data persist on docker restart")
    assert common.navigate_to_scene(browser, scene_name)
    assert common.delete_scene(browser, scene_name)
    assert common.delete_camera(browser, camera_name)
    exit_code = 0

  finally:
    common.record_test_result(TEST_NAME, exit_code)
    browser.close()

  assert exit_code == 0
  return exit_code
