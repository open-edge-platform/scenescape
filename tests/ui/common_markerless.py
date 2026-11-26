#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for the markerless (Polycam) auto calibration UI tests."""

import base64
import json
import threading
import time

import cv2
import requests
from selenium.webdriver.support.ui import WebDriverWait

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

POLYCAM_ZIP_ENV = "POLYCAM_ZIP_PATH"
POLYCAM_ZIP_DEFAULT = "tests/ui/test_media/Polycam.zip"
WEAK_MATCH_TOAST = (
  "Calibration failed: Weak or insufficient matches. "
  "This camera might not belong to this scene."
)
WEAK_MATCH_LOG = "Weak or insufficient matches. This camera might not belong to this scene."
# Registering the keyframes and loading NetVLAD run on CPU in the test stack.
REGISTRATION_TIMEOUT_SEC = 900
MODEL_TIMEOUT_SEC = 900
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

# The camera pose is on the sceneCamera of the scene-graph node named after the camera;
# needs EXPOSE_TEST_HOOKS.
CAMERA_POSITION_SCRIPT = """
  const node = window.__testScene && window.__testScene.getObjectByName(arguments[0]);
  return node && node.sceneCamera ? node.sceneCamera.position.toArray() : null;
"""


class FrameProvider:
  """! Stands in for the cameras: answers each calibration frame request with its camera's image."""

  def __init__(self, params, frames):
    """! @param frames  Dict of camera uid to the base64 JPEG served as its calibration frame."""
    self.frames = frames
    self.requested = {uid: threading.Event() for uid in frames}
    self.pubsub = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                         port=int(params["broker_port"]))

  def on_command(self, _client, _userdata, message):
    if message.payload.decode("utf-8") != "getcalibrationimage":
      return
    camera_uid = PubSub.parseTopic(message.topic)["camera_id"]
    self.requested[camera_uid].set()
    topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera_uid)
    self.pubsub.publish(topic, json.dumps({
      "id": camera_uid,
      "timestamp": get_iso_time(),
      "image": self.frames[camera_uid],
    }))

  def start(self):
    self.pubsub.connect()
    for camera_uid in self.frames:
      self.pubsub.addCallback(
        PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera_uid), self.on_command)
    self.pubsub.loopStart()

  def stop(self):
    self.pubsub.loopStop()
    self.pubsub.disconnect()


def encode_image(frame):
  """! Returns a BGR image as a base64 JPEG, the format of a camera calibration frame."""
  encoded, jpeg = cv2.imencode(".jpg", frame)
  assert encoded, "Cannot encode the calibration frame"
  return base64.b64encode(jpeg.tobytes()).decode("utf-8")


def read_image(path):
  """! Reads an image file as a base64 JPEG."""
  frame = cv2.imread(path)
  assert frame is not None, f"Cannot read the image {path}"
  return encode_image(frame)


def read_video_frame(path, position=0.5):
  """! Reads one frame of a video, as a base64 JPEG.
  @param    position                Where in the video to take it, from 0 to 1.
  """
  capture = cv2.VideoCapture(path)
  capture.set(cv2.CAP_PROP_POS_FRAMES, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) * position))
  read, frame = capture.read()
  capture.release()
  assert read, f"Cannot read a frame of {path}"
  return encode_image(frame)


def wait_for_model(scenescape_env, timeout=MODEL_TIMEOUT_SEC):
  """! Waits until the NetVLAD download container has finished; it runs alongside the stack."""
  container = f"{scenescape_env.project_name}-autocalibration-model-init-1"
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    state = scenescape_env.docker.container.inspect(container).state
    if not state.running and state.status != "created":
      assert state.exit_code == 0, f"The NetVLAD download failed, see the {container} log"
      return
    time.sleep(POLL_INTERVAL_SEC)
  raise AssertionError(f"The NetVLAD model was not downloaded within {timeout}s")


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


def wait_for_button_enabled(browser, button_id, timeout=BUTTON_TIMEOUT_SEC):
  """! Waits until a control of the 3D UI panel exists and is not disabled."""
  WebDriverWait(browser, timeout, POLL_INTERVAL_SEC).until(
    lambda driver: driver.execute_script(BUTTON_ENABLED_SCRIPT, button_id),
    f"'{button_id}' was not enabled within {timeout}s")


def click_button(browser, button_id):
  """! Clicks a 3D UI control by script, since its panel folder may be collapsed."""
  browser.execute_script("document.getElementById(arguments[0]).click();", button_id)


def camera_position(browser, camera_name):
  """! Position of a camera in the 3D scene graph, or None when it is not there."""
  return browser.execute_script(CAMERA_POSITION_SCRIPT, camera_name)


def calibrate_camera(browser, camera_name):
  """! Clicks auto calibrate of a camera and returns the final text of its toast.
  @param    browser                 Browser showing the 3D scene.
  @param    camera_name             Name of the camera whose panel is clicked.
  """
  wait_for_button_enabled(browser, f"{camera_name}-auto-calibrate")
  click_button(browser, f"{camera_name}-auto-calibrate")

  def settled(driver):
    text = driver.execute_script(TOAST_TEXT_SCRIPT, f"{camera_name}-Calibrate")
    return text if text and not text.startswith("Performing") else False

  return WebDriverWait(browser, CALIBRATION_TIMEOUT_SEC, POLL_INTERVAL_SEC).until(
    settled, f"No result for the auto calibration of '{camera_name}' within "
             f"{CALIBRATION_TIMEOUT_SEC}s")
