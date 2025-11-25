#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def test_sensor_scene_main(params, record_xml_attribute):
  """! Checks that user can create a sensor without attaching it to a scene.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10396"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test that a new sensor can be created without assigning it to a scene")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    sensor_id = "test_sensor"
    sensor_name = "Sensor_0"

    # Navigate to sensor creation page
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()
    browser.find_element(By.XPATH, "//*/a[contains(text(), '+ New Sensor')]").click()

    # Create sensor without assigning a scene
    common.create_sensor(browser, sensor_id, sensor_name)
    print("Clicked on 'Add New Sensor' without assigning a scene")

    # Navigate back to sensor list page (if needed)
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()

    # Wait for sensor name to appear in the list
    WebDriverWait(browser, 20).until(
      EC.presence_of_element_located((By.XPATH, f"//table//td[contains(text(), '{sensor_name}')]"))
    )
    print(f"Sensor '{sensor_name}' created successfully and appears in the list")

    exit_code = 0
  except Exception as e:
    print(f"Test failed: {e}")
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
