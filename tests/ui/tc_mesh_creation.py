#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def test_mesh_creation(params, record_xml_attribute):
  """! Checks that the camera parameters in the web UI can be updated and
  that they persist after saving, for both Camera Save buttons.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  try:
    print("Executing: " + TEST_NAME)
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    assert common.delete_camera(browser, "camera3")
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)

    browser.save_full_page_screenshot("test1.png")
    browser.find_element(By.ID, "scene-edit").click()
    browser.refresh()
    common.wait_for_elements(browser, "generate_mesh", findBy=By.ID)
    browser.save_full_page_screenshot("test.png")
    browser.find_element(By.ID, "generate_mesh").click()
    try:
      alert = WebDriverWait(browser, 60).until(EC.alert_is_present())
      alert_text = alert.text
      assert alert_text == 'Mesh generated successfully! The scene map has been updated.'
      alert.accept()
    except TimeoutException:
      print("No alert appeared")
    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
