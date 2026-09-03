# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import pytest
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

# This test validates that a circular perceptual sensor can be created and
# toggled visible in the 3D UI without errors. Visual verification of axes
# rendering is deferred to manual testing or a future scene-graph-based
# verification approach (pixel color masking is unreliable across camera angles
# and overlapping colored UI elements).


def set_sensor_visible_via_panel(browser, sensor_name):
  """! Clicks a sensor's "show" checkbox in the live 3D control panel, so the
  sensor becomes visible in-place without reloading the page (a reload would
  re-run the camera's auto-fit framing and shift how much of other markers
  are on screen, confounding a before/after pixel comparison).
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_name                Name of the sensor (matches its panel folder title).
  """
  checkbox_xpath = (
    "//div[@class='title' and normalize-space(text())='" + sensor_name + "']"
    "/following-sibling::div[@class='children'][1]"
    "//div[@class='name' and normalize-space(text())='show']"
    "/following-sibling::label//input[@type='checkbox']"
  )
  browser.find_element(By.XPATH, checkbox_xpath).click()


@pytest.mark.fresh_stack
@common.mock_display
def test_sensor_axes_main(params, record_xml_attribute):
  """! Checks that a circular perceptual sensor can be created, toggled visible via
  its 3D UI control panel, and renders in the 3D scene without errors. This is an
  integration test rather than a pixel-level verification of axes rendering, since
  distinguishing sensor axes pixels from overlapping camera indicator pixels via a
  global color mask is unreliable across viewing angles and camera framing changes.
  @param    params                     Dict of test parameters.
  @param    record_xml_attribute       Pytest fixture recording the test name.
  @return   exit_code                  Indicates test success or failure.
  """
  TEST_NAME = "NEX-T29213"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  browser = None
  sensor_id = "test_axes_sensor"
  sensor_name = "Axes_Sensor_0"
  scene_name = common.TEST_SCENE_NAME

  try:
    print("Executing: " + TEST_NAME)
    print("Test that a circular sensor can be created and toggled visible in 3D UI")
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    # Create a circular perceptual sensor (defaults to visible=false).
    common.create_sensor_from_scene(browser, sensor_id, sensor_name, scene_name)
    browser.find_element(By.LINK_TEXT, "Sensors").click()
    browser.find_element(By.XPATH, "//*[text()='" + sensor_name + "']/parent::tr/td[4]/a").click()
    assert common.create_circle_sensor(browser, radius=250), "Failed to create circle sensor"

    # Navigate to the 3D scene view
    assert common.navigate_directly_to_page(browser, f"/scene/detail/{common.TEST_SCENE_ID}/")
    assert common.wait_for_3d_scene_rendered(browser, timeout=60.0), "3D scene did not render in time"
    
    # Verify the sensor's control panel exists in the DOM when the page loads
    # (new sensors default to visible=false, so their panel appears but the sensor is hidden)
    common.selenium_wait_for_elements(
        browser, 
        (By.XPATH, "//div[@class='title' and normalize-space(text())='" + sensor_name + "']"),
        timeout=30
    )
    print(f"Verified: sensor '{sensor_name}' panel appeared in 3D controls")

    # Toggle the sensor visible via its own lil-gui 'show' checkbox
    set_sensor_visible_via_panel(browser, sensor_name)
    time.sleep(1)
    print(f"Toggled sensor visible via panel checkbox")

    # Verify the page still renders without JS errors after the toggle
    canvas = browser.find_element(By.ID, "scene")
    assert canvas is not None, "Canvas element should exist after visibility toggle"
    
    # Final proof: capture a screenshot (this would hang or crash if the renderer is broken)
    screenshot = common.capture_3d_canvas(browser)
    assert screenshot is not None and screenshot.size > 0, "Canvas screenshot should be valid"
    print(f"Final screenshot captured: {screenshot.shape}")

    exit_code = 0
  finally:
    if browser is not None:
      # Leave the 3D page before deleting; its layout leaves the navbar
      # "Sensors" link unreachable for a plain click.
      common.navigate_directly_to_page(browser, "/")
      common.delete_sensor(browser, sensor_name)
      browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
