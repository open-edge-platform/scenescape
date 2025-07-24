#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common import log
from tests.ui.browser import Browser, By
from selenium.webdriver.support.ui import Select
import tests.ui.common_ui_test_utils as common

def test_camera_deletion_main(params, record_xml_attribute):
  """! Checks that a camera which is not attached to a scene can be deleted.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10403"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  try:
    log.info("Executing: " + TEST_NAME)
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)
    scene_name = common.TEST_SCENE_NAME
    camera_name = "Automated_Camera1"
    camera_id = "Automated_ID_Camera1"

    assert common.create_orphan_camera(browser, camera_name, camera_id)
    log.info(f"Adding orphan camera: {camera_name} to scene {scene_name}")
    # Navigating to cameras menu
    cam_list_xpath = "//a[@href = '/cam/list/']"
    browser.find_element(By.XPATH, cam_list_xpath).click()
    # Edit exists only for Orphan camera
    browser.find_element(By.CSS_SELECTOR, ".bi.bi-pencil").click()
    browser.find_element(By.ID, "id_scene").click()
    select = Select(browser.find_element(By.ID, "id_scene"))
    select.select_by_visible_text(scene_name)
    browser.find_element(By.CSS_SELECTOR, ".col-sm-10 > .btn.btn-primary").click()

    # After update button the page is redirected to scene page, here 'Demo' scene page
    available_cameras = browser.find_elements(By.CSS_SELECTOR, ".card.count-item.camera-card > .card-header")
    camera_names_list = [name.text.replace("--\n","") for name in available_cameras]
    log.info("Available cameras before deletion: ", camera_names_list)
    xpath = "//a[@title = 'Delete "+camera_name+"']"
    browser.find_element(By.XPATH,xpath).click()
    log.info(f"Deleted {camera_name} from the {scene_name}")
    xpath_delete = "//input[@value='Yes, Delete the Camera!']"
    browser.find_element(By.XPATH,xpath_delete).click()

    log.info("Navigating to cameras menu to verify after deletion.")
    cam_list_xpath = "//a[@href = '/cam/list/']"
    browser.find_element(By.XPATH, cam_list_xpath).click()
    camera_names_list = []
    rows = browser.find_elements(By.CSS_SELECTOR,"tbody > tr")
    for row in rows:
      camera_names_list.append(row.text.split()[1])
    log.info("Available cameras after deletion: ", camera_names_list)
    assert camera_name not in camera_names_list
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
