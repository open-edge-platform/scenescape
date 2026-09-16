# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import pytest

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

POLYGON_POINTS_M = [[1.0, 1.0], [4.0, 1.0], [4.0, 4.0], [1.0, 4.0]]

@pytest.mark.test_name("NEX-T10401")
def test_sensor_area_main(params, result_recorder):
  """! Checks that a sensor covering the entire scene, a circular area, and a
  polygonal area can each be calibrated in the React calibrate workspace.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10401"
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
    print("Opening sensor calibrate workspace ...")
    common.open_sensor_calibrate_from_list(browser, sensor_name)

    area_select = browser.find_element(By.ID, "ss-sensor-cal-area")
    options = [opt.get_attribute("value") for opt in area_select.find_elements(By.TAG_NAME, "option")]
    assert options == ["scene", "circle", "poly"], f"Unexpected area options: {options}"
    assert area_select.get_attribute("value") == "scene"
    print(f"Default area type is entire scene; options={options}")

    validate_circular_sensor_area(browser, sensor_name)
    validate_polygon_sensor_area(browser, sensor_name)
    result_recorder.success()
  finally:
    if browser is not None:
      common.delete_sensor(browser, sensor_name)
      browser.close()
  return

def validate_polygon_sensor_area(browser, sensor_name):
  """! Configure a polygon area via the React calibrate map or points field."""
  wait = WebDriverWait(browser, common.BROWSER_WAIT * 4)
  common.set_sensor_cal_area(browser, "poly")
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-pts")))

  maps = browser.find_elements(By.CSS_SELECTOR, "svg.ss-sensor-area-map")
  if maps:
    # Clear any prior points so map click-draw is accepted.
    common.set_react_input_value(browser, "ss-sensor-cal-pts", "[]")
    time.sleep(0.2)
    draw_polygon_via_events(browser, [(60, 60), (160, 60), (160, 160), (60, 160)])
    wait.until(
      EC.presence_of_element_located(
        (By.CSS_SELECTOR, "svg.ss-sensor-area-map polygon.ss-sensor-area-coverage")
      )
    )
    polygon = browser.find_element(
      By.CSS_SELECTOR, "svg.ss-sensor-area-map polygon.ss-sensor-area-coverage"
    )
    print(f"POLYGON drawn on calibrate map: {polygon.get_attribute('points')}")
  else:
    print("Calibrate map unavailable; using Points JSON field")
    common.set_react_input_value(
      browser, "ss-sensor-cal-pts", json.dumps(POLYGON_POINTS_M)
    )

  pts_before = json.loads(
    browser.find_element(By.ID, "ss-sensor-cal-pts").get_attribute("value")
  )
  assert isinstance(pts_before, list) and len(pts_before) >= 3, (
    f"Expected polygon points before save, got {pts_before}"
  )
  assert common.save_sensor_calibration(browser)

  common.open_sensor_calibrate_from_list(browser, sensor_name)
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-area")))
  assert browser.find_element(By.ID, "ss-sensor-cal-area").get_attribute("value") == "poly"
  pts_after = json.loads(
    browser.find_element(By.ID, "ss-sensor-cal-pts").get_attribute("value")
  )
  assert len(pts_after) == len(pts_before), (
    f"Polygon vertex count changed after save: {pts_before} -> {pts_after}"
  )
  print("POLYGON area configuration persists")
  return

def draw_polygon_via_events(browser, vertex_offsets):
  """! Draws and closes a polygon on the React sensor area SVG using click events.

  Offsets are in SVG user units relative to the top-left of the viewBox. After
  three or more vertices, the first handle becomes the close target.

  @param    browser                 Object wrapping the Selenium driver.
  @param    vertex_offsets          List of (dx, dy) offsets for each vertex.
  """
  script = """
    const svg = document.querySelector('svg.ss-sensor-area-map');
    if (!svg) { return false; }
    const offsets = arguments[0];
    const fireClick = (el, x, y) => {
      const pt = svg.createSVGPoint();
      pt.x = x;
      pt.y = y;
      const ctm = svg.getScreenCTM();
      if (!ctm) { return; }
      const screen = pt.matrixTransform(ctm);
      el.dispatchEvent(new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window,
        clientX: screen.x, clientY: screen.y,
      }));
    };
    for (const [dx, dy] of offsets) {
      fireClick(svg, dx, dy);
    }
    const closeHandle = svg.querySelector('.ss-sensor-area-handle.is-close');
    if (closeHandle) {
      const r = closeHandle.getBoundingClientRect();
      closeHandle.dispatchEvent(new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window,
        clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
      }));
    }
    return true;
  """
  assert browser.execute_script(script, [list(v) for v in vertex_offsets]), (
    "React sensor area map SVG was not found"
  )
  WebDriverWait(browser, 10).until(
    lambda b: len(
      b.find_elements(By.CSS_SELECTOR, "svg.ss-sensor-area-map .ss-sensor-area-handle")
    ) >= len(vertex_offsets)
  )

def validate_circular_sensor_area(browser, sensor_name):
  """! Switch to circle area, change radius, save, and verify it persists."""
  wait = WebDriverWait(browser, common.BROWSER_WAIT * 4)
  common.set_sensor_cal_area(browser, "circle")
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-r")))
  if browser.find_elements(By.CSS_SELECTOR, "svg.ss-sensor-area-map"):
    wait.until(
      EC.presence_of_element_located(
        (By.CSS_SELECTOR, "svg.ss-sensor-area-map circle.ss-sensor-area-coverage")
      )
    )
  radius_field = browser.find_element(By.ID, "ss-sensor-cal-r")
  initial_radius = radius_field.get_attribute("value")
  new_radius = "2.5" if initial_radius != "2.5" else "3.5"
  common.set_react_input_value(browser, "ss-sensor-cal-r", new_radius)
  assert common.save_sensor_calibration(browser)

  common.open_sensor_calibrate_from_list(browser, sensor_name)
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-area")))
  assert browser.find_element(By.ID, "ss-sensor-cal-area").get_attribute("value") == "circle"
  wait.until(EC.presence_of_element_located((By.ID, "ss-sensor-cal-r")))
  verify_radius = browser.find_element(By.ID, "ss-sensor-cal-r").get_attribute("value")
  assert float(verify_radius) == float(new_radius), (
    f"Circle radius did not persist: before={initial_radius} set={new_radius} after={verify_radius}"
  )
  print("CIRCLE is shown and its radius was modified")
  print("CIRCLE radius set to: " + verify_radius)
  return
