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
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  require_password=True, auth="",
)

WAIT_SEC = 10
PANEL_WAIT_SEC = 100
FEED_ACTIVITY_WAIT_SEC = 2
FEED_ACTIVITY_SSIM_THRESHOLD = 0.995


def capture_when_rendered(browser):
  """! Wait for a rendered 3D frame and capture the scene canvas."""
  assert common.wait_for_3d_scene_rendered(browser)
  return common.capture_3d_canvas(browser)


class Scene3dUserInterfaceTest(UserInterfaceTest):
  BROWSER_WEBGL = True

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    return

  def getCameraPanelIds(self):
    panels = self.browser.find_elements(By.CSS_SELECTOR, "[id$='-control-panel']")
    return [panel.get_attribute("id") for panel in panels]

  def getPrimaryCameraPanelId(self):
    assert common.wait_for_elements(
      self.browser,
      "tracked-objects-button",
      findBy=By.ID,
      maxWait=PANEL_WAIT_SEC,
      refreshPage=False,
    ), "3D controls did not load (tracked-objects toggle missing)"

    assert common.wait_for_elements(
      self.browser,
      "[id$='-control-panel']",
      findBy=By.CSS_SELECTOR,
      maxWait=PANEL_WAIT_SEC,
      refreshPage=False,
    ), "No pre-existing camera control panels were rendered in 3D UI"

    camera_panel_ids = sorted(
      panel_id for panel_id in self.getCameraPanelIds()
      if panel_id and panel_id != "new-camera-control-panel"
    )

    log.info(f"Detected camera control panels: {camera_panel_ids}")
    assert camera_panel_ids, "No camera control panels were found"
    return camera_panel_ids[0]

  def assertLiveFeedIsActive(self):
    """! Ensure camera feed is updating before validating pause behavior."""
    frame_before = capture_when_rendered(self.browser)
    time.sleep(FEED_ACTIVITY_WAIT_SEC)
    frame_after = capture_when_rendered(self.browser)
    assert not common.are_images_similar(
      frame_before,
      frame_after,
      comparison_threshold=FEED_ACTIVITY_SSIM_THRESHOLD,
    ), "No active camera feed detected before pausing video"

  def checkPauseVideoButton(self):
    try:
      assert self.login()

      log.info("Navigate to the Scene detail page.")
      common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

      log.info("Get camera control panel and pause video button IDs.")
      camera_panel_id = self.getPrimaryCameraPanelId()

      camera_name = camera_panel_id.removesuffix("-control-panel")
      project_frame_id = f"{camera_name}-project-frame"
      pause_button_id = f"{camera_name}-pause-video"
      tracked_objects_button_id = "tracked-objects-button"

      log.info(f"Disable tracked objects drawing: {tracked_objects_button_id}")
      tracked_objects_widget = self.browser.find_element(By.ID, tracked_objects_button_id)
      tracked_objects_input = tracked_objects_widget.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
      if tracked_objects_input.is_selected():
        self.executeScript("arguments[0].click();", tracked_objects_widget)
        time.sleep(WAIT_SEC)

      tracked_objects_input = tracked_objects_widget.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
      assert not tracked_objects_input.is_selected(), "Tracked objects toggle did not turn off"

      log.info(f"Expand camera control panel: {camera_panel_id}")
      self.clickOnElement(camera_panel_id, delay=PANEL_WAIT_SEC)
      time.sleep(WAIT_SEC)

      log.info(f"Enable project frame before pausing video: {project_frame_id}")
      self.clickOnElement(project_frame_id, delay=WAIT_SEC)
      time.sleep(WAIT_SEC)

      log.info("Verify that camera feed is active before pausing video.")
      self.assertLiveFeedIsActive()

      pause_video = self.browser.find_element(By.ID, pause_button_id)
      selected_before = pause_video.is_selected()
      log.info(f"Pause video control reached (selected_before={selected_before})")

      self.clickOnElement(pause_button_id, delay=WAIT_SEC)
      time.sleep(WAIT_SEC)

      pause_video = self.browser.find_element(By.ID, pause_button_id)
      selected_after = pause_video.is_selected()
      log.info(f"Pause video control clicked (selected_after={selected_after})")
      assert selected_before != selected_after, "Pause video toggle state did not change"

      log.info("Capture screenshot after pausing video and verify it stays stable.")
      paused_view_1 = capture_when_rendered(self.browser)
      time.sleep(WAIT_SEC)
      paused_view_2 = capture_when_rendered(self.browser)
      assert common.are_images_similar(paused_view_1, paused_view_2), "Paused camera view changed unexpectedly"

      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

@pytest.mark.fresh_stack
@common.mock_display
@pytest.mark.test_name("NEX-T10482")
def test_pause_video_button_3d_ui(scenescape_env, request, record_xml_attribute):
  """! Test the toggle "pause video" works as expected.
  @param    request                 List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  log.info("Executing: NEX-T10482")
  log.info("Test the toggle 'pause video' works as expected.")

  test = Scene3dUserInterfaceTest("NEX-T10482", request, record_xml_attribute)
  try:
    test.checkPauseVideoButton()
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()

  assert test.exitCode == 0

def main():
  return test_pause_video_button_3d_ui(None, None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
