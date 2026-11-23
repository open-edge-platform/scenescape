# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""AprilTags must be detectable in the calibration frames DLStreamer publishes.

DLStreamer answers a localize command with a base64 camera frame and the camera
intrinsics, the input autocalibration solves a camera pose from. This test plays
that consumer role against the live Queuing pipeline: it decodes the frame and
detects the AprilTags in it with the autocalibration detector settings.
"""

import base64
import json
import queue
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from dt_apriltags import Detector

from scene_common.mqtt import PubSub
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  auth=AUTH_CONTROLLER,
)

CAMERA_ID = "atag-qcam1"
# atag-qcam1 intrinsics from the Queuing scene, as a camera matrix.
INTRINSICS = [[905, 0, 640], [0, 905, 360], [0, 0, 1]]
# Still frame of the same camera; its tags are the ones visible in the live video.
REFERENCE_FRAME = "tests/ui/test_media/atag-qcam1-frame.png"
# Autocalibration cannot solve a camera pose from fewer tags.
MIN_APRILTAG_COUNT = 4
FRAME_TIMEOUT = 120
RETRY_INTERVAL = 1.0
MAX_FRAMES = 10


def make_detector():
  # Mirrors CameraCalibrationApriltag in autocalibration/src/atag_camera_calibration.py.
  return Detector(families="tag36h11", nthreads=1, quad_decimate=1.0, quad_sigma=0.0,
                  refine_edges=1, decode_sharpening=0.25, debug=0)


def detect_tag_ids(detector, image):
  gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
  return {tag.tag_id for tag in detector.detect(gray)}


def decode_frame(message):
  data = np.frombuffer(base64.b64decode(message["image"], validate=True), np.uint8)
  return cv2.imdecode(data, cv2.IMREAD_COLOR)


def request_frame(client, frames):
  """Ask DLStreamer for a calibration frame, re-asking until one arrives."""
  cmd_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=CAMERA_ID)
  # Unlike getcalibrationimage, localize makes DLStreamer return the intrinsics with the frame.
  command = json.dumps({"command": "localize", "payload_intrinsics": INTRINSICS})
  deadline = time.monotonic() + FRAME_TIMEOUT
  while time.monotonic() < deadline:
    client.publish(cmd_topic, command)
    try:
      return frames.get(timeout=RETRY_INTERVAL)
    except queue.Empty:
      continue
  return None


@pytest.mark.test_name("NEX-T17408")
def test_apriltags_detected_in_dlstreamer_calibration_frame(params, repo_root, result_recorder):
  """! Request calibration frames from DLStreamer for atag-qcam1, check that each
  carries the camera intrinsics, decode its base64 image and check that every
  AprilTag visible to the camera is detected.
  @param    params           Dict of test parameters.
  @param    repo_root        Repository root path.
  @param    result_recorder  Fixture recording the Zephyr result.
  """
  detector = make_detector()
  reference = cv2.imread(str(Path(repo_root) / REFERENCE_FRAME))
  assert reference is not None, f"cannot read {REFERENCE_FRAME}"
  expected_ids = detect_tag_ids(detector, reference)
  assert len(expected_ids) >= MIN_APRILTAG_COUNT, (
    f"reference frame shows only {len(expected_ids)} AprilTags")

  frames = queue.Queue()
  image_topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=CAMERA_ID)

  def on_connect(client, _userdata, _flags, _rc):
    client.subscribe(image_topic)

  def on_frame(_client, _userdata, msg):
    frames.put(json.loads(msg.payload))

  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"])
  client.onConnect = on_connect
  client.addCallback(image_topic, on_frame)
  client.connect()
  client.loopStart()

  best_ids = set()
  try:
    for _ in range(MAX_FRAMES):
      message = request_frame(client, frames)
      assert message is not None, "no calibration frame received from DLStreamer"
      assert message["id"] == CAMERA_ID
      assert message.get("calibrate") is True
      assert message.get("intrinsics") == INTRINSICS, (
        f"calibration frame carries intrinsics {message.get('intrinsics')}, expected {INTRINSICS}")
      image = decode_frame(message)
      assert image is not None, "calibration frame is not a decodable image"
      assert message["resolution"] == [image.shape[1], image.shape[0]]

      found_ids = detect_tag_ids(detector, image)
      log.info(f"Detected AprilTags {sorted(found_ids)}, expected {sorted(expected_ids)}")
      if len(found_ids & expected_ids) > len(best_ids & expected_ids):
        best_ids = found_ids
      if expected_ids <= found_ids:
        break
  finally:
    client.loopStop()

  missing = expected_ids - best_ids
  assert not missing, f"AprilTags {sorted(missing)} not detected in any of {MAX_FRAMES} frames"
  result_recorder.success()
