#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import time
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def test_scene_details_main(params, record_xml_attribute):
  """! Checks that the scene detail page is accessible from the scene summary page.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10395"
  record_xml_attribute("name", TEST_NAME)

  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test that the user can view scene details")
    browser = Browser()
    assert common.check_page_login(browser, params)
    scene_name = "Demo"
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(1) > .nav-link").click()
    assert scene_name in browser.page_source

    print("Scene is accessible from the list of scenes")
    browser.find_element(By.XPATH, "//*[text()='" + scene_name + "']/parent::*/div[2]/div/a[1]").click()
    time.sleep(3)
    status_scene_name = browser.find_element(By.ID, "scene_name").is_displayed()
    status_floorplan = browser.find_element(By.CSS_SELECTOR, "#svgout > image:nth-child(4)").is_displayed()
    status_cameras = browser.find_element(By.CSS_SELECTOR, "#camera1").is_displayed()
    assert status_scene_name is True or status_floorplan is True or status_cameras is True
    print("Details are displayed in the scene summary view")
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code

if __name__ == '__main__':
  exit(test_scene_details_main() or 0)
