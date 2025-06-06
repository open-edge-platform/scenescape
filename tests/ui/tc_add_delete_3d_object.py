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

from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def test_add_delete_3d_object(params, record_xml_attribute):
  """! Checks that a 3D object can be both created and deleted using the web UI.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10428"
  record_xml_attribute("name", TEST_NAME)
  PAGE_NAME = "Object Library"
  OBJECT_NAME = '3D Object'
  FILE_TO_UPLOAD = "/workspace/tests/ui/test_media/box.glb"
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
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
    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
