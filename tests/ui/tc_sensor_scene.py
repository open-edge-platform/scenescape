#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def test_sensor_scene_main(params, record_xml_attribute):
  """! Checks that user cannot create a sensor that is not attached to a scene.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10396"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test that a new sensor must be added to a scene")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    sensor_id = "test_sensor"
    sensor_name = "Sensor_0"
    scene_name = common.TEST_SCENE_NAME
    print("Adding sensor " + sensor_name + " Home -> sensors -> +New sensors")
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()
    browser.find_element(By.XPATH, "//*/a[contains(text(), '+ New Sensor')]").click()
    browser.find_element(By.ID, "id_sensor_id").send_keys(sensor_id)
    browser.find_element(By.ID, "id_name").send_keys(sensor_name)
    browser.find_element(By.CSS_SELECTOR, ".btn:nth-child(1)").click()
    print("clicked on 'Add New Sensor")
    get_error = WebDriverWait(browser, 20).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#id_scene"))).get_attribute("validationMessage")
    assert get_error == "Please select an item in the list."
    print("validation error: " + get_error)
    print("Assigning " + sensor_name + " to a scene...")

    browser.find_element(By.XPATH, "//*[@id = 'id_scene']/option[. = '" + scene_name + "']").click()
    browser.find_element(By.XPATH, "//*[@type = 'submit']").click()
    common.verify_sensor_under_scene(browser, sensor_name)
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
