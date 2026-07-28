#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time

import pytest
import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest
from tests.ui.browser import By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

WAIT_SEC = 1
PANEL_WAIT_SEC = 100

class Scene3dCameraCreationTest(UserInterfaceTest):
  BROWSER_WEBGL = True

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.createdCameraName = ""

    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    return

  def getCameraPanelIds(self):
    panels = self.browser.find_elements(By.CSS_SELECTOR, "[id$='-control-panel']")
    return [panel.get_attribute("id") for panel in panels]

  def cleanupCreatedCamera(self):
    if not self.createdCameraName:
      return

    log.info(f"Cleaning up test camera: {self.createdCameraName}")
    assert common.navigate_directly_to_page(self.browser, "/cam/list/")

    rows_to_delete = self.browser.find_elements(
      By.XPATH,
      "//td[text()='" + self.createdCameraName + "']/parent::tr",
    )
    for _ in rows_to_delete:
      self.browser.find_element(
        By.XPATH,
        "//td[text()='" + self.createdCameraName + "']/parent::tr//a[contains(@href,'cam/delete/')]",
      ).click()
      self.browser.find_element(By.XPATH, "//*[@type = 'submit']").click()
      assert common.navigate_directly_to_page(self.browser, "/cam/list/")

    assert self.createdCameraName not in self.browser.page_source

  def checkCameraCreation(self):
    try:
      assert self.login()

      log.info("Navigate to the Scene detail page.")
      common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

      log.info("Expand camera1 controls.")
      self.clickOnElement("camera1-control-panel", delay=PANEL_WAIT_SEC)
      time.sleep(WAIT_SEC)

      add_camera_button_xpath = "//div[@id='panel-3d-controls']//div[contains(@class,'name') and normalize-space()='add camera']/ancestor::button[1]"
      assert common.wait_for_elements(
        self.browser,
        add_camera_button_xpath,
        findBy=By.XPATH,
        maxWait=30,
        refreshPage=False,
      ), "3D UI add camera button not found"

      camera_panel_ids_before = self.getCameraPanelIds()
      log.info(f"Camera control panels before creation: {camera_panel_ids_before}")

      timestamp = int(time.time())
      self.createdCameraName = f"Test_Cam_{timestamp}"
      log.info(f"Create camera from 3D UI with name {self.createdCameraName}")

      self.browser.find_element(By.XPATH, add_camera_button_xpath).click()

      log.info("Wait for temporary new-camera control panel")
      assert common.wait_for_elements(
        self.browser,
        "new-camera-control-panel",
        findBy=By.ID,
        maxWait=30,
        refreshPage=False,
      ), "Temporary new-camera control panel was not created"
      self.clickOnElement("new-camera-control-panel", delay=10)

      log.info("Set camera name and save from 3D camera controls")
      name_input = self.browser.find_element(By.ID, "new-camera-name")
      name_input.clear()
      name_input.send_keys(self.createdCameraName)
      self.clickOnElement("new-camera-save-camera", delay=10)

      created_panel_id = f"{self.createdCameraName}-control-panel"
      log.info(f"Wait for created camera control panel: {created_panel_id}")
      assert common.wait_for_elements(
        self.browser,
        created_panel_id,
        findBy=By.ID,
        maxWait=30,
        refreshPage=False,
      ), f"Created camera control panel not found: {created_panel_id}"

      camera_panel_ids_after = self.getCameraPanelIds()
      log.info(f"Camera control panels after creation: {camera_panel_ids_after}")
      assert created_panel_id in camera_panel_ids_after

      self.exitCode = 0
    finally:
      if self.createdCameraName:
        self.cleanupCreatedCamera()
      self.recordTestResult()
    return

@pytest.mark.fresh_stack
@common.mock_display
@pytest.mark.test_name("NEX-T10558")
def test_camera_creation_3d_ui(scenescape_env, request, record_xml_attribute):
  """! Test that the user is able to create a camera in the 3D UI interface.
  @param    request                 List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  log.info("Executing: NEX-T10558")
  log.info("Test that the user is able to create a camera in the 3D UI interface.")

  test = Scene3dCameraCreationTest("NEX-T10558", request, record_xml_attribute)
  try:
    test.checkCameraCreation()
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()

  assert test.exitCode == 0

def main():
  return test_camera_creation_3d_ui(None, None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
