#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.utils.log import get_logger
import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

import numpy as np

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="")

TEST_WAIT_TIME = 5
TEST_SSIM_THRESHOLD = 0.98 # 98% similarity

@pytest.mark.test_name("NEX-T10426")
def test_manual_distortion_controls(params, result_recorder):
  """Distortion coefficients can be unlocked and submitted during manual calibration."""
  browser = None
  try:
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()

    for coefficient in ('k1', 'k2', 'p1', 'p2', 'k3'):
      lock = browser.find_element(By.ID, f'enabled_distortion_{coefficient}')
      field = browser.find_element(By.ID, f'id_distortion_{coefficient}')
      assert lock.is_displayed() and lock.is_selected()
      assert not field.is_enabled()

    distortion_lock = browser.find_element(By.ID, 'enabled_distortion_k1')
    distortion_field = browser.find_element(By.ID, 'id_distortion_k1')
    distortion_lock.click()
    assert distortion_field.is_enabled()
    assert not distortion_field.get_attribute('readonly')
    distortion_field.clear()
    distortion_field.send_keys('0.125')
    assert browser.execute_script(
      "return new FormData(document.getElementById('calibration_form')).get('distortion_k1');"
    ) == '0.125'
    distortion_lock.click()
    assert not distortion_field.is_enabled()
    assert not browser.execute_script(
      "return new FormData(document.getElementById('calibration_form')).has('distortion_k1');"
    )

    diagnostics = browser.execute_script(
      """
      const calibration = window.camera_calibration;
      calibration.camCanvas.clearCalibrationPoints();
      calibration.viewport.clearCalibrationPoints();
      for (let index = 0; index < 5; index++) {
        calibration.camCanvas.addCalibrationPoint(80 + index * 80, 90 + index * 50);
        calibration.viewport.addCalibrationPoint(index, index % 2, 0);
      }
      calibration.camCanvas.drawImage();
      calibration.showCalibrationFitStatus({
        rejectionRequested: true,
        rejectionApplied: true,
        fitPointCount: 4,
        rejectedIndices: [1],
        outlierThresholdPx: 10,
        rmsError: 1.25,
        perPointErrors: [0.5, 12.0, 1.2, 11.1, 0.3],
        geometryWarnings: [
          "Map points form a thin line. On the floor plan, drag them into a wide triangle or rectangle across the visible area — not along one line near the camera — then recheck the fit.",
        ],
      }, ["p0", "p1", "p2", "p3", "p4"]);
      calibration.rejectedPointIndices = [1];
      const appliedSummary = document.getElementById("calibration-fit-summary").textContent;
      const appliedGuidance = document.getElementById(
        "calibration-geometry-warnings").textContent;
      const appliedDetails = document.getElementById("calibration-point-errors").textContent;
      const appliedFitClass = document.getElementById(
        "calibration-fit-status").className;
      const appliedGuidanceClass = document.getElementById(
        "calibration-geometry-guidance").className;
      const guidanceHidden = document.getElementById(
        "calibration-geometry-guidance").hidden;
      const acceptedNames = calibration.getAcceptedCalibrationPointNames(
        calibration.camCanvas.getCalibrationPoints());
      const mapRejected = calibration.viewport.children
        .find((point) => point.name === "calibrationPoint_p1");
      const mapHighError = calibration.viewport.children
        .find((point) => point.name === "calibrationPoint_p3");
      const rejectedHalo = mapRejected.children.find(
        (child) => child.name === "calibrationHalo");
      const highErrorHalo = mapHighError.children.find(
        (child) => child.name === "calibrationHalo");
      const appliedCameraRejected = calibration.camCanvas.calibrationPointDiagnostics.get("p1");
      const appliedCameraHighError = calibration.camCanvas.calibrationPointDiagnostics.get("p3");
      const appliedHaloState = {
        mapPointColor: mapRejected.material.color.getHexString(),
        mapRejectedHaloVisible: rejectedHalo.visible,
        mapRejectedHaloColor: rejectedHalo.material.color.getHexString(),
        mapHighErrorHaloVisible: highErrorHalo.visible,
        mapHighErrorHaloColor: highErrorHalo.material.color.getHexString(),
        legend: document.getElementById("calibration-fit-status").textContent,
      };
      calibration.showCalibrationFitStatus({
        rejectionRequested: true,
        rejectionApplied: false,
        ransacInlierCount: 3,
        fitPointCount: 5,
        rejectedIndices: [1, 3],
        outlierThresholdPx: 10,
        rmsError: 4.25,
        perPointErrors: [0.5, 12.0, 1.2, 11.1, 0.3],
      }, ["p0", "p1", "p2", "p3", "p4"]);
      const fallbackSummary = document.getElementById("calibration-fit-summary").textContent;
      const fallbackDetails = document.getElementById("calibration-point-errors").textContent;
      const fallbackGuidanceHidden = document.getElementById(
        "calibration-geometry-guidance").hidden;
      const fallbackCameraRejected = calibration.camCanvas.calibrationPointDiagnostics.get("p1");
      calibration.clearCalibrationPoints();
      return {
        summary: fallbackSummary,
        appliedSummary,
        appliedGuidance,
        appliedDetails,
        appliedFitClass,
        appliedGuidanceClass,
        guidanceHidden,
        fallbackGuidanceHidden,
        details: fallbackDetails,
        acceptedNames,
        cameraRejected: appliedCameraRejected,
        cameraHighError: appliedCameraHighError,
        fallbackCameraRejected,
        statusHiddenAfterClear: document.getElementById("calibration-diagnostics").hidden,
        rejectedAfterClear: calibration.rejectedPointIndices,
        diagnosticsAfterClear: [
          ...calibration.camCanvas.calibrationPointDiagnostics.keys(),
        ],
        ...appliedHaloState,
      };
      """
    )
    assert "4 of 5 point pairs" in diagnostics["appliedSummary"]
    assert "only 3 usable point pairs" in diagnostics["summary"]
    assert "All 5 pairs were used" in diagnostics["summary"]
    assert "4.25 px" in diagnostics["summary"]
    assert "1 rejected by RANSAC" in diagnostics["appliedSummary"]
    assert "1.25 px" in diagnostics["appliedSummary"]
    # Rejected p1 must not inflate the high-residual count (only p3).
    assert "1 pair(s) have final residuals above 10.0 px" in diagnostics["appliedSummary"]
    assert "thin line" not in diagnostics["appliedSummary"]
    assert "thin line" in diagnostics["appliedGuidance"]
    assert "wide triangle or rectangle" in diagnostics["appliedGuidance"]
    assert diagnostics["guidanceHidden"] is False
    assert "alert-secondary" in diagnostics["appliedFitClass"]
    assert "alert-warning" in diagnostics["appliedGuidanceClass"]
    assert "p1: 12.00 px (rejected by RANSAC)" in diagnostics["appliedDetails"]
    assert "p3: 11.10 px (included, residual above threshold)" in diagnostics["appliedDetails"]
    assert "flagged by RANSAC, included in fallback fit" in diagnostics["details"]
    assert diagnostics["fallbackGuidanceHidden"] is True
    assert diagnostics["acceptedNames"] == ["p0", "p2", "p3", "p4"]
    assert diagnostics["cameraRejected"] == "rejected"
    # Identity color stays green for p1; diagnostic is a red halo instead.
    assert diagnostics["mapPointColor"] == "00ff00"
    assert diagnostics["mapRejectedHaloVisible"] is True
    assert diagnostics["mapRejectedHaloColor"] == "dc3545"
    assert diagnostics["cameraHighError"] == "high-error"
    assert diagnostics["mapHighErrorHaloVisible"] is True
    assert diagnostics["mapHighErrorHaloColor"] == "fd7e14"
    assert diagnostics["fallbackCameraRejected"] == "rejected"
    assert "Red halo" in diagnostics["legend"]
    assert "Orange halo" in diagnostics["legend"]
    assert diagnostics["statusHiddenAfterClear"] is True
    assert diagnostics["rejectedAfterClear"] == []
    assert diagnostics["diagnosticsAfterClear"] == []

    name_sets = browser.execute_script(
      """
      const calibration = window.camera_calibration;
      calibration.camCanvas.clearCalibrationPoints();
      calibration.viewport.clearCalibrationPoints();
      for (let index = 0; index < 6; index++) {
        calibration.camCanvas.addCalibrationPoint(80 + index * 80, 90 + index * 50);
        calibration.viewport.addCalibrationPoint(index, index % 2, 0);
      }
      // Equal counts, but only four shared names (camera keeps p4, map keeps p5).
      calibration.camCanvas.calibrationPoints =
        calibration.camCanvas.calibrationPoints.filter((point) => point.name !== "p5");
      calibration.camCanvas.calibrationPointNames.push("p5");
      const mapP4 = calibration.viewport.children.find(
        (child) => child.name === "calibrationPoint_p4");
      calibration.viewport.remove(mapP4);
      calibration.viewport.calibrationPointNames.push("p4");

      const camPoints = calibration.camCanvas.getCalibrationPoints();
      const mapPoints = calibration.viewport.getCalibrationPoints();
      const mismatchedValid = calibration.isValidCalibration(camPoints, mapPoints);
      let wouldThrowOnSave = false;
      if (mismatchedValid) {
        try {
          Object.keys(camPoints)
            .map((name) => mapPoints[name])
            .map((point) => `${point[0]},${point[1]},${point[2]}`);
        } catch (error) {
          wouldThrowOnSave = true;
        }
      }

      calibration.camCanvas.clearCalibrationPoints();
      calibration.viewport.clearCalibrationPoints();
      for (let index = 0; index < 4; index++) {
        calibration.camCanvas.addCalibrationPoint(80 + index * 80, 90 + index * 50);
        calibration.viewport.addCalibrationPoint(index, index % 2, 0);
      }
      const matchingValid = calibration.isValidCalibration(
        calibration.camCanvas.getCalibrationPoints(),
        calibration.viewport.getCalibrationPoints(),
      );
      return {
        camNames: Object.keys(camPoints).sort(),
        mapNames: Object.keys(mapPoints).sort(),
        mismatchedValid,
        wouldThrowOnSave,
        matchingValid,
      };
      """
    )
    assert name_sets["camNames"] == ["p0", "p1", "p2", "p3", "p4"]
    assert name_sets["mapNames"] == ["p0", "p1", "p2", "p3", "p5"]
    assert name_sets["mismatchedValid"] is False
    assert name_sets["wouldThrowOnSave"] is False
    assert name_sets["matchingValid"] is True
    result_recorder.success()
  finally:
    if browser is not None:
      browser.close()

@pytest.mark.fresh_stack
@pytest.mark.test_name("NEX-T10426")
def test_manual_camera_calibration(params, result_recorder):
  """! Checks that the camera calibration can be set manually and saved.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  browser = None
  try:
    log.info("Executing: NEX-T10426")
    log.info("Test that camera pose can be be set manually")
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    viewport_dimensions = browser.execute_script("return [window.innerWidth, window.innerHeight];")

    overlay_opacity = browser.find_element(By.ID, 'overlay_opacity')
    location = overlay_opacity.location
    size = overlay_opacity.size
    element_bottom_y = location['y'] + size['height']

    current_viewport_height = 2000
    required_height = element_bottom_y + 50

    if required_height > current_viewport_height:
      browser.setViewportSize(viewport_dimensions[0], required_height)
    else:
      browser.setViewportSize(viewport_dimensions[0], current_viewport_height)

    slider_width = overlay_opacity.size['width']
    desired_offset = int(slider_width * 0.8)

    slider_action = browser.actionChains()
    slider_action.move_to_element_with_offset(overlay_opacity, 1, 1) \
             .click_and_hold() \
             .move_by_offset(desired_offset, 0) \
             .release() \
             .perform()

    cam_values_init = common.get_calibration_points(browser, 'camera')
    map_values_init = common.get_calibration_points(browser, 'map')

    initial_cam_x = cam_values_init[0][0]
    initial_map_x = map_values_init[0][0]
    log.info("Take_screenshot before manual calibration")
    assert common.render_calibration_preview(browser, 'initial-id_transforms')
    camera_view_before = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_before = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_before = common.get_element_screenshot(camera_view_before)
    map_pic_before = common.get_element_screenshot(map_view_before)
    log.info("Screenshot taken before manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Change calibration settings")
    assert common.change_cam_calibration(browser, initial_cam_x * 2, initial_map_x * 10)
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_cam_calibration(browser, cam_values_init[0], map_values_init[0])
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after saving manual calibration")
    assert common.render_calibration_preview(browser, 'initial-id_transforms')
    camera_view_after = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_after = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_after = common.get_element_screenshot(camera_view_after)
    map_pic_after = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after saving manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Revert to initial calibration settings")
    assert common.change_cam_calibration(browser, initial_cam_x, initial_map_x)
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_calibration_initialization(browser, [cam_values_init[0]], [map_values_init[0]])
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    browser.find_element(By.ID, 'cam_calibrate_1').click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after reverting to the previous calibration settings")
    assert common.render_calibration_preview(browser, 'initial-id_transforms')
    camera_view_after = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_after = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_after_revert = common.get_element_screenshot(camera_view_after)
    map_pic_after_revert = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after reverting to the previous calibration setting")

    log.info("Validating of difference in screenshots after calibration")

    assert not np.array_equal(cam_pic_before, cam_pic_after), \
    "Expected camera images to be different, but they are the same"
    assert not np.array_equal(map_pic_before, map_pic_after), \
    "Expected map images to be different, but they are the same"

    cropped_cam_before, cropped_cam_after_revert = common.crop_to_common_shape(cam_pic_before, cam_pic_after_revert)
    cropped_map_before, cropped_map_after_revert = common.crop_to_common_shape(map_pic_before, map_pic_after_revert)

    ssim_cam = common.get_images_similarity(cropped_cam_before, cropped_cam_after_revert)
    ssim_map = common.get_images_similarity(cropped_map_before, cropped_map_after_revert)

    assert ssim_cam >= TEST_SSIM_THRESHOLD
    assert ssim_map >= TEST_SSIM_THRESHOLD

    result_recorder.success()
  finally:
    if browser is not None:
      browser.close()
