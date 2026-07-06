#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tests.ui.common_ui_test_utils as common
import os
import cv2
from tests.ui.browser import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@common.mock_display
@common.scenescape_login_headed
def get_baseline_screenshot(params):
  """! Take baseline screenshot of the current 3D scene.
  @param    params                  List of test parameters.
  @return   BOOL                    Boolean representing whether the 3D file is uploaded successully.
  """
  scene_3D_page = common.InteractWith3DScene(params)
  return scene_3D_page.get_3D_scene_screenshot()

@common.mock_display
@common.scenescape_login_headed
def upload_3D_scene_asset(browser, file_name, file_path):
  '''! This function uploads a 3D file as a 3D map.
  @param    browser                 Object wrapping the Selenium webdriver.
  @param    file_name               Filename of the 3D file to be uploaded.
  @param    file_path               Path for the 3D file to be uploaded.
  @return   BOOL                    Boolean representing whether the 3D file is uploaded successully.
  '''
  scene_update_params = common.InteractionParams(file_name, file_path, f"/scene/update/{common.TEST_SCENE_ID}/", "", "#id_map", element_location="")
  upload_checks = common.CheckInteraction()
  scene_update_page = common.InteractWithSceneUpdate(browser, scene_update_params)
  return scene_update_page.upload_scene_3D_map(upload_checks)

@common.mock_display
@common.scenescape_login_headed
def check_3D_scene_asset_in_3D_scene(browser, base_screenshot, file_name, file_path, DEBUG, timeout_s=10):
  '''! This function verifies that a user can view a file in the 3D scene view.
  @param    browser                 Object wrapping the Selenium webdriver.
  @param    base_screenshot         Screenshot to validate the 3D file visibility against.
  @param    file_name               Filename of the 3D file to be uploaded.
  @param    file_path               Path for the 3D file to be uploaded.
  @param    DEBUG                   Boolean representing whether this function is running in debug mode.
  @return   BOOL                    Boolean representing whether the 3D file is visible.
  '''

  if not common.navigate_directly_to_page(browser, f"/scene/detail/{common.TEST_SCENE_ID}/"):
    log.error("Failed to navigate to scene detail page.")
    return False

  try:
    map_url = WebDriverWait(browser, timeout_s).until(
      EC.presence_of_element_located((By.CSS_SELECTOR, "#map-url"))
    ).get_attribute("value")
  except TimeoutException:
    log.error(f"Timed out after {timeout_s}s waiting for #map-url on scene detail page.")
    return False

  base_name = os.path.splitext(file_name)[0]
  ext = os.path.splitext(file_name)[1].lower()
  if not map_url or ext not in map_url.lower() or base_name not in map_url:
    log.error(f"Expected a {file_name!r} map URL, got: {map_url!r}")
    return False

  scene_3D_params = common.InteractionParams(map_url, file_path, f"/scene/detail/{common.TEST_SCENE_ID}/", "", "", element_location="#map-url", \
                                      element_type="attribute", screenshot_threshold=0.85, debug=DEBUG)
  scene_3D_params.add_screenshot(base_screenshot)
  scene_3D_page = common.InteractWith3DScene(browser, scene_3D_params)
  return scene_3D_page.check_3D_asset_visible()

def file_visibility_test(params, file_name, base_screenshot, DEBUG):
  '''! This function uploads and verifies that a user can view a file in the 3D scene view.
  @param    params                  List of test parameters.
  @param    file_name               Filename of the 3D file to be uploaded.
  @param    base_screenshot         Screenshot of validate 3D file visibility against.
  @param    DEBUG                   Boolean representing whether this function is running in debug mode.
  @return   upload_success          Boolean representing whether the 3D file is uploaded successfully.
  @return   object_visible_success  Boolean representing whether the uploaded 3D file is visible.
  '''
  file_path = os.path.join(common.TEST_MEDIA_PATH, file_name)
  upload_success = upload_3D_scene_asset(params, file_name, file_path)

  object_visible_success = False
  if upload_success:
    object_visible_success = check_3D_scene_asset_in_3D_scene(params, base_screenshot, file_name, file_path, DEBUG)

  return upload_success, object_visible_success

def test_3D_file_upload_visibility(params, record_xml_attribute):
  """! This test checks that an uploaded .glb file uploaded as a 3D map is visible in Scenescape's 3D view.
  @param    params                  List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  TEST_NAME = "NEX-T10427"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  DEBUG = False
  success_1 = False
  success_2 = False

  try:
    base_screenshot = get_baseline_screenshot(params)
    if DEBUG:
      cv2.imwrite("test_view_3d_glb_screenshot_base.png", base_screenshot)

    # glb test
    success_1, success_2 = file_visibility_test(params, "box.glb", base_screenshot, DEBUG)
    assert success_1
    assert success_2

  finally:
    if (success_1 and success_2):
      exit_code = 0
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
