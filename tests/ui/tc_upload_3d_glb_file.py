#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser

def test_upload_glb_main(params, record_xml_attribute):
  """! Checks that a user can upload a .glb file as a 3D scene map.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10425"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  browser = Browser()
  assert common.check_page_login(browser, params)
  assert common.check_db_status(browser)

  file_name = "box.glb"
  file_path = common.TEST_MEDIA_PATH + file_name
  scene_update_params = common.InteractionParams(file_name, file_path, f"/scene/update/{common.TEST_SCENE_ID}/", "" ,"#id_map", "#map_wrapper a")
  upload_checks = common.CheckInteraction(file_name_in_page=True, file_on_server=True)
  scene_update_page = common.InteractWithSceneUpdate(browser, scene_update_params)

  if scene_update_page.upload_scene_3D_map(upload_checks):
    exit_code = 0
  browser.close()

  common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return
