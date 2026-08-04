# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path

import orjson
import pytest

from analytics.service import AnalyticsService
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation


def _service(visibility_topic='regulated', rewrite_all_time=False):
  service = AnalyticsService.__new__(AnalyticsService)
  service.cert = None
  service.root_cert = None
  service.rewrite_all_time = rewrite_all_time
  service.regulate_cache = {}
  service.mqtt_auth = None
  service.schema_val = MagicMock()
  service.scene_data_schema_validator = None
  service.pubsub = MagicMock()
  service.cache_manager = MagicMock()
  service.visibility_topic = visibility_topic
  return service


class TestInit:

  def test_init_wires_collaborators(self):
    with patch('analytics.service.SchemaValidation') as mock_schema, \
         patch('analytics.service.PubSub') as mock_pubsub_cls, \
         patch('analytics.service.CacheManager') as mock_cache_cls:
      mock_pubsub_instance = MagicMock()
      mock_pubsub_cls.return_value = mock_pubsub_instance

      service = AnalyticsService(
        rewrite_all_time=False, mqtt_broker='broker', mqtt_auth='auth',
        rest_url='rest', rest_auth='rest-auth', client_cert='cert',
        root_cert='root', schema_file='schema.json',
        visibility_topic='regulated', data_source='rest',
      )

    mock_schema.assert_called_once_with('schema.json', is_multi_message=True)
    mock_pubsub_cls.assert_called_once_with('auth', 'cert', 'root', 'broker', keepalive=60)
    assert mock_pubsub_instance.onConnect == service.onConnect
    mock_pubsub_instance.connect.assert_called_once()
    mock_cache_cls.assert_called_once()
    assert service.visibility_topic == 'regulated'
    assert service.scene_data_schema_validator is None

  def test_init_loads_scene_data_schema_when_file_exists(self):
    with patch('analytics.service.SchemaValidation') as mock_schema, \
         patch('analytics.service.PubSub'), \
         patch('analytics.service.CacheManager'), \
         patch('analytics.service.Path') as mock_path_cls:
      mock_path_cls.return_value.exists.return_value = True
      meta_validator = MagicMock(name='meta')
      scene_validator = MagicMock(name='scene')
      mock_schema.side_effect = [meta_validator, scene_validator]

      service = AnalyticsService(
        rewrite_all_time=False, mqtt_broker='broker', mqtt_auth='auth',
        rest_url='rest', rest_auth='rest-auth', client_cert='cert',
        root_cert='root', schema_file='schema.json',
        visibility_topic='regulated', data_source='rest',
        scene_data_schema_file='scene-data.schema.json',
      )

    assert mock_schema.call_count == 2
    mock_schema.assert_any_call('scene-data.schema.json', is_multi_message=False)
    assert service.scene_data_schema_validator is scene_validator


class TestShouldPublish:

  def test_true_when_last_is_none(self):
    service = _service()
    assert service.shouldPublish(None, 100.0, 1.0) is True

  def test_true_when_delay_elapsed(self):
    service = _service()
    assert service.shouldPublish(10.0, 11.0, 1.0) is True

  def test_false_when_within_delay(self):
    service = _service()
    assert service.shouldPublish(10.0, 10.5, 1.0) is False


class TestCalculateRate:

  def test_first_call_initialises_rate(self):
    service = _service()
    with patch('analytics.service.get_epoch_time', return_value=100.0):
      rate = service.calculateRate()

    assert service.regulate_last == 100.0
    assert rate == pytest.approx(100 / 101)

  def test_second_call_uses_running_average(self):
    service = _service()
    with patch('analytics.service.get_epoch_time', return_value=100.0):
      first_rate = service.calculateRate()
    with patch('analytics.service.get_epoch_time', return_value=105.0):
      second_rate = service.calculateRate()

    expected = (first_rate * 100 + 5.0) / 101
    assert second_rate == pytest.approx(expected)
    assert service.regulate_last == 105.0


class TestPublishDetections:

  def test_initialises_scene_attrs_and_delegates(self):
    service = _service()
    scene = SimpleNamespace(uid='scene1')
    service.publishRegulatedDetections = MagicMock()
    service.publishRegionDetections = MagicMock()

    service.publishDetections(scene, ['obj'], 10.0, 'person', {'id': 'x'}, 'cam1')

    assert scene.lastPubCount == {}
    assert scene.last_published_detection['anything'] is None
    service.publishRegulatedDetections.assert_called_once_with(
      scene, ['obj'], 'person', {'id': 'x'}, 'cam1')
    service.publishRegionDetections.assert_called_once_with(
      scene, ['obj'], 'person', {'id': 'x'})

  def test_does_not_reinitialise_existing_attrs(self):
    service = _service()
    scene = SimpleNamespace(uid='scene1', lastPubCount={'existing': 1})
    service.publishRegulatedDetections = MagicMock()
    service.publishRegionDetections = MagicMock()

    service.publishDetections(scene, [], 10.0, 'person', {}, None)

    assert scene.lastPubCount == {'existing': 1}


class TestPublishRegulatedDetections:

  def _scene_obj(self, uid='scene1', cameras=None, regulated_rate=30):
    return SimpleNamespace(uid=uid, cameras=cameras or {}, regulated_rate=regulated_rate)

  def test_first_publish_sends_message_and_records_last(self):
    service = _service()
    scene_obj = self._scene_obj()
    jdata = {'timestamp': 'ts', 'id': 'scene1', 'name': 'Scene 1'}

    with patch('analytics.service.buildDetectionsList', return_value=[{'id': 'obj-1'}]), \
         patch('analytics.service.computeCameraBounds'), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegulatedDetections(scene_obj, [SimpleNamespace(gid='obj-1')], 'person', jdata, None)

    service.pubsub.publish.assert_called_once()
    topic_arg, payload_arg = service.pubsub.publish.call_args.args
    assert topic_arg == PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id='scene1')
    published = orjson.loads(payload_arg)
    assert published['objects'] == [{'id': 'obj-1'}]
    assert service.regulate_cache['scene1']['last'] == 100.0

  def test_second_call_within_rate_interval_does_not_republish(self):
    service = _service()
    scene_obj = self._scene_obj(regulated_rate=1)  # 1 second interval
    jdata = {'timestamp': 'ts', 'id': 'scene1', 'name': 'Scene 1'}

    with patch('analytics.service.buildDetectionsList', return_value=[]), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegulatedDetections(scene_obj, [], 'person', jdata, None)
    with patch('analytics.service.buildDetectionsList', return_value=[]), \
         patch('analytics.service.get_epoch_time', return_value=100.1):
      service.publishRegulatedDetections(scene_obj, [], 'person', jdata, None)

    assert service.pubsub.publish.call_count == 1

  def test_regulated_topic_computes_camera_bounds_for_matching_objects(self):
    service = _service(visibility_topic='regulated')
    scene_obj = self._scene_obj()
    msg_obj = SimpleNamespace(gid='obj-1')
    jdata = {'timestamp': 'ts', 'id': 'scene1', 'name': 'Scene 1'}

    with patch('analytics.service.buildDetectionsList', return_value=[{'id': 'obj-1'}]), \
         patch('analytics.service.computeCameraBounds') as mock_bounds, \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegulatedDetections(scene_obj, [msg_obj], 'person', jdata, None)

    mock_bounds.assert_called_once_with(scene_obj, msg_obj, {'id': 'obj-1'})

  def test_unregulated_topic_does_not_compute_camera_bounds(self):
    service = _service(visibility_topic='unregulated')
    scene_obj = self._scene_obj()
    msg_obj = SimpleNamespace(gid='obj-1')
    jdata = {'timestamp': 'ts', 'id': 'scene1', 'name': 'Scene 1'}

    with patch('analytics.service.buildDetectionsList', return_value=[{'id': 'obj-1'}]), \
         patch('analytics.service.computeCameraBounds') as mock_bounds, \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegulatedDetections(scene_obj, [msg_obj], 'person', jdata, None)

    mock_bounds.assert_not_called()

  def test_none_topic_does_not_compute_camera_bounds(self):
    service = _service(visibility_topic='none')
    scene_obj = self._scene_obj()
    msg_obj = SimpleNamespace(gid='obj-1')
    jdata = {'timestamp': 'ts', 'id': 'scene1', 'name': 'Scene 1'}

    with patch('analytics.service.buildDetectionsList', return_value=[{'id': 'obj-1'}]), \
         patch('analytics.service.computeCameraBounds') as mock_bounds, \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegulatedDetections(scene_obj, [msg_obj], 'person', jdata, None)

    mock_bounds.assert_not_called()

  def test_camera_rate_recorded_when_camera_configured(self):
    service = _service()
    scene_obj = self._scene_obj(cameras={'cam1': object()})
    jdata = {
      'timestamp': 'ts', 'id': 'scene1', 'name': 'Scene 1', 'rate': 12.5,
      'objects': [{'visibility': ['cam1', 'cam-unknown']}],
    }

    with patch('analytics.service.buildDetectionsList', return_value=[]), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegulatedDetections(scene_obj, [], 'person', jdata, None)

    assert service.regulate_cache['scene1']['rate'] == {'cam1': 12.5}


class TestPublishRegionDetections:

  def test_publishes_when_objects_present_in_region(self):
    service = _service()
    scene = SimpleNamespace(uid='scene1', name='SceneA', regions={'roi': object()},
                             lastPubCount={})
    obj = SimpleNamespace(chain_data=SimpleNamespace(regions={'roi': {'entered': 't'}}))
    jdata = {'timestamp': '2026-01-01T00:00:00.000Z'}

    with patch('analytics.service.buildDetectionsList', return_value=[{'id': 'obj-1'}]), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegionDetections(scene, [obj], 'person', jdata)

    service.pubsub.publish.assert_called_once()
    assert scene.lastPubCount['SceneA/roi/person'] == 1

  def test_publishes_baseline_zero_when_region_never_published_before(self):
    """First observation of a region (even with no objects) is published once
    to establish the baseline of zero occupancy."""
    service = _service()
    scene = SimpleNamespace(uid='scene1', name='SceneA', regions={'roi': object()},
                             lastPubCount={})
    jdata = {'timestamp': '2026-01-01T00:00:00.000Z'}

    with patch('analytics.service.buildDetectionsList', return_value=[]), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegionDetections(scene, [], 'person', jdata)

    service.pubsub.publish.assert_called_once()
    assert scene.lastPubCount['SceneA/roi/person'] == 0

  def test_publishes_transition_to_empty_once(self):
    service = _service()
    scene = SimpleNamespace(uid='scene1', name='SceneA', regions={'roi': object()},
                             lastPubCount={'SceneA/roi/person': 1})
    jdata = {'timestamp': '2026-01-01T00:00:00.000Z'}

    with patch('analytics.service.buildDetectionsList', return_value=[]), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegionDetections(scene, [], 'person', jdata)

    service.pubsub.publish.assert_called_once()
    assert scene.lastPubCount['SceneA/roi/person'] == 0

  def test_no_further_publish_after_transition_to_empty(self):
    service = _service()
    scene = SimpleNamespace(uid='scene1', name='SceneA', regions={'roi': object()},
                             lastPubCount={'SceneA/roi/person': 0})
    jdata = {'timestamp': '2026-01-01T00:00:00.000Z'}

    with patch('analytics.service.buildDetectionsList', return_value=[]), \
         patch('analytics.service.get_epoch_time', return_value=100.0):
      service.publishRegionDetections(scene, [], 'person', jdata)

    service.pubsub.publish.assert_not_called()


class TestHandleSceneDataMessage:

  def _message(self, scene_id='scene1', thing_type='person', objects=None, timestamp='2026-01-01T00:00:00.000Z'):
    payload = orjson.dumps({'objects': objects or [], 'timestamp': timestamp})
    return SimpleNamespace(topic=f'scenescape/data/scene/{scene_id}/{thing_type}', payload=payload)

  def test_unknown_scene_returns_early(self):
    service = _service()
    service.cache_manager.sceneWithID.return_value = None
    message = self._message()

    service.handleSceneDataMessage(None, None, message)

    service.cache_manager.sceneWithID.assert_called_once_with('scene1')

  def test_invalid_json_returns_early(self):
    service = _service()
    message = SimpleNamespace(
      topic='scenescape/data/scene/scene1/person',
      payload=b'not-json',
    )

    service.handleSceneDataMessage(None, None, message)

    service.cache_manager.sceneWithID.assert_not_called()

  def test_invalid_utf8_returns_early(self):
    service = _service()
    message = SimpleNamespace(
      topic='scenescape/data/scene/scene1/person',
      payload=b'\xff\xfe',
    )

    service.handleSceneDataMessage(None, None, message)

    service.cache_manager.sceneWithID.assert_not_called()

  def test_invalid_scene_data_schema_returns_early(self):
    service = _service()
    service.scene_data_schema_validator = MagicMock()
    service.scene_data_schema_validator.validate.return_value = False
    scene = MagicMock()
    service.cache_manager.sceneWithID.return_value = scene
    service.publishDetections = MagicMock()
    message = self._message()

    service.handleSceneDataMessage(None, None, message)

    service.scene_data_schema_validator.validate.assert_called_once()
    scene.updateTrackedObjects.assert_not_called()
    scene._updateVisible.assert_not_called()
    scene._updateEvents.assert_not_called()
    service.publishDetections.assert_not_called()

  def test_known_scene_processes_and_publishes(self):
    service = _service()
    scene = MagicMock()
    scene.getTrackedObjects.return_value = ['analytics-obj']
    service.cache_manager.sceneWithID.return_value = scene
    service.publishDetections = MagicMock()
    message = self._message()

    service.handleSceneDataMessage(None, None, message)

    scene.updateTrackedObjects.assert_called_once_with('person', [])
    scene.getTrackedObjects.assert_called_once_with('person')
    scene._updateVisible.assert_called_once_with(['analytics-obj'])
    scene._updateEvents.assert_called_once()
    method_names = [name for name, _, _ in scene.method_calls]
    assert method_names.index('_updateVisible') < method_names.index('_updateEvents')
    args, kwargs = scene._updateEvents.call_args
    assert args[0] == 'person'
    assert args[2] == ['analytics-obj']
    assert kwargs['publish_fn'] == service.pubsub.publish
    service.publishDetections.assert_called_once()


class TestHandleSensorMessage:

  def _message(self, payload_dict):
    return SimpleNamespace(
      topic='scenescape/data/sensor/sensor1',
      payload=orjson.dumps(payload_dict),
    )

  def test_invalid_json_returns_early(self):
    service = _service()
    message = SimpleNamespace(
      topic='scenescape/data/sensor/sensor1',
      payload=b'not-json',
    )

    service.handleSensorMessage(None, None, message)

    service.schema_val.validateMessage.assert_not_called()
    service.cache_manager.sceneWithSensorID.assert_not_called()

  def test_invalid_utf8_returns_early(self):
    service = _service()
    message = SimpleNamespace(
      topic='scenescape/data/sensor/sensor1',
      payload=b'\xff\xfe',
    )

    service.handleSensorMessage(None, None, message)

    service.schema_val.validateMessage.assert_not_called()
    service.cache_manager.sceneWithSensorID.assert_not_called()

  def test_invalid_schema_returns_early(self):
    service = _service()
    service.schema_val.validateMessage.return_value = False
    message = self._message({'id': 'sensor1', 'value': 1, 'timestamp': '2026-01-01T00:00:00.000Z'})

    service.handleSensorMessage(None, None, message)

    service.cache_manager.sceneWithSensorID.assert_not_called()

  def test_unknown_scene_returns_early(self):
    service = _service()
    service.schema_val.validateMessage.return_value = True
    service.cache_manager.sceneWithSensorID.return_value = None
    message = self._message({'id': 'sensor1', 'value': 1, 'timestamp': '2026-01-01T00:00:00.000Z'})

    service.handleSensorMessage(None, None, message)

  def test_processing_failure_invalidates_cache(self):
    service = _service()
    service.schema_val.validateMessage.return_value = True
    scene = MagicMock()
    scene.processSensorData.return_value = False
    service.cache_manager.sceneWithSensorID.return_value = scene
    message = self._message({'id': 'sensor1', 'value': 1, 'timestamp': '2026-01-01T00:00:00.000Z'})

    with patch('analytics.service.publish_events') as mock_publish:
      service.handleSensorMessage(None, None, message)

    service.cache_manager.invalidate.assert_called_once()
    mock_publish.assert_not_called()

  def test_success_path_publishes_events(self):
    service = _service()
    service.schema_val.validateMessage.return_value = True
    scene = MagicMock(uid='scene1', name='Scene 1')
    scene.processSensorData.return_value = True
    service.cache_manager.sceneWithSensorID.return_value = scene
    message = self._message({'id': 'sensor1', 'value': 1, 'timestamp': '2026-01-01T00:00:00.000Z'})

    with patch('analytics.service.publish_events') as mock_publish:
      service.handleSensorMessage(None, None, message)

    mock_publish.assert_called_once_with(scene, '2026-01-01T00:00:00.000Z', service.pubsub.publish)

  def test_rewrite_all_time_overrides_timestamp(self):
    service = _service(rewrite_all_time=True)
    service.schema_val.validateMessage.return_value = True
    scene = MagicMock(uid='scene1', name='Scene 1')
    scene.processSensorData.return_value = True
    service.cache_manager.sceneWithSensorID.return_value = scene
    message = self._message({'id': 'sensor1', 'value': 1, 'timestamp': 'ignored'})

    with patch('analytics.service.publish_events') as mock_publish, \
         patch('analytics.service.get_epoch_time', return_value=200.0), \
         patch('analytics.service.get_iso_time', return_value='rewritten-ts'):
      service.handleSensorMessage(None, None, message)

    scene.processSensorData.assert_called_once()
    call_jdata = scene.processSensorData.call_args.args[0]
    assert call_jdata['timestamp'] == 'rewritten-ts'
    mock_publish.assert_called_once_with(scene, 'rewritten-ts', service.pubsub.publish)


class TestHandleDatabaseMessage:

  def test_update_command_calls_both_updaters(self):
    service = _service()
    service.updateSubscriptions = MagicMock()
    service.updateRegulateCache = MagicMock()
    message = SimpleNamespace(payload=b'update')

    service.handleDatabaseMessage(None, None, message)

    service.updateSubscriptions.assert_called_once()
    service.updateRegulateCache.assert_called_once()

  def test_other_command_is_noop(self):
    service = _service()
    service.updateSubscriptions = MagicMock()
    service.updateRegulateCache = MagicMock()
    message = SimpleNamespace(payload=b'noop')

    service.handleDatabaseMessage(None, None, message)

    service.updateSubscriptions.assert_not_called()
    service.updateRegulateCache.assert_not_called()

  def test_exception_in_updater_is_caught(self):
    service = _service()
    service.updateSubscriptions = MagicMock(side_effect=RuntimeError("boom"))
    service.updateRegulateCache = MagicMock()
    message = SimpleNamespace(payload=b'update')

    service.handleDatabaseMessage(None, None, message)  # must not raise


class TestOnConnect:

  def test_nonzero_rc_exits_process(self):
    service = _service()

    with pytest.raises(SystemExit):
      service.onConnect(None, None, None, 1)

  def test_zero_rc_subscribes(self):
    service = _service()
    service.updateSubscriptions = MagicMock()

    service.onConnect(None, None, None, 0)

    assert service.subscribed == set()
    service.updateSubscriptions.assert_called_once()
    service.pubsub.addCallback.assert_called_once_with(
      PubSub.formatTopic(PubSub.CMD_DATABASE), service.handleDatabaseMessage)


class TestUpdateSubscriptions:

  def test_subscribes_to_scene_and_sensor_topics(self):
    service = _service()
    scene = SimpleNamespace(uid='scene1', sensors={'sensor1': object()})
    service.cache_manager.allScenes.return_value = [scene]

    service.updateSubscriptions()

    service.cache_manager.invalidate.assert_called_once()
    assert service.scenes == [scene]
    add_calls = [c.args[0] for c in service.pubsub.addCallback.call_args_list]
    assert PubSub.formatTopic(PubSub.DATA_SCENE, scene_id='scene1', thing_type='+') in add_calls
    assert PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id='sensor1') in add_calls

  def test_removes_stale_subscriptions(self):
    service = _service()
    stale_topic = 'stale/topic'
    service.subscribed = {(stale_topic, MagicMock())}
    service.cache_manager.allScenes.return_value = []

    service.updateSubscriptions()

    service.pubsub.removeCallback.assert_called_once_with(stale_topic)
    assert service.subscribed == set()


class TestUpdateRegulateCache:

  def test_pops_scenes_no_longer_present(self):
    service = _service()
    service.regulate_cache = {'scene1': {}, 'scene2': {}}
    service.scenes = []

    service.updateRegulateCache()

    assert service.regulate_cache == {}

  def test_keeps_scenes_still_present(self):
    service = _service()
    service.regulate_cache = {'scene1': {}}
    service.scenes = [SimpleNamespace(uid='scene1')]

    service.updateRegulateCache()

    assert 'scene1' in service.regulate_cache


_SCENE_DATA_SCHEMA = (
  Path(__file__).resolve().parents[3]
  / "tracker"
  / "schema"
  / "scene-data.schema.json"
)


class TestHandleSceneDataMessageSchemaAndVisibility:

  def _message(self, payload_dict, scene_id='scene1', thing_type='person'):
    return SimpleNamespace(
      topic=f'scenescape/data/scene/{scene_id}/{thing_type}',
      payload=orjson.dumps(payload_dict),
    )

  def test_controller_shaped_payload_passes_real_schema_and_processes(self):
    service = _service()
    service.scene_data_schema_validator = SchemaValidation(
      str(_SCENE_DATA_SCHEMA), is_multi_message=False)
    scene = MagicMock()
    scene.getTrackedObjects.return_value = []
    service.cache_manager.sceneWithID.return_value = scene
    service.publishDetections = MagicMock()
    payload = {
      'id': 'scene1',
      'name': 'Demo',
      'timestamp': '2026-01-20T10:05:01.590Z',
      'unique_detection_count': 1,
      'rate': 10.0,
      'objects': [{
        'id': 'track-1',
        'type': 'person',
        'translation': [1.0, 2.0, 0.0],
        'velocity': [0.0, 0.0, 0.0],
        'size': [0.5, 0.5, 1.8],
        'rotation': [0, 0, 0, 1],
        'confidence': None,
      }],
    }

    service.handleSceneDataMessage(None, None, self._message(payload))

    scene.updateTrackedObjects.assert_called_once()
    scene._updateVisible.assert_called_once()
    scene._updateEvents.assert_called_once()
    service.publishDetections.assert_called_once()

  def test_tracker_shaped_payload_passes_real_schema_and_processes(self):
    service = _service()
    service.scene_data_schema_validator = SchemaValidation(
      str(_SCENE_DATA_SCHEMA), is_multi_message=False)
    scene = MagicMock()
    scene.getTrackedObjects.return_value = []
    service.cache_manager.sceneWithID.return_value = scene
    service.publishDetections = MagicMock()
    payload = {
      'id': '3bc091c7-e449-46a0-9540-29c499bca18c',
      'name': 'Retail',
      'timestamp': '2026-01-20T10:05:01.590Z',
      'objects': [{
        'id': '8cce2bc7-51fc-4a6e-8c5d-a73ac72d3eb2',
        'category': 'person',
        'translation': [-0.33, 2.48, 0.0],
        'velocity': [-0.04, 0.2, 0.0],
        'size': [0.5, 0.5, 1.85],
        'rotation': [0, 0, 0, 1],
      }],
    }

    service.handleSceneDataMessage(None, None, self._message(payload))

    scene.updateTrackedObjects.assert_called_once()
    service.publishDetections.assert_called_once()

  def test_omitted_visibility_filled_before_events_on_real_scene(self):
    """Glue: ingest None visibility → FOV fill → events see non-empty list."""
    from analytics.adapters.scene_model import AnalyticsScene

    service = _service()
    scene = AnalyticsScene('Demo', None)
    scene.uid = 'scene1'
    scene.cameras['cam1'] = SimpleNamespace(
      cameraID='cam1',
      pose=SimpleNamespace(
        regionOfView=SimpleNamespace(isPointWithin=lambda pt: True)),
    )
    service.cache_manager.sceneWithID.return_value = scene
    service.publishDetections = MagicMock()

    captured = {}

    def _capture_events(detection_type, when, objects, publish_fn=None):
      captured['visibility'] = [getattr(o, 'visibility', None) for o in objects]

    scene._updateEvents = _capture_events

    payload = {
      'id': 'scene1',
      'name': 'Demo',
      'timestamp': '2026-01-20T10:05:01.590Z',
      'objects': [{
        'id': 'obj-1',
        'category': 'person',
        'translation': [1.0, 1.0, 0.0],
        'velocity': [0.0, 0.0, 0.0],
        'size': [0.5, 0.5, 1.8],
        'rotation': [0, 0, 0, 1],
      }],
    }

    service.handleSceneDataMessage(None, None, self._message(payload))

    assert captured.get('visibility') == [['cam1']]
    service.publishDetections.assert_called_once()
