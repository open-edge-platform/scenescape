#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  require_password=True, auth="",
)

# compose-web_default loads sample_data/exampledb (Retail / Queuing), not testdb Demo.
SCENE_NAME = "Retail"

def test_scene_details_main(params, record_xml_attribute):
  """! Checks that the scene detail page is accessible from the scene summary page.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10395"
  record_xml_attribute("name", TEST_NAME)

  exit_code = 1
  browser = None
  try:
    print("Executing: " + TEST_NAME)
    print("Test that the user can view scene details")
    browser = Browser()
    assert common.check_page_login(browser, params)
    browser.find_element(By.ID, "nav-scenes").click()
    assert SCENE_NAME in browser.page_source

    print("Scene is accessible from the list of scenes")
    assert common.navigate_to_scene(browser, SCENE_NAME)
    time.sleep(3)

    def _displayed(by, value):
      els = browser.find_elements(by, value)
      return bool(els) and els[0].is_displayed()

    status_scene_name = _displayed(By.ID, "scene_name")
    status_floorplan = _displayed(By.CSS_SELECTOR, "#svgout > image:nth-child(4)")
    status_cameras = _displayed(By.ID, "camera1") or _displayed(
      By.ID, "card-preview-camera1"
    )
    assert status_scene_name or status_floorplan or status_cameras
    print("Details are displayed in the scene summary view")
    exit_code = 0
  finally:
    if browser is not None:
      browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code

if __name__ == '__main__':
  exit(test_scene_details_main() or 0)
