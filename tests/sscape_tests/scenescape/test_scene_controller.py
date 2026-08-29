#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import threading

import orjson
import pytest
import tempfile
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from controller.scene_controller import SceneController
from controller.external_source import IdentityClaimRegistry
from scene_common.mqtt import PubSub


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

  @patch('controller.scene.IntelLabsTracking')
  def test_deserialize_without_reid_config_key_gives_empty_dict(
    self, mock_tracking
  ):
    """Scene.deserialize with no reid_config_data key results in empty dict on the scene."""
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

  @patch('controller.scene.TimeChunkedIntelLabsTracking')
  def test_deserialize_with_reid_config_stores_config_on_scene(
    self, mock_tracking
  ):
    """Scene deserialized with reid_config_data stores it on the scene object."""
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

  @patch('controller.scene.IntelLabsTracking')
  def test_deserialize_with_pose_adjustment_config_stores_routing_on_scene(
    self, mock_tracking
  ):
    """Scene deserialized with pose adjustment config applies configured label routes."""
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

  def _build_controller(self, visibility_topic='unregulated', publish_external=False):
    controller = SceneController.__new__(SceneController)
    controller.pubsub = MagicMock()
    controller.visibility_topic = visibility_topic
    controller.publish_external = publish_external
    return controller

  def test_publish_scene_detections_publishes_and_invokes_external_builder(self):
    """Scene publish emits DATA_SCENE and triggers external publish path."""
    scene_controller = self._build_controller('unregulated')
    scene_controller.publishExternalDetections = MagicMock()
    scene = SimpleNamespace(uid='scene-1', name='Test Scene')
    jdata = {'timestamp': '2026-01-01T00:00:01Z', 'debug_hmo_start_time': 10.0}
    objects = [SimpleNamespace(gid='obj-1')]

    with patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'o1'}]), \
         patch('controller.scene_controller.get_epoch_time', return_value=15.0):
      scene_controller.publishSceneDetections(scene, objects, 'person', jdata)

    assert scene_controller.pubsub.publish.call_count == 1
    scene_controller.publishExternalDetections.assert_called_once_with(scene, 'person', objects, jdata)
    assert jdata['debug_hmo_processing_time'] == 5.0

  def test_publish_scene_detections_publishes_empty_objects_every_time(self):
    """Empty objects lists free-run; no detections is still publishable state."""
    scene_controller = self._build_controller('unregulated')
    scene_controller.publishExternalDetections = MagicMock()
    scene = SimpleNamespace(uid='scene-1', name='Test Scene')
    jdata = {'timestamp': '2026-01-01T00:00:01Z'}

    with patch('controller.scene_controller.buildDetectionsList', return_value=[]):
      scene_controller.publishSceneDetections(scene, [], 'person', jdata)
      scene_controller.publishSceneDetections(scene, [], 'person', jdata)

    assert scene_controller.pubsub.publish.call_count == 2
    for call in scene_controller.pubsub.publish.call_args_list:
      payload = orjson.loads(call.args[1])
      assert payload['objects'] == []
    assert scene_controller.publishExternalDetections.call_count == 2

  def test_publish_external_detections_publishes_with_sensor_enriched_objects(self):
    """External publish emits when shouldPublish allows."""
    scene_controller = self._build_controller('unregulated')
    scene = SimpleNamespace(
      uid='scene-1',
      parent='parent-1',
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

  def test_publish_external_detections_skips_standalone_root_scene(self):
    """Scenes without a parent skip hierarchy external publish (ADR 16)."""
    scene_controller = self._build_controller('unregulated')
    scene = SimpleNamespace(
      uid='scene-1',
      parent=None,
      external_update_rate=2,
      last_published_detection=defaultdict(lambda: None),
      reid_config_data={'minimum_bbox_area': 5000},
    )
    jdata_base = {'timestamp': '2026-01-01T00:00:01Z', 'objects': ['unchanged']}
    scene_controller.shouldPublish = MagicMock(return_value=True)

    with patch('controller.scene_controller.get_epoch_time', side_effect=[100.0, 101.0]), \
         patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'o1'}]) as mock_build:
      scene_controller.publishExternalDetections(scene, 'person', [object()], jdata_base)

    scene_controller.pubsub.publish.assert_not_called()
    scene_controller.shouldPublish.assert_not_called()
    mock_build.assert_not_called()

  def test_publish_external_detections_exports_root_when_publish_external_set(self):
    """--publish-external lets a remote-child root publish DATA_EXTERNAL."""
    scene_controller = self._build_controller('unregulated', publish_external=True)
    scene = SimpleNamespace(
      uid='scene-1',
      parent=None,
      external_update_rate=2,
      last_published_detection=defaultdict(lambda: None),
      reid_config_data={'minimum_bbox_area': 5000},
    )
    jdata_base = {'timestamp': '2026-01-01T00:00:01Z', 'objects': ['unchanged']}
    scene_controller.shouldPublish = MagicMock(return_value=True)

    with patch('controller.scene_controller.get_epoch_time', side_effect=[100.0, 101.0]), \
         patch('controller.scene_controller.buildDetectionsList', return_value=[{'id': 'o1'}]):
      scene_controller.publishExternalDetections(scene, 'person', [object()], jdata_base)

    assert scene_controller.pubsub.publish.call_count == 1

  def _publish_external_with_reid_manager(self, uuid_manager, write_intent=True, category='person'):
    """Publish external detections for a scene whose CATEGORY SUBTRACKER owns uuid_manager.

    Every Tracking instance -- top-level and per-category -- builds its own
    separate UUIDManager (see Tracking.__init__/_createTrackers), and the
    real reid work only ever runs on the per-category subtracker's instance.
    The top-level tracker gets its own distinct, idle MagicMock UUIDManager
    here so any regression that resolves the wrong instance fails loudly
    rather than by coincidence passing against a single shared mock.
    """
    scene_controller = self._build_controller('unregulated')
    scene_controller.shouldPublish = MagicMock(return_value=True)
    scene = SimpleNamespace(
      uid='scene-1',
      parent='parent-1',
      external_update_rate=2,
      last_published_detection=defaultdict(lambda: None),
      reid_config_data={'minimum_bbox_area': 5000},
      tracker=SimpleNamespace(
        uuid_manager=MagicMock(),
        trackers={category: SimpleNamespace(uuid_manager=uuid_manager)},
      ),
    )
    jdata_base = {'timestamp': '2026-01-01T00:00:01Z', 'objects': []}
    with patch.object(scene_controller, '_sceneHasReidWriteIntent', return_value=write_intent), \
         patch('controller.scene_controller.get_epoch_time', side_effect=[100.0, 101.0]), \
         patch('controller.scene_controller.buildDetectionsList',
               return_value=[{'id': 'o1'}]) as mock_build:
      scene_controller.publishExternalDetections(scene, category, [object()], jdata_base)
    return mock_build.call_args.kwargs

  def test_publish_external_wires_will_enroll_when_policy_confirms(self):
    """Confirmed healthy writes must stamp will_enroll on hierarchy output."""
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=True,
      reid_write_confirmed=True, reid_empty_batch_before_confirm=False)
    kwargs = self._publish_external_with_reid_manager(uuid_manager)
    assert kwargs['will_enroll_reid'] is True
    assert kwargs['withhold_reid'] is False
    assert kwargs['reid_enrolled_fn'] is not None

  def test_publish_external_wires_withhold_before_confirmed_write(self):
    """Schema-ready but unconfirmed writes must withhold local hierarchy reid."""
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=True,
      reid_write_confirmed=False, reid_empty_batch_before_confirm=False)
    kwargs = self._publish_external_with_reid_manager(uuid_manager)
    assert kwargs['will_enroll_reid'] is False
    assert kwargs['withhold_reid'] is True
    assert kwargs['reid_enrolled_fn'] is None

  def test_publish_external_wires_passthrough_when_writes_unhealthy(self):
    """Unhealthy writes before confirm forward without will_enroll so parents may sole-enroll."""
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=False,
      reid_write_confirmed=False, reid_empty_batch_before_confirm=False)
    kwargs = self._publish_external_with_reid_manager(uuid_manager)
    assert kwargs['will_enroll_reid'] is False
    assert kwargs['withhold_reid'] is False
    assert kwargs['reid_enrolled_fn'] is None

  def test_publish_external_wires_will_enroll_when_confirmed_even_if_unhealthy(self):
    """After a confirmed write, keep will_enroll mode so parents do not dual-enroll."""
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=False,
      reid_write_confirmed=True, reid_empty_batch_before_confirm=False)
    kwargs = self._publish_external_with_reid_manager(uuid_manager)
    assert kwargs['will_enroll_reid'] is True
    assert kwargs['withhold_reid'] is False
    assert kwargs['reid_enrolled_fn'] is not None

  def test_publish_external_wires_passthrough_on_empty_batch_before_confirm(self):
    """Empty batches before confirm must not withhold forever on the wire."""
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=True,
      reid_write_confirmed=False, reid_empty_batch_before_confirm=True)
    kwargs = self._publish_external_with_reid_manager(uuid_manager)
    assert kwargs['will_enroll_reid'] is False
    assert kwargs['withhold_reid'] is False
    assert kwargs['reid_enrolled_fn'] is None

  @staticmethod
  def _scene_with_category_uuid_manager(uuid_manager, category='person'):
    """Build a scene with a real category subtracker plus a separate, idle
    top-level tracker UUIDManager, mirroring Tracking.__init__/_createTrackers.
    """
    return SimpleNamespace(tracker=SimpleNamespace(
      uuid_manager=MagicMock(),
      trackers={category: SimpleNamespace(uuid_manager=uuid_manager)}))

  def test_hierarchy_reid_policy_will_enroll_when_confirmed_even_if_reid_disabled(self):
    """Confirmed writes keep will_enroll mode after slow-query reid disable."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=False, reid_database=database, reid_write_healthy=True,
      reid_write_confirmed=True, reid_empty_batch_before_confirm=False)
    scene = self._scene_with_category_uuid_manager(uuid_manager)

    with patch.object(scene_controller, '_sceneHasReidWriteIntent', return_value=True):
      assert scene_controller._hierarchyReidPublishPolicy(scene, 'person') == 'will_enroll'

  def test_hierarchy_reid_policy_withholds_when_write_intent_before_schema(self):
    """TLS ReID certs without a ready schema withhold embeddings instead of racing."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=False)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=True)
    scene = self._scene_with_category_uuid_manager(uuid_manager)

    with patch('controller.scene_controller.get_reid_use_tls', return_value=True), \
         patch('controller.scene_controller.get_reid_client_cert', return_value='/tmp/reid.crt'), \
         patch('controller.scene_controller.get_reid_client_key', return_value='/tmp/reid.key'), \
         patch('controller.scene_controller.os.path.exists', return_value=True):
      assert scene_controller._hierarchyReidPublishPolicy(scene, 'person') == 'withhold'

  def test_hierarchy_reid_policy_passthrough_without_write_intent(self):
    """Children without ReID client material keep parent-only passthrough enrollment."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=False)
    uuid_manager = SimpleNamespace(reid_enabled=True, reid_database=database)
    scene = self._scene_with_category_uuid_manager(uuid_manager)

    with patch('controller.scene_controller.get_reid_use_tls', return_value=True), \
         patch('controller.scene_controller.get_reid_client_cert', return_value='/missing/reid.crt'), \
         patch('controller.scene_controller.get_reid_client_key', return_value='/missing/reid.key'), \
         patch('controller.scene_controller.os.path.exists', return_value=False):
      assert scene_controller._hierarchyReidPublishPolicy(scene, 'person') == 'passthrough'

  def test_hierarchy_reid_policy_withholds_non_tls_until_schema_ready(self):
    """REID_USE_TLS=false implies write intent even with default endpoint env."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=False)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=True)
    scene = self._scene_with_category_uuid_manager(uuid_manager)

    with patch('controller.scene_controller.get_reid_use_tls', return_value=False):
      assert scene_controller._hierarchyReidPublishPolicy(scene, 'person') == 'withhold'

  def test_hierarchy_reid_policy_requires_write_intent_even_when_schema_ready(self):
    """Schema alone without write intent stays passthrough (no false will_enroll)."""
    scene_controller = SceneController.__new__(SceneController)
    database = SimpleNamespace(_schema_ready=True)
    uuid_manager = SimpleNamespace(
      reid_enabled=True, reid_database=database, reid_write_healthy=True)
    scene = self._scene_with_category_uuid_manager(uuid_manager)

    with patch.object(scene_controller, '_sceneHasReidWriteIntent', return_value=False):
      assert scene_controller._hierarchyReidPublishPolicy(scene, 'person') == 'passthrough'

  def test_track_has_reid_enrollment_for_pending_vectors_or_database_id(self):
    """Enrollment advertising covers pending writes, gathering, and rematched database ids."""
    scene_controller = SceneController.__new__(SceneController)
    uuid_manager = SimpleNamespace(
      features_for_database={},
      enrollment_features={},
      local_enrollment_features={},
      quality_features={},
      active_query={},
      active_ids={},
      active_ids_lock=MagicMock())
    uuid_manager.active_ids_lock.__enter__ = MagicMock(return_value=None)
    uuid_manager.active_ids_lock.__exit__ = MagicMock(return_value=False)
    scene = self._scene_with_category_uuid_manager(uuid_manager)
    obj = SimpleNamespace(rv_id='track-1', category='person')

    assert scene_controller._trackHasReidEnrollment(scene, obj) is False

    uuid_manager.features_for_database['track-1'] = {'reid_vectors': [[0.1]]}
    assert scene_controller._trackHasReidEnrollment(scene, obj) is True

    uuid_manager.features_for_database.clear()
    uuid_manager.quality_features['track-1'] = [[0.1]]
    assert scene_controller._trackHasReidEnrollment(scene, obj) is True

    uuid_manager.quality_features.clear()
    uuid_manager.active_ids['track-1'] = ['db-uuid', 0.9]
    assert scene_controller._trackHasReidEnrollment(scene, obj) is True

  @patch('controller.scene_controller.metrics')
  def test_publish_detections_initializes_scene_state_and_calls_all_publish_paths(
    self, mock_metrics
  ):
    """publishDetections initializes state and calls the scene publisher."""
    scene_controller = self._build_controller()
    scene_controller.publishSceneDetections = MagicMock()

    scene = SimpleNamespace(uid='scene-1', name='Test Scene')
    objects = [object()]
    jdata = {'timestamp': '2026-01-01T00:00:01Z'}

    scene_controller.publishDetections(scene, objects, 10.0, 'person', jdata, 'cam-1')

    assert hasattr(scene, 'last_published_detection')
    scene_controller.publishSceneDetections.assert_called_once_with(scene, objects, 'person', jdata)
    mock_metrics.record_object_count.assert_called_once()


class TestHierarchyReidPublishPolicyResolvesCorrectUUIDManager:
  """Regression test (see bug: _hierarchyReidPublishPolicy/_trackHasReidEnrollment
  read the idle top-level scene.tracker.uuid_manager instead of the per-category
  subtracker's UUIDManager that actually runs queries and confirms writes --
  see Tracking.__init__ / _createTrackers, where every Tracking instance,
  top-level and per-category, builds its own separate UUIDManager).
  """

  def _build_controller(self):
    return SceneController.__new__(SceneController)

  def test_will_enroll_reflects_category_subtracker_write_confirmed(self):
    """A confirmed write on the category subtracker's UUIDManager must be
    visible to policy -- not masked by the top-level tracker's own idle
    UUIDManager, which never confirms anything."""
    scene_controller = self._build_controller()

    top_level_um = MagicMock()
    top_level_um.reid_write_confirmed = False  # idle, never does real work

    person_um = MagicMock()
    person_um.reid_write_confirmed = True  # this is the one that actually wrote

    scene = SimpleNamespace(
      tracker=SimpleNamespace(
        uuid_manager=top_level_um,
        trackers={'person': SimpleNamespace(uuid_manager=person_um)},
      )
    )

    with patch.object(scene_controller, '_sceneHasReidWriteIntent', return_value=True):
      policy = scene_controller._hierarchyReidPublishPolicy(scene, 'person')

    assert policy == 'will_enroll', (
      "Policy must resolve the 'person' subtracker's UUIDManager "
      "(reid_write_confirmed=True), not the idle top-level tracker's own "
      "UUIDManager (reid_write_confirmed=False)."
    )

  def test_withholds_when_top_level_um_is_confirmed_but_category_is_not(self):
    """Inverse case: if a bug resolved the top-level UUIDManager instead,
    this would incorrectly return 'will_enroll'. Guards against reintroducing
    the wrong-instance bug in either direction."""
    scene_controller = self._build_controller()

    top_level_um = MagicMock()
    top_level_um.reid_write_confirmed = True  # would be wrong if read

    person_um = MagicMock()
    person_um.reid_write_confirmed = False
    person_um.reid_enabled = True
    person_um.reid_write_healthy = True
    person_um.reid_empty_batch_before_confirm = False
    person_um.reid_database = SimpleNamespace(_schema_ready=True)

    scene = SimpleNamespace(
      tracker=SimpleNamespace(
        uuid_manager=top_level_um,
        trackers={'person': SimpleNamespace(uuid_manager=person_um)},
      )
    )

    with patch.object(scene_controller, '_sceneHasReidWriteIntent', return_value=True):
      policy = scene_controller._hierarchyReidPublishPolicy(scene, 'person')

    assert policy != 'will_enroll', (
      "Must not report will_enroll based on the top-level tracker's "
      "UUIDManager state; the 'person' subtracker has not confirmed a write."
    )

  def test_track_has_reid_enrollment_uses_category_subtracker(self):
    """_trackHasReidEnrollment must check the object's own category's
    subtracker, not the top-level tracker's UUIDManager."""
    scene_controller = self._build_controller()

    top_level_um = MagicMock()
    top_level_um.features_for_database = {}
    top_level_um.enrollment_features = {}
    top_level_um.local_enrollment_features = {}
    top_level_um.quality_features = {}
    top_level_um.active_query = {}
    top_level_um.active_ids = {}
    top_level_um.active_ids_lock = threading.Lock()

    person_um = MagicMock()
    person_um.features_for_database = {}
    person_um.enrollment_features = {}
    person_um.local_enrollment_features = {}
    person_um.quality_features = {42: [[0.1, 0.2]]}  # this track IS accumulating
    person_um.active_query = {}
    person_um.active_ids = {}
    person_um.active_ids_lock = threading.Lock()

    scene = SimpleNamespace(
      tracker=SimpleNamespace(
        uuid_manager=top_level_um,
        trackers={'person': SimpleNamespace(uuid_manager=person_um)},
      )
    )
    aobj = SimpleNamespace(rv_id=42, category='person')

    assert scene_controller._trackHasReidEnrollment(scene, aobj) is True


class TestParseTrustedSources:
  """Unit tests for the trusted-positioning-source allowlist parser."""

  def test_empty_or_none_value_trusts_nothing(self):
    """Fails closed: unset/empty config trusts no source."""
    from controller.scene_controller import _parseTrustedSources

    assert _parseTrustedSources(None) == frozenset()
    assert _parseTrustedSources('') == frozenset()

  def test_parses_comma_separated_ids_and_trims_whitespace(self):
    from controller.scene_controller import _parseTrustedSources

    result = _parseTrustedSources(' positioning-svc-1 , positioning-svc-2,,')

    assert result == frozenset({'positioning-svc-1', 'positioning-svc-2'})


class TestSceneControllerHandleExternalSourceObject:
  """Unit tests for SceneController._handleExternalSourceObject."""

  def _build_controller(self):
    controller = SceneController.__new__(SceneController)
    controller.external_source_pose_cache = MagicMock()
    controller.identity_claim_registry = IdentityClaimRegistry()
    controller.trusted_positioning_sources = frozenset({'positioning-svc-1'})
    return controller

  def test_ingests_objects_when_pose_resolves(self):
    """Resolves a pose and delegates ingestion to scene.processSceneData. Every
    external-source object's id is trusted as global identity by default (no
    source allowlist required), so retrack is always disabled."""
    scene_controller = self._build_controller()
    fake_camera_pose = MagicMock()
    scene_controller.external_source_pose_cache.resolve.return_value = (fake_camera_pose, None)
    scene = SimpleNamespace(uid='scene-1', processSceneData=MagicMock(return_value=True))
    jdata = {
      'source_id': 'drone-1',
      'objects': [{'id': 'agent-track-1', 'category': 'vehicle', 'translation': [1.0, 2.0, 0.0]}],
    }

    result = scene_controller._handleExternalSourceObject(scene, jdata, 'vehicle', 42.0)

    assert result is True
    scene_controller.external_source_pose_cache.resolve.assert_called_once_with(
      scene, 'drone-1', None, 42.0, trusted_scene_pose=False)
    scene.processSceneData.assert_called_once()
    args, kwargs = scene.processSceneData.call_args
    assert args[0] is jdata
    assert args[0]['objects'] == jdata['objects']
    assert args[1].name == 'drone-1'
    assert args[1].retrack is False
    assert args[2] is fake_camera_pose
    assert args[3] == 'vehicle'
    assert kwargs == {'when': 42.0}

  def test_trusted_scene_pose_flag_is_passed_through(self):
    """Only allowlisted source_ids are marked trusted for scene-frame poses."""
    scene_controller = self._build_controller()
    scene_controller.external_source_pose_cache.resolve.return_value = (MagicMock(), None)
    scene = SimpleNamespace(uid='scene-1', processSceneData=MagicMock(return_value=True))
    jdata = {'source_id': 'positioning-svc-1', 'objects': []}

    scene_controller._handleExternalSourceObject(scene, jdata, 'vehicle', 42.0)

    scene_controller.external_source_pose_cache.resolve.assert_called_once_with(
      scene, 'positioning-svc-1', None, 42.0, trusted_scene_pose=True)

  def test_skips_ingestion_without_crashing_when_pose_unavailable(self):
    """When no transform can be resolved, ingestion is skipped but not treated as failure."""
    scene_controller = self._build_controller()
    scene_controller.external_source_pose_cache.resolve.return_value = (None, 'no_pose_available')
    scene = SimpleNamespace(uid='scene-1', processSceneData=MagicMock())
    jdata = {'source_id': 'drone-1', 'objects': []}

    result = scene_controller._handleExternalSourceObject(scene, jdata, 'vehicle', 42.0)

    assert result is True
    scene.processSceneData.assert_not_called()

  def test_no_source_allowlist_required_for_identity_trust(self):
    """Any source_id, with no prior configuration, has its object ids trusted as
    global identity: retrack is False regardless of source_id."""
    scene_controller = self._build_controller()
    scene_controller.external_source_pose_cache.resolve.return_value = (MagicMock(), None)
    scene = SimpleNamespace(uid='scene-1', processSceneData=MagicMock(return_value=True))
    jdata = {'source_id': 'never-before-seen-source', 'objects': [
      {'id': 'tag-1', 'category': 'person', 'translation': [1.0, 2.0, 0.0]},
    ]}

    scene_controller._handleExternalSourceObject(scene, jdata, 'person', 42.0)

    args, _ = scene.processSceneData.call_args
    assert args[1].retrack is False
    assert len(args[0]['objects']) == 1

  def test_colliding_id_from_different_source_is_dropped(self):
    """If a different source_id is already using the same id in the same scene and
    category, the newly arriving, colliding object is dropped rather than merged
    into an unrelated track; non-colliding objects in the same message still pass."""
    scene_controller = self._build_controller()
    scene_controller.external_source_pose_cache.resolve.return_value = (MagicMock(), None)
    scene = SimpleNamespace(uid='scene-1', processSceneData=MagicMock(return_value=True))

    first_jdata = {'source_id': 'source-a', 'objects': [
      {'id': 'tag-1', 'category': 'person', 'translation': [0.0, 0.0, 0.0]},
    ]}
    scene_controller._handleExternalSourceObject(scene, first_jdata, 'person', 10.0)

    second_jdata = {'source_id': 'source-b', 'objects': [
      {'id': 'tag-1', 'category': 'person', 'translation': [1.0, 1.0, 0.0]},
      {'id': 'tag-2', 'category': 'person', 'translation': [2.0, 2.0, 0.0]},
    ]}
    scene_controller._handleExternalSourceObject(scene, second_jdata, 'person', 11.0)

    args, _ = scene.processSceneData.call_args
    accepted_ids = [obj['id'] for obj in args[0]['objects']]
    assert accepted_ids == ['tag-2']

  def test_same_source_reclaiming_its_own_id_is_not_a_collision(self):
    """A source repeatedly reporting the same id for the same object is not a
    collision; the object is accepted on every message."""
    scene_controller = self._build_controller()
    scene_controller.external_source_pose_cache.resolve.return_value = (MagicMock(), None)
    scene = SimpleNamespace(uid='scene-1', processSceneData=MagicMock(return_value=True))
    jdata_1 = {'source_id': 'uwb-hub-1', 'objects': [
      {'id': 'tag-aa:bb:cc', 'category': 'person', 'translation': [1.0, 2.0, 0.0]},
    ]}
    jdata_2 = {'source_id': 'uwb-hub-1', 'objects': [
      {'id': 'tag-aa:bb:cc', 'category': 'person', 'translation': [1.1, 2.1, 0.0]},
    ]}

    scene_controller._handleExternalSourceObject(scene, jdata_1, 'person', 10.0)
    scene_controller._handleExternalSourceObject(scene, jdata_2, 'person', 11.0)

    args, _ = scene.processSceneData.call_args
    assert len(args[0]['objects']) == 1
    assert args[0]['objects'][0]['id'] == 'tag-aa:bb:cc'
    assert args[1].uid == 'uwb-hub-1'


class TestParseExternalSourceBindings:
  """Unit tests for CONTROLLER_EXTERNAL_SOURCE_BINDINGS parsing."""

  def test_parses_publisher_to_scene_pairs(self):
    from controller.scene_controller import _parseExternalSourceBindings
    result = _parseExternalSourceBindings(
      'drone-1:scene-a,drone-1:scene-b,pos-1:scene-a')
    assert result['drone-1'] == frozenset({'scene-a', 'scene-b'})
    assert result['pos-1'] == frozenset({'scene-a'})

  def test_empty_is_no_bindings(self):
    from controller.scene_controller import _parseExternalSourceBindings
    assert _parseExternalSourceBindings(None) == {}
    assert _parseExternalSourceBindings('') == {}


class TestScenesForExternalPublisher:
  """Unit tests for SceneController._scenesForExternalPublisher."""

  def _build_controller(self, bindings=None):
    controller = SceneController.__new__(SceneController)
    controller.external_source_bindings = bindings or {}
    controller.external_source_pose_cache = MagicMock()
    controller.cache_manager = MagicMock()
    return controller

  def test_manual_binding_wins(self):
    scene = SimpleNamespace(uid='scene-a', trs_xyz_to_lla=None)
    controller = self._build_controller({'drone-1': frozenset({'scene-a'})})
    controller.cache_manager.sceneWithID.return_value = scene

    scenes = controller._scenesForExternalPublisher(
      'drone-1', {'pose': {'reference_frame': 'scene'}}, 1.0)

    assert scenes == [scene]

  def test_wgs84_auto_attaches_geo_scenes(self):
    geo = SimpleNamespace(uid='geo', trs_xyz_to_lla=object())
    plain = SimpleNamespace(uid='plain', trs_xyz_to_lla=None)
    controller = self._build_controller()
    controller.cache_manager.allScenes.return_value = [geo, plain]

    scenes = controller._scenesForExternalPublisher(
      'drone-1', {'pose': {'reference_frame': 'wgs84'}}, 1.0)

    assert scenes == [geo]

  def test_scene_frame_without_binding_is_empty(self):
    controller = self._build_controller()
    scenes = controller._scenesForExternalPublisher(
      'pos-1', {'pose': {'reference_frame': 'scene', 'translation': [0, 0, 0]}}, 1.0)
    assert scenes == []


class TestSceneControllerHandleChildSceneObject:
  """Unit tests for SceneController._handleChildSceneObject."""

  def _build_controller(self):
    controller = SceneController.__new__(SceneController)
    controller.cache_manager = MagicMock()
    return controller

  def test_root_scene_hierarchy_echo_is_ignored(self):
    """Hierarchy publishes from a root scene (no parent) return None, not failure."""
    scene_controller = self._build_controller()
    root = SimpleNamespace(uid='root-1', parent=None)
    scene_controller.cache_manager.sceneWithID.return_value = root
    # Local roots must not consult remote-child parent recovery.
    scene_controller._parentUidForRemoteChild = MagicMock()

    result = scene_controller._handleChildSceneObject(
      'root-1', {'objects': []}, 'person', 42.0)

    assert result is None
    assert root.parent is None
    scene_controller.cache_manager.sceneWithRemoteChildID.assert_not_called()
    scene_controller._parentUidForRemoteChild.assert_not_called()

  def test_child_scene_forwards_to_parent(self):
    """Configured child scenes still transform into the parent scene."""
    scene_controller = self._build_controller()
    child = SimpleNamespace(uid='child-1', parent='parent-1', cameraPose=MagicMock())
    parent = SimpleNamespace(uid='parent-1', processSceneData=MagicMock(return_value=True))
    scene_controller.cache_manager.sceneWithID.side_effect = lambda uid: {
      'child-1': child, 'parent-1': parent,
    }.get(uid)

    success, scene = scene_controller._handleChildSceneObject(
      'child-1', {'objects': [{'id': 'o1'}]}, 'person', 42.0)

    assert success is True
    assert scene is parent
    parent.processSceneData.assert_called_once()

  def test_unknown_sender_returns_failure_tuple(self):
    """Unknown hierarchy senders fail closed without raising."""
    scene_controller = self._build_controller()
    scene_controller.cache_manager.sceneWithID.return_value = None
    scene_controller.cache_manager.sceneWithRemoteChildID.return_value = None

    success, scene = scene_controller._handleChildSceneObject(
      'missing', {'objects': []}, 'person', 42.0)

    assert success is False
    assert scene is None


class TestScenesForExternalPublisherAdditional:
  """Extra binding / fan-out cases for publisher-centric attach."""

  def _build_controller(self, bindings=None):
    controller = SceneController.__new__(SceneController)
    controller.external_source_bindings = bindings or {}
    controller.external_source_pose_cache = MagicMock()
    controller.cache_manager = MagicMock()
    return controller

  def test_wgs84_fans_out_to_all_geo_scenes(self):
    geo1 = SimpleNamespace(uid='g1', trs_xyz_to_lla=object())
    geo2 = SimpleNamespace(uid='g2', trs_xyz_to_lla=object())
    plain = SimpleNamespace(uid='plain', trs_xyz_to_lla=None)
    controller = self._build_controller()
    controller.cache_manager.allScenes.return_value = [geo1, plain, geo2]

    scenes = controller._scenesForExternalPublisher(
      'drone-1', {'pose': {'reference_frame': 'wgs84'}}, 1.0)

    assert scenes == [geo1, geo2]

  def test_pose_omit_uses_live_cache_scenes(self):
    scene = SimpleNamespace(uid='cached-scene')
    controller = self._build_controller()
    controller.external_source_pose_cache.scenesWithLiveCache.return_value = [
      'cached-scene']
    controller.cache_manager.sceneWithID.return_value = scene

    scenes = controller._scenesForExternalPublisher('drone-1', {}, 10.0)

    assert scenes == [scene]
    controller.external_source_pose_cache.scenesWithLiveCache.assert_called_once_with(
      'drone-1', 10.0)


class TestTrustedScenePoseWithManualBinding:
  """Manual binding + trusted positioning source enables scene-frame ingest."""

  def test_bound_trusted_source_reaches_process_scene_data(self):
    controller = SceneController.__new__(SceneController)
    controller.external_source_bindings = {'pos-1': frozenset({'scene-a'})}
    controller.trusted_positioning_sources = frozenset({'pos-1'})
    controller.identity_claim_registry = IdentityClaimRegistry()
    fake_pose = MagicMock()
    controller.external_source_pose_cache = MagicMock()
    controller.external_source_pose_cache.resolve.return_value = (fake_pose, None)
    scene = SimpleNamespace(uid='scene-a', processSceneData=MagicMock(return_value=True))
    controller.cache_manager = MagicMock()
    controller.cache_manager.sceneWithID.return_value = scene

    jdata = {
      'source_id': 'pos-1',
      'pose': {
        'reference_frame': 'scene',
        'translation': [1.0, 2.0, 0.0],
        'rotation': [0, 0, 0, 1],
      },
      'objects': [{'id': 't1', 'category': 'person', 'translation': [0, 0, 0]}],
    }
    scenes = controller._scenesForExternalPublisher('pos-1', jdata, 5.0)
    assert scenes == [scene]

    assert controller._handleExternalSourceObject(scene, jdata, 'person', 5.0) is True
    controller.external_source_pose_cache.resolve.assert_called_once_with(
      scene, 'pos-1', jdata['pose'], 5.0, trusted_scene_pose=True)
    scene.processSceneData.assert_called_once()


class TestHandleMovingObjectExternal:
  """DATA_EXTERNAL wiring in handleMovingObjectMessage (helpers tested elsewhere)."""

  def _build_controller(self):
    controller = SceneController.__new__(SceneController)
    controller.schema_val = MagicMock()
    controller.schema_val.validateMessage.return_value = True
    controller.ntp_server = 'ntp'
    controller.ntp_client = MagicMock()
    controller.last_time_sync = None
    controller.time_offset = 0
    controller.max_lag = 3600
    controller.rewrite_all_time = False
    controller.rewrite_bad_time = False
    controller.cache_manager = MagicMock()
    controller.external_source_bindings = {}
    controller._handleExternalSourceObject = MagicMock(return_value=True)
    controller._scenesForExternalPublisher = MagicMock(return_value=[MagicMock()])
    controller.publishDetections = MagicMock()
    return controller

  def _external_message(self, scene_id, payload):
    message = MagicMock()
    message.topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=scene_id, thing_type='person')
    message.payload = json.dumps(payload).encode('utf-8')
    return message

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_source_id_topic_mismatch_is_dropped(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    controller = self._build_controller()
    message = self._external_message('drone-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'source_id': 'other-drone',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller._scenesForExternalPublisher.assert_not_called()
    controller._handleExternalSourceObject.assert_not_called()
    controller.cache_manager.invalidate.assert_not_called()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_matching_source_id_ingests_and_publishes(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    controller = self._build_controller()
    scene = MagicMock()
    scene.uid = 'scene-a'
    scene.name = 'Scene A'
    scene.tracker.getUniqueIDCount.return_value = 1
    scene.tracker.currentObjects.return_value = ['obj']
    controller._scenesForExternalPublisher.return_value = [scene]
    message = self._external_message('drone-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'source_id': 'drone-1',
      'objects': [{'id': 't1'}],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller._scenesForExternalPublisher.assert_called_once()
    controller._handleExternalSourceObject.assert_called_once()
    controller.publishDetections.assert_called_once()
    controller.cache_manager.invalidate.assert_not_called()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_no_scene_binding_returns_without_invalidate(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    controller = self._build_controller()
    controller._scenesForExternalPublisher.return_value = []
    message = self._external_message('drone-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'source_id': 'drone-1',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller._handleExternalSourceObject.assert_not_called()
    controller.publishDetections.assert_not_called()
    controller.cache_manager.invalidate.assert_not_called()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_ingest_failure_invalidates_cache(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    controller = self._build_controller()
    scene = MagicMock()
    scene.name = 'Scene A'
    controller._scenesForExternalPublisher.return_value = [scene]
    controller._handleExternalSourceObject.return_value = False
    message = self._external_message('drone-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'source_id': 'drone-1',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller.cache_manager.invalidate.assert_called_once()
    controller.publishDetections.assert_not_called()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_hierarchy_root_echo_none_is_ignored(
    self, _mock_epoch, _mock_adjust, _mock_metrics
  ):
    """Hierarchy messages (no source_id) that return None must not invalidate."""
    controller = self._build_controller()
    # Not a local no-parent scene, so the cheap early reject does not fire and
    # the legacy _handleChildSceneObject None path still applies.
    controller.cache_manager.sceneWithID.return_value = None
    controller._handleChildSceneObject = MagicMock(return_value=None)
    message = self._external_message('root-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller._handleChildSceneObject.assert_called_once()
    controller._scenesForExternalPublisher.assert_not_called()
    controller.cache_manager.invalidate.assert_not_called()
    controller.publishDetections.assert_not_called()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_own_hierarchy_echo_rejected_before_heavy_work(
    self, mock_epoch, mock_adjust, _mock_metrics
  ):
    """Local scene with no parent: drop own external echo before NTP/schema."""
    controller = self._build_controller()
    controller.cache_manager.sceneWithID.return_value = SimpleNamespace(
      uid='root-1', parent=None)
    controller._handleChildSceneObject = MagicMock()
    message = self._external_message('root-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller.cache_manager.sceneWithID.assert_called_once_with('root-1')
    controller._handleChildSceneObject.assert_not_called()
    controller.schema_val.validateMessage.assert_not_called()
    mock_adjust.assert_not_called()
    mock_epoch.assert_not_called()
    controller._scenesForExternalPublisher.assert_not_called()
    controller.publishDetections.assert_not_called()
    controller.cache_manager.invalidate.assert_not_called()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_local_child_hierarchy_echo_still_ingested(
    self, _mock_epoch, mock_adjust, _mock_metrics
  ):
    """Local child with a parent must still reach _handleChildSceneObject."""
    controller = self._build_controller()
    controller.cache_manager.sceneWithID.return_value = SimpleNamespace(
      uid='child-1', parent='parent-1')
    parent_scene = MagicMock()
    parent_scene.uid = 'parent-1'
    parent_scene.name = 'Parent'
    parent_scene.tracker.getUniqueIDCount.return_value = 0
    parent_scene.tracker.currentObjects.return_value = []
    controller._handleChildSceneObject = MagicMock(return_value=(True, parent_scene))
    message = self._external_message('child-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller._handleChildSceneObject.assert_called_once()
    mock_adjust.assert_called_once()
    controller.publishDetections.assert_called_once()

  @patch('controller.scene_controller.metrics')
  @patch('controller.scene_controller.adjust_time', return_value=(0.0, None))
  @patch('controller.scene_controller.get_epoch_time', return_value=100.0)
  def test_remote_child_hierarchy_ingest_succeeds_when_not_local(
    self, _mock_epoch, mock_adjust, _mock_metrics
  ):
    """Parent-side remote ingest: sceneWithID(child) is None so early reject
    must not fire; successful _handleChildSceneObject still publishes."""
    controller = self._build_controller()
    # Remote child is not a local scene on the parent controller.
    controller.cache_manager.sceneWithID.return_value = None
    parent_scene = MagicMock()
    parent_scene.uid = 'parent-1'
    parent_scene.name = 'Parent'
    parent_scene.tracker.getUniqueIDCount.return_value = 0
    parent_scene.tracker.currentObjects.return_value = []
    controller._handleChildSceneObject = MagicMock(return_value=(True, parent_scene))
    message = self._external_message('remote-child-1', {
      'timestamp': '2026-01-01T00:00:00Z',
      'objects': [],
    })

    controller.handleMovingObjectMessage(None, None, message)

    controller.cache_manager.sceneWithID.assert_called_with('remote-child-1')
    controller._handleChildSceneObject.assert_called_once()
    mock_adjust.assert_called_once()
    controller.publishDetections.assert_called_once()
    controller.cache_manager.invalidate.assert_not_called()


class TestSceneControllerShutdown:
  """Controller owns pose/identity sweep threads; shutdown must stop both."""

  def test_shutdown_stops_external_source_background_sweeps(self):
    controller = SceneController.__new__(SceneController)
    controller.external_source_pose_cache = MagicMock()
    controller.identity_claim_registry = MagicMock()

    controller.shutdown()
    controller.shutdown()  # idempotent

    assert controller.external_source_pose_cache.stopBackgroundSweep.call_count == 2
    assert controller.identity_claim_registry.stopBackgroundSweep.call_count == 2


class TestUpdateSubscriptionsExternalWildcard:
  """Publisher-centric interim subscribe uses one external wildcard."""

  def test_subscribes_external_wildcard_once(self):
    controller = SceneController.__new__(SceneController)
    controller.cache_manager = MagicMock()
    scene = SimpleNamespace(uid='scene-1', cameras={}, sensors={})
    controller.cache_manager.allScenes.return_value = [scene]
    controller.pubsub = MagicMock()
    controller.subscribed = set()
    controller.subscribed_children = {}
    controller.root_cert = None

    controller.updateSubscriptions()

    expected = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id='+', thing_type='+')
    topics = {topic for topic, _cb in controller.subscribed}
    assert expected in topics
    # No per-scene inbox subscribe.
    assert PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id='scene-1', thing_type='+') not in topics


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

