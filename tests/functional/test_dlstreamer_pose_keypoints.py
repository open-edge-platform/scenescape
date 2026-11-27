# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify sscape_policies publishes pose keypoints from a live DLStreamer pose pipeline."""

import json
import time

import pytest

from scene_common.mqtt import PubSub
from tests.utils.profiles import POSE_VIDEO
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

SCENESCAPE_SPEC = FuncTestSpec(profile=POSE_VIDEO, auth=AUTH_CONTROLLER)

POSE_CAMERAS = ('atag-qcam1', 'atag-qcam2')
NON_POSE_CAMERAS = ('camera1', 'camera2')
COCO17_NAMES = [
  'nose', 'eye_l', 'eye_r', 'ear_l', 'ear_r',
  'shoulder_l', 'shoulder_r', 'elbow_l', 'elbow_r', 'wrist_l', 'wrist_r',
  'hip_l', 'hip_r', 'knee_l', 'knee_r', 'ankle_l', 'ankle_r',
]
MIN_PERSONS_PER_CAMERA = 5
MESSAGE_TIMEOUT = 120
# Bbox-relative coordinates may sit marginally outside the box.
COORD_TOLERANCE = 0.05


@pytest.fixture
def docker_backend(request):
  if request.config.getoption('--backend') != 'docker':
    pytest.skip('Pose pipeline compose override is Docker-only')


def _collect_persons(params, cameras):
  """Return person objects published by DLStreamer on the given camera topics."""
  topics = [PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam) for cam in cameras]
  persons = []
  counts = {cam: 0 for cam in cameras}
  subscribed = []

  def on_connect(connection, userdata, flags, result):
    assert result == 0, f'MQTT connect failed: {result}'
    connection.subscribe([(topic, 0) for topic in topics])

  def on_message(connection, userdata, message):
    payload = json.loads(message.payload)
    camera_id = payload.get('id')
    for obj in payload.get('objects', {}).get('person', []):
      persons.append((camera_id, obj))
      if camera_id in counts:
        counts[camera_id] += 1

  client = PubSub(params['auth'], None, params['rootcert'],
                  params['broker_url'], params['broker_port'])
  client.onConnect = on_connect
  client.onMessage = on_message
  client.client.on_subscribe = lambda *_args: subscribed.append(True)
  try:
    client.connect()
    deadline = time.monotonic() + MESSAGE_TIMEOUT
    while (min(counts.values()) < MIN_PERSONS_PER_CAMERA
           and time.monotonic() < deadline):
      client.client.loop(timeout=0.2)
  finally:
    client.client.disconnect()

  assert subscribed, f'MQTT subscription to {topics} was not acknowledged'
  short = {cam: n for cam, n in counts.items() if n < MIN_PERSONS_PER_CAMERA}
  assert not short, (
    f'Cameras below {MIN_PERSONS_PER_CAMERA} person detections within '
    f'{MESSAGE_TIMEOUT}s: {short}')
  return persons


def _check_keypoints(camera_id, obj):
  keypoints = obj.get('keypoints')
  assert keypoints, f'{camera_id}: person detection has no keypoints: {obj}'
  assert [kp['name'] for kp in keypoints] == COCO17_NAMES, (
    f'{camera_id}: unexpected joint names {[kp.get("name") for kp in keypoints]}')
  for kp in keypoints:
    for axis in ('x', 'y'):
      value = kp[axis]
      assert isinstance(value, (int, float)), f'{camera_id}: {kp} {axis} is not numeric'
      assert -COORD_TOLERANCE <= value <= 1 + COORD_TOLERANCE, (
        f'{camera_id}: {kp} {axis} is not bbox-relative (0..1)')
    confidence = kp.get('confidence')
    assert isinstance(confidence, (int, float)) and 0 <= confidence <= 1, (
      f'{camera_id}: {kp} has no valid confidence')

  connections = obj.get('keypoint_connections')
  assert connections and len(connections) % 2 == 0, (
    f'{camera_id}: keypoint_connections must be a non-empty flat list of name pairs')
  assert set(connections) <= set(COCO17_NAMES), (
    f'{camera_id}: keypoint_connections reference unknown joints {connections}')
  assert 'bounding_box_px' in obj, f'{camera_id}: keypoints lack the bbox they are relative to'


@pytest.mark.test_name('NEX-T31987')
def test_pose_pipeline_publishes_keypoints(docker_backend, scenescape_env, params, result_recorder):
  """
  ## Name
  DLStreamer pose pipeline publishes per-person keypoints on the camera data topic

  ## Objective
  sscape_policies.detectionPolicy converts the yolo11n-pose keypoints tensor into the
  keypoints and keypoint_connections fields expected by the Scene Controller.

  ## Labels
  - Functional

  ## Steps
  1. Start the stack with the Queuing cameras running queuing-config-pose.json.
  2. Subscribe to scenescape/data/camera/atag-qcam1 and atag-qcam2.
  3. Collect person detections.
  4. Verify every detection has 17 COCO keypoints with bbox-relative x/y,
     per-joint confidence and name-pair connections.
  """
  persons = _collect_persons(params, POSE_CAMERAS)
  for camera_id, obj in persons:
    _check_keypoints(camera_id, obj)
  result_recorder.success()


@pytest.mark.test_name('NEX-T31988')
def test_non_pose_pipeline_publishes_no_keypoints(
    docker_backend, scenescape_env, params, result_recorder):
  """
  ## Name
  Non-pose DLStreamer pipelines publish detections without keypoints

  ## Objective
  sscape_policies.detectionPolicy does not add keypoint fields when the detector
  produces no keypoints tensor.

  ## Labels
  - Functional

  ## Steps
  1. Start the stack; Retail cameras run the default person detector.
  2. Subscribe to scenescape/data/camera/camera1 and camera2.
  3. Collect person detections.
  4. Verify none carries keypoints or keypoint_connections.
  """
  persons = _collect_persons(params, NON_POSE_CAMERAS)
  for camera_id, obj in persons:
    assert 'keypoints' not in obj, f'{camera_id}: unexpected keypoints in {obj}'
    assert 'keypoint_connections' not in obj, (
      f'{camera_id}: unexpected keypoint_connections in {obj}')
  result_recorder.success()
