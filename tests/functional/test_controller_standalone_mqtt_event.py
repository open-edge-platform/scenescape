#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for the Scene Controller standalone MQTT event flow.

Covers:
  - Controller publishes tracked objects on DATA_REGULATED when detections
    arrive on DATA_CAMERA.
  - Controller resets its tracker (assigns fresh object IDs) after a scene
    update arrives via CMD_DATABASE.
  - Controller keeps the tracker (object IDs) of every other scene when one
    scene is updated.
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

SCENE_B_NAME = "controller-tracker-isolation-b"
SCENE_B_SCALE = 100.0
# Sensor.sensor_id is limited to 20 characters.
CAMERA_B_ID = "tracker-iso-cam-b"
# 3D-2D point correspondence calibration copied from the sample cameras.
CAMERA_B_TRANSFORM_TYPE = "3d-2d point correspondence"
CAMERA_B_TRANSFORMS = [278.0, 61.0, 621.0, 132.0, 559.0, 460.0, 66.0, 289.0,
                       0.1, 5.38, 3.04, 5.35, 3.05, 2.42, 0.1, 2.45]


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


def _publish_until(tester, camera_ids, condition):
  """! Publish a detection for every camera on each frame until condition()
  holds, or the wait timeout expires.

  @param    tester        ServiceMqttTest instance (connected), used to publish.
  @param    camera_ids    IDs of the cameras to publish detections for.
  @param    condition     Callable returning a truthy value once publishing can stop.
  @return   True if condition() held within MAX_WAIT_S, False on timeout.
  """
  topics = {cam_id: PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
            for cam_id in camera_ids}
  end = time.time() + tester.MAX_WAIT_S
  while time.time() < end:
    for cam_id, topic in topics.items():
      tester.publish(topic, json.dumps(_detection(cam_id)))
    time.sleep(1.0 / FRAME_RATE)
    if condition():
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


@pytest.mark.test_name("NEX-T30936")
def test_controller_keeps_unrelated_scene_tracker_after_scene_update(
    result_recorder, rest, scene_uid, repo_root, mqtt_tester, params):
  """! Verify that a scene REST update (CMD_DATABASE -> cache invalidate)
  resets the tracker of the updated scene only: the tracked object IDs of the
  other Controller scene must survive, while the updated scene gets fresh IDs.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    rest               Authenticated RESTClient fixture.
  @param    scene_uid          UID of the test scene (scene A).
  @param    repo_root          Repository root path fixture.
  @param    mqtt_tester        Connected ServiceMqttTest fixture, used for scene A.
  @param    params             Dict of functional-test connection parameters.
  """
  map_image = f"{repo_root}/tests/resources/maps/HazardZoneSceneLarge.png"
  with open(map_image, "rb") as f:
    map_data = f.read()

  tester_b = ServiceMqttTest(params)
  scene_b_uid = None
  try:
    scene_b = rest.createScene({
      'name': SCENE_B_NAME,
      'map': (map_image, map_data),
      'scale': SCENE_B_SCALE,
    })
    assert scene_b.statusCode == 201, f"Failed to create scene B: {scene_b.errors}"
    scene_b_uid = scene_b['uid']
    camera_b = rest.createCamera({
      'name': CAMERA_B_ID,
      'sensor_id': CAMERA_B_ID,
      'scene': scene_b_uid,
      'transform_type': CAMERA_B_TRANSFORM_TYPE,
      'transforms': CAMERA_B_TRANSFORMS,
    })
    assert camera_b.statusCode == 201, f"Failed to create camera B: {camera_b.errors}"

    reg_topic_a = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
    reg_topic_b = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_b_uid)
    mqtt_tester.connect([reg_topic_a])
    tester_b.connect([reg_topic_b])
    camera_ids = [CAMERA_ID, CAMERA_B_ID]

    both_tracked = _publish_until(
      mqtt_tester, camera_ids, lambda: mqtt_tester.has_objects() and tester_b.has_objects())
    assert both_tracked, (
      f"Scenes A and B did not both publish tracked objects within "
      f"{mqtt_tester.MAX_WAIT_S}s")
    ids_a_before = mqtt_tester.get_tracked_ids()
    ids_b_before = tester_b.get_tracked_ids()

    res = rest.updateScene(scene_b_uid, {'name': SCENE_B_NAME + "-modified"})
    assert res.statusCode == 200, f"Failed to update scene B: {res.errors}"
    log.info(f"Updated scene B uid={scene_b_uid} via REST")
    mqtt_tester.clear_messages()

    # The Controller handles the update asynchronously, so output of scene B's old
    # tracker can still arrive. Wait for an ID it did not produce, then collect again
    # so only the new tracker's output is compared.
    b_reset = _publish_until(
      mqtt_tester, camera_ids, lambda: tester_b.get_tracked_ids() - ids_b_before)
    assert b_reset, (
      f"Scene B published no tracked object with a fresh ID within "
      f"{mqtt_tester.MAX_WAIT_S}s after its REST update")
    tester_b.clear_messages()
    both_resumed = _publish_until(
      mqtt_tester, camera_ids, lambda: mqtt_tester.has_objects() and tester_b.has_objects())
    assert both_resumed, (
      f"Scenes A and B did not both resume publishing tracked objects within "
      f"{mqtt_tester.MAX_WAIT_S}s after scene B's REST update")

    ids_a_after = mqtt_tester.get_tracked_ids()
    ids_b_after = tester_b.get_tracked_ids()
    assert ids_a_before & ids_a_after, (
      f"Scene A lost its tracked object IDs after scene B was updated "
      f"(before={ids_a_before}, after={ids_a_after}); its tracker was rebuilt")
    assert ids_b_before.isdisjoint(ids_b_after), (
      f"Scene B tracked object IDs overlap before and after its update "
      f"(before={ids_b_before}, after={ids_b_after}); its tracker was not reset")
    log.info(
      "PASS: scene A kept its tracked IDs while scene B was reset by its REST update")
    result_recorder.success()
  finally:
    tester_b.disconnect()
    if scene_b_uid is not None:
      try:
        rest.deleteScene(scene_b_uid)
      except Exception as exc:
        log.warning(f"Failed to delete scene B uid={scene_b_uid}: {exc}")
