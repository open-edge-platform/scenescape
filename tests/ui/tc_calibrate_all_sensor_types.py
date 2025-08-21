#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from abc import ABC, abstractmethod

import time
import re

class TestSensorCalibrationBase(ABC):
  """! Base class for testing sensor calibration."""

  def __init__(self, equality_tests, count_tests):
    """! Initiated class.
    @param    equality_tests    Dict of equality tests.
    @param    count_tests       Dict of count tests.
    @return   None
    """
    self.equality_tests = equality_tests
    self.count_tests = count_tests
    self.elements = {}
    return

  def get_base_elements(self, browser):
    """! Get created sensor base web elements to test.
    @param    browser   Object wrapping the Selenium driver.
    @return   None
    """
    assert common.open_sensor_tab(browser)
    sensor_elements = browser.find_elements(By.CSS_SELECTOR, "td.sensor-id")
    pattern = re.compile(r'<td[^>]*class="[^"]*sensor-id[^"]*"[^>]*>(.*?)</td>')
    sensor_names = []
    for html in [el.get_attribute("outerHTML") for el in sensor_elements]:
      match = pattern.search(html)
      if match:
        sensor_names.append(match.group(1).strip())

    element_sensor_name = None
    if self.equality_tests['sensor_name'] in sensor_names:
      element_sensor_name = self.equality_tests['sensor_name']
    else:
      raise AssertionError(f"Sensor name '{self.equality_tests['sensor_name']}' not found in element sensor names: {sensor_names}")

    self.elements["sensor_name"] = element_sensor_name
    self.elements["sensor_id"] =  element_sensor_name
    self.elements["sensor_graphic"] = browser.find_element(By.ID, "sensor_test_sensor")
    self.elements["sensor_graphic_subtags"] = self.elements["sensor_graphic"].find_elements(By.XPATH, "./child::*")
    self.elements["sensor_graphic_height"] = self.elements["sensor_graphic"].size["height"]
    self.elements["sensor_graphic_width"] = self.elements["sensor_graphic"].size["width"]
    return

  def test_values(self):
    """! Check test assertions equality and count tests.
    @return   None
    """
    log.info("---------------------------------------")
    log.info("sensor_type: ", self.sensor_type)
    log.info("---------------------------------------")
    log.info(self.equality_tests)
    log.info(self.elements)
    for test in self.equality_tests:
      log.info(test)
      assert self.elements[test] == self.equality_tests[test]
    for test in self.count_tests:
      log.info(test)
      assert len(self.elements[test]) == self.count_tests[test]
    return

  def execute_test(self, args):
    """! Execute sensor calibration test.
    @param    args    Arguments for getting sensor related web elements.
    @return   None
    """
    self.create_sensor(args)
    time.sleep(5)
    self.get_elements(args[0])
    self.test_values()
    return

  @abstractmethod
  def create_sensor(self, args: list) -> bool:
    """! Method for creating and calibrating a sensor.
    @param    args    List of args for sensor calibration.
    @return   BOOL    Boolean representing successful calibration.
    """
    raise NotImplementedError("Method not implemented.")
    return

  @abstractmethod
  def get_elements(self, browser: Browser) -> None :
    """! Method for getting all web elements related to the sensor.
    @param    browser   Object wrapping the Selenium driver.
    @return   None
    """
    raise NotImplementedError("Method not implemented.")
    return

class TestDefaultSensorCalibration(TestSensorCalibrationBase):
  """! Class for sensor calibrating a sensor that covers the entire scene."""

  def __init__(self, equality_tests, count_tests):
    """! Initiated class.
    @param    equality_tests    Dict of equality tests.
    @param    count_tests       Dict of count tests.
    @return   None
    """
    TestSensorCalibrationBase.__init__(self, equality_tests, count_tests)
    self.sensor_type = "entire_scene"
    return

  def create_sensor(self, args: list) -> bool:
    """! Method for creating and calibrating a sensor covering the entire scene.
    @param    args    List of args for sensor calibration.
    @return   BOOL    Boolean representing successful calibration.
    """
    return common.create_sensor_from_scene(*args)

  def get_elements(self, browser: Browser) -> None:
    """! Method for getting all web elements related to a sensor covering the entire scene.
    @param    browser   Object wrapping the Selenium driver.
    @return   None
    """
    return self.get_base_elements(browser)

class TestCircleSensorCalibration(TestSensorCalibrationBase):
  """! Class for sensor calibrating a sensor that covering a circular area."""

  def __init__(self, equality_tests, count_tests):
    """! Initiated class.
    @param    equality_tests    Dict of equality tests.
    @param    count_tests       Dict of count tests.
    @return   None
    """
    TestSensorCalibrationBase.__init__(self, equality_tests, count_tests)
    self.sensor_type = "circle"
    return

  def create_sensor(self, args):
    """! Method for creating and calibrating a sensor covering a circular area.
    @param    args    List of args for sensor calibration.
    @return   BOOL    Boolean representing successful calibration.
    """
    common.open_scene_manage_sensors_tab(*args)
    return common.create_circle_sensor(*args)

  def get_elements(self, browser: Browser) -> None:
    """! Method for getting all web elements related to a sensor covering a circular area.
    @param    browser   Object wrapping the Selenium driver.
    @return   None
    """
    common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    self.get_base_elements(browser)
    sensor_graphic_circle = browser.find_element(By.CSS_SELECTOR, "#sensor_test_sensor > circle")
    self.elements["sensor_graphic_tag"] = sensor_graphic_circle.tag_name
    self.elements["circle_radius"] = sensor_graphic_circle.value_of_css_property("r")
    return

class TestTriangleSensorCalibration(TestSensorCalibrationBase):
  """! Class for sensor calibrating a sensor that covering a triangular area."""

  def __init__(self, equality_tests, count_tests):
    """! Initiated class.
    @param    equality_tests    Dict of equality tests.
    @param    count_tests       Dict of count tests.
    @return   None
    """
    TestSensorCalibrationBase.__init__(self, equality_tests, count_tests)
    self.sensor_type = "triangle"
    return

  def create_sensor(self, args: list) -> bool:
    """! Method for creating and calibrating a sensor covering a triangular area.
    @param    args    List of args for sensor calibration.
    @return   BOOL    Boolean representing successful calibration.
    """
    common.open_scene_manage_sensors_tab(*args)
    return common.create_triangle_sensor(*args)

  def get_elements(self, browser: Browser) -> None:
    """! Method for getting all web elements related to a sensor covering a triangular area.
    @param    browser   Object wrapping the Selenium driver.
    @return   None
    """
    common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    self.get_base_elements(browser)
    sensor_graphic_polygon = browser.find_element(By.CSS_SELECTOR, "#sensor_test_sensor > polygon")
    self.elements["sensor_graphic_tag"] = sensor_graphic_polygon.tag_name
    self.elements["polygon_points"] = sensor_graphic_polygon.get_attribute("points")
    return

def test_sensor_calibration(params, record_xml_attribute):
  """! Tests sensor calibration for sensors covering: (1) The entire scene, (2) A circular area, (3) A polygonal area.
  @param    params                  List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  TEST_NAME = "NEX-T10457"
  record_xml_attribute("name", TEST_NAME)
  SENSOR_NAME = "test_sensor"
  SENSOR_ID = SENSOR_NAME
  exit_code = 1
  try:
    log.info("Executing: " + TEST_NAME)
    browser = Browser()
    viewport_dimensions = browser.execute_script("return [window.innerWidth, window.innerHeight];")
    browser.setViewportSize(viewport_dimensions[0], 1200)
    assert common.check_page_login(browser, params)

    sensor_1_equality_tests = {
      "sensor_name": SENSOR_NAME,
      "sensor_id": SENSOR_ID,
      "sensor_graphic_height": 14.0,
      "sensor_graphic_width": 14.0
    }
    sensor_1_count_tests = {"sensor_graphic_subtags": 3}
    sensor_1_test = TestDefaultSensorCalibration(sensor_1_equality_tests, sensor_1_count_tests)
    sensor_1_test.execute_test([browser, SENSOR_ID, SENSOR_NAME, common.TEST_SCENE_NAME])

    sensor_2_equality_tests = {
      "sensor_name": SENSOR_NAME,
      "sensor_id": SENSOR_ID,
      "sensor_graphic_height": 677.0,
      "sensor_graphic_width": 677.0,
      "sensor_graphic_tag": "circle",
      "circle_radius": "337px"
    }
    sensor_2_count_tests = {"sensor_graphic_subtags": 5}
    sensor_2_test = TestCircleSensorCalibration(sensor_2_equality_tests, sensor_2_count_tests)
    sensor_2_test.execute_test([browser])

    sensor_3_equality_tests = {
      "sensor_name": SENSOR_NAME,
      "sensor_id": SENSOR_ID,
      "sensor_graphic_height": 612.0,
      "sensor_graphic_width": 812.0,
      "sensor_graphic_tag": "polygon",
      "polygon_points": "50,21,50,621,850,621"
    }
    sensor_3_count_tests = {"sensor_graphic_subtags": 5}
    sensor_3_test = TestTriangleSensorCalibration(sensor_3_equality_tests, sensor_3_count_tests)
    sensor_3_test.execute_test([browser])
    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
