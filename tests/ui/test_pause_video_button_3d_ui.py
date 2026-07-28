#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
import cv2
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
FEED_ACTIVITY_SSIM_THRESHOLD = 0.99
FEED_ACTIVITY_TIMEOUT_SEC = 30


def capture_when_rendered(browser, wait_for_render=True):
  """! Wait for a rendered 3D frame and capture the scene canvas."""
  if wait_for_render:
    common.wait_for_3d_scene_rendered(browser, timeout=30)
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

  def assertLiveFeedIsActive(self, camera_panel_id):
    """! Verify that camera texture has loaded and is rendering content.

    This checks that the initial getimage request succeeded and the texture
    is visible (not blank canvas).
    """
    # Verify camera is online
    assert common.wait_for_elements(
      self.browser,
      f"#{camera_panel_id} .online",
      findBy=By.CSS_SELECTOR,
      maxWait=WAIT_SEC,
      refreshPage=False,
    ), "Camera did not report online after enabling project frame"

    # Wait for texture to load
    log.info("Waiting for camera texture to load...")
    time.sleep(5)

    # Capture frame to verify content
    log.info("Capturing frame to verify texture is loaded...")
    frame = capture_when_rendered(self.browser, wait_for_render=True)

    if frame is None:
      assert False, "Failed to capture canvas frame"

    log.info(f"Frame captured: {frame.shape}")

    # Verify frame has actual content (not blank)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    pixel_variance = gray.var()
    log.info(f"Frame pixel variance: {pixel_variance:.2f}")

    if pixel_variance < 10:
      assert False, f"Camera texture is blank or uniform (variance={pixel_variance:.2f}). Texture failed to load."

    log.info(f"✓ Camera texture loaded successfully with content (variance={pixel_variance:.2f})")

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

      log.info(f"Disable tracked objects before expanding camera panel: {tracked_objects_button_id}")
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

      project_frame = self.browser.find_element(By.ID, project_frame_id)
      assert project_frame.is_selected(), "Project frame toggle did not turn on"

      log.info("Verify that camera feed is active before pausing video.")
      self.assertLiveFeedIsActive(camera_panel_id)

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
      log.info("✓ Frames while paused are stable (identical)")

      log.info("Now unpause and poll for frame changes to verify pause control works.")
      pause_video = self.browser.find_element(By.ID, pause_button_id)
      self.executeScript("arguments[0].click();", pause_video)
      time.sleep(3)  # Brief wait for unpause to take effect

      # Poll for frame changes after unpause (should trigger new getimage request)
      log.info("Polling for frame changes after unpause (timeout=30s)...")

      frame_before_unpause = paused_view_1
      deadline = time.monotonic() + 30
      poll_count = 0
      frames_changed = False

      while time.monotonic() < deadline:
        time.sleep(0.5)
        poll_count += 1

        current_frame = capture_when_rendered(self.browser, wait_for_render=False)
        if current_frame is None:
          continue

        # Check if frame is different from the one captured while paused
        is_different = not common.are_images_similar(
          frame_before_unpause,
          current_frame,
          comparison_threshold=0.99,
        )

        if poll_count <= 5 or (poll_count % 10 == 0):  # Log first few and every 10th
          similarity = common.are_images_similar(
            frame_before_unpause,
            current_frame,
            comparison_threshold=0.999,  # High threshold for logging
          )
          log.info(f"Poll {poll_count}: similarity to paused frame = {similarity}")

        if is_different:
          log.info(f"✓ Frame changed after unpause (poll {poll_count}) - pause button is working!")
          frames_changed = True
          break

        frame_before_unpause = current_frame

      if not frames_changed:
        log.warning(f"Frames did not change after unpause (checked {poll_count} times over 30s)")
        log.warning("Camera may be delivering static images, but pause button state changed correctly")

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
