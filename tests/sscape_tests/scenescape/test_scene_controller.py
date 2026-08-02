#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pytest
import tempfile
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from controller.scene_controller import SceneController


class TestSceneControllerExtractTrackerRate:
  """Unit tests for SceneController._extractTrackerRate."""

  def test_extract_tracker_rate_returns_default_when_missing(self):
    """Returns default fps when parameter is not present in config."""
    scene_controller = SceneController.__new__(SceneController)

    tracker_config = {}
    default_rate = 15

    result = scene_controller._extractTrackerRate(
      tracker_config,
      'effective_object_update_rate',
      default_rate,
    )

    assert result == default_rate

  @pytest.mark.parametrize(
    'raw_rate,expected_rate',
    [
      (30, 30),
      ('24', 24),
    ],
  )
  def test_extract_tracker_rate_returns_valid_integer_rates(self, raw_rate, expected_rate):
    """Returns parsed integer when config contains a valid rate."""
    scene_controller = SceneController.__new__(SceneController)
    tracker_config = {'effective_object_update_rate': raw_rate}

    result = scene_controller._extractTrackerRate(
      tracker_config,
      'effective_object_update_rate',
      15,
    )

    assert result == expected_rate

  def test_extract_tracker_rate_accepts_min_and_max_boundaries(self):
    """Accepts values equal to provided min/max boundaries."""
    scene_controller = SceneController.__new__(SceneController)

    min_config = {'effective_object_update_rate': 10}
    max_config = {'effective_object_update_rate': 30}

    min_result = scene_controller._extractTrackerRate(
      min_config,
      'effective_object_update_rate',
      15,
      min_rate=10,
    )
    max_result = scene_controller._extractTrackerRate(
      max_config,
      'effective_object_update_rate',
      15,
      max_rate=30,
    )

    assert min_result == 10
    assert max_result == 30

  @pytest.mark.parametrize(
    'raw_rate,min_rate,max_rate',
    [
      (0, None, None),
      ('abc', None, None),
      (5, 10, None),
      (45, None, 30),
    ],
  )
  def test_extract_tracker_rate_raises_for_invalid_values(
    self,
    raw_rate,
    min_rate,
    max_rate,
  ):
    """Raises ValueError for malformed or out-of-range rates."""
    scene_controller = SceneController.__new__(SceneController)
    tracker_config = {'effective_object_update_rate': raw_rate}

    with pytest.raises(ValueError, match='Invalid value for effective_object_update_rate'):
      scene_controller._extractTrackerRate(
        tracker_config,
        'effective_object_update_rate',
        30,
        min_rate=min_rate,
        max_rate=max_rate,
      )


class _BoolRaises:
  """Helper that raises during bool conversion to exercise exception path."""

  def __bool__(self):
    raise TypeError('cannot convert to bool')


class TestSceneControllerExtractTimeChunkingEnabled:
  """Unit tests for SceneController._extractTimeChunkingEnabled."""

  def test_extract_time_chunking_enabled_defaults_to_true_when_missing(self):
    """Sets time chunking to True when key is missing."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.tracker_config_data = {}

    scene_controller._extractTimeChunkingEnabled({})

    assert scene_controller.tracker_config_data['time_chunking_enabled'] is True

  @pytest.mark.parametrize(
    'raw_value,expected_value',
    [
      (True, True),
      (False, False),
      (1, True),
      (0, False),
    ],
  )
  def test_extract_time_chunking_enabled_sets_boolean_value(self, raw_value, expected_value):
    """Stores bool-converted value when key is present."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.tracker_config_data = {}

    scene_controller._extractTimeChunkingEnabled({'time_chunking_enabled': raw_value})

    assert scene_controller.tracker_config_data['time_chunking_enabled'] is expected_value

  def test_extract_time_chunking_enabled_raises_for_unboolable_value(self):
    """Raises ValueError when bool conversion fails."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.tracker_config_data = {}

    with pytest.raises(ValueError, match='Invalid value for time_chunking_enabled'):
      scene_controller._extractTimeChunkingEnabled({'time_chunking_enabled': _BoolRaises()})


class TestSceneControllerExtractReidConfigData:
  """Regression tests: extractReidConfigData must read and store all reid config fields."""

  def test_extracts_all_known_reid_config_fields(self):
    """All reid config keys are loaded into scene_controller.reid_config_data."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.reid_config_data = {}

    reid_config = {
      'feature_accumulation_threshold': 8,
      'similarity_metric': 'L2',
      'similarity_threshold': 55,
      'stale_feature_timeout_secs': 7.5,
      'stale_feature_check_interval_secs': 2.0,
      'minimum_bbox_area': 5000,
      'feature_slice_size': 10,
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
      json.dump(reid_config, f)
      tmp_path = f.name

    try:
      scene_controller.extractReidConfigData(tmp_path)
    finally:
      os.unlink(tmp_path)

    assert scene_controller.reid_config_data == reid_config

  def test_extract_reid_config_data_raises_for_missing_file(self):
    """Missing REID config file propagates FileNotFoundError."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.reid_config_data = {}

    with pytest.raises(FileNotFoundError):
      scene_controller.extractReidConfigData('definitely-missing-reid-config.json')


class TestSceneControllerExtractPoseAdjustmentConfigData:
  """Regression tests for pose-adjustment config file loading."""

  def test_extracts_pose_adjustment_routes(self):
    """Pose adjustment route config file is loaded into scene_controller.pose_adjustment_config_data."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.pose_adjustment_config_data = {}

    pose_adjustment_config = {
      'person': ['pedestrian', 'human'],
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
      json.dump(pose_adjustment_config, f)
      tmp_path = f.name

    try:
      scene_controller.extractPoseAdjustmentConfigData(tmp_path)
    finally:
      os.unlink(tmp_path)

    assert scene_controller.pose_adjustment_config_data == pose_adjustment_config

  def test_extract_pose_adjustment_config_data_raises_for_missing_file(self):
    """Missing pose-adjustment config file propagates FileNotFoundError."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.pose_adjustment_config_data = {}

    with pytest.raises(FileNotFoundError):
      scene_controller.extractPoseAdjustmentConfigData(
        'definitely-missing-pose-adjustment-config.json'
      )


class TestSceneDeserializeReidConfigPropagation:
  """Regression tests: Scene.deserialize must propagate reid_config_data to the tracker."""

  @patch('controller.scene.ControllerMode')
  @patch('controller.scene.IntelLabsTracking')
  def test_deserialize_without_reid_config_key_gives_empty_dict(
    self, mock_tracking, mock_mode
  ):
    """Scene.deserialize with no reid_config_data key results in empty dict on the scene."""
    mock_mode.isAnalyticsOnly.return_value = False

    mock_tracker_instance = MagicMock()
    mock_tracking.return_value = mock_tracker_instance

    from controller.scene import Scene
    with patch.object(Scene, 'available_trackers', {'intel_labs': mock_tracking,
                                                    'time_chunked_intel_labs': mock_tracking}):
      scene_data = {
        'uid': 'test-uid-1',
        'name': 'test_scene',
        'map': None,
      }
      scene = Scene.deserialize(scene_data)

    assert scene.reid_config_data == {}

  @patch('controller.scene.ControllerMode')
  @patch('controller.scene.TimeChunkedIntelLabsTracking')
  def test_deserialize_with_reid_config_stores_config_on_scene(
    self, mock_tracking, mock_mode
  ):
    """Scene deserialized with reid_config_data stores it on the scene object."""
    mock_mode.isAnalyticsOnly.return_value = False
    mock_tracking.return_value = MagicMock()

    from controller.scene import Scene
    with patch.object(Scene, 'available_trackers', {'intel_labs': mock_tracking,
                                                    'time_chunked_intel_labs': mock_tracking}):
      reid_config = {'feature_accumulation_threshold': 8, 'similarity_threshold': 55}
      scene_data = {
        'uid': 'test-uid-2',
        'name': 'test_scene',
        'map': None,
        'reid_config_data': reid_config,
        'tracker_config': [1.0, 2.0, 3.0, 15, True, 15, 5.0],
      }
      scene = Scene.deserialize(scene_data)

    assert scene.reid_config_data == reid_config

  @patch('controller.scene.ControllerMode')
  @patch('controller.scene.IntelLabsTracking')
  def test_deserialize_with_pose_adjustment_config_stores_routing_on_scene(
    self, mock_tracking, mock_mode
  ):
    """Scene deserialized with pose adjustment config applies configured label routes."""
    mock_mode.isAnalyticsOnly.return_value = False
    mock_tracking.return_value = MagicMock()

    from controller.scene import Scene
    with patch.object(Scene, 'available_trackers', {'intel_labs': mock_tracking,
                                                    'time_chunked_intel_labs': mock_tracking}):
      scene_data = {
        'uid': 'test-uid-3',
        'name': 'test_scene',
        'map': None,
        'pose_adjustment_config_data': {
          'person': ['pedestrian', 'human'],
        },
      }
      scene = Scene.deserialize(scene_data)

    assert scene.pose_adjustment_config_data == scene_data['pose_adjustment_config_data']
    assert scene.pose_adjustment._resolved_detection_types['pedestrian'] == 'person'


class TestSceneControllerPublishers:
  """Unit tests for SceneController publish* methods."""

  def _build_controller(self, visibility_topic='unregulated'):
    controller = SceneController.__new__(SceneController)
    controller.pubsub = MagicMock()
    controller.visibility_topic = visibility_topic
    controller.regulate_cache = {}
    return controller

  def test_publish_region_detections_publishes_each_cycle_while_region_non_empty(self):
    """Region detections publish every invocation while objects remain in region."""
    scene_controller = self._build_controller()
    scene = SimpleNamespace(
      uid='scene-1',
      name='Test Scene',
      regions=['roi-1'],
      lastPubCount={},
    )
    obj = SimpleNamespace(chain_data=SimpleNamespace(regions={'roi-1': {'entered': '2026-01-01T00:00:00Z'}}))
    jdata = {'timestamp': '2026-01-01T00:00:01Z'}

    with patch('controller.scene_controller.get_epoch_time', return_value=10.0), \
         patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'o1'}]):
      scene_controller.publishRegionDetections(scene, [obj], 'person', dict(jdata))
      scene_controller.publishRegionDetections(scene, [obj], 'person', dict(jdata))

    assert scene_controller.pubsub.publish.call_count == 2
    assert scene.lastPubCount['Test Scene/roi-1/person'] == 1

  def test_publish_events_publishes_region_events_and_clears_transient_event_lists(self):
    """Region events are published and objects/count queues are cleared afterward."""
    scene_controller = self._build_controller()

    class FakeRegion:
      def __init__(self):
        self.uuid = 'roi-1'
        self.name = 'ROI'
        self.singleton_type = None

      def serialize(self):
        return {'name': self.name}

    region = FakeRegion()
    scene = SimpleNamespace(
      uid='scene-1',
      name='Test Scene',
      events={'objects': [('roi-1', region)]},
    )

    scene_controller._buildAllRegionObjsList = MagicMock(return_value=({}, 0))
    scene_controller._buildEnteredObjsList = MagicMock()
    scene_controller._buildExitedObjsList = MagicMock()
    scene_controller._clearSensorValuesOnExit = MagicMock()

    with patch('controller.scene_controller.Region', FakeRegion):
      scene_controller.publishEvents(scene, '2026-01-01T00:00:01Z')

    assert scene_controller.pubsub.publish.call_count == 1
    assert 'objects' not in scene.events
    assert 'count' not in scene.events
    scene_controller._clearSensorValuesOnExit.assert_called_once_with(scene)

  def test_publish_regulated_detections_publishes_cached_payload_when_rate_allows(self):
    """Regulated payload publishes with cached objects and scene rate metadata."""
    scene_controller = self._build_controller('unregulated')
    scene_obj = SimpleNamespace(
      uid='scene-1',
      regulated_rate=5,
      cameras={'cam-1': object()},
    )
    msg_object = SimpleNamespace(gid='obj-1')
    jdata = {
      'timestamp': '2026-01-01T00:00:01Z',
      'id': 'scene-1',
      'name': 'Test Scene',
      'rate': 7,
      'objects': [],
    }

    scene_controller.calculateRate = MagicMock(return_value=0.5)
    scene_controller.shouldPublish = MagicMock(return_value=True)

    with patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'obj-1'}]), \
         patch('controller.scene_controller.get_epoch_time', return_value=42.0):
      scene_controller.publishRegulatedDetections(scene_obj, [msg_object], 'person', jdata, 'cam-1')

    assert scene_controller.pubsub.publish.call_count == 1
    cached = scene_controller.regulate_cache['scene-1']
    assert cached['rate']['cam-1'] == 7
    assert cached['last'] == 42.0

  def test_publish_scene_detections_publishes_and_invokes_external_builder(self):
    """Scene publish emits DATA_SCENE and triggers external publish path."""
    scene_controller = self._build_controller('unregulated')
    scene_controller.publishExternalDetections = MagicMock()
    scene = SimpleNamespace(uid='scene-1', name='Test Scene', lastPubCount={})
    jdata = {'timestamp': '2026-01-01T00:00:01Z', 'debug_hmo_start_time': 10.0}
    objects = [SimpleNamespace(gid='obj-1')]

    with patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'o1'}]), \
         patch('controller.scene_controller.get_epoch_time', return_value=15.0):
      scene_controller.publishSceneDetections(scene, objects, 'person', jdata)

    assert scene_controller.pubsub.publish.call_count == 1
    scene_controller.publishExternalDetections.assert_called_once_with(scene, 'person', objects, jdata)
    assert scene.lastPubCount['Test Scene/person'] == 1
    assert jdata['debug_hmo_processing_time'] == 5.0

  def test_publish_external_detections_publishes_with_sensor_enriched_objects(self):
    """External publish emits when shouldPublish allows and does not mutate base payload."""
    scene_controller = self._build_controller('unregulated')
    scene = SimpleNamespace(
      uid='scene-1',
      external_update_rate=2,
      last_published_detection=defaultdict(lambda: None),
      reid_config_data={'minimum_bbox_area': 5000},
    )
    jdata_base = {'timestamp': '2026-01-01T00:00:01Z', 'objects': ['unchanged']}

    scene_controller.shouldPublish = MagicMock(return_value=True)
    with patch('controller.scene_controller.get_epoch_time', side_effect=[100.0, 101.0]), \
         patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'o1'}]) as mock_build:
      scene_controller.publishExternalDetections(scene, 'person', [object()], jdata_base)

    assert scene_controller.pubsub.publish.call_count == 1
    assert scene.last_published_detection['person'] == 101.0
    assert jdata_base['objects'] == ['unchanged']
    # Confirm reid provenance stamping is actually wired through to buildDetectionsList
    _, call_kwargs = mock_build.call_args
    assert call_kwargs['attach_reid_provenance'] is True
    assert call_kwargs['minimum_bbox_area'] == 5000
    assert call_kwargs['will_enroll_reid'] is False
    assert call_kwargs['withhold_reid'] is False
    assert call_kwargs['reid_enrolled_fn'] is None

  def test_hierarchy_reid_policy_will_enroll_when_schema_ready(self):
    """Schema-ready ReID scenes advertise will_enroll on hierarchy output."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(reid_enabled=True, reid_database=database)
    scene = SimpleNamespace(tracker=SimpleNamespace(uuid_manager=uuid_manager))

    assert scene_controller._hierarchyReidPublishPolicy(scene) == 'will_enroll'

  def test_hierarchy_reid_policy_withholds_when_write_intent_before_schema(self):
    """TLS ReID certs without a ready schema withhold embeddings instead of racing."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=False)
    uuid_manager = SimpleNamespace(reid_enabled=True, reid_database=database)
    scene = SimpleNamespace(tracker=SimpleNamespace(uuid_manager=uuid_manager))

    with patch('controller.scene_controller.get_reid_use_tls', return_value=True), \
         patch('controller.scene_controller.get_reid_client_cert', return_value='/tmp/reid.crt'), \
         patch('controller.scene_controller.get_reid_client_key', return_value='/tmp/reid.key'), \
         patch('controller.scene_controller.os.path.exists', return_value=True):
      assert scene_controller._hierarchyReidPublishPolicy(scene) == 'withhold'

  def test_hierarchy_reid_policy_passthrough_without_write_intent(self):
    """Children without ReID client material keep parent-only passthrough enrollment."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=False)
    uuid_manager = SimpleNamespace(reid_enabled=True, reid_database=database)
    scene = SimpleNamespace(tracker=SimpleNamespace(uuid_manager=uuid_manager))

    with patch('controller.scene_controller.get_reid_use_tls', return_value=True), \
         patch('controller.scene_controller.get_reid_client_cert', return_value='/missing/reid.crt'), \
         patch('controller.scene_controller.get_reid_client_key', return_value='/missing/reid.key'), \
         patch('controller.scene_controller.os.path.exists', return_value=False):
      assert scene_controller._hierarchyReidPublishPolicy(scene) == 'passthrough'

  def test_hierarchy_reid_policy_withholds_non_tls_until_schema_ready(self):
    """Non-TLS ReID still withholds early frames so parents cannot sole-enroll first."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=False)
    uuid_manager = SimpleNamespace(reid_enabled=True, reid_database=database)
    scene = SimpleNamespace(tracker=SimpleNamespace(uuid_manager=uuid_manager))

    with patch('controller.scene_controller.get_reid_use_tls', return_value=False):
      assert scene_controller._hierarchyReidPublishPolicy(scene) == 'withhold'

  def test_track_has_reid_enrollment_for_pending_vectors_or_database_id(self):
    """Enrollment advertising covers pending writes and rematched database ids."""
    scene_controller = SceneController.__new__(SceneController)
    uuid_manager = SimpleNamespace(
      features_for_database={},
      active_ids={},
      active_ids_lock=MagicMock())
    uuid_manager.active_ids_lock.__enter__ = MagicMock(return_value=None)
    uuid_manager.active_ids_lock.__exit__ = MagicMock(return_value=False)
    scene = SimpleNamespace(tracker=SimpleNamespace(uuid_manager=uuid_manager))
    obj = SimpleNamespace(rv_id='track-1')

    assert scene_controller._trackHasReidEnrollment(scene, obj) is False

    uuid_manager.features_for_database['track-1'] = {'reid_vectors': [[0.1]]}
    assert scene_controller._trackHasReidEnrollment(scene, obj) is True

    uuid_manager.features_for_database.clear()
    uuid_manager.active_ids['track-1'] = ['db-uuid', 0.9]
    assert scene_controller._trackHasReidEnrollment(scene, obj) is True

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.ControllerMode')
  def test_publish_detections_initializes_scene_state_and_calls_all_publish_paths(
    self, mock_mode, mock_metrics
  ):
    """publishDetections initializes state and calls scene/regulated/region publishers."""
    scene_controller = self._build_controller()
    scene_controller.publishSceneDetections = MagicMock()
    scene_controller.publishRegulatedDetections = MagicMock()
    scene_controller.publishRegionDetections = MagicMock()

    mock_mode.isAnalyticsOnly.return_value = False

    scene = SimpleNamespace(uid='scene-1', name='Test Scene')
    objects = [object()]
    jdata = {'timestamp': '2026-01-01T00:00:01Z'}

    scene_controller.publishDetections(scene, objects, 10.0, 'person', jdata, 'cam-1')

    assert hasattr(scene, 'lastPubCount')
    assert hasattr(scene, 'last_published_detection')
    scene_controller.publishSceneDetections.assert_called_once_with(scene, objects, 'person', jdata)
    scene_controller.publishRegulatedDetections.assert_called_once_with(scene, objects, 'person', jdata, 'cam-1')
    scene_controller.publishRegionDetections.assert_called_once_with(scene, objects, 'person', jdata)
    mock_metrics.record_object_count.assert_called_once()

  @patch('controller.scene_controller.ControllerMode')
  def test_publish_detections_skips_scene_publish_in_analytics_only_mode(self, mock_mode):
    """publishDetections skips Scene topic output when analytics-only mode is enabled."""
    scene_controller = self._build_controller()
    scene_controller.publishSceneDetections = MagicMock()
    scene_controller.publishRegulatedDetections = MagicMock()
    scene_controller.publishRegionDetections = MagicMock()

    mock_mode.isAnalyticsOnly.return_value = True
    scene = SimpleNamespace(uid='scene-1', name='Test Scene')

    scene_controller.publishDetections(scene, [], 10.0, 'person', {'timestamp': '2026-01-01T00:00:01Z'}, None)

    scene_controller.publishSceneDetections.assert_not_called()
    scene_controller.publishRegulatedDetections.assert_called_once()
    scene_controller.publishRegionDetections.assert_called_once()


class TestSceneControllerRemoteChildParent:
  """Unit tests for remote-child parent injection and recovery (NEX-T21933)."""

  TEST_NAME = "NEX-T21933"

  def test_with_remote_child_parent_injects_when_missing(self):
    """Omits or null parent are filled from the enclosing scene uid."""
    info = {'remote_child_id': 'child-1', 'child_type': 'remote'}
    assert SceneController._withRemoteChildParent(info, 'parent-uid')['parent'] == 'parent-uid'
    assert SceneController._withRemoteChildParent(
      {'remote_child_id': 'child-1', 'parent': None}, 'parent-uid')['parent'] == 'parent-uid'

  def test_with_remote_child_parent_preserves_existing_parent(self):
    """Existing parent values are left unchanged."""
    info = {'remote_child_id': 'child-1', 'parent': 'already-set'}
    assert SceneController._withRemoteChildParent(info, 'other')['parent'] == 'already-set'

  def test_parent_uid_for_remote_child_finds_link(self):
    """Positive: scan of child-scene links returns the enclosing parent uid."""
    scene_controller = SceneController.__new__(SceneController)
    parent = SimpleNamespace(uid='parent-1')
    other = SimpleNamespace(uid='other-1')
    scene_controller.cache_manager = MagicMock()
    scene_controller.cache_manager.allScenes.return_value = [other, parent]
    scene_controller.cache_manager.data_source.getChildScenes.side_effect = (
      lambda uid: {
        'other-1': {'results': []},
        'parent-1': {'results': [
          {'remote_child_id': 'remote-abc', 'child_type': 'remote'},
        ]},
      }[uid]
    )

    assert scene_controller._parentUidForRemoteChild('remote-abc') == 'parent-1'

  def test_parent_uid_for_remote_child_returns_none_when_unlinked(self):
    """Negative: unknown remote_child_id yields None."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.cache_manager = MagicMock()
    scene_controller.cache_manager.allScenes.return_value = [
      SimpleNamespace(uid='parent-1')]
    scene_controller.cache_manager.data_source.getChildScenes.return_value = {
      'results': [{'remote_child_id': 'someone-else', 'child_type': 'remote'}],
    }

    assert scene_controller._parentUidForRemoteChild('missing') is None

  def test_handle_child_scene_object_recovers_missing_parent(self):
    """Positive: DATA_EXTERNAL path recovers parent onto the cached remote scene."""
    scene_controller = SceneController.__new__(SceneController)
    parent_scene = MagicMock()
    parent_scene.processSceneData.return_value = True
    remote_sender = SimpleNamespace(
      parent=None, name='remote', cameraPose=object())

    scene_controller.cache_manager = MagicMock()
    scene_controller.cache_manager.sceneWithID.side_effect = (
      lambda uid: None if uid == 'remote-1' else parent_scene)
    scene_controller.cache_manager.sceneWithRemoteChildID.return_value = remote_sender
    scene_controller._parentUidForRemoteChild = MagicMock(return_value='parent-1')

    success, scene = scene_controller._handleChildSceneObject(
      'remote-1', {'objects': {}}, 'person', 1.0)

    assert success is True
    assert scene is parent_scene
    assert remote_sender.parent == 'parent-1'
    parent_scene.processSceneData.assert_called_once()

  def test_handle_child_scene_object_fails_when_parent_unrecoverable(self):
    """Negative: still errors when no parent link can be recovered."""
    scene_controller = SceneController.__new__(SceneController)
    remote_sender = SimpleNamespace(
      parent=None, name='remote', cameraPose=object())

    scene_controller.cache_manager = MagicMock()
    scene_controller.cache_manager.sceneWithID.return_value = None
    scene_controller.cache_manager.sceneWithRemoteChildID.return_value = remote_sender
    scene_controller._parentUidForRemoteChild = MagicMock(return_value=None)

    success, scene = scene_controller._handleChildSceneObject(
      'remote-1', {'objects': {}}, 'person', 1.0)

    assert success is False
    assert scene is remote_sender
    assert remote_sender.parent is None

