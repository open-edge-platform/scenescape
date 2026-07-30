# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
from tests.utils.log import get_logger
log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

@pytest.mark.test_name("NEX-T10554")
def test_3d_asset_crud_ui(params, repo_root, result_recorder):
  """! Verify the CRUD of object library via GUI.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """

  PAGE_NAME = "Object Library"
  OBJECT_NAME = 'Test Object'
  FILE_TO_UPLOAD = f"{repo_root}/tests/ui/test_media/box.glb"
  SPECIFIC_3D_ELEMENTS = "#id_rotation_x, #id_rotation_y, #id_rotation_z, [id^=id_translation], #id_scale"
  browser = None

  try:
    log.info("Executing: NEX-T10554")
    log.info("Verify the CRUD of object library via GUI.")
    browser = Browser()
    assert common.check_page_login(browser, params)
    browser.find_element(By.ID, "nav-object-library").click()
    assert PAGE_NAME in browser.page_source
    log.info("Object Library exists in the navigation bar.")

    # Clean up any pre-existing object with the same name before starting
    if browser.find_elements(By.XPATH, "//td[text()='{0}']".format(OBJECT_NAME)):
      assert common.delete_object_library(browser, OBJECT_NAME)

    log.info("Step 1. Verify the creation of object in object library")

    # Navigate to the object create form
    browser.find_element(By.CSS_SELECTOR, "a[href^='/asset/create/']").click()

    # Case 1 (negative): clearing x_size prevents submission
    browser.find_element(By.ID, "id_name").send_keys(OBJECT_NAME)
    browser.find_element(By.ID, "id_x_size").clear()
    browser.find_element(By.CSS_SELECTOR, "input[value='Add New Object']").click()
    assert not browser.execute_script("return document.getElementById('id_x_size').validity.valid"), \
      "Expected x_size to be invalid when empty"
    assert browser.find_elements(By.CSS_SELECTOR, "input[value='Add New Object']"), \
      "Form was unexpectedly submitted when x_size was empty"
    log.info("  Case 1: HTML5 required validation blocks submission for null x_size - PASS")

    # Case 2 (positive): Successfully create an object
    browser.find_element(By.ID, "id_x_size").send_keys("1.0")
    browser.find_element(By.CSS_SELECTOR, "input[value='Add New Object']").click()
    assert browser.find_elements(By.XPATH, "//td[text()='{0}']".format(OBJECT_NAME)), \
      f"Object '{OBJECT_NAME}' not found in object library after creation"
    log.info(f"  Case 2: Object '{OBJECT_NAME}' saved successfully - PASS")

    log.info("Step 2. Verify the fields in object / asset 3D form toggle on condition")

    # Navigate to the edit page of the created object
    common.selenium_wait_for_elements(browser, (By.ID, f"obj-manage-{OBJECT_NAME}"))
    browser.find_element(By.ID, f"obj-manage-{OBJECT_NAME}").click()
    common.selenium_wait_for_elements(browser, (By.ID, "id_name"))

    # Persistence check: verify Step 1 values were saved correctly
    assert browser.find_element(By.ID, "id_name").get_attribute("value") == OBJECT_NAME, \
      "Object name did not persist after creation"
    log.info("  Persistence: name saved correctly - PASS")

    # Without a model file the form must expose exactly these fields and hide the 3D-only ones
    expected_fields_no_model = [
      "id_name", "id_model_3d", "id_mark_color",
      "id_x_size", "id_y_size", "id_z_size",
      "id_tracking_radius", "id_project_to_map", "id_rotation_from_velocity",
    ]
    for field_id in expected_fields_no_model:
      assert len(browser.find_elements(By.ID, field_id)) == 1, \
        f"Expected field '{field_id}' not found in form without 3D model"
    assert len(browser.find_elements(By.CSS_SELECTOR, SPECIFIC_3D_ELEMENTS)) == 0, \
      "3D-specific fields are visible when no 3D model file is set"
    log.info("Toggle without model file: expected fields present, 3D fields hidden - PASS")

    # Change mark color to white and save
    mark_color_field = browser.find_element(By.ID, "id_mark_color")
    mark_color_field.clear()
    mark_color_field.send_keys("#ffffff")
    browser.find_element(By.CSS_SELECTOR, "input[value='Update Object']").click()
    common.selenium_wait_for_elements(browser, (By.ID, f"obj-manage-{OBJECT_NAME}"))
    log.info("mark_color updated to #ffffff and saved - PASS")

    log.info("Step 3. Verify 3D model upload in objects")

    # Re-open the edit page and upload the 3D model
    browser.find_element(By.ID, f"obj-manage-{OBJECT_NAME}").click()
    common.selenium_wait_for_elements(browser, (By.ID, "id_name"))

    # Persistence check: verify mark_color was saved correctly in Step 2
    assert browser.find_element(By.ID, "id_mark_color").get_attribute("value") == "#ffffff", \
      "mark_color did not persist after update"
    log.info("  Persistence: mark_color #ffffff saved correctly - PASS")

    browser.find_element(By.ID, "id_model_3d").send_keys(FILE_TO_UPLOAD)

    # With a model file selected the form must expose the 3D-specific fields and hide mark_color
    expected_fields_with_model = [
      "id_name", "id_model_3d",
      "id_x_size", "id_y_size", "id_z_size",
      "id_tracking_radius", "id_project_to_map", "id_rotation_from_velocity",
      "id_scale", "id_rotation_x", "id_rotation_y", "id_rotation_z",
      "id_translation_x", "id_translation_y", "id_translation_z",
    ]
    for field_id in expected_fields_with_model:
      assert len(browser.find_elements(By.ID, field_id)) == 1, \
        f"Expected field '{field_id}' not found in form with 3D model"
    assert len(browser.find_elements(By.ID, "id_mark_color")) == 0, \
      "mark_color field is still visible after selecting a 3D model file"
    log.info("Toggle with model file: 3D fields visible, mark_color hidden - PASS")

    # Save and verify the model file link persists in the edit page
    browser.find_element(By.CSS_SELECTOR, "input[value='Update Object']").click()
    common.selenium_wait_for_elements(browser, (By.ID, f"obj-manage-{OBJECT_NAME}"))
    browser.find_element(By.ID, f"obj-manage-{OBJECT_NAME}").click()
    common.selenium_wait_for_elements(browser, (By.ID, "id_name"))
    model_file_name = FILE_TO_UPLOAD.split("/")[-1]
    browser.find_element(By.LINK_TEXT, model_file_name)
    log.info(f"3D model '{model_file_name}' uploaded and verified in object detail - PASS")

    # Cleanup
    assert common.delete_object_library(browser, OBJECT_NAME)
    log.info(f"Object '{OBJECT_NAME}' deleted - PASS")

    result_recorder.success()

  finally:
    if browser is not None:
      browser.close()
