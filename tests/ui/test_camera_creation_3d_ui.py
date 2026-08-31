# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import pytest
import tests.ui.common_ui_test_utils as common
from tests.ui.browser import By, Browser
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

WAIT_SEC = 1
PANEL_WAIT_SEC = 100

def get_camera_panel_ids(browser):
  panels = browser.find_elements(By.CSS_SELECTOR, "[id$='-control-panel']")
  return [panel.get_attribute("id") for panel in panels]

def cleanup_created_camera(browser, camera_name):
  if not camera_name:
    return

  log.info(f"Cleaning up test camera: {camera_name}")
  assert common.navigate_directly_to_page(browser, "/cam/list/")

  rows_to_delete = browser.find_elements(
    By.XPATH,
    "//td[text()='" + camera_name + "']/parent::tr",
  )
  for _ in rows_to_delete:
    browser.find_element(
      By.XPATH,
      "//td[text()='" + camera_name + "']/parent::tr//a[contains(@href,'cam/delete/')]",
    ).click()
    browser.find_element(By.XPATH, "//*[@type = 'submit']").click()
    assert common.navigate_directly_to_page(browser, "/cam/list/")

  remaining_rows = browser.find_elements(
    By.XPATH,
    "//td[text()='" + camera_name + "']/parent::tr",
  )
  assert len(remaining_rows) == 0, f"Camera '{camera_name}' still exists in table after deletion"

@pytest.mark.fresh_stack
@common.mock_display(require_xvfb=True)
@pytest.mark.test_name("NEX-T10558")
def test_camera_creation_3d_ui(params, result_recorder):
  """! Test that the user is able to create a camera in the 3D UI interface.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  created_camera_name = ""
  browser = None
  add_camera_button_xpath = "//div[@id='panel-3d-controls']//div[contains(@class,'name') and normalize-space()='add camera']/ancestor::button[1]"

  log.info(f"Executing: NEX-T10558")
  log.info("Test that the user is able to create a camera in the 3D UI interface.")

  try:
    browser = Browser(headless=False, webgl=True)
    assert common.check_page_login(browser, params)

    log.info("Navigate to the Scene detail page.")
    assert common.navigate_directly_to_page(browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    log.info("Expand camera1 controls.")
    common.selenium_wait_for_elements(browser, (By.ID, "camera1-control-panel"), PANEL_WAIT_SEC)
    assert common.click_when_clickable(browser, (By.ID, "camera1-control-panel"), timeout_s=PANEL_WAIT_SEC), (
      "Timed out waiting for camera1-control-panel to become clickable"
    )
    time.sleep(WAIT_SEC)

    assert common.wait_for_elements(
      browser,
      add_camera_button_xpath,
      findBy=By.XPATH,
      maxWait=30,
      refreshPage=False,
    ), "3D UI add camera button not found"

    camera_panel_ids_before = get_camera_panel_ids(browser)
    log.info(f"Camera control panels before creation: {camera_panel_ids_before}")

    created_camera_name = f"Test_Cam_{time.time()}"
    log.info(f"Create camera from 3D UI with name {created_camera_name}")

    assert common.click_when_clickable(browser, (By.XPATH, add_camera_button_xpath)), (
      "Timed out waiting for add camera button to become clickable"
    )

    log.info("Wait for temporary new-camera control panel")
    assert common.wait_for_elements(
      browser,
      "new-camera-control-panel",
      findBy=By.ID,
      maxWait=30,
      refreshPage=False,
    ), "Temporary new-camera control panel was not created"
    assert common.click_when_clickable(browser, (By.ID, "new-camera-control-panel")), (
      "Timed out waiting for new-camera-control-panel to become clickable"
    )

    log.info("Set camera name and save from 3D camera controls")
    name_input = browser.find_element(By.ID, "new-camera-name")
    name_input.clear()
    name_input.send_keys(created_camera_name)
    assert common.click_when_clickable(browser, (By.ID, "new-camera-save-camera"), timeout_s=20), (
      "Timed out waiting for new-camera-save-camera to become clickable"
    )

    created_panel_id = f"{created_camera_name}-control-panel"
    log.info(f"Wait for created camera control panel: {created_panel_id}")
    assert common.wait_for_elements(
      browser,
      created_panel_id,
      findBy=By.ID,
      maxWait=30,
      refreshPage=False,
    ), f"Created camera control panel not found: {created_panel_id}"

    camera_panel_ids_after = get_camera_panel_ids(browser)
    log.info(f"Camera control panels after creation: {camera_panel_ids_after}")
    assert created_panel_id in camera_panel_ids_after

    result_recorder.success()

  finally:
    if browser is not None:
      if created_camera_name:
        cleanup_created_camera(browser, created_camera_name)
      browser.close()
