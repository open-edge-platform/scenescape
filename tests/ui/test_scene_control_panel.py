# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from tests.utils.log import get_logger
import tests.ui.common_ui_test_utils as common
from tests.ui.browser import By, Browser
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

def load_scene_until_panel_ready(browser, scene_path, per_attempt=120, attempts=3):
  """! Navigate to the 3D scene and wait for the camera control panel to appear.

  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_path                 Path of the 3D scene detail page.
  @param    per_attempt                Seconds to wait for the panel per load attempt.
  @param    attempts                   Number of full (re)load attempts before giving up.
  @return   element or None            The panel element, or None if it never appeared.
  """
  locator = (By.ID, "camera1-control-panel")
  for attempt in range(1, attempts + 1):
    common.navigate_directly_to_page(browser, scene_path)
    deadline = time.monotonic() + per_attempt
    while time.monotonic() < deadline:
      elements = browser.find_elements(*locator)
      if elements:
        return elements[0]
      time.sleep(1)
    log.info(f"Camera panel not ready after {per_attempt}s "
             f"(attempt {attempt}/{attempts}); reloading the scene.")
  return None

@common.mock_display
def test_scene_control_panel(params, record_xml_attribute):
  """! Test the Scene Control Panel in the 3D UI.
  @param    params                  List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  TEST_NAME = "NEX-T10474"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  WAIT_SEC = 1
  browser = None

  try:
    log.info("Executing: " + TEST_NAME)
    log.info("Test for scene control panel in 3D UI")

    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    interaction_page = common.InteractWith3DScene(browser)
    scene_path = f"/scene/detail/{common.TEST_SCENE_ID}/"

    log.info("Turn off tracked objects and hide stats graph.")
    # Load the scene and wait for the camera control panel
    assert load_scene_until_panel_ready(browser, scene_path) is not None, \
      "camera1-control-panel did not appear (3D scene failed to load)"
    time.sleep(WAIT_SEC)
    browser.find_element(By.ID, "tracked-objects-button").click()
    interaction_page.hide_stats()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take first floor plane screenshot.")
    time.sleep(WAIT_SEC)
    common.wait_for_3d_scene_rendered(browser)
    plane_view_1 = common.capture_3d_canvas(browser)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Toggle floor plane off.")
    time.sleep(WAIT_SEC)
    browser.find_element(By.ID, 'plane-view-label').click()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take second floor plane screenshot.")
    time.sleep(WAIT_SEC)
    plane_view_2 = common.capture_3d_canvas(browser)

    log.info("AC(1) Check if floor plane screenshots are different.")
    assert not common.are_images_similar(plane_view_1, plane_view_2, 0.7)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Toggle floor plane on.")
    time.sleep(WAIT_SEC)
    plane_view = browser.find_element(By.ID, "plane-view-label")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(plane_view).click(card_title).click(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take first 3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_3d_1 = common.capture_3d_canvas(browser)

    log.info("AC(1) Check if floor plane screenshot is identical after toggling back on.")
    assert common.are_images_similar(plane_view_1, screen_3d_1)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Change map perspective.")
    time.sleep(WAIT_SEC)
    common.change_map_perspective(browser)

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take second 3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_3d_2 = common.capture_3d_canvas(browser)

    log.info("AC(4) Check if 3D screenshots are different.")
    assert not common.are_images_similar(screen_3d_1, screen_3d_2)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Reset 3D view.")
    reset = browser.find_element(By.ID, "reset")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(reset).move_to_element(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take third 3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_3d_3 = common.capture_3d_canvas(browser)

    log.info("AC(5) Check if 3D screenshots are identical.")
    assert common.are_images_similar(screen_3d_1, screen_3d_3)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Click 2D view.")
    button_2d = browser.find_element(By.ID, "2d-button")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(button_2d).move_to_element(card_title).perform()

    log.info("Take first 2D screenshot.")
    time.sleep(WAIT_SEC)
    screen_2d_1 = common.capture_3d_canvas(browser)

    log.info("Change map perspective.")
    time.sleep(WAIT_SEC)
    common.change_map_perspective(browser)

    log.info("Take second 2D screenshot.")
    time.sleep(WAIT_SEC)
    screen_2d_2 = common.capture_3d_canvas(browser)

    log.info("AC(3) Check if 2D screenshots are identical.")
    assert common.are_images_similar(screen_2d_1, screen_2d_2)

    log.info("Click 3D view.")
    button_3d = browser.find_element(By.ID, "3d-button")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(button_3d).move_to_element(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take first 2D/3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_2d_3d_1 = common.capture_3d_canvas(browser)

    log.info("Change map perspective.")
    time.sleep(WAIT_SEC)
    common.change_map_perspective(browser)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Click 2D view.")
    time.sleep(WAIT_SEC)
    button_2d = browser.find_element(By.ID, "2d-button")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(button_2d).move_to_element(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take second 2D/3D screenshot.")
    time.sleep(WAIT_SEC)

    screen_2d_3d_2 = common.capture_3d_canvas(browser)

    log.info("AC(3) Check if 2D and 3D screenshots are similar (2D perspective is slightly different).")
    assert common.are_images_similar(screen_2d_3d_1, screen_2d_3d_2, 0.8)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Navigate to scene details.")
    browser.find_element(By.ID, "scene-detail-button").click()

    log.info("AC(2) Check if URL has changed to scene details.")
    time.sleep(WAIT_SEC)
    assert browser.current_url.split("/")[-2] == common.TEST_SCENE_ID

    exit_code = 0

  finally:
    if browser is not None:
      # quit() (not close()) terminates the geckodriver process and the Firefox
      # instance. close() only closes the window and leaves geckodriver running,
      # so the heavy WebGL/Mesa-software Firefox would linger and starve the next
      # WebGL test's geckodriver of resources ("Can not connect to the Service").
      browser.quit()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
