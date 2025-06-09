#!/usr/bin/env python3

# Copyright (C) 2023-2024 Intel Corporation
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

from scene_common import log
import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest

POSITION_THRESHOLD = 0.001
ROTATION_THRESHOLD = 0.001
TEST_NAME = "NEX-T10473"
WAIT_SEC = 3

class WillOurShipGo(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

  def setUpCalibrationTest(self):
    """! Sets up the scene for testing the 3D UI calibration by navigating to the page,
    disabling the stats, tracked objects, and video playback, and enabling the project frame
    """
    # Navigate to 3D UI page
    self.navigateDirectlyToPage(f"/scene/detail/{common.TEST_SCENE_ID}/")
    time.sleep(WAIT_SEC)

    # Hide scene stats monitor
    self.toggleElementDisplay("stats", False, waitTime=WAIT_SEC)

    # Disable tracked objects
    self.clickOnElement("tracked-objects-button", waitTime=WAIT_SEC)

    # Expand camera 1 menu
    self.clickOnElement("camera1-control-panel", waitTime=WAIT_SEC, delay=100)

    # Toggle project frame for camera 1
    self.clickOnElement("camera1-project-frame", waitTime=WAIT_SEC)

    # Pause the video feed
    self.clickOnElement("camera1-pause-video", waitTime=WAIT_SEC)

  def getCameraPose(self, cameraName):
    """! Gets the pose values for the specified camera
    @param     cameraName    name of the camera to get pose values for
    @return    pos, rot      position and rotation for all three axes
    """
    camera_pose = [
      float(
        self.browser.find_element(
          self.By.ID, f"{cameraName}-{item}").
        get_attribute("value"))
      for item in ["posX", "posY", "posZ", "rotX", "rotY", "rotZ"]
    ]

    return camera_pose[:3], camera_pose[3:]

  def singleClick3DScene(self, xOffset: int = 0, yOffset: int = 0,
                         resetPosition: bool = False, waitTime: int = 1) -> None:
    """! Single click the scene at specified offset from current position
    @param    xOffset          Offset from current x postition
    @param    yOffset          Offset from current y postition
    @param    resetPosition    Reset position to the previous location if True
    @param    waitTime        Time to wait after performing action (in seconds)
    """
    action = self.browser.actionChains()
    action.move_by_offset(xOffset, yOffset).click().pause(waitTime).perform()
    if resetPosition:
      action.move_by_offset(xOffset * -1, yOffset * -1).perform()

  def doubleClick3DScene(self, xOffset: int = 0, yOffset: int = 0,
                         resetPosition: bool = False, waitTime: int = 1) -> None:
    """! Double click the scene at specified offset from current position
    @param    xOffset          Offset from current x postition
    @param    yOffset          Offset from current y postition
    @param    resetPosition    Reset position to the previous location if True
    @param    waitTime         Time to wait after performing action (in seconds)
    """
    action = self.browser.actionChains()
    action.move_by_offset(xOffset, yOffset).double_click().pause(waitTime).perform()
    if resetPosition:
      action.move_by_offset(xOffset * -1, yOffset * -1).perform()

  def clickAndDrag3DScene(self, xOffset: int = 0, yOffset: int = 0,
                          dragBack: bool = False, waitTime: int = 1) -> None:
    """! Click and drag to specified offset from current position
    @param    xOffset     Offset from current x postition
    @param    yOffset     Offset from current y postition
    @param    dragBack    Click and drag back to original position if True
    @param    waitTime    Time to wait after performing action (in seconds)
    """
    self.browser.actionChains().click_and_hold().move_by_offset(
      xOffset, yOffset).release().pause(waitTime).perform()
    if dragBack:
      self.browser.actionChains().click_and_hold().move_by_offset(
        xOffset * -1, yOffset * -1).release().pause(waitTime).perform()

  def rightClick3DScene(self, xOffset: int = 0, yOffset: int = 0,
                        waitTime: int = 1) -> None:
    """! Right click the scene at specified offset from current position
    @param    xOffset     Offset from current x postition
    @param    yOffset     Offset from current y postition
    @param    waitTime    Time to wait after performing action (in seconds)
    """
    self.browser.actionChains().move_by_offset(
      xOffset, yOffset).context_click().pause(waitTime).perform()

  def comparePoses(self, p1, p2, r1, r2, pThreshold=POSITION_THRESHOLD,
                        rThreshold=ROTATION_THRESHOLD) -> bool:
    """! Compares the position and rotation values and returns false if they are
    significantly different.
    @param       p1                         First position to compare
    @param       p2                         Second position to compare
    @param       r1                         First set of rotation values to compare
    @param       r2                         Second set of rotation values to compare
    @param       pThreshold                Maximum acceptable difference between p values
    @param       rThreshold                Maximum acceptable difference between r values
    @returns     (pResult and rResult)    Returns True if both values within treshold
    """
    print(f"p1: {p1}\np2: {p2}\nr1: {r1}\nr2: {r2}")
    pResult = all(abs(p1_i - p2_i) < pThreshold for (p1_i, p2_i) in zip(p1, p2))
    rResult = all((abs(180 - ((180 - r1_i + r2_i) % 360)))
                   < rThreshold for (r1_i, r2_i) in zip(r1, r2))
    return (pResult and rResult)

  def compareImageRegion(self, image1, image2, xMin=250, xMax=450, yMin=150, yMax=350):
    """! Checks if a region in an image matches another image
    @param    image1    The first image to compare
    @param    image2    The second image to compare
    @param    xMin      Minimum x value of region
    @param    yMin      Minimum y value of region
    @param    xMax      Maximum x value of region
    @param    yMax      Maximum y value of region
    """
    assert not self.compareImages(
      image1[yMin: yMax, xMin: xMax, :], image2[yMin: yMax, xMin: xMax, :], 0)

  def checkForMalfunctions(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      assert self.login()
      assert self.checkDbStatus()

      self.setUpCalibrationTest()

      ss_base = self.getPageScreenshot()

      log.info("Create 1st 3D calibration point")
      self.doubleClick3DScene(400, 300)

      log.info("Check that 1st point is added")
      ss_one_point = self.getPageScreenshot()
      assert self.compareImages(ss_base, ss_one_point, 0)

      log.info("Remove 3D calibration point")
      self.rightClick3DScene()

      log.info("Check that 3D calibration point is removed")
      ss_remove_point = self.getPageScreenshot()
      assert not self.compareImages(ss_base, ss_remove_point, 0)

      log.info("Re-add the calibration point")
      self.doubleClick3DScene()

      log.info("Check that 3D calibration point is re-added")
      ss_readd_point = self.getPageScreenshot()
      assert not self.compareImages(ss_one_point, ss_readd_point, 0)

      log.info("Check dragging with 1st point does not change frame")
      self.clickAndDrag3DScene(-50, 0, dragBack=True)
      ss_drag_one_point = self.getPageScreenshot()
      assert not self.compareImages(ss_one_point, ss_drag_one_point, 0)

      log.info("Add 2nd calibration point")
      self.doubleClick3DScene(-100, 0)

      log.info("Check that 2nd point is added")
      ss_two_points = self.getPageScreenshot()
      assert self.compareImages(ss_one_point, ss_two_points, 0)

      log.info("Check dragging with 2nd point does not change frame")
      self.clickAndDrag3DScene(0, -50, dragBack=True)
      ss_drag_two_points = self.getPageScreenshot()
      assert not self.compareImages(ss_two_points, ss_drag_two_points, 0)

      log.info("Add 3rd calibration point")
      self.doubleClick3DScene(0, -100)

      log.info("Check that 3rd point is added")
      ss_three_points = self.getPageScreenshot()
      assert self.compareImages(ss_two_points, ss_three_points, 0)

      log.info("Check dragging with 3rd point does not change frame")
      self.clickAndDrag3DScene(50, 0, dragBack=True)
      ss_drag_three_points = self.getPageScreenshot()
      assert not self.compareImages(ss_three_points, ss_drag_three_points, 0)

      log.info("Add 4th calibration point")
      self.doubleClick3DScene(100, 0)

      log.info("Check that 4th point is added")
      ss_four_points = self.getPageScreenshot()
      assert self.compareImages(ss_three_points, ss_four_points, 0)

      log.info("Check adding 5th calibration point is not possible")
      self.doubleClick3DScene(0, -50, resetPosition=True)
      ss_five_points = self.getPageScreenshot()
      assert not self.compareImages(ss_four_points, ss_five_points, 0)

      log.info("Check toggling calibration points visibility off hides points")
      self.clickOnElement("camera1-calibration", waitTime=WAIT_SEC)
      ss_disable_visibility = self.getPageScreenshot()
      self.compareImageRegion(ss_base, ss_disable_visibility)

      log.info("Check toggling calibration points visibility on shows points")
      self.clickOnElement("camera1-calibration", waitTime=WAIT_SEC)
      ss_enable_visibility = self.getPageScreenshot()
      self.compareImageRegion(ss_four_points, ss_enable_visibility)

      log.info("Check closing camera tab hides points")
      self.clickOnElement("camera1-control-panel", waitTime=WAIT_SEC)
      ss_close_camera_tab = self.getPageScreenshot()
      self.compareImageRegion(ss_base, ss_close_camera_tab)

      log.info("Check re-opening camera tab reveals points")
      self.clickOnElement("camera1-control-panel", waitTime=WAIT_SEC)
      ss_reopen_camera_tab = self.getPageScreenshot()
      self.compareImageRegion(ss_four_points, ss_reopen_camera_tab)

      log.info("Check dragging calibration point to side changes camera pose")
      position_initial, rotation_initial = self.getCameraPose("camera1")
      self.clickAndDrag3DScene(0, 50)
      ss_drag_four_points = self.getPageScreenshot()
      position_dragged, rotation_dragged = self.getCameraPose("camera1")
      assert not self.comparePoses(
        position_initial, position_dragged, rotation_initial, rotation_dragged)
      assert self.compareImages(ss_four_points, ss_drag_four_points, 0)

      log.info("Check returning to original point preserves camera pose")
      self.clickAndDrag3DScene(0, -50)
      position_final, rotation_final = self.getCameraPose("camera1")
      ss_drag_four_points_return = self.getPageScreenshot()
      assert not self.compareImages(ss_four_points, ss_drag_four_points_return, 1)
      assert self.comparePoses(
        position_initial, position_final, rotation_initial, rotation_final)

      self.exitCode = 0
    finally:
      self.browser.close()
      self.recordTestResult()
    return

@common.mock_display
def test_3d_ui_calibration(request, record_xml_attribute):
  """! Test the 3D UI calibration points.
  @param    request                 Pytest request object with test parameters
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_3d_ui_calibration(None, None)


if __name__ == '__main__':
  os._exit(main() or 0)
