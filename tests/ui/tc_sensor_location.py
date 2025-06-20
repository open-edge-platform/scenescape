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

import time
import random
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def change_sensor_location(browser, sensor_name):
  """! Changes a sensor location randomly.
  @param    browser       Object wrapping the Selenium driver.
  @param    sensor_name   Name of the sensor.
  @return   BOOL          Boolean representing action success.
  """
  retVal = False
  browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()
  browser.find_element(By.XPATH, "//*[text()='" + sensor_name + "']/parent::tr/td[4]/a").click()
  map_canvas = browser.find_elements(By.ID, "svgout")
  if map_canvas is None:
    return retVal
  browser.execute_script("window.scrollTo(0,100);")
  sensor_draggable = browser.find_elements(By.CSS_SELECTOR, ".is-handle")
  sensor = sensor_draggable[-1]

  action = browser.actionChains()
  action.drag_and_drop_by_offset(sensor, 10, random.randint(50, 80)).perform()
  time.sleep(1)
  print("Changed the Sensor Location")
  browser.find_element(By.NAME, "save").click()
  print("Clicked 'Save Calibration'")
  retVal = True

  return retVal

def verify_sensor_location(browser, sensor_name):
  """! Verifies that the sensor location has changed.
  @param    browser       Object wrapping the Selenium driver.
  @param    sensor_name   Name of the sensor.
  @return   BOOL          Boolean representing action success.
  """
  old_x_value = '138'
  old_y_value = '188'
  retVal = False
  browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()
  browser.find_element(By.XPATH, "//*[text()='" + sensor_name + "']/parent::tr/td[4]/a").click()
  browser.execute_script("window.scrollTo(0,100);")
  sensor_coord = browser.find_element(By.CSS_SELECTOR, ".is-handle")
  x_value = sensor_coord.get_attribute('x')
  y_value = sensor_coord.get_attribute('y')
  if x_value != old_x_value and y_value != old_y_value:
    print(f"Location persists: x= '{x_value}' y= '{y_value}'")
    retVal = True
  else:
    print("Location does not persist!")
    retVal = False
  return retVal

def test_sensor_location_main(params, record_xml_attribute):
  """! Checks that a sensor can be created and it location changed.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10400"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  sensor_id = "test_sensor"
  sensor_name = "Sensor_0"
  scene_name = common.TEST_SCENE_NAME
  try:
    print("Executing: " + TEST_NAME)
    print("Test setting a sensor location in the scene")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    common.create_sensor_from_scene(browser, sensor_id, sensor_name, scene_name)
    assert change_sensor_location(browser, sensor_name)
    assert verify_sensor_location(browser, sensor_name)
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return
