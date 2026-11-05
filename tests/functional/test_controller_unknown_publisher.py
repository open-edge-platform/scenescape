#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional test: hierarchy messages from an unknown publisher must not
rebuild live scenes.

A DATA_EXTERNAL message without 'source_id' is a child-scene (hierarchy)
publish. When its publisher is neither a known scene nor a remote child, the
Controller drops it; it must not invalidate the scene cache, which would give
every live scene a fresh tracker and reset its tracked object IDs.
"""

import json
import time
import pytest

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

from tests.functional.common_service import ServiceMqttTest
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

FRAME_RATE = 10
CAMERA_ID = "camera1"
UNKNOWN_PUBLISHER_ID = "unknown-hierarchy-publisher"
THING_TYPE = "person"
# Longer than the Controller's FAILURE_RATE_LIMIT_WINDOW_SECS (10 s), so a
# throttled (rather than skipped) invalidation would also show up.
STREAM_S = 15


def _camera_detection():
  return {
    "id": CAMERA_ID,
    "objects": {
      THING_TYPE: [
        {
          "id": 1,
          "category": THING_TYPE,
          "bounding_box": {"x": 0.5, "y": 0.1, "width": 0.2, "height": 0.4},
        }
      ]
    },
    "rate": float(FRAME_RATE),
    "timestamp": get_iso_time(),
  }


def _unknown_hierarchy_message():
  # No 'source_id': routed as a child-scene publish, not an external source.
  return {
    "id": UNKNOWN_PUBLISHER_ID,
    "objects": [],
    "timestamp": get_iso_time(),
  }


def _publish_detections_until_tracked(tester, cam_topic):
  """! Publish camera detections until DATA_REGULATED contains tracked objects.

  @param    tester      ServiceMqttTest instance (connected).
  @param    cam_topic   DATA_CAMERA topic string.
  @return   True if tracked objects were received within MAX_WAIT_S.
  """
  end = time.time() + tester.MAX_WAIT_S
  while time.time() < end:
    tester.publish(cam_topic, json.dumps(_camera_detection()))
    time.sleep(1.0 / FRAME_RATE)
    if tester.has_objects():
      return True
  return False


@pytest.fixture
def mqtt_tester(params):
  """Provide a connected ServiceMqttTest and disconnect it on teardown."""
  h = ServiceMqttTest(params)
  try:
    yield h
  finally:
    h.disconnect()


# TODO: replace the placeholder Zephyr ID with the registered one.
@pytest.mark.test_name("NEX-T00000")
def test_controller_keeps_tracker_while_unknown_publisher_streams(
    result_recorder, scene_uid, mqtt_tester):
  """! Verify that a live scene keeps its tracked object IDs while an unknown
  publisher streams hierarchy messages (DATA_EXTERNAL without 'source_id').

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    scene_uid          UID of the test scene.
  @param    mqtt_tester        Connected ServiceMqttTest fixture.
  """
  cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
  unknown_topic = PubSub.formatTopic(
    PubSub.DATA_EXTERNAL, scene_id=UNKNOWN_PUBLISHER_ID, thing_type=THING_TYPE)

  mqtt_tester.connect([reg_topic])
  assert _publish_detections_until_tracked(mqtt_tester, cam_topic), (
    f"No DATA_REGULATED message with tracked objects received on "
    f"{reg_topic} within {mqtt_tester.MAX_WAIT_S}s"
  )
  ids_before = mqtt_tester.get_tracked_ids()
  mqtt_tester.clear_messages()

  end = time.time() + STREAM_S
  while time.time() < end:
    mqtt_tester.publish(unknown_topic, json.dumps(_unknown_hierarchy_message()))
    mqtt_tester.publish(cam_topic, json.dumps(_camera_detection()))
    time.sleep(1.0 / FRAME_RATE)

  assert mqtt_tester.has_objects(), (
    f"Scene stopped publishing tracked objects on {reg_topic} while "
    f"{UNKNOWN_PUBLISHER_ID} was streaming")
  ids_after = mqtt_tester.get_tracked_ids()
  assert ids_after <= ids_before, (
    f"New tracked object IDs appeared while {UNKNOWN_PUBLISHER_ID} was streaming "
    f"(before={ids_before}, after={ids_after}); the scene tracker was rebuilt")
  log.info("PASS: scene kept its tracked IDs while an unknown publisher streamed")
  result_recorder.success()
