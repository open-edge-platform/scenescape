# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Resolved platform output uses the pose cache, not the object-tracking lifecycle."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import orjson
import pytest

from controller.external_source import ExternalSourcePoseCache
from controller.scene_controller import SceneController
from controller.source_state import SourceStatePublisher
from scene_common.earth_lla import convertLLAToECEF
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import get_iso_time


@pytest.fixture
def source_setup():
  pubsub = MagicMock()
  pubsub.publish.return_value.rc = 0
  publisher = SourceStatePublisher(pubsub)
  cache = ExternalSourcePoseCache(on_remove=publisher.remove)
  scene = SimpleNamespace(uid='scene-1', trs_xyz_to_lla=None)
  camera = {
    'id': 'front',
    'mount': {'translation': [0.2, 0, -0.1],
              'rotation': [-0.5, 0.5, -0.5, 0.5]},
    'intrinsics': {'fx': 800, 'fy': 810, 'cx': 600, 'cy': 350},
    'objects': [],
  }
  message = {
    'pose': {'reference_frame': 'scene', 'translation': [2, 3, 10],
             'rotation': [0, 0, 0, 1]},
    'cameras': [camera],
    'objects': [],
  }
  cache.resolveMessage(scene, 'drone-1', message, 100, trusted_scene_pose=True)
  return scene, message, cache, publisher, pubsub


def _payload(pubsub):
  return orjson.loads(pubsub.publish.call_args.args[1])

def _publish(publisher, cache, scene_uid, source_id, message, when):
  scene = SimpleNamespace(uid=scene_uid, trs_xyz_to_lla=None)
  _, state, reason = cache.resolveMessage(
    scene, source_id, message, when, trusted_scene_pose=True)
  if reason is None:
    publisher.publish(scene_uid, source_id, state)


def test_retained_snapshot_matches_output_contract(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  topic, raw_payload = pubsub.publish.call_args.args
  assert topic == 'scenescape/data/source/scene-1/drone-1'
  assert PubSub.parseTopic(topic)['source_id'] == 'drone-1'
  template = PubSub.getTopicByTemplateName('DATA_SOURCE').template
  assert PubSub.match_topic(template, topic) == ('scene-1', 'drone-1')
  assert PubSub.match_topic(template, topic + '/extra') is None
  assert pubsub.publish.call_args.kwargs == {'qos': 1, 'retain': True}
  payload = orjson.loads(raw_payload)
  assert payload['scene_id'] == scene.uid
  assert payload['source_id'] == 'drone-1'
  assert payload['translation'] == [2, 3, 10]
  assert payload['rotation'] == [0, 0, 0, 1]
  assert payload['cameras'] == [{key: value for key, value in message['cameras'][0].items()
                                 if key != 'objects'}]
  assert 'resolution' not in payload
  assert 'resolution' not in payload['cameras'][0]
  assert 'objects' not in payload
  schema_path = Path(__file__).resolve().parents[3] / 'controller/src/schema/metadata.schema.json'
  schema = SchemaValidation(str(schema_path), is_multi_message=True)
  assert schema.validateMessage('source_state', payload, True)
  del payload['expires_at']
  assert not schema.validateMessage('source_state', payload, True)


def test_cached_pose_does_not_gain_a_new_acquisition_time_or_expiry(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  _publish(publisher, cache, scene.uid, 'drone-1', {}, 110)
  payload = _payload(pubsub)
  assert payload['timestamp'] == get_iso_time(100)
  assert payload['expires_at'] == get_iso_time(130)
  assert payload['cameras'][0]['intrinsics'] == message['cameras'][0]['intrinsics']

def test_pose_refresh_replaces_complete_camera_snapshot(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  pose = dict(message['pose'], translation=[4, 5, 12])
  camera = dict(message['cameras'][0],
                intrinsics=dict(message['cameras'][0]['intrinsics'], fx=1000))
  updated = dict(message, pose=pose, cameras=[camera])
  _publish(publisher, cache, scene.uid, 'drone-1', updated, 110)
  assert _payload(pubsub)['translation'] == [4, 5, 12]
  assert _payload(pubsub)['cameras'][0]['mount'] == message['cameras'][0]['mount']
  assert _payload(pubsub)['expires_at'] == get_iso_time(140)
  assert _payload(pubsub)['cameras'][0]['intrinsics']['fx'] == 1000
  cache.sweepExpired(141)
  cache.resolve(scene, 'drone-1', pose, 150, trusted_scene_pose=True)
  _publish(publisher, cache, scene.uid, 'drone-1', {}, 150)
  assert 'cameras' not in _payload(pubsub)


def test_out_of_order_pose_and_calibration_do_not_regress_state(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  old_camera = dict(message['cameras'][0],
                    intrinsics=dict(message['cameras'][0]['intrinsics'], fx=400),
                    mount={'translation': [0, 0, 0], 'rotation': [0, 0, 0, 1]})
  old_message = dict(message, pose=dict(message['pose'], translation=[0, 0, 0]),
                     cameras=[old_camera])
  _publish(publisher, cache, scene.uid, 'drone-1', old_message, 90)
  payload = _payload(pubsub)
  assert payload['translation'] == [2, 3, 10]
  assert payload['cameras'][0]['intrinsics']['fx'] == 800
  assert payload['cameras'][0]['mount'] == message['cameras'][0]['mount']


@pytest.mark.parametrize('scene_uid,when', [('scene-2', 110), ('scene-1', 131)])
def test_missing_or_expired_source_is_not_published(source_setup, scene_uid, when):
  _, _, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene_uid, 'drone-1', {}, when)
  pubsub.publish.assert_not_called()


@pytest.mark.parametrize('remove', ['sweep', 'invalidate'])
def test_removal_clears_retained_snapshot(source_setup, remove):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  if remove == 'sweep':
    assert cache.sweepExpired(131) == 1
  else:
    cache.invalidate(scene_uid=scene.uid)
  pubsub.publish.assert_called_with(
    'scenescape/data/source/scene-1/drone-1', b'', qos=1, retain=True)


def test_scene_and_source_snapshots_are_isolated(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  other = SimpleNamespace(uid='scene-2', trs_xyz_to_lla=None)
  pose = dict(message['pose'], translation=[20, 30, 40])
  cache.resolve(other, 'drone-1', pose, 100, trusted_scene_pose=True)
  cache.resolve(scene, 'drone-2', pose, 100, trusted_scene_pose=True)
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  _publish(publisher, cache, other.uid, 'drone-1', {}, 100)
  assert _payload(pubsub)['translation'] == [20, 30, 40]
  assert 'cameras' not in _payload(pubsub)
  assert cache.resolveMessage(scene, 'drone-2', {}, 100)[1].cameras is None


def test_wgs84_output_uses_resolved_scene_coordinates(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  scene.trs_xyz_to_lla = np.eye(4)
  scene.trs_xyz_to_lla[:3, 3] = convertLLAToECEF([37.4, -122.1, 10])
  pose = {'reference_frame': 'wgs84', 'lat_long_alt': [37.4, -122.1, 10]}
  _, state, reason = cache.resolveMessage(
    scene, 'drone-1', dict(message, pose=pose), 110)
  assert reason is None
  publisher.publish(scene.uid, 'drone-1', state)
  np.testing.assert_allclose(_payload(pubsub)['translation'], [0, 0, 0], atol=1e-8)


def test_publisher_logs_mqtt_queue_failure(source_setup, monkeypatch):
  scene, message, cache, publisher, pubsub = source_setup
  error = MagicMock()
  monkeypatch.setattr('controller.source_state.log.error', error)
  pubsub.publish.return_value.rc = 4
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  assert 'mqtt_rc=4' in error.call_args.args[0]


def test_handler_publishes_pose_only_state_and_rejects_untrusted_pose(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  controller = SceneController.__new__(SceneController)
  controller.external_source_pose_cache = cache
  controller.source_state_publisher = publisher
  controller.trusted_positioning_sources = {'drone-1'}
  message['source_id'] = 'drone-1'
  controller._handleExternalSourceObject(scene, message, 'person', 110)
  assert _payload(pubsub)['timestamp'] == get_iso_time(110)
  pubsub.reset_mock()
  controller.trusted_positioning_sources = set()
  controller._handleExternalSourceObject(scene, message, 'person', 120)
  pubsub.publish.assert_not_called()


def test_drone_configuration_without_pose_does_not_change_snapshot(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  camera = dict(message['cameras'][0],
                intrinsics=dict(message['cameras'][0]['intrinsics'], fx=400))
  _publish(publisher, cache, scene.uid, 'drone-1', {'cameras': [camera]}, 110)
  assert _payload(pubsub)['cameras'][0]['intrinsics']['fx'] == 400
  assert _payload(pubsub)['timestamp'] == get_iso_time(100)


def test_new_snapshot_clears_omitted_distortion(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  camera = dict(message['cameras'][0], distortion={'k1': 0.1})
  _publish(publisher, cache, scene.uid, 'drone-1', dict(message, cameras=[camera]), 100)
  assert _payload(pubsub)['cameras'][0]['distortion'] == {'k1': 0.1}
  _publish(publisher, cache, scene.uid, 'drone-1', message, 110)
  assert 'distortion' not in _payload(pubsub)['cameras'][0]


def test_legacy_source_accepts_intrinsics_without_pose(source_setup):
  scene, message, _, _, _ = source_setup
  cache = ExternalSourcePoseCache()
  cache.resolve(scene, 'legacy', message['pose'], 100, trusted_scene_pose=True)
  intrinsics, reason = cache.resolveIntrinsics(
    scene.uid, 'legacy', {'fx': 400, 'fy': 410, 'cx': 300, 'cy': 175}, None, 110)
  assert reason is None
  assert intrinsics.intrinsics[0, 0] == 400
  _, state, reason = cache.resolveMessage(scene, 'legacy', {}, 110)
  assert reason is None
  assert state.intrinsics['fx'] == 400
  assert state.when == 100


@pytest.mark.parametrize('field', ['mount', 'intrinsics', 'objects'])
def test_incomplete_drone_pose_keeps_previous_snapshot(source_setup, field):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  incomplete = dict(message)
  incomplete['cameras'] = [dict(message['cameras'][0])]
  del incomplete['cameras'][0][field]
  pose, state, reason = cache.resolveMessage(
    scene, 'drone-1', incomplete, 110, trusted_scene_pose=True)
  assert pose is None and state is None
  assert reason == 'invalid_intrinsics'
  assert cache.resolveMessage(scene, 'drone-1', {}, 110)[1].when == 100


def test_handler_rejects_camera_pixels_without_camera_configuration(source_setup):
  scene, message, cache, publisher, pubsub = source_setup
  _publish(publisher, cache, scene.uid, 'drone-1', message, 100)
  pubsub.reset_mock()
  controller = SceneController.__new__(SceneController)
  controller.external_source_pose_cache = cache
  controller.source_state_publisher = publisher
  controller.trusted_positioning_sources = set()
  message = {'source_id': 'drone-1', 'objects': [], 'cameras': [{
    'id': 'front',
    'objects': [{'category': 'person',
                 'bounding_box_px': {'x': 1, 'y': 1, 'width': 2, 'height': 2}}],
  }]}
  controller._handleExternalSourceObject(scene, message, 'person', 110)
  pubsub.publish.assert_not_called()


@pytest.mark.parametrize('fx', [0, -1, float('inf'), float('nan')])
def test_handler_does_not_publish_invalid_calibration(source_setup, fx):
  scene, message, cache, publisher, pubsub = source_setup
  controller = SceneController.__new__(SceneController)
  controller.external_source_pose_cache = cache
  controller.source_state_publisher = publisher
  controller.trusted_positioning_sources = {'drone-1'}
  message['source_id'] = 'drone-1'
  message['cameras'][0]['intrinsics']['fx'] = fx
  controller._handleExternalSourceObject(scene, message, 'person', 110)
  pubsub.publish.assert_not_called()
