#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests that the Scene Controller releases the resources of scenes it replaces.

Every CMD_DATABASE update that changes a scene makes the Controller rebuild that scene
with a new tracker, and a deleted scene is dropped from the cache. The retired trackers' threads
(category trackers, UUID manager timers and pools) must stop, otherwise the number of
threads in the Controller grows with every update. The thread count is read from /proc
inside the Controller container, so the real Scene, tracker and UUID manager teardown
path is exercised.
"""

import json
import time

import pytest

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

from tests.functional.common_service import ServiceMqttTest
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

FRAME_RATE = 10
CAMERA_ID = "camera1"
EXTRA_SCENE_NAME = "leak-deleted-scene"
EXTRA_CAMERA_ID = "leakcam"

SCENE_UPDATES = 10
# Every unreleased tracker keeps at least a category thread, two timers and a pool
# worker, so a leak adds several times this per update; the margin is for noise only.
MAX_THREAD_GROWTH = 10
# What a deleted scene's tracker holds at minimum: category thread, two timers, pool worker.
MIN_RELEASED_THREADS = 3
SETTLE_TIMEOUT_S = 30
# The web service can stall on a scene update while the stack is busy rebuilding scenes.
REST_TIMEOUT_S = 60
THREAD_COUNT_CMD = "awk '/^Threads:/ {n += $2} END {print n}' /proc/[0-9]*/status"


def _detection(camera_id):
  return {
    "id": camera_id,
    "objects": {
      "person": [{
        "id": 1,
        "category": "person",
        "bounding_box": {"x": 0.5, "y": 0.1, "width": 0.2, "height": 0.4},
      }]
    },
    "rate": float(FRAME_RATE),
    "timestamp": get_iso_time(),
  }


def _thread_count(scenescape_env):
  """! Count the threads of every process in the Scene Controller container.

  @param    scenescape_env    ScenescapeEnv fixture.
  @return   int
  """
  out = scenescape_env.docker.compose.execute(
    "scene", ["sh", "-c", THREAD_COUNT_CMD], tty=False)
  return int(out.strip())


def _settled_thread_count(scenescape_env, timeout=SETTLE_TIMEOUT_S):
  """! Wait until the thread count is unchanged between two readings one second apart.

  @return   int   The settled count, or the last reading if it kept changing.
  """
  end = time.time() + timeout
  previous = _thread_count(scenescape_env)
  while time.time() < end:
    time.sleep(1)
    current = _thread_count(scenescape_env)
    if current == previous:
      return current
    previous = current
  return previous


def _publish_frames(tester, camera_ids):
  """! Publish one detection frame for each camera and pace the caller to FRAME_RATE."""
  for camera_id in camera_ids:
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
    tester.publish(topic, json.dumps(_detection(camera_id)))
  time.sleep(1.0 / FRAME_RATE)


def _publish_until(tester, camera_ids, condition):
  """! Publish detections until condition() holds or the wait timeout expires.

  @return   True if condition() held within MAX_WAIT_S, False on timeout.
  """
  end = time.time() + tester.MAX_WAIT_S
  while time.time() < end:
    _publish_frames(tester, camera_ids)
    if condition():
      return True
  return False


def _wait_for_threads_at_most(scenescape_env, limit, timeout=SETTLE_TIMEOUT_S, tester=None,
                              camera_ids=()):
  """! Poll the thread count until it is at most limit.

  A scene is only rebuilt or dropped when the Controller looks it up for a message, so
  callers that need that to happen pass a tester and cameras to keep publishing frames.

  @return   int   The last thread count read.
  """
  end = time.time() + timeout
  count = _thread_count(scenescape_env)
  while count > limit and time.time() < end:
    if tester is not None:
      for _ in range(FRAME_RATE):
        _publish_frames(tester, camera_ids)
    else:
      time.sleep(1)
    count = _thread_count(scenescape_env)
  return count


@pytest.fixture
def mqtt_tester(params):
  """Provide a connected ServiceMqttTest and disconnect it on teardown."""
  h = ServiceMqttTest(params)
  try:
    yield h
  finally:
    h.disconnect()


@pytest.mark.test_name("NEX-T31116")
def test_controller_thread_count_stays_bounded_over_scene_updates(
    result_recorder, scenescape_env, rest, scene_uid, mqtt_tester):
  """
  ## Name
  Controller Thread Count Stays Bounded Over Scene Updates

  ## Objective
  Verify that repeated scene updates through the REST API do not make the number of threads in the Scene Controller grow, i.e. the tracker of each replaced scene is torn down.

  ## Labels
  - Functional
  - API

  ## Steps
  1. Publish detections until the Scene Controller outputs tracked objects for the Demo scene
  2. Record the settled thread count of the Scene Controller container as the baseline
  3. Update the scene name through the REST API several times, publishing detections after each update until tracking resumes
  4. Wait for the thread count to settle
  5. Verify the thread count is at most the baseline plus the allowed growth
  6. Restore the original scene name
  """
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
  rest.timeout = REST_TIMEOUT_S
  original_res = rest.getScenes({'id': scene_uid})
  assert original_res['count'] > 0, f"Scene uid={scene_uid} not found"
  original_name = original_res['results'][0]['name']

  try:
    mqtt_tester.connect([reg_topic])
    assert _publish_until(mqtt_tester, [CAMERA_ID], mqtt_tester.has_objects), (
      f"No tracked objects received on {reg_topic} within {mqtt_tester.MAX_WAIT_S}s")
    seen_ids = mqtt_tester.get_tracked_ids()
    baseline = _settled_thread_count(scenescape_env)
    log.info(f"Controller thread count before the updates: {baseline}")

    for i in range(SCENE_UPDATES):
      res = rest.updateScene(scene_uid, {'name': f"{original_name}-{i}"})
      assert res.statusCode == 200, f"Failed to update scene: {res.errors}"
      # Frames make the Controller rebuild the scene and start the new tracker's threads.
      assert _publish_until(
        mqtt_tester, [CAMERA_ID], lambda: mqtt_tester.get_tracked_ids() - seen_ids), (
        f"Tracking did not resume after update {i} within {mqtt_tester.MAX_WAIT_S}s")
      seen_ids |= mqtt_tester.get_tracked_ids()

    limit = baseline + MAX_THREAD_GROWTH
    final = _wait_for_threads_at_most(scenescape_env, limit)
    log.info(f"Controller thread count after {SCENE_UPDATES} updates: {final} "
             f"(baseline {baseline}, limit {limit})")
    assert final <= limit, (
      f"Controller threads grew from {baseline} to {final} over {SCENE_UPDATES} scene "
      f"updates; the trackers of replaced scenes are not being stopped")
    result_recorder.success()
  finally:
    try:
      rest.updateScene(scene_uid, {'name': original_name})
    except Exception as exc:
      log.warning(f"Failed to restore scene name: {exc}")


@pytest.mark.test_name("NEX-T31117")
def test_controller_stops_tracker_threads_of_a_deleted_scene(
    result_recorder, scenescape_env, rest, scene_uid, mqtt_tester):
  """
  ## Name
  Controller Stops Tracker Threads Of Deleted Scene

  ## Objective
  Verify that deleting a scene through the REST API stops the threads of its tracker in the Scene Controller.

  ## Labels
  - Functional
  - API

  ## Steps
  1. Create an extra scene with a camera copied from the Demo scene camera
  2. Publish detections for both cameras until the Scene Controller outputs tracked objects for the extra scene
  3. Record the settled thread count of the Scene Controller container
  4. Delete the extra scene through the REST API
  5. Keep publishing detections for the Demo scene camera so the Scene Controller rebuilds its scenes
  6. Verify the thread count drops by at least the minimum a tracker holds
  7. Delete the extra scene if the test failed before deleting it
  """
  rest.timeout = REST_TIMEOUT_S
  demo = rest.getScenes({'id': scene_uid})['results'][0]
  demo_camera = rest.getCamera(CAMERA_ID)
  assert demo_camera, (demo_camera.statusCode, demo_camera.errors)

  extra_scene = rest.createScene({"name": EXTRA_SCENE_NAME, "scale": demo.get("scale") or 1000})
  assert extra_scene.statusCode == 201, (extra_scene.statusCode, extra_scene.errors)
  extra_uid = extra_scene["uid"]
  deleted = False

  try:
    created = rest.createCamera({
      "name": EXTRA_CAMERA_ID, "sensor_id": EXTRA_CAMERA_ID, "scene": extra_uid,
      "intrinsics": demo_camera["intrinsics"], "distortion": demo_camera["distortion"],
      "transform_type": "euler", "translation": demo_camera["translation"],
      "rotation": demo_camera["rotation"], "scale": demo_camera["scale"],
    })
    assert created, (created.statusCode, created.errors)

    extra_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=extra_uid)
    mqtt_tester.connect([extra_topic])
    cameras = [CAMERA_ID, EXTRA_CAMERA_ID]
    assert _publish_until(mqtt_tester, cameras, mqtt_tester.has_objects), (
      f"No tracked objects received on {extra_topic} within {mqtt_tester.MAX_WAIT_S}s")
    with_scene = _settled_thread_count(scenescape_env)

    res = rest.deleteScene(extra_uid)
    assert res.statusCode in (200, 204), (res.statusCode, res.errors)
    deleted = True

    # Both scenes' trackers are alive again after the rebuild the deletion triggers, so
    # what remains is the deleted scene's share.
    limit = with_scene - MIN_RELEASED_THREADS
    after = _wait_for_threads_at_most(
      scenescape_env, limit, tester=mqtt_tester, camera_ids=[CAMERA_ID])
    log.info(f"Controller thread count with the scene: {with_scene}, "
             f"after deleting it: {after} (limit {limit})")
    assert after <= limit, (
      f"Controller threads went from {with_scene} to {after} after deleting a tracking "
      f"scene; expected at most {limit}, so its tracker threads are not being stopped")
    result_recorder.success()
  finally:
    if not deleted:
      try:
        rest.deleteScene(extra_uid)
      except Exception as exc:
        log.warning(f"Failed to delete scene {extra_uid}: {exc}")
