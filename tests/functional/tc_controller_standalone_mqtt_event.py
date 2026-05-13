#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Microservices needed for test:
#   * broker
#   * ntpserv
#   * pgserver
#   * web (REST + DB)
#   * scene (controller)

import json
import time

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time

from tests.functional.common_service import ServiceMqttTest
import tests.common_test_utils as common

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


def test_controller_publishes_tracking_on_detection(record_xml_attribute, params, scene_uid):
  """! Verify that the Controller service publishes tracked objects on
  DATA_REGULATED when a detection is sent on DATA_CAMERA.

  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test connection parameters.
  @param    scene_uid               UID of the test scene.
  """
  TEST_NAME = "NEX-T12595"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  h = ServiceMqttTest(params)
  exit_code = 1
  try:
    h.connect([reg_topic])
    ctrl_up = _publish_detections_until_tracked(h, cam_topic)
    assert ctrl_up, (
        f"No DATA_REGULATED message with tracked objects received on "
        f"{reg_topic} within {h.MAX_WAIT_S}s"
    )
    log.info("PASS: controller published tracking output on DATA_REGULATED")
    exit_code = 0
  finally:
    h.disconnect()

  common.record_test_result(TEST_NAME, exit_code)


def test_controller_creates_tracker_after_scene_update(record_xml_attribute, params, scene_uid):
  """! Verify that the Controller creates a new tracker for a scene after
  receiving an 'update' message on CMD_DATABASE.

  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test connection parameters.
  @param    scene_uid               UID of the test scene.
  """
  TEST_NAME = "NEX-T22793"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password']), \
      "REST authentication failed"

  original_res = rest.getScenes({'id': scene_uid})
  assert original_res['count'] > 0, f"Scene uid={scene_uid} not found"
  original_name = original_res['results'][0]['name']

  h = ServiceMqttTest(params)
  exit_code = 1
  try:
    h.connect([reg_topic])

    ctrl_up = _publish_detections_until_tracked(h, cam_topic)
    assert ctrl_up, (
        f"No DATA_REGULATED message with tracked objects received on "
        f"{reg_topic} within {h.MAX_WAIT_S}s"
    )

    ids_before = h.get_tracked_ids()
    res = rest.updateScene(scene_uid, {'name': original_name + "-modified"})
    assert res.statusCode == 200, f"Failed to update scene: {res.errors}"
    log.info(
        f"Updated scene uid={scene_uid} via REST, waiting for tracking to resume")
    h.clear_messages()

    resumed = _publish_detections_until_tracked(h, cam_topic)
    assert resumed, (
        f"No DATA_REGULATED message with tracked objects received on "
        f"{reg_topic} within {h.MAX_WAIT_S}s after scene REST update"
    )

    ids_after = h.get_tracked_ids()
    assert ids_before.isdisjoint(ids_after), (
        f"Tracked object IDs overlap before and after scene update "
        f"(before={ids_before}, after={ids_after}); tracker may not have been reset"
    )
    log.info(
        "PASS: controller resumed tracking with fresh IDs after scene REST update")
    exit_code = 0
  finally:
    h.disconnect()
    rest.updateScene(scene_uid, {'name': original_name})

  common.record_test_result(TEST_NAME, exit_code)
