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


def _wait_for_controller_output(tester, cam_topic):
  """! Publish detections until DATA_REGULATED contains tracked objects.

  @param    tester      ServiceMqttTest instance (connected).
  @param    cam_topic   DATA_CAMERA topic string.
  @return   True if objects were received within MAX_WAIT, False on timeout.
  """
  end = time.time() + tester.MAX_WAIT
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

  tester = ServiceMqttTest(params)
  try:
    tester.connect([reg_topic])
    found = _wait_for_controller_output(tester, cam_topic)
    assert found, (
      f"No DATA_REGULATED message with tracked objects received on "
      f"{reg_topic} within {tester.MAX_WAIT}s"
    )
    log.info("PASS: controller published tracking output on DATA_REGULATED")
    exit_code = 0
  finally:
    tester.disconnect()
  
  common.record_test_result(TEST_NAME, exit_code)
  