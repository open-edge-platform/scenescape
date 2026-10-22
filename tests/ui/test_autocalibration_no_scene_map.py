# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser, By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_AUTOCALIBRATION
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_AUTOCALIBRATION,
  require_password=True, auth="",
)

SCENE_NAME = "Queuing"
# Queuing scene cameras: atag-qcam1 and atag-qcam2
CAM_URLS = ("/cam/calibrate/1", "/cam/calibrate/2")
AUTOCAL_BUTTON_ID = "auto-autocalibration"
# Static template default or backend registration error, depending on timing.
EXPECTED_TITLES = (
  "Auto Calibrate system not available for this scene",
  "Error: Scene has no map",
  "No map available for scene",
)
TITLE_TIMEOUT_S = 60


def scene_has_map(browser):
  """! Checks the scene edit page for a map link."""
  return len(browser.find_elements(By.CSS_SELECTOR, "#map_wrapper a")) > 0


def open_scene_edit(browser):
  """! Opens the Queuing scene edit page."""
  assert common.navigate_to_scene(browser, SCENE_NAME), f"Scene {SCENE_NAME} not found"
  browser.find_element(By.ID, "scene-edit").click()


def wait_for_expected_title(browser):
  """! Waits until the autocalibration button shows one of the no-map messages.
  @return   str    Final button title.
  """
  last = {"title": None}

  def has_expected_title(_):
    last["title"] = browser.find_element(By.ID, AUTOCAL_BUTTON_ID).get_attribute("title")
    return last["title"] in EXPECTED_TITLES

  try:
    WebDriverWait(browser, TITLE_TIMEOUT_S).until(has_expected_title)
  except TimeoutException:
    raise AssertionError(
      f"Autocalibration button title {last['title']!r} not in {EXPECTED_TITLES!r} "
      f"after {TITLE_TIMEOUT_S}s")
  return last["title"]


@common.mock_display
@pytest.mark.test_name("NEX-T12748")
def test_autocalibration_no_scene_map(params, result_recorder):
  """! Verify autocalibration is disabled and reports a message when the scene map is deleted.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  browser = None

  try:
    log.info("Executing: NEX-T12748")
    browser = Browser(headless=False, webgl=True)
    assert common.check_page_login(browser, params)

    log.info("1. Delete the Queuing scene map by ticking 'clear' and saving.")
    open_scene_edit(browser)
    assert scene_has_map(browser), f"Scene {SCENE_NAME} has no map before the test starts"
    browser.find_element(By.ID, "map-clear_id").click()
    browser.find_element(By.ID, "save").click()

    log.info("2. Verify the map was deleted.")
    open_scene_edit(browser)
    assert not scene_has_map(browser), "Scene map link still present after clearing the map"
    assert not browser.find_elements(By.ID, "map-clear_id"), \
      "'Clear' checkbox still present, map was not deleted"

    for cam_url in CAM_URLS:
      log.info(f"3. Open {cam_url} and hover over the autocalibration button.")
      assert common.navigate_directly_to_page(browser, cam_url)
      button = WebDriverWait(browser, 15).until(
        lambda d: d.find_element(By.ID, AUTOCAL_BUTTON_ID))
      browser.actionChains().move_to_element(button).pause(1).perform()

      title = wait_for_expected_title(browser)
      log.info(f"Autocalibration button tooltip: {title!r}")
      assert not button.is_enabled(), \
        f"Autocalibration button should be disabled when scene has no map ({cam_url})"

    result_recorder.success()

  finally:
    if browser is not None:
      browser.quit()
