# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
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

# This test validates the axes-helper feature itself via a deterministic
# scene-graph assertion: it reads the live Three.js scene graph through a
# test-only hook (window.__testScene), which the server only renders when the
# stack is started with EXPOSE_TEST_HOOKS (test/CI environments only, never
# production). This replaces pixel/canvas-existence checks, which cannot
# distinguish "AxesHelper works" from "AxesHelper was removed".


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


def get_axes_helper_state(browser, sensor_name):
  """! Reads the live Three.js scene graph via the test-only window.__testScene
  hook and reports whether the named sensor node exists and owns an AxesHelper.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_name                Name of the sensor's scene-graph node.
  @return   dict                       hooksAvailable/found/visible/hasAxesHelper/
                                       isAxesHelper/position, per availability.
  """
  script = """
    const testScene = window.__testScene;
    if (!testScene) return {hooksAvailable: false};
    const node = testScene.getObjectByName(arguments[0]);
    if (!node) return {hooksAvailable: true, found: false};
    const helper = node.axesHelper;
    if (!helper) {
      return {hooksAvailable: true, found: true, visible: node.visible, hasAxesHelper: false};
    }
    return {
      hooksAvailable: true,
      found: true,
      visible: node.visible,
      hasAxesHelper: true,
      isAxesHelper: helper.type === 'AxesHelper',
      position: helper.position.toArray(),
    };
  """
  return browser.execute_script(script, sensor_name)


def wait_for_axes_helper_state(browser, sensor_name, predicate, timeout=15.0, poll_interval=0.5):
  """! Polls get_axes_helper_state() until predicate(state) is true or the
  timeout elapses, returning the last observed state either way.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_name                Name of the sensor's scene-graph node.
  @param    predicate                  Callable taking the state dict, returning bool.
  @param    timeout                    Maximum seconds to poll.
  @param    poll_interval              Seconds between polls.
  @return   dict                       The last observed state.
  """
  deadline = time.monotonic() + timeout
  state = get_axes_helper_state(browser, sensor_name)
  while time.monotonic() < deadline and not predicate(state):
    time.sleep(poll_interval)
    state = get_axes_helper_state(browser, sensor_name)
  return state


@pytest.mark.fresh_stack
@common.mock_display
def test_sensor_axes_main(params, record_xml_attribute):
  """! Checks that a circular perceptual sensor's scene-graph node owns a
  THREE.AxesHelper with a real position, that toggling the sensor visible
  flips the node's visibility, and that deleting the sensor removes the node
  (and its AxesHelper) from the scene graph. Uses a deterministic scene-graph
  assertion via a test-only hook rather than inferring correctness from
  rendered pixels, so the test fails if updateAxesHelper() is removed or broken.
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
  sensor_deleted = False

  try:
    print("Executing: " + TEST_NAME)
    print("Test that a circular sensor's AxesHelper exists, tracks visibility, and is removed on delete")
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
    # (new sensors default to visible=false, so their panel appears but the sensor is hidden).
    # This also confirms the sensor's async REST-backed thing object has finished
    # loading, which the scene-graph check below depends on.
    common.selenium_wait_for_elements(
        browser,
        (By.XPATH, "//div[@class='title' and normalize-space(text())='" + sensor_name + "']"),
        timeout=30
    )
    print(f"Verified: sensor '{sensor_name}' panel appeared in 3D controls")

    # Deterministic scene-graph assertion: the sensor's node must already own
    # an AxesHelper with a real position (set unconditionally in the
    # SceneRegion constructor).
    initial_state = get_axes_helper_state(browser, sensor_name)
    assert initial_state.get("hooksAvailable"), (
      "window.__testScene test hook is unavailable; ensure the stack was "
      "started with EXPOSE_TEST_HOOKS enabled"
    )
    assert initial_state.get("found"), "Sensor node not found in the scene graph after creation"
    assert initial_state.get("hasAxesHelper"), "Sensor has no AxesHelper after creation"
    assert initial_state.get("isAxesHelper"), "Sensor's axesHelper.type is not 'AxesHelper'"
    position = initial_state.get("position")
    assert isinstance(position, list) and len(position) == 3, "AxesHelper position missing or malformed"
    assert all(isinstance(v, (int, float)) for v in position), "AxesHelper position contains non-numeric values"
    assert initial_state.get("visible") is False, "New sensor's node should default to invisible"
    print(f"Verified: AxesHelper present at position {position}")

    # Toggle the sensor visible via its own lil-gui 'show' checkbox and confirm
    # the scene-graph node's visibility actually flips (not just the checkbox UI).
    set_sensor_visible_via_panel(browser, sensor_name)
    visible_state = wait_for_axes_helper_state(
        browser, sensor_name, lambda s: s.get("visible") is True)
    assert visible_state.get("visible") is True, "Sensor node did not become visible after toggling the panel checkbox"
    assert visible_state.get("hasAxesHelper"), "AxesHelper disappeared after toggling visibility"
    print("Verified: sensor node visibility flipped to true via panel checkbox")

    # Verify the page still renders without JS errors after the toggle
    canvas = browser.find_element(By.ID, "scene")
    assert canvas is not None, "Canvas element should exist after visibility toggle"
    screenshot = common.capture_3d_canvas(browser)
    assert screenshot is not None and screenshot.size > 0, "Canvas screenshot should be valid"
    print(f"Screenshot captured: {screenshot.shape}")

    # Exercise deletion as a test step, and prove
    # the sensor's node - and therefore its AxesHelper - is gone afterward.
    common.navigate_directly_to_page(browser, "/")
    assert common.delete_sensor(browser, sensor_name), "Failed to delete sensor"
    sensor_deleted = True

    assert common.navigate_directly_to_page(browser, f"/scene/detail/{common.TEST_SCENE_ID}/")
    assert common.wait_for_3d_scene_rendered(browser, timeout=60.0), "3D scene did not render in time after delete"
    deleted_state = get_axes_helper_state(browser, sensor_name)
    assert deleted_state.get("hooksAvailable"), "window.__testScene test hook is unavailable after reload"
    assert deleted_state.get("found") is False, (
      "Deleted sensor's node (and its AxesHelper) should no longer exist in the scene graph"
    )
    print("Verified: deleted sensor's node and AxesHelper are gone from the scene graph")

    exit_code = 0
  finally:
    if browser is not None:
      if not sensor_deleted:
        # Leave the 3D page before deleting; its layout leaves the navbar
        # "Sensors" link unreachable for a plain click.
        common.navigate_directly_to_page(browser, "/")
        common.delete_sensor(browser, sensor_name)
      browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
