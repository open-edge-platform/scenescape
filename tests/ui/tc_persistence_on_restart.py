#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
  return
