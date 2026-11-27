#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

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

FOREIGN_FRAME = "tests/ui/test_media/foreign-scene-frame.jpg"
SCENE_NAME = "markerless_scene"
CAMERA_NAME = "markerless_cam"


@common.mock_display
@pytest.mark.test_name("NEX-T10578")
def test_markerless_wrong_scene_notification_ui(
    polycam_zip, scenescape_env, params, scene_factory, repo_root, result_recorder):
  """
  ## Name
  Notify the user when a camera from a different scene is auto calibrated

  ## Objective
  Verify the system informs the user that an auto calibration attempted with a
  camera from a different scene might not belong to the scene, instead of
  silently returning a poor localization. Retrieval from the Polycam dataset
  finds weak or no matches for such a camera.

  ## Labels
  - UI
  - 3D UI
  - Auto Calibration
  - Markerless
  - Negative

  ## Steps
  1. Create a scene with the Polycam dataset as its map, so its calibration type is Markerless.
  2. Register the dataset with the autocalibration service and wait until it is processed.
  3. Add a camera to the scene and make its calibration frame an image of a different scene.
  4. Open the 3D UI of the scene and click auto calibrate under the camera settings.
  5. Assert the 3D UI reports that the camera might not belong to this scene.
  6. Assert the autocalibration log has the same error.
  7. Assert the camera was not moved by the failed calibration.
  """
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), "REST authentication failed"

  log.info("Step 1. Create the Markerless scene")
  scene_uid = scene_factory(SCENE_NAME, cameras=(CAMERA_NAME,), map_image=polycam_zip)["uid"]
  scene = rest.getScene(scene_uid)
  assert scene["camera_calibration"] == "Markerless", \
    f"Scene calibration type is '{scene['camera_calibration']}', not Markerless"
  camera_uid = rest.getCameras({"name": CAMERA_NAME})["results"][0]["uid"]

  log.info("Step 2. Register the Polycam dataset")
  markerless.wait_for_model(scenescape_env)
  markerless.register_scene(params, scene_uid)

  log.info("Step 3. Serve a frame of a different scene as the camera's calibration frame")
  provider = markerless.FrameProvider(
    params, {camera_uid: markerless.read_image(os.path.join(repo_root, FOREIGN_FRAME))})
  browser = None
  try:
    provider.start()

    log.info("Step 4. Click auto calibrate in the 3D UI")
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.navigate_directly_to_page(browser, f"/scene/detail/{scene_uid}/")
    markerless.wait_for_button_enabled(browser, f"{CAMERA_NAME}-auto-calibrate")
    position_before = markerless.camera_position(browser, CAMERA_NAME)
    assert position_before, f"Camera '{CAMERA_NAME}' is not in the 3D scene graph"

    log.info("Step 5. Check the notification in the 3D UI")
    assert markerless.calibrate_camera(browser, CAMERA_NAME) == markerless.WEAK_MATCH_TOAST
    assert provider.requested[camera_uid].is_set(), \
      "The 3D UI never asked the camera for a calibration frame"

    log.info("Step 6. Check the autocalibration log")
    container = f"{scenescape_env.project_name}-autocalibration-1"
    assert markerless.WEAK_MATCH_LOG in scenescape_env.docker.container.logs(container), \
      f"'{markerless.WEAK_MATCH_LOG}' is missing from the {container} log"

    log.info("Step 7. Check the camera was not moved")
    assert markerless.camera_position(browser, CAMERA_NAME) == position_before
    result_recorder.success()
  finally:
    provider.stop()
    if browser is not None:
      browser.close()
