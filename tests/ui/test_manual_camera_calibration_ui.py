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

@common.mock_display
@pytest.mark.test_name("NEX-T10426")
def test_manual_camera_calibration(demo_scene, params, result_recorder):
  """! Checks that the camera calibration can be set manually and saved.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  browser = None
  try:
    log.info("Executing: NEX-T10426")
    log.info("Test that camera pose can be be set manually")
    browser = Browser(headless=False, webgl=True)
    assert common.check_page_login(browser, params), "Login failed"
    assert common.check_db_status(browser), "Database is not ready"

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    common.camera_calibrate_link(browser).click()
    time.sleep(TEST_WAIT_TIME)
    assert browser.execute_script("return Boolean(window.camera_calibration?.viewport);"), \
      "Calibration page did not initialise its 3D viewport (is WebGL available?)"

    # The calibration helpers write to the live form, so both checks run on a detached clone.
    pose_handoff = browser.execute_script("""
      const originalForm = document.getElementById("calibration_form");
      const form = originalForm.cloneNode(true);
      originalForm.parentNode.replaceChild(form, originalForm);
      const resolutionField = document.getElementById("detected_resolution");
      const detectedResolution = resolutionField.value;
      try {
        const calibration = new window.camera_calibration.constructor();
        let matrix;
        const points = {p0: [0, 0], p1: [1, 0], p2: [1, 1], p3: [0, 1]};
        calibration.camCanvas = {
          calibrationUpdated: true,
          getCalibrationPoints: () => points,
          getImageSize: () => [1280, 720],
          updateImageSrc: (image, onLoad) => onLoad(),
        };
        calibration.viewport = {
          sceneScale: 100,
          scaleFactor: 0.5,
          calibrationUpdated: true,
          projectionCamera: {matrix: null, updateMatrix() {}},
          getCalibrationPoints: () => points,
          setCameraPose(pose) {
            matrix = pose;
            this.projectionCamera.matrix = pose;
          },
        };
        $("#id_width").val(1280);
        $("#id_height").val(720);
        $("#id_intrinsics_cx").val(640);
        $("#id_intrinsics_cy").val(360);
        calibration.isResolutionUpdated = true;
        calibration.resolutionNeedsRefit = true;
        const response = {poseMatrix: [
          [1, 0, 0, 120], [0, -1, 0, 60], [0, 0, -1, 80], [0, 0, 0, 1],
        ]};
        if (!calibration.applyFittedCalibrationPose(response))
          return "API-fitted pose was rejected";
        const isExpectedTranslation = (elements) => elements.slice(12, 15)
          .every((v, i) => Math.abs(v - [2.4, 1.2, 1.6][i]) < 1e-9);
        if (!isExpectedTranslation(matrix.elements))
          return "API-fitted pose translation was not converted to metres";
        const remembered = calibration.calibrationPoseMatrix;
        if (!remembered || remembered === matrix ||
            !isExpectedTranslation(remembered.elements))
          return "API-fitted pose was not remembered as the calibration pose";
        if (!calibration.isResolutionUpdated || calibration.resolutionNeedsRefit ||
            calibration.camCanvas.calibrationUpdated ||
            calibration.viewport.calibrationUpdated)
          return "API-fitted pose did not clear the refit flags";

        let requests = 0;
        calibration.calibrationFitState = "ready";
        calibration.calculateCalibrationIntrinsics = () => { requests++; };
        calibration.getCameraPositionAndRotation = () => {
          throw new Error("Video updates must not overwrite the API-fitted pose");
        };
        calibration.projectImage = () => {};
        const updateFrame = () => calibration.updateCalibrationViews(
          "", [[1000, 0, 640], [0, 1000, 360], [0, 0, 1]], [0, 0, 0, 0, 0]);
        updateFrame();
        if (requests !== 0) return "Video frame refit an unchanged calibration";
        calibration.viewport.calibrationUpdated = true;
        updateFrame();
        if (requests !== 1) return "Video frame did not refit a moved calibration point";
        for (const state of ["pending", "failed", "stale"]) {
          calibration.calibrationFitState = state;
          updateFrame();
          if (requests !== 1) return `Video frame refit while the fit was ${state}`;
        }
        return "ok";
      } finally {
        form.parentNode.replaceChild(originalForm, form);
        resolutionField.value = detectedResolution;
      }
    """)
    assert pose_handoff == "ok", f"Calibration pose / video-update handoff: {pose_handoff}"

    principal_point_save = browser.execute_script("""
      const originalForm = document.getElementById("calibration_form");
      const form = originalForm.cloneNode(true);
      originalForm.parentNode.replaceChild(form, originalForm);
      const originalAlert = window.alert;
      try {
        const calibration = new window.camera_calibration.constructor();
        const camPoints = {p0: [0, 0], p1: [1, 0], p2: [1, 1], p3: [0, 1]};
        const mapPoints = {p0: [0, 0, 0], p1: [1, 0, 0], p2: [1, 1, 0], p3: [0, 1, 0]};
        let imageSize;
        calibration.camCanvas = {
          getCalibrationPoints: () => camPoints,
          getImageSize: () => imageSize,
        };
        calibration.viewport = {
          sceneScale: 100,
          scaleFactor: 0.5,
          projectionCamera: {matrix: null, updateMatrix() {}},
          getCalibrationPoints: () => mapPoints,
          setCameraPose(pose) { this.projectionCamera.matrix = pose; },
        };
        calibration.setupSaveCameraButton();
        let submitted;
        const alerts = [];
        form.submit = () => { submitted = new FormData(form); };
        window.alert = (message) => { alerts.push(message); };
        const save = (fitState) => {
          submitted = null;
          alerts.length = 0;
          calibration.calibrationFitState = fitState;
          $(form).triggerHandler("submit");
        };
        const width = form.querySelector("#id_width");
        const height = form.querySelector("#id_height");
        const cx = form.querySelector("#id_intrinsics_cx");
        const cy = form.querySelector("#id_intrinsics_cy");
        for (const [w, h] of [[640, 480], [1280, 720]]) {
          const label = `${w}x${h}`;
          const resized = w !== 640;
          width.value = 640;
          height.value = 480;
          cx.value = 320;
          cy.value = 240;
          cx.disabled = cy.disabled = true;
          imageSize = [w, h];
          calibration.isResolutionUpdated = calibration.resolutionNeedsRefit = false;
          const cameraMatrix = [[800, 0, 320], [0, 800, 240], [0, 0, 1]];
          if (!calibration.centerManualIntrinsics(cameraMatrix))
            return `${label}: image size rejected`;
          if (calibration.resolutionNeedsRefit !== resized)
            return `${label}: resolutionNeedsRefit=${calibration.resolutionNeedsRefit}`;
          if (cameraMatrix[0][2] !== w / 2 || cameraMatrix[1][2] !== h / 2)
            return `${label}: preview principal point not centred`;
          if (!calibration.applyFittedCalibrationPose({poseMatrix: [
            [1, 0, 0, 120], [0, -1, 0, 60], [0, 0, -1, 80], [0, 0, 0, 1],
          ]})) return `${label}: API-fitted pose was rejected`;
          if (calibration.resolutionNeedsRefit ||
              calibration.isResolutionUpdated !== resized)
            return `${label}: fit did not keep the resolution change for Save`;
          if (!cx.disabled || !cy.disabled)
            return `${label}: principal point became editable before Save`;
          save("stale");
          if (submitted || alerts.length !== 1)
            return `${label}: Save was not blocked by a stale fit`;
          save("ready");
          if (!submitted) return `${label}: Save did not submit (${alerts.join("; ")})`;
          if (alerts.length) return `${label}: unexpected alert: ${alerts[0]}`;
          const expected = {width: w, height: h, intrinsics_cx: w / 2, intrinsics_cy: h / 2};
          for (const [name, value] of Object.entries(expected)) {
            if (submitted.get(name) !== String(value))
              return `${label}: submitted ${name}=${submitted.get(name)}, expected ${value}`;
          }
        }
        return "ok";
      } finally {
        window.alert = originalAlert;
        $(form).off();
        form.parentNode.replaceChild(originalForm, form);
      }
    """)
    assert principal_point_save == "ok", \
      f"Save must submit the image resolution and centred principal point: {principal_point_save}"

    log.info("Verify distortion coefficient lock controls")
    for coefficient in ('k1', 'k2', 'p1', 'p2', 'k3'):
      lock = browser.find_element(By.ID, f'enabled_distortion_{coefficient}')
      field = browser.find_element(By.ID, f'id_distortion_{coefficient}')
      assert lock.is_displayed() and lock.is_selected(), f"{coefficient} lock is not shown checked"
      assert not field.is_enabled(), f"{coefficient} is editable while locked"

    distortion_lock = browser.find_element(By.ID, 'enabled_distortion_k1')
    distortion_field = browser.find_element(By.ID, 'id_distortion_k1')
    distortion_lock.click()
    assert distortion_field.is_enabled(), "k1 is not editable after unlocking"
    distortion_field.clear()
    distortion_field.send_keys('0.125')
    assert distortion_field.get_attribute('value') == '0.125', "k1 did not accept a typed value"
    distortion_lock.click()
    assert not distortion_field.is_enabled(), "k1 is editable after re-locking"

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
    assert cam_values_init, "Could not read the stored camera calibration points"
    assert map_values_init, "Could not read the stored map calibration points"

    initial_cam_x = cam_values_init[0][0]
    initial_map_x = map_values_init[0][0]
    log.info("Take_screenshot before manual calibration")
    assert common.render_calibration_preview(browser, 'initial-id_transforms'), \
      "Could not render the initial calibration preview"
    camera_view_before = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_before = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_before = common.get_element_screenshot(camera_view_before)
    map_pic_before = common.get_element_screenshot(map_view_before)
    log.info("Screenshot taken before manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Change calibration settings")
    assert common.change_cam_calibration(browser, initial_cam_x * 2, initial_map_x * 10), \
      "Could not change and save the camera calibration"
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_cam_calibration(browser, cam_values_init[0], map_values_init[0]), \
      "Changed calibration points were not persisted"
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    common.camera_calibrate_link(browser).click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after saving manual calibration")
    assert common.render_calibration_preview(browser, 'initial-id_transforms'), \
      "Could not render the changed calibration preview"
    camera_view_after = browser.find_element(By.ID, 'camera_img_canvas')
    map_view_after = browser.find_element(By.ID, 'map_canvas_3D')
    cam_pic_after = common.get_element_screenshot(camera_view_after)
    map_pic_after = common.get_element_screenshot(map_view_after)
    log.info("Screenshot taken after saving manual calibration")
    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")

    log.info("Revert to initial calibration settings")
    assert common.change_cam_calibration(browser, initial_cam_x, initial_map_x), \
      "Could not revert and save the camera calibration"
    log.info("Calibrating Camera...Saving Camera...")
    assert common.check_calibration_initialization(browser, [cam_values_init[0]], [map_values_init[0]]), \
      "Reverted calibration points were not persisted"
    log.info("Calibration Saved")

    common.navigate_directly_to_page(browser, f"/{common.TEST_SCENE_ID}/")
    common.camera_calibrate_link(browser).click()
    time.sleep(TEST_WAIT_TIME)

    log.info("Take_screenshot after reverting to the previous calibration settings")
    assert common.render_calibration_preview(browser, 'initial-id_transforms'), \
      "Could not render the reverted calibration preview"
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

    assert ssim_cam >= TEST_SSIM_THRESHOLD, f"Camera view SSIM after revert {ssim_cam:.3f} < {TEST_SSIM_THRESHOLD}"
    assert ssim_map >= TEST_SSIM_THRESHOLD, f"Map view SSIM after revert {ssim_map:.3f} < {TEST_SSIM_THRESHOLD}"

    result_recorder.success()
  finally:
    if browser is not None:
      browser.close()
