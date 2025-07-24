#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import glob
import time
import tests.common_test_utils as tests_common
import tests.ui.common_ui_test_utils as common
from tests.ui.browser import By, Browser

TEST_WAIT_TIME = 5
TEST_NAME = "NEX-T10434"
TEST_IMAGE_THRESHOLD = 0
WORKSPACE = os.path.join(common.TEST_MEDIA_PATH, TEST_NAME)

def test_live_button(params, record_xml_attribute=None):
  """! Test for functionality of the 'live-view' button for cameras.
  Takes screenshot of the camera1 element for baseline, then enables live-view
  and takes a second screenshot. Waits for some time (TEST_WAIT_TIME) and
  takes a final screenshot. Compares all three to ensure the
  image contents in the element are changing.
  @param    params                Dict of test parameters.
  @param    record_xml_attribute  Pytest fixture recording the test name.
  @return   exit_code             0 for successful test, 1 otherwise.
  """
  if record_xml_attribute is not None:
    record_xml_attribute("name", TEST_NAME)

  image_array = []
  files_path = glob.iglob(os.path.join(WORKSPACE, "*.png"))
  img1_path = os.path.join(WORKSPACE, "img_1.png")
  img2_path = os.path.join(WORKSPACE, "img_2.png")
  img3_path = os.path.join(WORKSPACE, "img_3.png")

  if not os.path.exists(WORKSPACE):
    os.mkdir(WORKSPACE)
  else:
    for files in os.listdir(WORKSPACE):
      os.remove(os.path.join(WORKSPACE, files))

  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test that the 'Live View' button in a scene works.")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    camera1_box = browser.find_element(By.ID, 'camera1')
    live_toggle = browser.find_element(By.ID, "live-view")
    if live_toggle.is_selected():
      raise Exception("Live View is initially on. Expected to be off")

    time.sleep(TEST_WAIT_TIME)

    assert common.take_screenshot(browser, camera1_box, img1_path)
    print("Screenshot taken BEFORE enabling 'Live View' button")

    #enable "Live View" toggle
    browser.execute_script("arguments[0].click();", live_toggle)
    print("Clicked on 'Live View'")

    time.sleep(TEST_WAIT_TIME)

    assert common.take_screenshot(browser, camera1_box, img2_path)
    print("Screenshot taken AFTER enabling 'Live View' button")

    time.sleep(TEST_WAIT_TIME)

    assert common.take_screenshot(browser, camera1_box, img3_path)
    print("Screenshot taken AFTER waiting for some time")

    assert common.read_images(image_array, files_path)
    assert len(image_array) == 3
    assert common.compare_images(image_array[0], image_array[1], TEST_IMAGE_THRESHOLD)
    print("img_1 and img_2 not equals")
    assert common.compare_images(image_array[1], image_array[2], TEST_IMAGE_THRESHOLD)
    print("img_2 and img_3 not equals")

    exit_code = 0

    # Delete the images
    os.remove( img1_path )
    os.remove( img2_path )
    os.remove( img3_path )

  finally:
    browser.close()
    tests_common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
