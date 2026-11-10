# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live View previews must stay small and must not delay camera detections.

The browser requests a new Live View frame each time it receives one. This test
repeats that loop against a camera whose source is wider than the preview limit,
and watches the same camera's detections on the same MQTT connection.
"""

import base64
import json
import threading
import time

import cv2
import numpy as np
import pytest

from scene_common.mqtt import PubSub
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  auth=AUTH_CONTROLLER,
)

# queuing-cam1 is 1280x720, wider than the default 960 px Live View limit.
CAMERA_ID = "atag-qcam1"
NATIVE_RESOLUTION = [1280, 720]
PREVIEW_SHAPE = (540, 960)
MAX_PAYLOAD_BYTES = 300 * 1024
# The controller drops detections older than its maxlag (1.0 s).
MAX_DETECTION_GAP = 1.0
FIRST_IMAGE_TIMEOUT = 120
LIVE_VIEW_SECONDS = 20
MIN_IMAGES = 5
RETRY_INTERVAL = 1.0


class LiveViewRecorder:
  """Plays the browser's Live View loop and records images and detections."""

  def __init__(self):
    self.lock = threading.Lock()
    self.images = []
    self.detection_times = []
    self.last_image_time = 0.0
    self.cmd_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=CAMERA_ID)
    self.image_topic = PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id=CAMERA_ID)
    self.data_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)

  def on_connect(self, client, _userdata, _flags, _rc):
    client.subscribe(self.image_topic)
    client.subscribe(self.data_topic)
    client.publish(self.cmd_topic, "getimage")

  def on_image(self, client, _userdata, msg):
    with self.lock:
      self.images.append((len(msg.payload), json.loads(msg.payload)))
      self.last_image_time = time.monotonic()
    client.publish(self.cmd_topic, "getimage")

  def on_detections(self, _client, _userdata, _msg):
    with self.lock:
      self.detection_times.append(time.monotonic())

  def image_count(self):
    with self.lock:
      return len(self.images)

  def seconds_since_last_image(self):
    with self.lock:
      return time.monotonic() - self.last_image_time

  def run_until(self, client, done):
    """Re-request a frame whenever the loop stalls, until done() is true."""
    while not done():
      if self.seconds_since_last_image() > RETRY_INTERVAL:
        client.publish(self.cmd_topic, "getimage")
      time.sleep(0.1)


def decoded_shape(message):
  jpeg = np.frombuffer(base64.b64decode(message["image"]), np.uint8)
  return cv2.imdecode(jpeg, cv2.IMREAD_COLOR).shape[:2]


def largest_gap(times, start, end):
  points = [start] + [t for t in times if start <= t <= end] + [end]
  return max(later - earlier for earlier, later in zip(points, points[1:]))


@pytest.mark.test_name("NEX-T30935")
def test_live_view_preview_is_small_and_does_not_delay_detections(params, result_recorder):
  """! Run the Live View request loop on a 1280x720 camera and check that every
  published preview is downscaled with the native resolution reported, stays
  small, and that detections keep arriving without gaps beyond the controller's maxlag.
  @param    params           Dict of test parameters.
  @param    result_recorder  Fixture recording the Zephyr result.
  """
  recorder = LiveViewRecorder()
  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"])
  client.onConnect = recorder.on_connect
  client.addCallback(recorder.image_topic, recorder.on_image)
  client.addCallback(recorder.data_topic, recorder.on_detections)
  client.connect()
  client.loopStart()

  try:
    deadline = time.monotonic() + FIRST_IMAGE_TIMEOUT
    recorder.run_until(client, lambda: recorder.image_count() > 0 or time.monotonic() > deadline)
    assert recorder.image_count() > 0, "no Live View image received from the pipeline"

    live_start = time.monotonic()
    live_end = live_start + LIVE_VIEW_SECONDS
    recorder.run_until(client, lambda: time.monotonic() >= live_end)
  finally:
    client.loopStop()

  with recorder.lock:
    images = list(recorder.images)
    detection_times = list(recorder.detection_times)
  log.info(f"Received {len(images)} images and {len(detection_times)} detection messages")

  assert len(images) >= MIN_IMAGES
  for size, message in images:
    assert message["id"] == CAMERA_ID
    assert message["resolution"] == NATIVE_RESOLUTION
    assert decoded_shape(message) == PREVIEW_SHAPE
    assert size <= MAX_PAYLOAD_BYTES, f"Live View payload is {size} bytes"

  gap = largest_gap(detection_times, live_start, live_end)
  log.info(f"Largest gap between detections during Live View: {gap:.2f} s")
  assert gap <= MAX_DETECTION_GAP, f"detections stalled for {gap:.2f} s during Live View"

  result_recorder.success()
