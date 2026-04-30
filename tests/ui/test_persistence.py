#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
import pytest
from scene_common import log
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

SCENE_NAME = "Selenium Sample Scene"
CAMERA_ID = "camtest1"
CAMERA_NAME = "camtest1"
SCALE = 1000


@pytest.mark.test_name("NEX-T10393_PAGE_NAVIGATE")
@pytest.mark.preserve_db
def test_persistence_on_page_navigate(params, result_recorder):
  """! Checks that a scene can be created and a camera added.
  @param    params                  Dict of test parameters.
  """
  browser = Browser()
  try:
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    def _cleanup_test_artifacts():
      """Remove leftover scene/camera so the test is deterministic."""
      try:
        common.navigate_to_scene(browser, SCENE_NAME)
        common.delete_scene(browser, SCENE_NAME)
      except Exception:
        pass
      try:
        common.delete_camera(browser, CAMERA_NAME)
      except Exception:
        pass

    _cleanup_test_artifacts()

    sensor_count_loc = "[name='" + SCENE_NAME + "'] .sensor-count"
    log.info("Creating Scene " + SCENE_NAME)
    map_image = os.path.join(common.TEST_MEDIA_PATH, "HazardZoneScene.png")
    assert common.create_scene(browser, SCENE_NAME, SCALE, map_image)
    assert SCENE_NAME in browser.page_source

    camera_count = browser.find_element(By.CSS_SELECTOR, sensor_count_loc).text
    log.info("Editing scene by adding camera " + SCENE_NAME)
    assert common.add_camera_to_scene(browser, SCENE_NAME, CAMERA_ID, CAMERA_NAME)
    browser.find_element(By.ID, "home").click()
    changed_camera_count = browser.find_element(By.CSS_SELECTOR, sensor_count_loc).text

    assert int(changed_camera_count) == int(camera_count) + 1
    log.info("Edited info (camera addition to scene) persists on page navigation, camera count: " + str(changed_camera_count))
    assert common.validate_scene_data(browser, SCENE_NAME, SCALE, map_image)
    log.info("Scene data persist on page navigation")

    result_recorder.success()
  finally:
    browser.close()


@pytest.mark.test_name("NEX-T10393_RESTART")
def test_persistence_on_restart(params, result_recorder):
  """! Checks that the scene constructed in test_persistence_on_page_navigate is
  still in the scenescape database after a restart.
  @param    params                  Dict of test parameters.
  """
  browser = Browser()
  try:
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    def _cleanup_test_artifacts():
      """Remove scene and camera created by the page-navigate test."""
      try:
        common.navigate_to_scene(browser, SCENE_NAME)
        common.delete_scene(browser, SCENE_NAME)
      except Exception:
        pass
      try:
        common.delete_camera(browser, CAMERA_NAME)
      except Exception:
        pass

    map_image = os.path.join(common.TEST_MEDIA_PATH, "HazardZoneScene.png")
    browser.find_element(By.ID, "nav-scenes").click()
    time.sleep(1)

    sensor_count_loc = "[name='" + SCENE_NAME + "'] .sensor-count"
    assert SCENE_NAME in browser.page_source
    changed_camera_count = browser.find_element(By.CSS_SELECTOR, sensor_count_loc).text
    assert int(changed_camera_count) == 1
    log.info("Edited info (camera addition to scene) persists on docker restart, camera count: " + str(changed_camera_count))
    assert common.validate_scene_data(browser, SCENE_NAME, SCALE, map_image)
    log.info("Scene data persist on docker restart")

    _cleanup_test_artifacts()

    result_recorder.success()
  finally:
    browser.close()
