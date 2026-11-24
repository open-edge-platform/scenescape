#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
import pytest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@pytest.mark.test_name("NEX-T10425")
def test_upload_glb_main(params, demo_scene, result_recorder):
  """! Checks that a user can upload a .glb file as a 3D scene map.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  file_name = "box.glb"
  file_path = common.TEST_MEDIA_PATH + file_name
  browser = None
  try:
    browser = Browser()
    assert common.check_page_login(browser, params), "Login to the web UI failed"
    assert common.check_db_status(browser), "Database status check failed"

    scene_update_params = common.InteractionParams(file_name, file_path, f"/scene/update/{common.TEST_SCENE_ID}/", "" ,"#id_map", "#map_wrapper a")
    upload_checks = common.CheckInteraction(file_name_in_page=True, file_on_server=True)
    scene_update_page = common.InteractWithSceneUpdate(browser, scene_update_params)

    assert scene_update_page.upload_scene_3D_map(upload_checks), \
      f"Uploading {file_name} as the scene map failed"
    result_recorder.success()
  finally:
    if browser is not None:
      browser.quit()
