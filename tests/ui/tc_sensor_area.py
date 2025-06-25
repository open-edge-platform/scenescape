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
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def test_sensor_area_main(params, record_xml_attribute):
  """! Checks that a sensor covering the entire scene, a circular area, and a
  triangular area can each be calibrated.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10401"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test measurement area configuration for a sensor")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    sensor_id = "test_sensor"
    sensor_name = "Sensor_0"
    scene_name = common.TEST_SCENE_NAME
    common.create_sensor_from_scene(browser, sensor_id, sensor_name, scene_name)
    print("Navigating to sensor edit tab ...")
    browser.find_element(By.LINK_TEXT, "Sensors").click()
    browser.find_element(By.XPATH, "//*[text()='" + sensor_name + "']/parent::tr/td[4]/a").click()
    get_radio = browser.find_elements(By.XPATH, "//*[@type='radio']")
    count_radio = len(get_radio)
    radio_list = []
    if count_radio == 3:
      for elem in get_radio:
        radio_list.append(elem.get_attribute('value'))
      print(f"There are {count_radio} area types as a radio button: \n{radio_list}")

    entire_scene = browser.find_element(By.ID, "id_area_0")
    assert entire_scene.is_selected()
    browser.find_element(By.ID, "id_area_1").click()
    circle_area = browser.find_element(By.CLASS_NAME, "sensor_r")
    assert circle_area.is_displayed()
    get_initial_radius = circle_area.get_attribute("r")

    slider = browser.find_element(By.ID, "id_sensor_r")
    action = browser.actionChains()
    action.click_and_hold(slider).move_by_offset(40, 0).release().perform()
    save_circle = browser.find_element(By.NAME, "save")
    save_circle.click()
    time.sleep(1)

    browser.find_element(By.ID, "sensors-tab").click()
    browser.find_element(By.CLASS_NAME, "sensor_calibrate").click()
    time.sleep(3)

    verify_radius = browser.find_element(By.CLASS_NAME, "sensor_r")
    get_new_radius = verify_radius.get_attribute("r")
    assert get_initial_radius is not get_new_radius
    print("CIRCLE is shown and its radius was modified using the slider")
    print("CIRCLE radius set to: " + get_new_radius)

    browser.find_element(By.ID, "id_area_2").click()
    svg = browser.find_element(By.ID, "svgout")
    time.sleep(1)
    action = browser.actionChains()
    action.drag_and_drop_by_offset(svg, 50, -50)
    action.perform()
    action.click()

    action2 = browser.actionChains()
    action2.move_by_offset(70, 50).perform()
    time.sleep(1)
    action2.click()

    action2.move_by_offset(0, 80).perform()
    time.sleep(1)
    action2.click()

    action2.move_by_offset(50, -80).perform()
    time.sleep(1)
    action2.click()

    polygon_list = browser.find_elements(By.TAG_NAME, "polygon")
    polygon_points = polygon_list[-1].get_attribute("points")
    p_list = list(map(float, polygon_points.split(",")))
    all_points = browser.find_elements(By.CLASS_NAME, "vertex")
    save_polygon = browser.find_element(By.NAME, "save")
    for point in all_points:
      if float(point.get_attribute("cx")) == p_list[0] and float(point.get_attribute("cy")) == p_list[1]:
        point.click()
        print(f"POLYGON with 3 points created \n{p_list}")
        save_polygon.click()
        time.sleep(3)
        break

    verify_polygon = browser.find_elements(By.TAG_NAME, "polygon")
    verify_points = verify_polygon[-1].get_attribute("points")
    verify_list = list(map(float, verify_points.split(",")))
    assert p_list == verify_list
    print("POLYGON area configuration persists")
    exit_code = 0
  finally:
    common.delete_sensor(browser, sensor_name)
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
    assert exit_code == 0
    return
