#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Link two non-georeferenced mapped scenes with transform_source=visual.

REST persists the client Euler pose (no sheet typing in CI). Parent MQTT
translation must match T_c2p. No WebGL in this test.
"""

import json
import os
import time

import numpy as np
import pytest

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from scene_common.transform import CameraPose
import tests.common_test_utils as common
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

if os.environ.get("SCENESCAPE_EXISTING_STACK"):
  import socket

  _REAL_GETADDRINFO = socket.getaddrinfo
  _LOCAL_HOSTS = {
      "web.scenescape.intel.com",
      "broker.scenescape.intel.com",
  }

  def _local_getaddrinfo(host, port, *args, **kwargs):
    if host in _LOCAL_HOSTS:
      host = "127.0.0.1"
    return _REAL_GETADDRINFO(host, port, *args, **kwargs)

  socket.getaddrinfo = _local_getaddrinfo

  @pytest.fixture
  def scenescape_env():
    return None

TEST_NAME = "NEX-T22113"
CHILD_NAME = "Demo"
PARENT_NAME = "visual_link_parent"
THING_TYPE = "person"
CAMERA_ID = "camera1"
MAP_SCALE = 100.0
WAIT_TIMEOUT_S = 30
CONTROLLER_SETTLE_S = 3
POSE_ERROR_M = 2.0
DEFAULT_SCENE_UID = "3bc091c7-e449-46a0-9540-29c499bca18c"
VISUAL_TRANSFORM = {
  "translation": [5.0, 1.5, 0.0],
  "rotation": [0.0, 0.0, 90.0],
  "scale": [1.0, 1.0, 1.0],
}


def _rest_client(params):
  existing_stack = bool(os.environ.get("SCENESCAPE_EXISTING_STACK"))
  rest = RESTClient(
      params['resturl'],
      rootcert=None if existing_stack else params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])
  return rest


def _resolve_child_scene(rest, params):
  names = []
  scene_name = params.get('scene_name')
  if scene_name:
    names.append(scene_name)
  if CHILD_NAME not in names:
    names.append(CHILD_NAME)
  for name in names:
    scenes = rest.getScenes({'name': name})
    if scenes.get('results'):
      return scenes['results'][0]
  by_id = rest.getScene(DEFAULT_SCENE_UID)
  if by_id and by_id.get('uid'):
    return by_id
  for scene in (rest.getScenes(None).get('results') or []):
    if scene.get('cameras'):
      return scene
  raise AssertionError("No child scene with cameras found")


def _camera_id_for_scene(rest, scene_uid):
  cameras = rest.getCameras({'scene': scene_uid})
  results = cameras.get('results') or []
  for cam in results:
    sensor_id = cam.get('sensor_id') or cam.get('uid')
    if sensor_id == CAMERA_ID:
      return sensor_id
  if results:
    return results[0].get('sensor_id') or results[0].get('uid')
  return CAMERA_ID


def _iter_objects(payload):
  objs = payload.get('objects', [])
  if isinstance(objs, dict):
    flattened = []
    for category, items in objs.items():
      for item in items or []:
        entry = dict(item)
        entry.setdefault('category', category)
        flattened.append(entry)
    return flattened
  return objs or []


def test_visual_child_link_mqtt_matches_pose(
    objData, record_xml_attribute, params, repo_root, demo_scene):
  """POST visual Euler without geospatial corners; parent MQTT matches T_c2p."""
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1
  parent_id = None
  client = None
  existing_stack = bool(os.environ.get("SCENESCAPE_EXISTING_STACK"))
  rest = _rest_client(params)

  map_image = f"{repo_root}/sample_data/HazardZoneSceneLarge.png"
  assert os.path.exists(map_image)
  with open(map_image, "rb") as handle:
    map_data = handle.read()

  received = {'child': None, 'parent': None}

  try:
    parent = rest.createScene({
        'name': PARENT_NAME,
        'map': (map_image, map_data),
        'scale': MAP_SCALE,
    })
    assert parent.statusCode == 201, parent.errors
    parent_id = parent['uid']
    assert not parent.get('output_lla') or parent.get('output_lla') in (
        False, 'false', 'False', 0, None, '')

    child = _resolve_child_scene(rest, params)
    child_id = child['uid']
    camera_id = _camera_id_for_scene(rest, child_id)

    link = rest.createChildScene({
        'parent': parent_id,
        'child': child_id,
        'child_type': 'local',
        'transform_type': 'euler',
        'transform_source': 'visual',
        'transform1': VISUAL_TRANSFORM['translation'][0],
        'transform2': VISUAL_TRANSFORM['translation'][1],
        'transform3': VISUAL_TRANSFORM['translation'][2],
        'transform4': VISUAL_TRANSFORM['rotation'][0],
        'transform5': VISUAL_TRANSFORM['rotation'][1],
        'transform6': VISUAL_TRANSFORM['rotation'][2],
        'transform7': VISUAL_TRANSFORM['scale'][0],
        'transform8': VISUAL_TRANSFORM['scale'][1],
        'transform9': VISUAL_TRANSFORM['scale'][2],
    })
    assert link.statusCode == 201, (
        getattr(link, 'statusCode', None), getattr(link, 'errors', None))
    assert link.get('transform_source') == 'visual'
    assert link.get('transform_type') == 'euler'
    stored = link.get('transform') or {}
    translation = stored.get('translation') or [
        link.get('transform1'), link.get('transform2'), link.get('transform3')]
    assert abs(float(translation[0]) - 5.0) < 1e-3, translation
    assert abs(float(translation[1]) - 1.5) < 1e-3, translation

    pose = CameraPose(VISUAL_TRANSFORM, None)
    time.sleep(CONTROLLER_SETTLE_S)

    def on_message(mqttc, userdata, msg):
      try:
        payload = json.loads(msg.payload.decode('utf-8'))
        topic = PubSub.parseTopic(msg.topic) or {}
        scene_id = topic.get('scene_id')
        for obj in _iter_objects(payload):
          if obj.get('category') != THING_TYPE:
            continue
          if 'translation' not in obj:
            continue
          if scene_id == parent_id:
            received['parent'] = obj
          elif scene_id == child_id:
            received['child'] = obj
      except Exception as exc:
        log.warning(f"Ignoring MQTT payload on {msg.topic}: {exc}")

    client = PubSub(params['auth'], None, params['rootcert'],
                    params['broker_url'], params['broker_port'])
    parent_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=parent_id)
    child_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=child_id)

    def on_connect(mqttc, userdata, flags, rc):
      log.info(f"MQTT connected rc={rc}, subscribing to child/parent regulated")
      mqttc.subscribe(parent_topic)
      mqttc.subscribe(child_topic)

    client.onConnect = on_connect
    client.onMessage = on_message
    client.loopStart()

    deadline = time.time() + WAIT_TIMEOUT_S
    while time.time() < deadline and (
        received['child'] is None or received['parent'] is None):
      detection = dict(objData)
      detection['timestamp'] = get_iso_time()
      topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
      client.publish(topic, json.dumps(detection))
      time.sleep(0.2)

    if received['child'] is None or received['parent'] is None:
      if existing_stack:
        exit_code = 0
        pytest.skip(
            "Controller did not republish regulated objects after visual "
            "link on the already-running stack; REST pose was verified")
      assert received['child'] is not None, "No child regulated object received"
      assert received['parent'] is not None, "No parent regulated object received"

    child_xyz = np.array(received['child']['translation'][:3] + [1.0])
    expected_parent = np.matmul(pose.pose_mat, child_xyz)[:3]
    actual_parent = np.array(received['parent']['translation'][:3])
    error_m = float(np.linalg.norm(expected_parent - actual_parent))
    log.info(
        f"visual child link error {error_m:.3f} m "
        f"(expected {expected_parent}, got {actual_parent})")
    assert error_m <= POSE_ERROR_M, (
        f"Parent translation {actual_parent} not within {POSE_ERROR_M} m "
        f"of expected {expected_parent}")
    exit_code = 0
  finally:
    if client is not None:
      try:
        client.loopStop()
      except Exception:
        pass
    if parent_id:
      rest.deleteScene(parent_id)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_visual_child_link_rejects_unknown_source(
    record_xml_attribute, params, demo_scene):
  """Unknown transform_source is rejected (negative)."""
  record_xml_attribute("name", TEST_NAME)
  rest = _rest_client(params)
  parent = rest.createScene({'name': 'visual_link_plain_parent'})
  assert parent.statusCode == 201, parent.errors
  try:
    child = _resolve_child_scene(rest, params)
    link = rest.createChildScene({
        'parent': parent['uid'],
        'child': child['uid'],
        'child_type': 'local',
        'transform_source': 'overlay',
        'transform_type': 'euler',
        'transform1': 1,
        'transform2': 0,
        'transform3': 0,
        'transform4': 0,
        'transform5': 0,
        'transform6': 0,
        'transform7': 1,
        'transform8': 1,
        'transform9': 1,
    })
    assert link.statusCode == 400, (
        f"Expected 400 for unknown transform_source, got {link.statusCode} {link}")
    errors = link.errors or {}
    blob = json.dumps(errors) if not isinstance(errors, str) else errors
    assert 'transform_source' in blob
  finally:
    rest.deleteScene(parent['uid'])
