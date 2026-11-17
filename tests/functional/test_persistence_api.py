#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.utils.log import get_logger
import os
import time
from http import HTTPStatus
import pytest
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
from scene_common import log

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

# Dedicated names so the test never collides with the shared demo scene.
SCENE_NAME = "persistence-api-scene"
CAMERA_NAME = "camtest1"
CAMERA_SENSOR_ID = "camtest1"

_RESTART_LOGIN_TIMEOUT = 120
_RESTART_LOGIN_POLL_INTERVAL = 2


def _cleanup_test_artifacts(rest):
  """Remove leftover scene/camera/sensors."""
  scenes = rest.getScenes({"name": SCENE_NAME}).get("results", [])
  for s in scenes:
    try:
      rest.deleteScene(s["uid"])
    except Exception:
      pass

  cams = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
  for c in cams:
    try:
      rest.deleteCamera(c["uid"])
    except Exception:
      pass

  try:
    sensors = rest.getSensors({"sensor_id": CAMERA_SENSOR_ID}).get("results", [])
  except Exception:
    sensors = []
  for s in sensors:
    try:
      rest.deleteSensor(s["uid"])
    except Exception:
      pass

  try:
    sensors_by_name = rest.getSensors({"name": CAMERA_NAME}).get("results", [])
  except Exception:
    sensors_by_name = []
  for s in sensors_by_name:
    try:
      rest.deleteSensor(s["uid"])
    except Exception:
      pass


def _create_scene_with_camera(rest):
  """Create the test scene and attach the test camera; return the scene UID."""
  map_file = os.path.join("tests", "resources", "maps", "HazardZoneScene.png")
  with open(map_file, "rb") as f:
    res = rest.createScene(
      {
        "name": SCENE_NAME,
        "scale": 1000,
        "map": f,
      }
    )
  assert res.statusCode == HTTPStatus.CREATED, \
    f"Failed to create scene: {getattr(res, 'errors', res)}"

  scenes = rest.getScenes({"name": SCENE_NAME}).get("results", [])
  assert scenes, f"Scene '{SCENE_NAME}' not found after creation"
  assert len(scenes) == 1, \
    f"Expected exactly one scene named '{SCENE_NAME}', found {len(scenes)}"
  scene_uid = scenes[0]["uid"]

  cam_payload = {
    "scene": scene_uid,
    "name": CAMERA_NAME,
    "sensor_id": CAMERA_SENSOR_ID,
    "type": "camera",
  }
  res = rest.createCamera(cam_payload)
  assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), \
    f"Failed to add camera: {getattr(res, 'errors', res)}"
  return scene_uid


@pytest.mark.test_name("NEX-T29232")
def test_persistence_on_page_navigate_api(params, rest, result_recorder):
  sceneName = SCENE_NAME

  # Clean up any existing artifacts so the test is deterministic
  _cleanup_test_artifacts(rest)

  try:
    scene_uid = _create_scene_with_camera(rest)

    # Validate scene persistence
    scenes = rest.getScenes({"name": sceneName}).get("results", [])
    assert scenes, f"Scene '{sceneName}' not found after camera creation"
    scene = scenes[0]
    assert scene["name"] == sceneName
    assert scene["scale"] == 1000
    assert "map" in scene

    # Validate camera persistence
    cameras = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    assert cameras, (
      f"Expected at least one camera named '{CAMERA_NAME}' "
      f"for scene '{sceneName}', but none were found"
    )
    cam = cameras[0]
    assert cam.get("name") == CAMERA_NAME, \
      f"Camera name mismatch: expected '{CAMERA_NAME}', got '{cam.get('name')}'"
    if "scene" in cam:
      assert cam["scene"] == scene_uid, \
        f"Camera '{CAMERA_NAME}' is not linked to scene '{sceneName}'"

    log.info(
      "Scene and camera persist on page navigation: "
      f"scene='{sceneName}', camera name='{CAMERA_NAME}'"
    )
  finally:
    _cleanup_test_artifacts(rest)

  result_recorder.success()


@pytest.mark.test_name("NEX-T29233")
def test_persistence_on_restart_api(params, rest, scenescape_env, result_recorder):
  """! Checks that a scene and camera created via the REST API are still
  present after the manager (web) service itself is restarted, proving the
  data is persisted in the database rather than only held in memory.

  @param    params                  Dict of test parameters.
  """
  _cleanup_test_artifacts(rest)
  try:
    _verify_persistence_on_restart(params, rest, scenescape_env)
  finally:
    _cleanup_test_artifacts(rest)

  result_recorder.success()


def _verify_persistence_on_restart(params, rest, scenescape_env):
  sceneName = SCENE_NAME
  expected_scene_uid = _create_scene_with_camera(rest)

  log.info("Restarting manager (web) service to verify database persistence...")
  # The Kubernetes env carries its own restart hook; Compose restarts via the docker client.
  if getattr(scenescape_env, "restart_web", None):
    scenescape_env.restart_web()
  else:
    scenescape_env.docker.compose.restart("web")

  # Wait for the manager to come back up and accept REST logins again.
  deadline = time.monotonic() + _RESTART_LOGIN_TIMEOUT
  authenticated = False
  while time.monotonic() < deadline:
    try:
      if rest.authenticate(params['user'], params['password']):
        authenticated = True
        break
    except Exception:
      pass
    time.sleep(_RESTART_LOGIN_POLL_INTERVAL)
  assert authenticated, "Manager did not accept REST logins again after restart"

  # After restart, the scene created above should still exist
  scenes = rest.getScenes({"name": sceneName}).get("results", [])
  assert scenes, f"Scene '{sceneName}' not found after restart"
  assert len(scenes) == 1, \
    f"Expected exactly one scene named '{sceneName}', found {len(scenes)}"
  scene = scenes[0]

  assert scene["name"] == sceneName
  assert scene["uid"] == expected_scene_uid
  assert scene["scale"] == 1000, f"Expected scale 1000, got {scene['scale']}"
  assert "map" in scene

  # Validate that the camera created above also survives restart
  cameras = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
  assert cameras, (
    f"Expected at least one camera named '{CAMERA_NAME}' "
    f"for scene '{sceneName}' after restart"
  )
  cam = cameras[0]
  assert cam.get("name") == CAMERA_NAME, \
    f"Camera name mismatch after restart: expected '{CAMERA_NAME}', got '{cam.get('name')}'"
  if "scene" in cam:
    assert cam["scene"] == expected_scene_uid, \
      f"Camera '{CAMERA_NAME}' is not linked to scene '{sceneName}' after restart"

  log.info(
    "Scene and camera persist after restart: "
    f"scene='{sceneName}', camera name='{CAMERA_NAME}'"
  )
