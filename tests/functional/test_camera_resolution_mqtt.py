#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MQTT detector resolution must not persist Cam width/height via Manager.

MQTT optics are ephemeral with extrinsics. These tests assert the Cam REST
record is unchanged after detector frames that carry resolution.
"""

import json
import time
import uuid

import pytest

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

INITIAL_RESOLUTION = [640, 480]
UPDATED_RESOLUTION = [1280, 720]
PUBLISH_REPEATS = 5
SETTLE_S = 3


def _camera_payload(scene_uid, sensor_id, resolution, pose_locked=False):
  return {
    "name": sensor_id,
    "sensor_id": sensor_id,
    "scene": scene_uid,
    "type": "camera",
    "pose_locked": pose_locked,
    "resolution": {"width": resolution[0], "height": resolution[1]},
    "intrinsics": {
      "fx": 570.0,
      "fy": 570.0,
      "cx": resolution[0] / 2.0,
      "cy": resolution[1] / 2.0,
    },
  }


def _detector_frame(camera_id, resolution=None):
  frame = {
    "id": camera_id,
    "timestamp": get_iso_time(),
    "rate": 10.0,
    "objects": {"person": []},
  }
  if resolution is not None:
    if isinstance(resolution, dict):
      frame["resolution"] = resolution
    else:
      frame["resolution"] = {"width": resolution[0], "height": resolution[1]}
  return frame


def _create_camera(rest, scene_uid, resolution=None, pose_locked=False):
  if resolution is None:
    resolution = INITIAL_RESOLUTION
  sensor_id = f"resmqtt-{uuid.uuid4().hex[:10]}"
  created = rest.createCamera(
    _camera_payload(scene_uid, sensor_id, resolution, pose_locked=pose_locked))
  assert created, (created.statusCode, created.errors)
  uid = created["uid"]
  cam = rest.getCamera(uid)
  assert cam, (cam.statusCode, cam.errors)
  assert cam.get("resolution") == resolution, (
    f"Create left unexpected resolution: {cam.get('resolution')}")
  time.sleep(2)
  return uid, sensor_id


def _delete_camera(rest, camera_uid):
  if not camera_uid:
    return
  try:
    rest.deleteCamera(camera_uid)
  except Exception as exc:
    log.warning(f"Cleanup deleteCamera({camera_uid}) failed: {exc}")


def _publish_frames(pubsub, sensor_id, resolution=None, repeats=PUBLISH_REPEATS):
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=sensor_id)
  for _ in range(repeats):
    pubsub.publish(topic, json.dumps(_detector_frame(sensor_id, resolution)))
    time.sleep(0.1)


def _assert_resolution_unchanged(rest, camera_uid, expected, settle_s=SETTLE_S):
  time.sleep(settle_s)
  cam = rest.getCamera(camera_uid)
  assert cam, (cam.statusCode, cam.errors)
  assert cam.get("resolution") == expected, (
    f"Resolution changed unexpectedly: got {cam.get('resolution')}, "
    f"expected {expected}")


@pytest.fixture
def mqtt_pubsub(params):
  pubsub = PubSub(
    params["auth"], None, params["rootcert"],
    params["broker_url"], int(params["broker_port"]))
  pubsub.connect()
  pubsub.loopStart()
  try:
    yield pubsub
  finally:
    pubsub.loopStop()


@pytest.mark.test_name("NEX-T30100")
def test_mqtt_resolution_does_not_persist_to_camera(
    rest, scene_uid, mqtt_pubsub, result_recorder, demo_scene):
  """Positive ephemeral contract: detector MQTT resolution must not PATCH Cam."""
  camera_uid = None
  try:
    camera_uid, sensor_id = _create_camera(rest, scene_uid)
    _publish_frames(mqtt_pubsub, sensor_id, UPDATED_RESOLUTION)
    _assert_resolution_unchanged(rest, camera_uid, INITIAL_RESOLUTION)
    log.info("PASS: MQTT resolution left durable Cam resolution unchanged")
    result_recorder.success()
  finally:
    _delete_camera(rest, camera_uid)


@pytest.mark.test_name("NEX-T30101")
def test_mqtt_invalid_resolution_does_not_replace_registered_size(
    rest, scene_uid, mqtt_pubsub, result_recorder, demo_scene):
  """Negative: invalid resolution on MQTT must not overwrite Cam width/height."""
  camera_uid = None
  try:
    camera_uid, sensor_id = _create_camera(rest, scene_uid)
    _publish_frames(
      mqtt_pubsub, sensor_id, {"width": 0, "height": 720})
    _assert_resolution_unchanged(rest, camera_uid, INITIAL_RESOLUTION)
    log.info("PASS: invalid MQTT resolution left Cam unchanged")
    result_recorder.success()
  finally:
    _delete_camera(rest, camera_uid)


@pytest.mark.test_name("NEX-T30102")
def test_mqtt_resolution_ignored_when_pose_locked(
    rest, scene_uid, mqtt_pubsub, result_recorder, demo_scene):
  """Negative: pose_locked cameras ignore MQTT optics including resolution."""
  camera_uid = None
  try:
    camera_uid, sensor_id = _create_camera(
      rest, scene_uid, pose_locked=True)
    _publish_frames(mqtt_pubsub, sensor_id, UPDATED_RESOLUTION)
    _assert_resolution_unchanged(rest, camera_uid, INITIAL_RESOLUTION)
    log.info("PASS: pose_locked blocked MQTT resolution update")
    result_recorder.success()
  finally:
    _delete_camera(rest, camera_uid)
