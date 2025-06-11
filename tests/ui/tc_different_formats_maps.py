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
from tests.ui.browser import Browser, By, NoSuchElementException
import tests.ui.common_ui_test_utils as common

def validate_image(browser, scene_name, image_name):
  """! Checks that a scene contains the expected scene map image_name.
  @param    browser       Object wrapping the Selenium driver.
  @param    scene_name    Name of the scene.
  @param    image_name    Expected name of the scene map.
  @return   BOOL          Boolean representing success.
  """
  validated = False
  src = browser.find_element(By.NAME, scene_name).find_element(By.CSS_SELECTOR, "img.cover").get_attribute("src")
  if image_name.split('.')[0] in src:
    print("Map uploaded for " + image_name)
    validated = True
    # browser.find_element(By.NAME, scene_name).find_element(By.NAME, "Edit").click()
    # image_text = browser.find_element(By.ID, "id_map_wrapper").find_element(By.TAG_NAME, "a").text
    # print("Found image: " + image_text)
    # if image_text.split('_')[0] in image_name:
    #   validated = True
    #   print("Map validated for " + image_name)
    # else:
    #   print("Map not validated for " + image_name)
  else:
    print("Map not uploaded for " + image_name)
  return validated

def test_different_formats_scene_main(params, record_xml_attribute):
  """! Checks the name of the uploaded map is correct in the scene management page.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10392"
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)

  exit_code = 1
  browser = Browser()
  map_image_dict = {"png_map_image": "SamplePngMap.png", "jpeg_map_image": "SampleJpegMap.jpeg", "jpg_map_image": "SampleJpgMap.jpg"}
  scene_name = "Selenium Sample Scene"
  scale = 1000
  logged_in = common.check_page_login(browser, params)

  try:
    try:
      print("Creating Scene with png format map...")
      map_image = os.path.join(common.TEST_MEDIA_PATH, map_image_dict["png_map_image"])
      common.create_scene(browser, scene_name, scale, map_image)
      if scene_name in browser.page_source:
        time.sleep(1)
        validate_create = validate_image(browser, scene_name, map_image_dict["png_map_image"])
        for key, value in map_image_dict.items():
          if key == "png_map_image":
            continue
          map_image = os.path.join(common.TEST_MEDIA_PATH, value)
          browser.find_element(By.NAME, scene_name).find_element(By.NAME, "Edit").click()
          browser.find_element(By.ID, "id_map").send_keys(map_image)
          browser.find_element(By.ID, "save").click()
          validate_next = validate_image(browser, scene_name, value)
          if validate_next == False:
            break
      else:
        print("Could not create " + scene_name)
    except NoSuchElementException as e:
      print("Could not test image formats for " + scene_name)
      validate_next = False
    try:
      print("Different image formats tested, deleting scene " + scene_name)
      common.delete_scene(browser, scene_name)
    except NoSuchElementException:
      print("Could not delete scene...")
  finally:
    browser.close()
    if logged_in and validate_create and validate_next:
      exit_code = 0
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code

if __name__ == '__main__':
  exit(test_different_formats_scene_main() or 0)
