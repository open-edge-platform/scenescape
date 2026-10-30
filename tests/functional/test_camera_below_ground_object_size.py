#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional test: objects detected by a camera positioned below ground level
(translation z < 0) are published with a non-negative height.

Regression test for CameraPose.projectBounds, which derived the projected
object height from the signed camera z coordinate.
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

FRAME_RATE = 10
CAMERA_ID = "camera_below_ground"
CAMERA_Z = -3.0
SETTLE_TIME_S = 3


def _detection():
  return {
    "id": CAMERA_ID,
    "objects": {
      "person": [
        {
          "id": 1,
          "category": "person",
          "bounding_box": {"x": 0.5, "y": 0.1, "width": 0.2, "height": 0.4},
        }
      ]
    },
    "rate": float(FRAME_RATE),
    "timestamp": get_iso_time(),
  }


def _first_object_size(tester):
  with tester._lock:
    for msg in tester._messages:
      if not isinstance(msg['data'], dict):
        continue
      for obj in msg['data'].get('objects', []):
        if obj.get('size'):
          return obj['size']
  return None


@pytest.fixture
def mqtt_tester(params):
  """Provide a connected ServiceMqttTest and disconnect it on teardown."""
  h = ServiceMqttTest(params)
  try:
    yield h
  finally:
    h.disconnect()


@pytest.fixture
def below_ground_camera(rest, scene_uid):
  """Create a camera at z < 0 in the test scene and delete it on teardown."""
  res = rest.createCamera({
    "name": CAMERA_ID,
    "sensor_id": CAMERA_ID,
    "scene": scene_uid,
    "intrinsics": {"fx": 905, "fy": 905, "cx": 640, "cy": 360},
    "transform_type": "euler",
    "translation": [0.0, 0.0, CAMERA_Z],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
  })
  assert res.statusCode in (200, 201), f"Failed to create camera: {res.errors}"
  time.sleep(SETTLE_TIME_S)
  try:
    yield res
  finally:
    try:
      rest.deleteCamera(res["uid"])
    except Exception as exc:
      log.warning(f"Failed to delete camera {res['uid']}: {exc}")


@pytest.mark.test_name("NEX-T29816")
def test_below_ground_camera_object_has_nonnegative_height(
    result_recorder, scene_uid, mqtt_tester, below_ground_camera):
  """! Verify that an object detected by a camera with z < 0 is published
  with a positive height.

  @param    result_recorder      Pytest fixture recording test pass/fail.
  @param    scene_uid            UID of the test scene.
  @param    mqtt_tester          Connected ServiceMqttTest fixture.
  @param    below_ground_camera  Camera created below ground level.
  """
  cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  mqtt_tester.connect([reg_topic])
  end = time.time() + mqtt_tester.MAX_WAIT_S
  size = None
  while time.time() < end and size is None:
    mqtt_tester.publish(cam_topic, json.dumps(_detection()))
    time.sleep(1.0 / FRAME_RATE)
    size = _first_object_size(mqtt_tester)

  assert size is not None, (
    f"No tracked object with size received on {reg_topic} "
    f"within {mqtt_tester.MAX_WAIT_S}s"
  )
  log.info(f"Published object size: {size}")
  assert all(dim >= 0 for dim in size), f"Negative object size: {size}"
  assert size[2] > 0, f"Object height is not positive: {size}"
  log.info("PASS: object detected by a below-ground camera has positive height")
  result_recorder.success()
