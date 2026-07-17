#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for the Scene Controller standalone MQTT event flow.

Covers:
  - Controller publishes tracked objects on DATA_REGULATED when detections
    arrive on DATA_CAMERA.
  - Controller resets its tracker (assigns fresh object IDs) after a scene
    update arrives via CMD_DATABASE.
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


def _detection(camera_id, with_objects=True):
  payload = {
    "id": camera_id,
    "objects": {},
    "rate": float(FRAME_RATE),
    "timestamp": get_iso_time(),
  }
  if with_objects:
    payload["objects"] = {
      "person": [
        {
          "id": 1,
          "category": "person",
          "bounding_box": {"x": 0.5, "y": 0.1, "width": 0.2, "height": 0.4},
        }
      ]
    }
  return payload


def _publish_detections_until_tracked(tester, cam_topic):
  """! Publish camera detections until DATA_REGULATED contains
  tracked objects, or the wait timeout expires.

  @param    tester      ServiceMqttTest instance (connected).
  @param    cam_topic   DATA_CAMERA topic string.
  @return   True if tracked objects were received within MAX_WAIT_S, False on timeout.
  """
  end = time.time() + tester.MAX_WAIT_S
  while time.time() < end:
    tester.publish(cam_topic, json.dumps(_detection(CAMERA_ID)))
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


@pytest.mark.test_name("NEX-T12595")
def test_controller_publishes_tracking_on_detection(
    result_recorder, scene_uid, mqtt_tester):
  """! Verify that the Controller service publishes tracked objects on
  DATA_REGULATED when a detection is sent on DATA_CAMERA.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    scene_uid          UID of the test scene.
  @param    mqtt_tester        Connected ServiceMqttTest fixture.
  """
  cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  mqtt_tester.connect([reg_topic])
  ctrl_up = _publish_detections_until_tracked(mqtt_tester, cam_topic)
  assert ctrl_up, (
    f"No DATA_REGULATED message with tracked objects received on "
    f"{reg_topic} within {mqtt_tester.MAX_WAIT_S}s"
  )
  log.info("PASS: controller published tracking output on DATA_REGULATED")
  result_recorder.success()


@pytest.mark.test_name("NEX-T22793")
def test_controller_creates_tracker_after_scene_update(
    result_recorder, rest, scene_uid, mqtt_tester):
  """! Verify that the Controller creates a new tracker for a scene after
  receiving an 'update' message on CMD_DATABASE.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    rest               Authenticated RESTClient fixture.
  @param    scene_uid          UID of the test scene.
  @param    mqtt_tester        Connected ServiceMqttTest fixture.
  """
  cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  original_res = rest.getScenes({'id': scene_uid})
  assert original_res['count'] > 0, f"Scene uid={scene_uid} not found"
  original_name = original_res['results'][0]['name']

  try:
    mqtt_tester.connect([reg_topic])

    ctrl_up = _publish_detections_until_tracked(mqtt_tester, cam_topic)
    assert ctrl_up, (
      f"No DATA_REGULATED message with tracked objects received on "
      f"{reg_topic} within {mqtt_tester.MAX_WAIT_S}s"
    )

    ids_before = mqtt_tester.get_tracked_ids()
    res = rest.updateScene(scene_uid, {'name': original_name + "-modified"})
    assert res.statusCode == 200, f"Failed to update scene: {res.errors}"
    log.info(
      f"Updated scene uid={scene_uid} via REST, waiting for tracking to resume")
    mqtt_tester.clear_messages()

    resumed = _publish_detections_until_tracked(mqtt_tester, cam_topic)
    assert resumed, (
      f"No DATA_REGULATED message with tracked objects received on "
      f"{reg_topic} within {mqtt_tester.MAX_WAIT_S}s after scene REST update"
    )

    ids_after = mqtt_tester.get_tracked_ids()
    assert ids_before.isdisjoint(ids_after), (
      f"Tracked object IDs overlap before and after scene update "
      f"(before={ids_before}, after={ids_after}); tracker may not have been reset"
    )
    log.info(
      "PASS: controller resumed tracking with fresh IDs after scene REST update")
    result_recorder.success()
  finally:
    try:
      rest.updateScene(scene_uid, {'name': original_name})
    except Exception as exc:
      log.warning(f"Failed to restore scene name: {exc}")
