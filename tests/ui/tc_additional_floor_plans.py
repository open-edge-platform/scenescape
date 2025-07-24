#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
