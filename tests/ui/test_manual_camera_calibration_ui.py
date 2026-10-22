#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.utils.log import get_logger
import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

import numpy as np

from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="")

TEST_WAIT_TIME = 5
TEST_SSIM_THRESHOLD = 0.98 # 98% similarity

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

    assert browser.execute_script("""
      const prototype = Object.getPrototypeOf(window.camera_calibration);
      const calibration = Object.create(prototype);
      let matrix;
      const points = {p0: [0, 0], p1: [1, 0], p2: [1, 1], p3: [0, 1]};
      calibration.camCanvas = {
        calibrationUpdated: true,
        getCalibrationPoints: () => points,
        getImageSize: () => [1280, 720],
        updateImageSrc: () => {},
      };
      calibration.viewport = {
        sceneScale: 100,
        scaleFactor: 0.5,
        calibrationUpdated: true,
        getCalibrationPoints: () => points,
        setCameraPose: (pose) => { matrix = pose; },
      };
      calibration.isResolutionUpdated = true;
      const response = {poseMatrix: [
        [1, 0, 0, 120], [0, -1, 0, 60], [0, 0, -1, 80], [0, 0, 0, 1],
      ]};
      if (!calibration.applyFittedCalibrationPose(response)) return false;
      const translation = matrix.elements.slice(12, 15);
      if (translation.some((v, i) => Math.abs(v - [2.4, 1.2, 1.6][i]) > 1e-9))
        return false;
      if (calibration.isResolutionUpdated || calibration.camCanvas.calibrationUpdated ||
          calibration.viewport.calibrationUpdated) return false;
      let requests = 0;
      calibration.calibrationFitState = "ready";
      calibration.calculateCalibrationIntrinsics = () => { requests++; };
      calibration.getCameraPositionAndRotation = () => {
        throw new Error("Video updates must not overwrite the API-fitted pose");
      };
      calibration.projectImage = () => {};
      const intrinsics = [[1000, 0, 640], [0, 1000, 360], [0, 0, 1]];
      calibration.updateCalibrationViews("", intrinsics, [0, 0, 0, 0, 0]);
      if (requests !== 0) return false;
      calibration.viewport.calibrationUpdated = true;
      calibration.updateCalibrationViews("", intrinsics, [0, 0, 0, 0, 0]);
      if (requests !== 1) return false;
      calibration.calibrationFitState = "pending";
      calibration.updateCalibrationViews("", intrinsics, [0, 0, 0, 0, 0]);
      return requests === 1;
    """), "Calibration pose scale or video-update handoff is inconsistent"

    log.info("Verify distortion coefficient lock controls")
    for coefficient in ('k1', 'k2', 'p1', 'p2', 'k3'):
      lock = browser.find_element(By.ID, f'enabled_distortion_{coefficient}')
      field = browser.find_element(By.ID, f'id_distortion_{coefficient}')
      assert lock.is_displayed() and lock.is_selected()
      assert not field.is_enabled()

    distortion_lock = browser.find_element(By.ID, 'enabled_distortion_k1')
    distortion_field = browser.find_element(By.ID, 'id_distortion_k1')
    distortion_lock.click()
    assert distortion_field.is_enabled()
    distortion_field.clear()
    distortion_field.send_keys('0.125')
    assert distortion_field.get_attribute('value') == '0.125'
    distortion_lock.click()
    assert not distortion_field.is_enabled()

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
