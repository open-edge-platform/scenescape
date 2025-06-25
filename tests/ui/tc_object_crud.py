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

import random
from scene_common import log
from selenium.webdriver.support.ui import Select
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common


def validate_object_crud(browser, file_path=None):
  """! Navigates to the object library page, then creates, updates and deletes a 3D object
  with an optional 3D model file.
  @param    browser             Object wrapping the Selenium driver.
  @param    [file_path=None]    Path of optional 3d model file to upload.
  @return   BOOL                Boolean representing successfully verifying CRUD operations
                                on an object.
  """
  OBJECT_NAME = 'Test 3D Object'
  OBJECT_NAME_2 = 'Test 3D Object-2'
  initial_loop_value = round(random.uniform(0.1, 10), 1)

  # Create 3D object
  assert common.create_object_library(browser, OBJECT_NAME)

  # Load object detail
  browser.find_element(By.ID, "obj-manage-{0}".format(OBJECT_NAME)).click()

  # Verify correct object detail loaded
  assert common.selenium_wait_for_elements(browser, (By.ID, "id_name")).get_attribute("value") == OBJECT_NAME

  # Based if it's a 3D object, check if the appropriate fields exists and update all fields
  common_elements = "#id_tracking_radius, #id_x_size, #id_y_size, #id_z_size"
  specific_3d_elements = "#id_rotation_x, #id_rotation_y, #id_rotation_z, [id^=id_translation], #id_scale"
  common_dropdowns = ["id_project_to_map", "id_rotation_from_velocity"]

  assert len(browser.find_elements(By.CSS_SELECTOR, common_elements)) == 4, \
    'Not found all common options'

  for elem_id in common_dropdowns:
    select = Select(browser.find_element(By.ID, elem_id))
    select.select_by_visible_text('Yes')

  if file_path:
    browser.find_element(By.ID, "id_model_3d").send_keys(file_path)
    common_elements += f", {specific_3d_elements}"
    assert len(browser.find_elements(By.CSS_SELECTOR, specific_3d_elements)) != 0, \
      'Not found any 3D options when a 3D model file was used!'
  else:
    assert len(browser.find_elements(By.CSS_SELECTOR, specific_3d_elements)) == 0, \
      'Some 3D elements were found when no 3D model file was used!'

  fld_id = browser.find_element(By.ID, "id_name")
  fld_id.clear()
  fld_id.send_keys(OBJECT_NAME_2)

  edit_elems = browser.find_elements(By.CSS_SELECTOR, common_elements)

  loop_value = initial_loop_value
  verify_elems = []
  for elem in edit_elems:
    elem.clear()
    elem.send_keys(loop_value)
    verify_elems.append(elem.get_attribute("id"))
    loop_value += 1

  browser.find_element(By.CSS_SELECTOR, "input[value='Update Object']").click()

  # Load updated object detail
  assert common.selenium_wait_for_elements(browser, (By.ID, "obj-manage-{0}".format(OBJECT_NAME_2)))
  browser.find_element(By.ID, "obj-manage-{0}".format(OBJECT_NAME_2)).click()

  # Verify object detail updated
  assert common.selenium_wait_for_elements(browser, (By.ID, "id_name")).get_attribute("value") == OBJECT_NAME_2

  loop_value = initial_loop_value
  for elem_id in verify_elems:
    assert common.selenium_wait_for_elements(browser, (By.ID, elem_id)).get_attribute("value") == str(loop_value)
    loop_value += 1

  if file_path:
    log.info('3D object updated!')
    # Verify 3D model present using file name
    browser.find_element(By.LINK_TEXT, file_path.split("/")[-1])
    # Test remove 3D model
    browser.find_element(By.ID, 'model_3d-clear_id').click()
    browser.find_element(By.CSS_SELECTOR, "input[value='Update Object']").click()
    log.info('3D model removed!')

    # Load updated object detail
    assert common.selenium_wait_for_elements(browser, (By.ID, "obj-manage-{0}".format(OBJECT_NAME_2)))
    browser.find_element(By.ID, "obj-manage-{0}".format(OBJECT_NAME_2)).click()

  # Check checkbox to remove 3D model is not shown
  assert len(browser.find_elements(By.ID, 'model_3d-clear_id')) == 0

  assert common.delete_object_library(browser, OBJECT_NAME_2)
  log.info('Object deleted!')

  return True

def test_object_crud(params, record_xml_attribute):
  """! Checks that CRUD operations can be performed on an object with and without a 3d model.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10429"

  record_xml_attribute("name", TEST_NAME)

  exit_code = 1
  try:
    log.info("Executing: " + TEST_NAME)
    log.info("Test that the user can perform CRUD operations on objects with and without a 3D model.")

    browser = Browser()
    assert common.check_page_login(browser, params)

    files = ["/workspace/tests/ui/test_media/box.glb", None]
    for file in files:
      log.info(f"Testing and validating CRUD operations on 3D object where file = {file}...")
      assert validate_object_crud(browser, file)

    exit_code = 0

  finally:
    browser.quit()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
