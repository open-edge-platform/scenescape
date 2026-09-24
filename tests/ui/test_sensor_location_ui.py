# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import random
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

SENSOR_HANDLE_SELECTOR = "svg.ss-sensor-area-map .ss-sensor-area-handle"


def change_sensor_location(browser, sensor_name):
  """! Changes a circular sensor center by dragging the React map handle.
  @param    browser       Object wrapping the Selenium driver.
  @param    sensor_name   Name of the sensor.
  @return   tuple|False   (cx, cy) after drag on success, else False.
  """
  wait = WebDriverWait(browser, common.BROWSER_WAIT * 4)
  common.open_sensor_calibrate_from_list(browser, sensor_name)
  common.set_sensor_cal_area(browser, "circle")
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-cx")))
  wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SENSOR_HANDLE_SELECTOR)))

  before_x = browser.find_element(By.ID, "ss-sensor-cal-cx").get_attribute("value")
  before_y = browser.find_element(By.ID, "ss-sensor-cal-cy").get_attribute("value")
  handle = browser.find_elements(By.CSS_SELECTOR, SENSOR_HANDLE_SELECTOR)[-1]
  action = browser.actionChains()
  action.drag_and_drop_by_offset(handle, 10, random.randint(50, 80)).perform()
  time.sleep(1)

  after_x = browser.find_element(By.ID, "ss-sensor-cal-cx").get_attribute("value")
  after_y = browser.find_element(By.ID, "ss-sensor-cal-cy").get_attribute("value")
  if (after_x, after_y) == (before_x, before_y):
    print(f"Center did not change after drag: {(before_x, before_y)}")
    return False
  print(f"Changed the Sensor Location to x={after_x} y={after_y}")
  if not common.save_sensor_calibration(browser):
    return False
  print("Clicked Save on React calibrate workspace")
  return (after_x, after_y)


def verify_sensor_location(browser, sensor_name, expected_center):
  """! Verifies that the sensor location has changed.
  @param    browser           Object wrapping the Selenium driver.
  @param    sensor_name       Name of the sensor.
  @param    expected_center   (cx, cy) strings expected after save.
  @return   BOOL              Boolean representing action success.
  """
  common.open_sensor_calibrate_from_list(browser, sensor_name)
  wait = WebDriverWait(browser, common.BROWSER_WAIT * 4)
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-cx")))
  x_value = browser.find_element(By.ID, "ss-sensor-cal-cx").get_attribute("value")
  y_value = browser.find_element(By.ID, "ss-sensor-cal-cy").get_attribute("value")
  ok = (x_value, y_value) == expected_center
  if ok:
    print(f"Location persists: x= '{x_value}' y= '{y_value}'")
  else:
    print(
      f"Location does not persist! got=({x_value}, {y_value}) "
      f"expected={expected_center}"
    )
  return ok


def test_sensor_location_main(params, record_xml_attribute):
  """! Checks that a sensor can be created and it location changed.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10400"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  browser = None
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
    new_center = change_sensor_location(browser, sensor_name)
    assert new_center
    assert verify_sensor_location(browser, sensor_name, new_center)
    exit_code = 0
  finally:
    if browser is not None:
      browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return
