#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@pytest.mark.test_name("NEX-T10428")
def test_add_delete_3d_object(params, repo_root, result_recorder):
  """! Checks that a 3D object can be both created and deleted using the web UI.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  @return   exit_code               Indicates test success or failure.
  """
  PAGE_NAME = "Object Library"
  OBJECT_NAME = '3D Object'
  FILE_TO_UPLOAD = f"{repo_root}/tests/ui/test_media/box.glb"
  try:
    print("Test that the user can create and delete 3D objects.")
    browser = Browser()
    assert common.check_page_login(browser, params)
    browser.find_element(By.ID, "nav-object-library").click()
    assert PAGE_NAME in browser.page_source
    print("Object Library exists in the navigation bar.")

    assert common.create_object_library(browser, OBJECT_NAME, model_file=FILE_TO_UPLOAD)
    print('3D object created!')
    assert common.delete_object_library(browser, OBJECT_NAME)
    print('3D object deleted!')
    result_recorder.success()

  finally:
    browser.close()
  return
