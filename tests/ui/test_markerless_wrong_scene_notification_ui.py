#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import os
import threading
import time

import cv2
import pytest
import requests
from selenium.webdriver.support.ui import WebDriverWait

import tests.ui.common_ui_test_utils as common
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.ui.browser import Browser
from tests.utils.log import get_logger
from tests.utils.profiles import MARKERLESS
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=MARKERLESS,
  auth=AUTH_CONTROLLER,
)

POLYCAM_ZIP_ENV = "POLYCAM_ZIP_PATH"
POLYCAM_ZIP_DEFAULT = "tests/ui/test_media/Polycam.zip"
FOREIGN_FRAME = "tests/ui/test_media/foreign-scene-frame.jpg"
SCENE_NAME = "markerless_scene"
CAMERA_NAME = "markerless_cam"
BUTTON_ID = f"{CAMERA_NAME}-auto-calibrate"
TOAST_ID = f"{CAMERA_NAME}-Calibrate"
EXPECTED_MESSAGE = (
  "Calibration failed: Weak or insufficient matches. "
  "This camera might not belong to this scene."
)
LOG_MESSAGE = "Weak or insufficient matches. This camera might not belong to this scene."
# Registering the keyframes and loading NetVLAD.
REGISTRATION_TIMEOUT_SEC = 900
BUTTON_TIMEOUT_SEC = 600
CALIBRATION_TIMEOUT_SEC = 300
POLL_INTERVAL_SEC = 5

BUTTON_ENABLED_SCRIPT = """
  const button = document.getElementById(arguments[0]);
  if (!button) return false;
  const controller = button.closest(".controller");
  return !(controller && controller.classList.contains("disabled"));
"""

TOAST_TEXT_SCRIPT = """
  const toast = document.getElementById(arguments[0]);
  const text = toast && toast.querySelector(".toast-text-overflow");
  return text ? text.textContent : null;
"""

# The camera is a scene-graph node named after the camera; needs EXPOSE_TEST_HOOKS.
CAMERA_POSITION_SCRIPT = """
  const node = window.__testScene && window.__testScene.getObjectByName(arguments[0]);
  return node ? node.position.toArray() : null;
"""


@pytest.fixture
def polycam_zip(repo_root):
  """! Path of the Polycam dataset, which is too large to keep in the repository."""
  path = os.environ.get(POLYCAM_ZIP_ENV) or os.path.join(repo_root, POLYCAM_ZIP_DEFAULT)
  if not os.path.isfile(path):
    pytest.skip(f"Polycam dataset not found; set {POLYCAM_ZIP_ENV} to its path")
  return path


class FrameProvider:
  """! Stands in for the camera: answers every calibration frame request with one fixed image."""

  def __init__(self, params, camera_uid, image_b64):
    self.camera_uid = camera_uid
    self.image_b64 = image_b64
    self.requested = threading.Event()
    self.pubsub = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                         port=int(params["broker_port"]))

  def on_command(self, _client, _userdata, message):
    if message.payload.decode("utf-8") != "getcalibrationimage":
      return
    self.requested.set()
    topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=self.camera_uid)
    self.pubsub.publish(topic, json.dumps({
      "id": self.camera_uid,
      "timestamp": get_iso_time(),
      "image": self.image_b64,
    }))

  def start(self):
    self.pubsub.connect()
    self.pubsub.addCallback(
      PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=self.camera_uid), self.on_command)
    self.pubsub.loopStart()

  def stop(self):
    self.pubsub.loopStop()
    self.pubsub.disconnect()


def encode_frame(path):
  """! Reads an image and returns it as a base64 JPEG, the format of a camera calibration frame."""
  frame = cv2.imread(path)
  assert frame is not None, f"Cannot read the foreign frame {path}"
  encoded, jpeg = cv2.imencode(".jpg", frame)
  assert encoded, f"Cannot encode the foreign frame {path}"
  return base64.b64encode(jpeg.tobytes()).decode("utf-8")


def register_scene(params, scene_uid):
  """! Registers the Polycam dataset with the autocalibration service and waits until it is done.
  @param    params                  Dict of test parameters.
  @param    scene_uid               UID of the Markerless scene.
  """
  url = f"{params['weburl']}/api/v1/autocalibration/scenes/{scene_uid}/registration"
  verify = params["rootcert"]
  response = requests.post(url, json={}, verify=verify, timeout=60)
  assert response.status_code in (200, 202), \
    f"Scene registration was rejected: {response.status_code} {response.text}"
  deadline = time.monotonic() + REGISTRATION_TIMEOUT_SEC
  while time.monotonic() < deadline:
    body = requests.get(url, verify=verify, timeout=60).json()
    if body.get("status") == "success":
      return
    assert body.get("status") in ("registering", "busy"), f"Scene registration failed: {body}"
    if body.get("status") == "busy":
      body = requests.post(url, json={}, verify=verify, timeout=60).json()
      if body.get("status") == "success":
        return
      assert body.get("status") in ("registering", "busy"), f"Scene registration failed: {body}"
    time.sleep(POLL_INTERVAL_SEC)
  raise AssertionError(f"Scene registration did not finish within {REGISTRATION_TIMEOUT_SEC}s")


def wait_for_calibration_toast(browser):
  """! Waits for the auto calibration toast of the camera to leave its in-progress text.
  @param    browser                 Browser showing the 3D scene.
  @return   str                     Final text of the toast.
  """
  def settled(driver):
    text = driver.execute_script(TOAST_TEXT_SCRIPT, TOAST_ID)
    return text if text and not text.startswith("Performing") else False

  return WebDriverWait(browser, CALIBRATION_TIMEOUT_SEC, POLL_INTERVAL_SEC).until(
    settled, f"No result for the auto calibration of '{CAMERA_NAME}' within "
             f"{CALIBRATION_TIMEOUT_SEC}s")


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
  register_scene(params, scene_uid)

  log.info("Step 3. Serve a frame of a different scene as the camera's calibration frame")
  provider = FrameProvider(params, camera_uid, encode_frame(os.path.join(repo_root, FOREIGN_FRAME)))
  browser = None
  try:
    provider.start()

    log.info("Step 4. Click auto calibrate in the 3D UI")
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.navigate_directly_to_page(browser, f"/scene/detail/{scene_uid}/")
    WebDriverWait(browser, BUTTON_TIMEOUT_SEC, POLL_INTERVAL_SEC).until(
      lambda driver: driver.execute_script(BUTTON_ENABLED_SCRIPT, BUTTON_ID),
      f"Auto calibrate of '{CAMERA_NAME}' was not enabled within {BUTTON_TIMEOUT_SEC}s")
    position_before = browser.execute_script(CAMERA_POSITION_SCRIPT, CAMERA_NAME)
    assert position_before, f"Camera '{CAMERA_NAME}' is not in the 3D scene graph"
    browser.execute_script("document.getElementById(arguments[0]).click();", BUTTON_ID)

    log.info("Step 5. Check the notification in the 3D UI")
    assert wait_for_calibration_toast(browser) == EXPECTED_MESSAGE
    assert provider.requested.is_set(), "The 3D UI never asked the camera for a calibration frame"

    log.info("Step 6. Check the autocalibration log")
    container = f"{scenescape_env.project_name}-autocalibration-1"
    assert LOG_MESSAGE in scenescape_env.docker.container.logs(container), \
      f"'{LOG_MESSAGE}' is missing from the {container} log"

    log.info("Step 7. Check the camera was not moved")
    assert browser.execute_script(CAMERA_POSITION_SCRIPT, CAMERA_NAME) == position_before
    result_recorder.success()
  finally:
    provider.stop()
    if browser is not None:
      browser.close()
