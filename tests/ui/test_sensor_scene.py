#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pytest

from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@pytest.mark.test_name("NEX-T10396")
def test_sensor_scene_main(params, result_recorder):
  """! Checks that user can create a sensor without attaching it to a scene.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  @return   exit_code               Indicates test success or failure.
  """
  browser = None
  try:
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
    print("Clicked on sensor create without assigning a scene")

    # Navigate back to sensor list page (if needed)
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()

    # Wait for sensor name to appear in the list
    WebDriverWait(browser, 20).until(
      EC.presence_of_element_located((By.XPATH, f"//table//td[contains(text(), '{sensor_name}')]"))
    )
    print(f"Sensor '{sensor_name}' created successfully and appears in the list")

    result_recorder.success()
  finally:
    if browser is not None:
      browser.close()

  return
