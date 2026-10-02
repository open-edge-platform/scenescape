# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for AprilTag detection in the DL Streamer pipeline.

These tests assert the tags reach MQTT as normal detections.
"""

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

CAMERA_ID = "atag-qcam1"

APRILTAG_CATEGORY = "apriltag"
PERSON_CATEGORY = "person"

EXPECTED_TAGS = {100, 101, 102, 103, 104, 105}


DETECTION_WAIT_S = 90
COLLECT_WINDOW_S = 30
POLL_INTERVAL_S = 0.5


def _apriltag_detections(frame):
  """! Return the AprilTag detections present in a camera frame.

  @param    frame   Decoded DATA_CAMERA payload.
  @return   list of detection dicts under the `apriltag` category.
  """
  return frame.get('objects', {}).get(APRILTAG_CATEGORY, [])


def _collect_frames(tester, camera_id, window_s):
  """! Collect every DATA_CAMERA payload published by `camera_id` over a window.

  @param    tester      Connected ServiceMqttTest instance.
  @param    camera_id   Camera id whose DATA_CAMERA topic is inspected.
  @param    window_s    Seconds to keep collecting before returning.
  @return   list of decoded payloads.
  """
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  end = time.time() + window_s
  while time.time() < end:
    time.sleep(POLL_INTERVAL_S)
  return [
    msg['data'] for msg in tester.get_messages()
    if msg['topic'] == topic and isinstance(msg['data'], dict)
  ]


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
  seen = 0
  while time.time() < end:
    msgs = tester.get_messages()
    for msg in msgs[seen:]:
      if msg['topic'] != topic or not isinstance(msg['data'], dict):
        continue
      if predicate(msg['data']):
        return msg['data']
    seen = len(msgs)
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
    mqtt_tester, CAMERA_ID, lambda f: bool(_apriltag_detections(f)),
    DETECTION_WAIT_S,
  )
  assert frame is not None, (
    f"No AprilTag detection received for {CAMERA_ID} within {DETECTION_WAIT_S}s"
  )

  frames = _collect_frames(mqtt_tester, CAMERA_ID, COLLECT_WINDOW_S)
  tags = set()
  people = 0

  for frame in frames:
    for detection in _apriltag_detections(frame):
      assert detection['category'] == APRILTAG_CATEGORY
      assert 0.0 < detection['confidence'] <= 1.0, (
        f"apriltag confidence out of range: {detection['confidence']}"
      )
      tags.add(detection['tag_id'])
    for detection in frame.get('objects', {}).get(PERSON_CATEGORY, []):
      people += 1
      assert 0.0 < detection['confidence'] <= 1.0

  assert EXPECTED_TAGS <= tags, (
    f"AprilTags never seen on {CAMERA_ID}: {sorted(EXPECTED_TAGS - tags)}"
  )
  assert people > 0, (
    f"No person detections on {CAMERA_ID} within {COLLECT_WINDOW_S}s"
  )

  log.info(
    f"{CAMERA_ID} reported AprilTags {sorted(tags)} and {people} person "
    f"detection(s) across {len(frames)} frames"
  )

  result_recorder.success()
