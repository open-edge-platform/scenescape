#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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

  def verify_calibration_points_exist(self, min_values=20):
    """Check if calibration points exist by verifying if the transforms field has values

    @param min_values  Minimum number of values required (9 for camera pose, 20+ for point correspondences)
    """
    try:
      # The calibration data is stored in the id_transforms hidden field
      transforms_field = self.browser.find_element(By.ID, "id_transforms")
      transforms_value = transforms_field.get_attribute('value')

      if transforms_value and transforms_value.strip():
        values = transforms_value.split(',')
        points_exist = len(values) >= min_values
        log.info(f"Found transforms field with {len(values)} values, points exist: {points_exist} (min required: {min_values})")
        return points_exist
      else:
        log.info("Transforms field is empty")
        return False

    except Exception as e:
      log.error(f"Error checking calibration points: {e}")
      return False

  def checkCalibration3d2dAprilTag(self):
    try:
      assert self.login()

      cam_url_1 = "/cam/calibrate/4"
      cam_url_2 = "/cam/calibrate/5"

      # Open 3D UI
      log.info("Navigate to the 3D Scene detail page.")
      common.navigate_directly_to_page(self.browser, "/scene/detail/302cf49a-97ec-402d-a324-c5077b280b7b/")

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

      log.info("Verify camera pose from 3D calibration (9 values: translation, rotation, scale).")
      has_points = self.verify_calibration_points_exist(min_values=9)
      assert has_points, "No camera pose found after 3D calibration"

      log.info("Press Auto Calibrate of atag-qcam1.")
      self.clickOnElement("auto-autocalibration", delay=WAIT_SEC)

      log.info("Press Save Camera of atag-qcam1.")
      self.clickOnElement("top_save", delay=WAIT_SEC)

      log.info("Verify calibration points after 2D auto-calibration of atag-qcam1.")
      self.navigateDirectlyToPage(cam_url_1) # Page goes back to scene after save
      has_points = self.verify_calibration_points_exist()
      assert has_points, "No calibration points found after 2D auto-calibration"

      # atag-qcam2
      log.info("Manage atag-qcam2.")
      self.navigateDirectlyToPage(cam_url_2)

      log.info("Verify camera pose from 3D calibration (9 values: translation, rotation, scale).")
      has_points = self.verify_calibration_points_exist(min_values=9)
      assert has_points, "No camera pose found after 3D calibration"

      log.info("Press Auto Calibrate of atag-qcam2.")
      self.clickOnElement("auto-autocalibration", delay=WAIT_SEC)

      log.info("Press Save Camera of atag-qcam2.")
      self.clickOnElement("top_save", delay=WAIT_SEC)

      log.info("Verify calibration points after 2D auto-calibration of atag-qcam2.")
      self.navigateDirectlyToPage(cam_url_2) # Page goes back to scene after save
      has_points = self.verify_calibration_points_exist()
      assert has_points, "No calibration points found after 2D auto-calibration"

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
