#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

def test_only_upload_glb_main(params, record_xml_attribute):
  """! Checks that a user can not upload a files that are not .glb as a 3D scene map.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10433"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  file_names = ["box_invalid.glb", "box.gltf", "box.obj", "good_data.txt"]
  element_id = "id_map"
  element_location = "#map_wrapper a"
  scene_name = common.TEST_SCENE_NAME

  try:
    print("Executing: " + TEST_NAME)

    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)
    browser.find_element(By.ID, "scene-edit").click()

    for name in file_names:
      print("Filename: ", name)
      file_path = os.path.join(common.TEST_MEDIA_PATH, name)
      file_object = common.File(file_path, element_id, element_location)
      assert not common.upload_scene_file(browser, scene_name, file_object)

    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
