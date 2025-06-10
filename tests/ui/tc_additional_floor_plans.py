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

import os
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

def test_additional_floor_plans_main(params, record_xml_attribute):
  """! Tests adding three different scene maps and full screen mode.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10405"
  record_xml_attribute("name", TEST_NAME)

  exit_code = 1
  print("Executing: " + TEST_NAME)
  print("Test that two additional floor plans can be uploaded to a scene")
  browser = Browser()
  assert common.check_page_login(browser, params)
  assert common.check_db_status(browser)
  scene_name = common.TEST_SCENE_NAME

  files = [
    common.File(os.path.join(common.TEST_MEDIA_PATH, "HazardZoneScene.png"), "id_map", "#map_wrapper a"),
  ]

  try:
    browser.find_element(By.ID, "scene-edit").click()

    for file_object in files:
      print("Filename: ", file_object.filename)
      assert common.upload_scene_file(browser, scene_name, file_object)

    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
