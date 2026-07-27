#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time

import pytest
from tests.ui.browser import By, Browser
from selenium.webdriver.support.ui import Select
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@pytest.mark.test_name("NEX-T10558")
def test_camera_creation_3d_ui(params, record_xml_attribute, repo_root):
  """! Test that the user is able to create a camera in the 3D UI interface.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """

  exit_code = 1
  camera_name = ""
  browser = None
  try:
    log.info("Executing: NEX-T10558")
    log.info("Test that the user is able to create a camera in the 3D UI interface.")
    log.info("Starting browser session")
    browser = Browser()
    assert common.check_page_login(browser, params)
    log.info("Login successful")
    assert common.check_db_status(browser)
    log.info("Database status check passed")

    # Navigate to the 3D UI page through scene name to avoid brittle DB-specific UUID assumptions.
    log.info(f"Navigating to scene details for scene: {common.TEST_SCENE_NAME}")
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    common.selenium_wait_for_elements(browser, (By.ID, "new-camera"), 20)
    log.info("3D scene controls loaded and new camera button is visible")

    # Verify camera can be created from the 3D scene page.
    available_cameras_before = browser.find_elements(By.CSS_SELECTOR, ".card.count-item.camera-card > .card-header")
    camera_names_before = [name.text.replace("--\n", "") for name in available_cameras_before]
    num_cameras_before = len(camera_names_before)
    log.info(f"Available cameras before creation: {camera_names_before}")

    timestamp = int(time.time())
    camera_name = f"Test_Cam_{timestamp}"
    camera_id = f"test-cam-{timestamp}"
    log.info(f"Creating camera with name={camera_name}, id={camera_id}")

    log.info("Opening new camera form")
    browser.find_element(By.ID, "new-camera").click()
    browser.find_element(By.ID, "id_sensor_id").send_keys(camera_id)
    browser.find_element(By.ID, "id_name").send_keys(camera_name)
    select = Select(browser.find_element(By.ID, "id_scene"))
    select.select_by_visible_text(common.TEST_SCENE_NAME)
    log.info("Submitting camera creation form")
    browser.find_element(By.XPATH, "//input[@value = 'Add New Camera']").click()

    # The app redirects after add; navigate back to scene details and verify camera panel count increased.
    log.info("Navigating back to scene details to verify camera creation")
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)

    cameras_added = False
    camera_names_after = []
    log.info("Polling camera cards for newly created camera")
    for _ in range(20):
      available_cameras_after = browser.find_elements(By.CSS_SELECTOR, ".card.count-item.camera-card > .card-header")
      camera_names_after = [name.text.replace("--\n", "") for name in available_cameras_after]
      if len(camera_names_after) == (num_cameras_before + 1) and camera_name in camera_names_after:
        cameras_added = True
        break
      time.sleep(1)
    log.info(f"Available cameras after creation attempt: {camera_names_after}")
    assert cameras_added, "Camera panel count did not increase after creating a camera in 3D UI"
    log.info(f"Camera creation verified successfully for {camera_name}")

    exit_code = 0

  finally:
    if browser is not None:
      if camera_name:
        log.info(f"Cleaning up test camera: {camera_name}")
        common.delete_camera(browser, camera_name)
      log.info("Closing browser session")
      browser.close()
    log.info(f"Recording test result with exit_code={exit_code}")
    common.record_test_result("NEX-T10558", exit_code)
  assert exit_code == 0
