# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify requested image GIDs against real regulated tracks in both modes."""

import base64
import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import pytest
import requests

from scene_common.mqtt import PubSub
from tests.utils.profiles import TRACK_ANNOTATION_CONTROLLER, TRACK_ANNOTATION_TRACKER
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec


CAMERA_ID = 'atag-qcam1'
PIPELINE_API = 'http://localhost:8081'
MESSAGE_TIMEOUT = 60
MAX_TRACK_AGE_SECONDS = 1
SCENESCAPE_SPEC = FuncTestSpec(profile=TRACK_ANNOTATION_CONTROLLER, auth=AUTH_CONTROLLER)


@pytest.fixture
def _env_matrix_setup(request, repo_root, tmp_path, monkeypatch):
  """Install test-only property mappings before the selected stack starts."""
  if request.config.getoption('--backend') != 'docker':
    pytest.skip('Track annotation uses the Docker DLSPS API')
  source = Path(repo_root) / 'sample_data/demo_scenes/Queuing/queuing-config.json'
  config = json.loads(source.read_text())
  for pipeline in config['config']['pipelines']:
    for parameter, property_name, value_type in (
        ('annotate_track_ids', 'annotate-track-ids', 'boolean'),
        ('track_topic', 'track-topic', 'string')):
      pipeline['parameters']['properties'][parameter] = {
        'element': {'name': 'datapublisher', 'property': property_name},
        'type': value_type,
      }
  destination = tmp_path / 'track-annotation.json'
  destination.write_text(json.dumps(config))
  monkeypatch.setenv('TRACK_ANNOTATION_CONFIG', str(destination))
  request.node._scenescape_spec = request.param


def _stop_pipelines(session):
  response = session.get(f'{PIPELINE_API}/pipelines/status', timeout=10)
  response.raise_for_status()
  for instance in response.json():
    response = session.delete(f"{PIPELINE_API}/pipelines/{instance['id']}", timeout=30)
    response.raise_for_status()


def _start_pipeline(session, name, payload):
  response = session.post(
    f'{PIPELINE_API}/pipelines/user_defined_pipelines/{name}', json=payload, timeout=30)
  response.raise_for_status()


@pytest.fixture
def annotation_pipeline(_env_matrix_setup, scenescape_env, repo_root):
  """Restart one real video pipeline with selected annotation settings."""
  source = Path(repo_root) / 'sample_data/demo_scenes/Queuing/queuing-config.json'
  originals = json.loads(source.read_text())['config']['pipelines']
  session = requests.Session()
  session.trust_env = False

  def configure(enabled, topic):
    _stop_pipelines(session)
    payload = json.loads(json.dumps(originals[0]['payload']))
    payload['parameters'].update(annotate_track_ids=enabled, track_topic=topic)
    _start_pipeline(session, originals[0]['name'], payload)

  try:
    yield configure
  finally:
    try:
      _stop_pipelines(session)
      for pipeline in originals:
        _start_pipeline(session, pipeline['name'], pipeline['payload'])
    finally:
      session.close()


def _timestamp(value):
  return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def _has_matching_tracks(image, snapshots, enabled):
  if not enabled:
    return True
  image_ids = set(image['track_ids'])
  return any(
    abs(timestamp - _timestamp(image['timestamp'])) <= MAX_TRACK_AGE_SECONDS
    and image_ids <= gids
    for timestamp, gids in snapshots
  )


def _check_image(image, enabled):
  jpeg = base64.b64decode(image['image'], validate=True)
  assert jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9'), 'Invalid JPEG'
  if not enabled:
    assert 'track_ids' not in image, 'Disabled annotation changed the image payload'
    return True
  assert isinstance(image.get('track_ids'), list), 'Missing track_ids array'
  assert len(image['track_ids']) == len(set(image['track_ids'])), 'Duplicate GIDs'
  return bool(image['track_ids'])


def _requested_image(client, images, snapshots, enabled):
  images.clear()
  deadline = time.monotonic() + MESSAGE_TIMEOUT
  next_request = 0
  candidate = None
  while time.monotonic() < deadline:
    client.client.loop(timeout=0.2)
    if time.monotonic() >= next_request:
      client.publish(PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=CAMERA_ID), 'getimage')
      next_request = time.monotonic() + 1
    if images:
      image = images.popleft()
      if _check_image(image, enabled):
        candidate = image
    if candidate is not None and _has_matching_tracks(candidate, snapshots, enabled):
      return candidate
  pytest.fail('No requested image with matching regulated GIDs' if enabled else 'No requested image')


@pytest.mark.test_name('NEX-T30954')
@pytest.mark.parametrize('_env_matrix_setup', [
  pytest.param(
    FuncTestSpec(profile=TRACK_ANNOTATION_CONTROLLER, auth=AUTH_CONTROLLER),
    id='scene-controller'),
  pytest.param(
    FuncTestSpec(profile=TRACK_ANNOTATION_TRACKER, auth=AUTH_CONTROLLER),
    id='cpp-tracker'),
], indirect=True)
def test_requested_image_track_ids(
    _env_matrix_setup, annotation_pipeline, rest, params, result_recorder):
  """
  ## Name
  Requested camera images contain GIDs matching regulated tracks in both tracking modes

  ## Objective
  Requested GIDs match camera bounds; disabled annotation preserves legacy images.

  ## Labels
  - Functional

  ## Steps
  1. Start Scene Controller + Analytics. Enable annotate-track-ids and set track-topic to the scene's regulated topic.
  2. Subscribe to regulated tracks and camera images.
  3. Send getimage to scenescape/cmd/camera/atag-qcam1.
  4. Compare image GIDs with regulated messages.
  5. Disable annotation and request another image.
  6. Repeat with C++ Tracker + Analytics, without Scene Controller running.
  """
  scenes = rest.getScenes({'name': 'Queuing'})['results']
  assert scenes, 'Queuing baseline scene is missing'
  scene = scenes[0]
  assert CAMERA_ID in {camera['uid'] for camera in scene['cameras']}
  topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene['uid'])
  image_topic = PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id=CAMERA_ID)
  snapshots = deque(maxlen=2000)
  images = deque(maxlen=20)
  subscribed = []

  def on_connect(connection, userdata, flags, result):
    assert result == 0, f'MQTT connect failed: {result}'
    connection.subscribe([(topic, 0), (image_topic, 0)])

  def on_message(connection, userdata, message):
    payload = json.loads(message.payload)
    if message.topic == topic:
      gids = {
        obj['id'] for obj in payload['objects']
        if CAMERA_ID in obj.get('camera_bounds', {})
      }
      snapshots.append((_timestamp(payload['timestamp']), gids))
    elif message.topic == image_topic:
      images.append(payload)

  client = PubSub(params['auth'], None, params['rootcert'],
                  params['broker_url'], params['broker_port'])
  client.onConnect = on_connect
  client.onMessage = on_message
  client.client.on_subscribe = lambda *_args: subscribed.append(True)
  try:
    client.connect()
    deadline = time.monotonic() + 10
    while not subscribed and time.monotonic() < deadline:
      client.client.loop(timeout=0.2)
    assert subscribed, 'MQTT subscription was not acknowledged'
    annotation_pipeline(True, topic)
    _requested_image(client, images, snapshots, enabled=True)
    annotation_pipeline(False, topic)
    _requested_image(client, images, snapshots, enabled=False)
    result_recorder.success()
  finally:
    client.disconnect()
