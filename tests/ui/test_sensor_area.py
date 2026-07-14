# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

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
  browser = None
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
    validate_circular_sensor_area(browser)
    validate_polygon_sensor_area(browser)
    exit_code = 0
  finally:
    if browser is not None:
      common.delete_sensor(browser, sensor_name)
      browser.close()
    common.record_test_result(TEST_NAME, exit_code)
    assert exit_code == 0
  return

def validate_polygon_sensor_area(browser):
  browser.find_element(By.ID, "id_area_2").click()
  WebDriverWait(browser, 10).until(
      EC.presence_of_element_located((By.ID, "svgout")))
  time.sleep(1)

  # Draw a polygon by dispatching mouseup events directly to the SVG at exact coordinates.
  vertex_offsets = [(60, 60), (160, 60), (160, 160), (60, 160)]
  draw_polygon_via_events(browser, vertex_offsets)

  polygon_list = browser.find_elements_with_wait(By.TAG_NAME, "polygon")
  polygon_points = polygon_list[-1].get_attribute("points")
  p_list = list(map(float, polygon_points.split(",")))
  expected_len = len(vertex_offsets) * 2
  assert len(p_list) == expected_len, (
    f"Expected {len(vertex_offsets)} vertices ({expected_len} coords), got {p_list}"
  )
  print(f"POLYGON with {len(p_list) // 2} points created \n{p_list}")

  browser.find_element(By.NAME, "save").click()
  time.sleep(3)

  verify_polygon = browser.find_elements_with_wait(By.TAG_NAME, "polygon")
  verify_points = verify_polygon[-1].get_attribute("points")
  verify_list = list(map(float, verify_points.split(",")))
  assert p_list == verify_list
  print("POLYGON area configuration persists")
  return

def draw_polygon_via_events(browser, vertex_offsets):
  """! Draws and closes a polygon on the sensor SVG using synthetic mouseup events.

  Each offset is relative to the top-left of the #svgout element and matches the
  coordinate the Snap.svg handler records (pageX/pageY minus the SVG offset). The
  polygon is closed by dispatching a final mouseup on the start-point vertex,
  which triggers closePolygon() and serializes the ROI into the form for saving.

  @param    browser                 Object wrapping the Selenium driver.
  @param    vertex_offsets          List of (dx, dy) offsets for each vertex.
  """
  script = """
    const svg = document.getElementById('svgout');
    const offsets = arguments[0];
    const rect = svg.getBoundingClientRect();
    const fire = (el, x, y) => el.dispatchEvent(new MouseEvent('mouseup', {
      bubbles: true, cancelable: true, view: window, clientX: x, clientY: y,
    }));
    for (const [dx, dy] of offsets) {
      fire(svg, rect.left + dx, rect.top + dy);
    }
    const start = svg.querySelector('.start-point');
    if (start) {
      const r = start.getBoundingClientRect();
      fire(start, r.left + r.width / 2, r.top + r.height / 2);
    }
  """
  browser.execute_script(script, [list(v) for v in vertex_offsets])
  WebDriverWait(browser, 10).until(
      lambda b: len(b.find_elements(By.CLASS_NAME, "vertex")) >= len(vertex_offsets))

def validate_circular_sensor_area(browser):
  browser.find_element(By.ID, "id_area_1").click()
  wait = WebDriverWait(browser, 2)
  circle_area = wait.until(
      EC.presence_of_element_located((By.CLASS_NAME, "sensor_r"))
  )
  assert circle_area.is_displayed()
  get_initial_radius = circle_area.get_attribute("r")

  slider = browser.find_element(By.ID, "id_sensor_r")
  action = browser.actionChains()
  action.click_and_hold(slider).move_by_offset(40, 0).release().perform()
  save_circle = browser.find_element(By.NAME, "save")
  save_circle.click()

  wait.until(EC.element_to_be_clickable((By.ID, "sensors-tab"))).click()
  wait.until(
      EC.element_to_be_clickable((By.CSS_SELECTOR, "a[id^='sensor_calibrate_']"))
  ).click()

  verify_radius = wait.until(
      EC.presence_of_element_located((By.CLASS_NAME, "sensor_r"))
  )
  get_new_radius = verify_radius.get_attribute("r")
  assert get_initial_radius is not get_new_radius
  print("CIRCLE is shown and its radius was modified using the slider")
  print("CIRCLE radius set to: " + get_new_radius)
  return
