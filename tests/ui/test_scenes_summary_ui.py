#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
import pytest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@pytest.mark.test_name("NEX-T10394")
def test_scenes_summary_main(demo_scene, params, record_xml_attribute):
  """! Creates a second scene and checks that both scenes are both visible in
  the scene summary view.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10394"
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

    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(1) > .nav-link").click()
    scenes_before = [el.text for el in browser.find_elements(By.CLASS_NAME, "card-header")]
    print(f"Scenes visible before creation: {scenes_before}")

    print("Creating Scene " + scene_name_1)
    assert common.create_scene(browser, scene_name_1, scale, map_image)

    time.sleep(1)
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(1) > .nav-link").click()
    scenes_name = browser.find_elements(By.CLASS_NAME, "card-header")
    scene_names = [el.text for el in scenes_name]
    nr_scenes = len(scene_names)
    print(f"The page shows {nr_scenes} scenes: {scene_names}")
    assert scene_name_0 in scene_names and scene_name_1 in scene_names
    assert nr_scenes == len(scenes_before) + 1, (
      f"Expected exactly one new scene, before={scenes_before}, after={scene_names}")
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
