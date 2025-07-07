#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import time
import tests.ui.common_ui_test_utils as common
from scene_common import log
from tests.ui import UserInterfaceTest
from tests.ui.browser import By, NoSuchElementException, WebDriverException

TEST_NAME = "NEX-T10475"
WAIT_SEC = 1

class Scene3dUserInterfaceTest(UserInterfaceTest):
  ELEM_STATS_PANEL = "panel-stats"
  ELEM_3D_CTL_PANEL = "panel-3d-controls"
  ELEM_SCENE_CTL_PANEL = "scene-controls-3d"

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']

    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    return

  def togglePanel(self, panel_id: str, hide: bool) -> bool:
    """! To toggle show/hide specified panel.
    @param    panel_id                 HTML element ID for the panel.
    @param    hide                     True to hide panel.
    @return   BOOL                     Boolean representing success status.
    """
    status = False

    if hide:
      str_script = "document.getElementById('{0}').style.display = 'none';".format(panel_id)
    else:
      str_script = "document.getElementById('{0}').style.removeProperty('display');".format(panel_id)

    try:
      self.executeScript(str_script)
      status = ("display: none" in self.findElement(By.ID, panel_id).get_attribute('style')) == hide
    except NoSuchElementException:
      log.error("Element #{0} not found!".format(panel_id))
    except WebDriverException:
      log.error("Browser error: {0}".format(str_script))

    return status

  def captureScreenshot(self):
    # Hide control panels and stats box
    assert self.togglePanel(self.ELEM_STATS_PANEL, True)
    assert self.togglePanel(self.ELEM_3D_CTL_PANEL, True)
    time.sleep(WAIT_SEC)
    cap = self.getPageScreenshot()

    # Show 3D control panel again for interaction
    assert self.togglePanel(self.ELEM_3D_CTL_PANEL, False)

    return cap

  def checkSceneCameraToggle(self):
    try:
      assert self.login()

      log.info("Navigate to the Scene detail page.")
      common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

      log.info("Expand camera1 controls")
      # Use camera panel loaded to detect 3D components loaded on page
      self.clickOnElement("camera1-control-panel", delay=100)

      log.info("Take initial 3D screenshot")
      # Screenshot is taken after camera panel is expanded due to camera control on 3D plane will be highlighted after expanding the specific camera panel
      screen_3d = self.captureScreenshot()

      log.info("Toggle camera1 scene camera")
      self.clickOnElement("camera1-scene-camera", delay=10)

      log.info("Take screenshot after toggled to show camera scene")
      screen_scene_camera = self.captureScreenshot()

      log.info("Check if inital 3D screenshot is different from screenshot taken after scene camera toggled")
      assert common.compare_images(screen_3d, screen_scene_camera, 50)

      log.info("Toggle scene camera again (to turn off scene camera and return to 3D plane view)")
      self.clickOnElement("camera1-scene-camera", delay=10)

      log.info("Take 3D plane screenshot")
      screen_3d_2 = self.captureScreenshot()

      log.info("Check if initial 3D screenshot taken before toggle is identical to screenshot after re-toggle (for scene camera turned off)")
      assert not common.compare_images(screen_3d, screen_3d_2, 0.0)

      log.info("Check scene camera view on camera2 to make sure the view is not only locked on to single camera")
      self.clickOnElement("camera2-control-panel", delay=100)
      self.clickOnElement("camera2-scene-camera", delay=10)
      screen_scene_camera_2 = self.captureScreenshot()
      assert common.compare_images(screen_scene_camera, screen_scene_camera_2, 30)

      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

@common.mock_display
def test_switch_3d_camera_scene_camera(request, record_xml_attribute):
  """! Test toggle scene camera under 3D camera control.
  @param    request                 List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  log.info("Executing: " + TEST_NAME)
  log.info("Test to switch between 3d scene camera view")

  test = Scene3dUserInterfaceTest(TEST_NAME, request, record_xml_attribute)
  test.checkSceneCameraToggle()

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_switch_3d_camera_scene_camera(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
