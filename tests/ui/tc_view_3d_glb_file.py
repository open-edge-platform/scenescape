#!/usr/bin/env python3

# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import tests.ui.common_ui_test_utils as common
import os
import cv2

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
def check_3D_scene_asset_in_3D_scene(browser, base_screenshot, file_name, file_path, DEBUG):
  '''! This function verifies that a user can view a file in the 3D scene view.
  @param    browser                 Object wrapping the Selenium webdriver.
  @param    base_screenshot         Screenshot to validate the 3D file visibility against.
  @param    file_name               Filename of the 3D file to be uploaded.
  @param    file_path               Path for the 3D file to be uploaded.
  @param    DEBUG                   Boolean representing whether this function is running in debug mode.
  @return   BOOL                    Boolean representing whether the 3D file is visible.
  '''
  scene_3D_params = common.InteractionParams("/media/" + file_name, file_path, f"/scene/detail/{common.TEST_SCENE_ID}/", "", "", element_location="#map-url", \
                                      element_type="attribute", screenshot_threshold=2.75, debug=DEBUG)
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
      cv2.imwrite("tc_view_3d_glb_screenshot_base.png", base_screenshot)

    # glb test
    success_1, success_2 = file_visibility_test(params, "box.glb", base_screenshot, DEBUG)
    assert success_1
    assert success_2

  finally:
    if (success_1 and success_2):
      exit_code = 0
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
