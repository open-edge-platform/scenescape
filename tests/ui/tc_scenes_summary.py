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
import time
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common

def test_scenes_summary_main(params, record_xml_attribute):
  """! Creates a second scene and checks that both scenes are both visible in
  the scene summary view.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10394"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  try:
    print("Executing: " + TEST_NAME)
    print("Test that the user can view a summary of all scenes")
    browser = Browser()
    assert common.check_page_login(browser, params)

    scene_name_0 = "Demo"
    scene_name_1 = "Scene-1"
    scale = 1000
    map_image = os.path.join(common.TEST_MEDIA_PATH, "SampleJpegMap.jpeg")
    print("Creating Scene " + scene_name_1)
    common.create_scene(browser, scene_name_1, scale, map_image)

    time.sleep(1)
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(1) > .nav-link").click()
    scenes_name = browser.find_elements(By.CLASS_NAME, "card-header")
    element1 = scenes_name[0].text
    element2 = scenes_name[1].text
    nr_scenes = len(scenes_name)
    print(f"The page shows {nr_scenes} scenes: {element1}, {element2}")
    assert element1 == scene_name_0 and element2 == scene_name_1
    assert nr_scenes == 2
    print("Test conditions met, deleting " + scene_name_1)
    exit_code = 0

  finally:
    common.delete_scene(browser, scene_name_1)
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return

if __name__ == '__main__':
  exit(test_scenes_summary_main() or 0)
