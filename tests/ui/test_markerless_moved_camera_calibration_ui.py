#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time

import pytest

import tests.ui.common_ui_test_utils as common
from scene_common.rest_client import RESTClient
from tests.ui import common_markerless as markerless
from tests.ui.browser import Browser
from tests.utils.log import get_logger
from tests.utils.profiles import MARKERLESS
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=MARKERLESS,
  auth=AUTH_CONTROLLER,
)

SCENE_NAME = "markerless_queuing"
OTHER_SCENE_NAME = "markerless_retail"
NATIVE_CAMERA = "atag-qcam2"
MOVED_CAMERA = "retail-camera1"
# The Polycam dataset scans the area seen by the Queuing cameras.
NATIVE_VIDEO = "sample_data/demo_scenes/Queuing/video/qcam2.mp4"
MOVED_VIDEO = "sample_data/demo_scenes/Retail/video/apriltag-cam1.mp4"
SUCCESS_TOAST = f"Finished auto camera calibration for {NATIVE_CAMERA}."
SAVE_TIMEOUT_SEC = 60
EULER = "euler"


def wait_for_saved_pose(rest, camera_uid):
  """! Waits until the camera is stored with the pose the 3D UI saves, an Euler transform."""
  deadline = time.monotonic() + SAVE_TIMEOUT_SEC
  while time.monotonic() < deadline:
    if rest.getCamera(camera_uid)["transform_type"] == EULER:
      return
    time.sleep(1)
  raise AssertionError(f"The calibrated pose of the camera was not saved within {SAVE_TIMEOUT_SEC}s")


@common.mock_display
@pytest.mark.test_name("NEX-T10577")
def test_markerless_moved_camera_calibration_ui(
    polycam_zip, scenescape_env, params, scene_factory, repo_root, result_recorder):
  """
  ## Name
  Auto-calibration when a camera from a different scene is added

  ## Objective
  Verify a Markerless scene auto calibrates and saves a camera that sees the
  scanned area, and reports insufficient matches for a camera moved in from a
  different scene instead of calibrating it.

  ## Labels
  - UI
  - 3D UI
  - Auto Calibration
  - Markerless
  - Negative

  ## Steps
  1. Create a Markerless scene from the Polycam dataset with a camera that sees its area, and register it.
  2. Create a second scene with a camera of its own.
  3. Open the 3D UI of the Markerless scene, auto calibrate its camera and save.
  4. Assert the camera is calibrated in the 3D UI and the new pose is saved.
  5. Move the camera of the second scene into the Markerless scene and open its 3D UI again.
  6. Auto calibrate the moved camera.
  7. Assert the 3D UI reports insufficient matches and the camera is not calibrated.
  """
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), "REST authentication failed"

  log.info("Steps 1-2. Create the Markerless scene, a second scene, and register the dataset")
  other_scene_uid = scene_factory(OTHER_SCENE_NAME, cameras=(MOVED_CAMERA,))["uid"]
  scene_uid = scene_factory(SCENE_NAME, cameras=(NATIVE_CAMERA,), map_image=polycam_zip)["uid"]
  assert rest.getScene(scene_uid)["camera_calibration"] == "Markerless"
  native_uid = rest.getCameras({"name": NATIVE_CAMERA})["results"][0]["uid"]
  moved_uid = rest.getCameras({"name": MOVED_CAMERA})["results"][0]["uid"]
  assert rest.getCamera(moved_uid)["scene"] == other_scene_uid
  assert rest.getCamera(native_uid)["transform_type"] != EULER
  markerless.wait_for_model(scenescape_env)
  markerless.register_scene(params, scene_uid)

  provider = markerless.FrameProvider(params, {
    native_uid: markerless.read_video_frame(os.path.join(repo_root, NATIVE_VIDEO)),
    moved_uid: markerless.read_video_frame(os.path.join(repo_root, MOVED_VIDEO)),
  })
  browser = None
  try:
    provider.start()
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    page = f"/scene/detail/{scene_uid}/"

    log.info("Step 3. Auto calibrate the camera of the scene and save")
    assert common.navigate_directly_to_page(browser, page)
    markerless.wait_for_button_enabled(browser, f"{NATIVE_CAMERA}-auto-calibrate")
    native_before = markerless.camera_position(browser, NATIVE_CAMERA)
    assert native_before, f"Camera '{NATIVE_CAMERA}' is not in the 3D scene graph"
    assert markerless.calibrate_camera(browser, NATIVE_CAMERA) == SUCCESS_TOAST
    markerless.wait_for_button_enabled(browser, f"{NATIVE_CAMERA}-save-camera", SAVE_TIMEOUT_SEC)
    markerless.click_button(browser, f"{NATIVE_CAMERA}-save-camera")

    log.info("Step 4. Check the camera is calibrated and saved")
    assert markerless.camera_position(browser, NATIVE_CAMERA) != native_before
    wait_for_saved_pose(rest, native_uid)

    log.info("Step 5. Move the camera of the second scene into the Markerless scene")
    moved = rest.updateCamera(moved_uid, {"scene": scene_uid})
    assert moved, f"Could not move the camera: {moved.statusCode} {moved.errors}"
    assert common.navigate_directly_to_page(browser, page)

    log.info("Steps 6-7. Auto calibrate the moved camera and check the notification")
    markerless.wait_for_button_enabled(browser, f"{MOVED_CAMERA}-auto-calibrate")
    moved_before = markerless.camera_position(browser, MOVED_CAMERA)
    assert moved_before, f"Camera '{MOVED_CAMERA}' is not in the 3D scene graph"
    assert markerless.calibrate_camera(browser, MOVED_CAMERA) == markerless.WEAK_MATCH_TOAST
    assert markerless.camera_position(browser, MOVED_CAMERA) == moved_before
    assert provider.requested[native_uid].is_set() and provider.requested[moved_uid].is_set()
    result_recorder.success()
  finally:
    provider.stop()
    if browser is not None:
      browser.close()
