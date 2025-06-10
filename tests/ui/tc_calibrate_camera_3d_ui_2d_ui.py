#!/usr/bin/env python3

# Copyright (C) 2024 Intel Corporation
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
import tests.ui.common_ui_test_utils as common
from scene_common import log
from tests.ui import UserInterfaceTest
from tests.ui.browser import By

TEST_NAME = "NEX-T10562"
WAIT_SEC = 100

class Scene3dUserInterfaceTest(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    return

  def checkCalibration3d2dAprilTag(self):
    try:
      assert self.login()

      aprilTagMsg="2D Camera Calibration has been disabled because camera transform is now in euler. Click Reset Points to calibrate the camera here."
      cam_url_1 = "/cam/calibrate/4"
      cam_url_2 = "/cam/calibrate/5"

      # Open 3D UI
      log.info("Navigate to the 3D Scene detail page.")
      common.navigate_directly_to_page(self.browser, "/scene/detail/2/")

      # 3D UI
      # atag-qcam1
      log.info("Expand atag-qcam1 controls.")
      self.clickOnElement("atag-qcam1-control-panel", delay=WAIT_SEC)

      log.info("Press auto calibrate button of atag-qcam1.")
      self.clickOnElement("lil-gui-name-29", delay=WAIT_SEC)

      log.info("Press save button of atag-qcam1.")
      self.clickOnElement("atag-qcam1-save-camera", delay=WAIT_SEC)

      # atag-qcam2
      log.info("Expand atag-qcam2 controls.")
      self.clickOnElement("atag-qcam2-control-panel", delay=WAIT_SEC)

      log.info("Press auto calibrate button of atag-qcam2.")
      self.clickOnElement("lil-gui-name-54", delay=WAIT_SEC)

      log.info("Press save button of atag-qcam2.")
      self.clickOnElement("atag-qcam2-save-camera", delay=WAIT_SEC)

      # Open 2D UI
      log.info("Navigate to the 2D Scene detail page.")
      self.clickOnElement("scene-detail-button", delay=WAIT_SEC)

      # 2D UI
      # atag-qcam1
      log.info("Manage atag-qcam1.")
      self.navigateDirectlyToPage(cam_url_1)

      log.info("Check calibrate-info message is equal.")
      aprilTagMsgByElem = self.browser.find_element(By.ID, "calibrate-info").text
      assert aprilTagMsgByElem == aprilTagMsg

      log.info("Press Reset Points of atag-qcam1.")
      self.clickOnElement("reset_points", delay=WAIT_SEC)

      log.info("Press Auto Calibrate of atag-qcam1.")
      self.clickOnElement("auto-camcalibration", delay=WAIT_SEC)

      log.info("Press Save Camera of atag-qcam1.")
      self.clickOnElement("top_save", delay=WAIT_SEC)

      self.navigateDirectlyToPage(cam_url_1)
      log.info("Check calibrate-info message is different.")
      aprilTagMsgByElem = self.browser.find_element(By.ID, "calibrate-info").text
      assert aprilTagMsgByElem != aprilTagMsg

      log.info("Press Save Camera of atag-qcam1.")
      self.clickOnElement("top_save", delay=WAIT_SEC)

      # atag-qcam2
      log.info("Manage atag-qcam2.")
      self.navigateDirectlyToPage(cam_url_2)

      log.info("Check calibrate-info message is equal.")
      aprilTagMsgByElem = self.browser.find_element(By.ID, "calibrate-info").text
      assert aprilTagMsgByElem == aprilTagMsg

      log.info("Press Reset Points of atag-qcam2.")
      self.clickOnElement("reset_points", delay=WAIT_SEC)

      log.info("Press Auto Calibrate of atag-qcam2.")
      self.clickOnElement("auto-camcalibration", delay=WAIT_SEC)

      log.info("Press Save Camera of atag-qcam2.")
      self.clickOnElement("top_save", delay=WAIT_SEC)

      self.navigateDirectlyToPage(cam_url_2)
      log.info("Check calibrate-info message is different.")
      aprilTagMsgByElem = self.browser.find_element(By.ID, "calibrate-info").text
      assert aprilTagMsgByElem != aprilTagMsg

      log.info("Press Save Camera of atag-qcam2.")
      self.clickOnElement("top_save", delay=WAIT_SEC)

      self.exitCode = 0
    finally:
      self.recordTestResult()
    return

@common.mock_display
def test_calibrate_camera_3d_ui_2d_ui(request, record_xml_attribute):
  """! Test to calibrate camera in 3D first and calibrate again camera in 2D using April Tag.
  @param    request                 List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  log.info("Executing: " + TEST_NAME)
  log.info("Test to calibrate camera in 3D first and calibrate again camera in 2D using April Tag.")

  test = Scene3dUserInterfaceTest(TEST_NAME, request, record_xml_attribute)
  test.checkCalibration3d2dAprilTag()

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_calibrate_camera_3d_ui_2d_ui(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
