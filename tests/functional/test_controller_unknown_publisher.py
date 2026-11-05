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


@pytest.mark.test_name("NEX-T31118")
def test_controller_keeps_tracker_while_unknown_publisher_streams(
    result_recorder, scene_uid, mqtt_tester):
  """
  ## Name
  Controller Keeps Tracker While Unknown Publisher Streams

  ## Objective
  Verify that a running scene keeps the IDs of the objects it is tracking while an unknown publisher (neither a known scene nor a child scene) sends scene-hierarchy MQTT messages to the Controller. The Controller must drop these messages without rebuilding the scene tracker, which would reset the tracked object IDs.

  ## Labels
  - Functional

  ## Steps
  1. Start the full stack with a scene that has the camera `camera1`, and connect an MQTT client to the broker as the Controller user
  2. Subscribe to the scene's regulated data topic (`scenescape/regulated/scene/<scene_uid>`)
  3. Publish a person detection for `camera1` on its camera data topic (`scenescape/data/camera/camera1`) every 0.1 s until the regulated topic reports a tracked object
  4. Note the IDs of the tracked objects and discard the messages received so far
  5. For 15 s (longer than the Controller's 10 s failure rate limit window), publish every 0.1 s both the same camera detection and a hierarchy message from the unknown publisher `unknown-hierarchy-publisher` on `scenescape/external/unknown-hierarchy-publisher/person`; the hierarchy message has no `source_id` field and an empty `objects` list
  6. Verify the regulated topic still reports tracked objects during this period
  7. Verify the tracked object IDs seen in step 6 are all among those noted in step 4, i.e. no new IDs were assigned because the scene tracker was not rebuilt
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
