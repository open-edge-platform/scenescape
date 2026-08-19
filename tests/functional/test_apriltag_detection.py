# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for AprilTag detection in the DL Streamer pipeline.

These tests assert the tags reach MQTT as normal detections.
"""

import re
import time

import pytest

from scene_common.mqtt import PubSub

from tests.functional.common_service import ServiceMqttTest
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import ATAG_DETECTION

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=ATAG_DETECTION,
  auth=AUTH_CONTROLLER,
)

pytestmark = [pytest.mark.preserve_db]

CAMERA_ID = "atag-qcam1"

APRILTAG_CATEGORY = re.compile(r"^apriltag_(\d+)$")
PERSON_CATEGORY = "person"

DETECTION_WAIT_S = 90
POLL_INTERVAL_S = 0.5


def _apriltag_categories(frame):
  """! Return the AprilTag category names present in a camera frame.

  @param    frame   Decoded DATA_CAMERA payload.
  @return   set of category names matching `apriltag_<id>`.
  """
  return {c for c in frame.get('objects', {}) if APRILTAG_CATEGORY.match(c)}


def _has_apriltag_and_person(frame):
  """! Return True when a camera frame carries both an AprilTag and a person.

  @param    frame   Decoded DATA_CAMERA payload.
  @return   bool
  """
  return bool(_apriltag_categories(frame)) and bool(
    frame.get('objects', {}).get(PERSON_CATEGORY))


def _wait_for_frame(tester, camera_id, predicate, timeout):
  """! Poll collected messages until a frame from `camera_id` satisfies `predicate`.

  @param    tester      Connected ServiceMqttTest instance.
  @param    camera_id   Camera id whose DATA_CAMERA topic is inspected.
  @param    predicate   Callable taking the decoded payload, returning bool.
  @param    timeout     Seconds to wait before giving up.
  @return   The matching payload, or None on timeout.
  """
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  end = time.time() + timeout
  while time.time() < end:
    for msg in tester.get_messages():
      if msg['topic'] != topic or not isinstance(msg['data'], dict):
        continue
      if predicate(msg['data']):
        return msg['data']
    time.sleep(POLL_INTERVAL_S)
  return None


@pytest.fixture
def mqtt_tester(params):
  """! Provide a ServiceMqttTest subscribed to every camera topic.

  @param    params    Connection parameters fixture.
  @return   Connected ServiceMqttTest, disconnected on teardown.
  """
  tester = ServiceMqttTest(params)
  tester.connect([PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id="+")])
  try:
    yield tester
  finally:
    tester.disconnect()


@pytest.mark.test_name("NEX-T17408")
def test_apriltag_detections_published(result_recorder, mqtt_tester):
  """! Verify the pipeline publishes AprilTag detections on DATA_CAMERA.

  @param    result_recorder   Pytest fixture recording test pass/fail.
  @param    mqtt_tester       ServiceMqttTest subscribed to all cameras.
  """
  frame = _wait_for_frame(
    mqtt_tester, CAMERA_ID, _has_apriltag_and_person, DETECTION_WAIT_S,
  )
  assert frame is not None, (
    f"No AprilTag or person detection received for {CAMERA_ID} within {DETECTION_WAIT_S}s"
  )

  categories = _apriltag_categories(frame)
  log.info(f"{CAMERA_ID} reported AprilTag categories: {sorted(categories)}")

  for category in categories:
    for detection in frame['objects'][category]:
      assert detection['category'] == category
      assert 0.0 < detection['confidence'] <= 1.0, (
        f"{category} confidence out of range: {detection['confidence']}"
      )
      box = detection['bounding_box_px']
      assert box['width'] > 0 and box['height'] > 0, (
        f"{category} has a degenerate bounding box: {box}"
      )
      assert box['x'] >= 0 and box['y'] >= 0, (
        f"{category} bounding box starts outside the frame: {box}"
      )

  people = frame['objects'][PERSON_CATEGORY]
  log.info(f"{CAMERA_ID} reported {len(people)} person detection(s)")
  for detection in people:
    assert 0.0 < detection['confidence'] <= 1.0

  result_recorder.success()
