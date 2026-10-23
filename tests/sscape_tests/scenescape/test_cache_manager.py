# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import threading
import time

import pytest
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

from scene_common.cache_manager import CacheManager
from scene_common.data_source import FileSceneDataSource, RestSceneDataSource
from controller.scene import Scene


class TestCacheManagerInitialization:
  """Test CacheManager initialization with different data sources."""

  def test_init_with_file_data_source_mock(self):
    """Test initialization with file-based data source (mocked)."""
    mock_data_source = Mock(spec=FileSceneDataSource)
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.camera_parameters = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    assert cache_mgr is not None
    assert hasattr(cache_mgr, 'cached_scenes_by_uid')
    assert hasattr(cache_mgr, 'camera_parameters')

  def test_init_with_rest_data_source(self, mock_rest_client):
    """Test initialization with REST data source."""
    with patch('scene_common.data_source.RESTClient', return_value=mock_rest_client):
      cache_mgr = CacheManager.__new__(CacheManager)
      cache_mgr._lock = threading.RLock()
      cache_mgr.cached_scenes_by_uid = {}
      cache_mgr._cached_scenes_by_cameraID = {}
      cache_mgr._cached_scenes_by_sensorID = {}
      cache_mgr.tracker_config_data = {}
      cache_mgr.data_source = mock_rest_client

    assert cache_mgr is not None

  def test_init_with_no_data_source_raises_error(self):
    """Test that initialization without data source raises ValueError."""
    with pytest.raises(ValueError, match="Invalid configuration"):
      CacheManager()

  def test_init_with_tracker_config(self):
    """Test initialization with tracker configuration."""
    tracker_config = {
      'max_unreliable_time': 5.0,
      'non_measurement_time_dynamic': 2.0,
      'non_measurement_time_static': 10.0,
      'effective_object_update_rate': 30,
      'time_chunking_enabled': False,
      'time_chunking_rate_fps': 30,
      'suspended_track_timeout_secs': 60,
      'persist_attributes': {'test_attr': 'value'}
    }

    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = tracker_config
    cache_mgr.data_source = mock_data_source

    assert cache_mgr.tracker_config_data == tracker_config


class TestCacheManagerRefreshScenes:
  """Test scene refresh functionality."""

  def test_refresh_scenes_with_empty_results(self):
    """Test that refreshScenes handles empty results gracefully."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    cache_mgr.refreshScenes()

    assert len(cache_mgr.cached_scenes_by_uid) == 0

  def test_refresh_scenes_handles_failed_request(self):
    """Test that refreshScenes handles failed data source requests."""
    mock_data_source = Mock()
    mock_response = Mock()
    mock_response.statusCode = 500
    mock_response.__contains__ = Mock(return_value=False)
    mock_data_source.getScenes.return_value = mock_response

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    with patch('scene_common.cache_manager.log.error') as mock_log_error:
      # Should not raise, just return without updating cache
      cache_mgr.refreshScenes()

    mock_log_error.assert_called_once_with("Failed to get results, error code: ", 500)

    assert len(cache_mgr.cached_scenes_by_uid) == 0

  def test_refresh_scenes_sets_cache_timestamp(self):
    """Test that refreshScenes sets the cache refresh timestamp."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    cache_mgr.refreshScenes()

    assert hasattr(cache_mgr, '_cache_refreshed')
    assert cache_mgr._cache_refreshed > 0

  def test_refresh_scenes_injects_pose_adjustment_config_into_scene_data(self):
    """Configured pose-adjustment routing is added to scene data before deserialization."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {
      'results': [
        {
          'uid': 'scene-1',
          'name': 'scene-1',
          'map': None,
          'cameras': [],
          'sensors': [],
        }
      ]
    }

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.reid_config_data = {}
    cache_mgr.pose_adjustment_config_data = {'person': ['pedestrian']}
    cache_mgr.data_source = mock_data_source

    with patch('controller.scene.Scene.deserialize') as mock_deserialize:
      scene = MagicMock(spec=Scene)
      scene.uid = 'scene-1'
      scene.cameras = {}
      scene.sensors = {}
      mock_deserialize.return_value = scene

      cache_mgr.refreshScenes()

    scene_data = mock_deserialize.call_args.args[0]
    assert scene_data['pose_adjustment_config_data'] == cache_mgr.pose_adjustment_config_data


class TestCacheManagerCameraParameters:
  """Test camera parameter management."""

  def test_camera_parameters_changed_with_intrinsics(self):
    """Test detecting intrinsics parameter changes."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.camera_parameters = {}

    message = {
      'id': 'cam-1',
      'intrinsics': {'cx': 320, 'cy': 240, 'fx': 500, 'fy': 500}
    }

    result = cache_mgr.cameraParametersChanged(message, 'intrinsics')

    # Should detect change on first call
    assert result is True
    assert cache_mgr.camera_parameters['cam-1']['intrinsics'] == message['intrinsics']

  def test_camera_parameters_changed_with_distortion(self):
    """Test detecting distortion parameter changes."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.camera_parameters = {}

    message = {
      'id': 'cam-1',
      'distortion': {'k1': 0.1, 'k2': 0.01, 'p1': 0.001, 'p2': 0.001, 'k3': 0.0}
    }

    result = cache_mgr.cameraParametersChanged(message, 'distortion')

    assert result is True
    assert cache_mgr.camera_parameters['cam-1']['distortion'] == message['distortion']

  def test_camera_parameters_no_change_on_duplicate(self):
    """Test that duplicate parameters are not considered changed."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.camera_parameters = {}

    message = {
      'id': 'cam-1',
      'intrinsics': {'cx': 320, 'cy': 240}
    }

    # First call should detect change
    result1 = cache_mgr.cameraParametersChanged(message, 'intrinsics')
    assert result1 is True

    # Second call with same data should not detect change
    result2 = cache_mgr.cameraParametersChanged(message, 'intrinsics')
    assert result2 is False

  def test_camera_parameters_changed_no_message_parameters(self):
    """Test handling when message has no parameters."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.camera_parameters = {}

    message = {'id': 'cam-1'}

    result = cache_mgr.cameraParametersChanged(message, 'intrinsics')

    assert result is False


class TestCacheManagerQueryMethods:
  """Test cache query methods."""

  def test_all_scenes_returns_cached_scenes(self):
    """Test allScenes returns all cached scenes."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene1 = Mock(spec=Scene)
    mock_scene2 = Mock(spec=Scene)
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene1, 'scene-2': mock_scene2}
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    cache_mgr._cache_refreshed = 0

    scenes = list(cache_mgr.allScenes())

    assert len(scenes) == 2

  def test_scene_with_id(self):
    """Test retrieving scene by ID."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    mock_scene.uid = 'scene-1'
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    cache_mgr._cache_refreshed = 0

    scene = cache_mgr.sceneWithID('scene-1')

    assert scene is not None
    assert scene.uid == 'scene-1'

  def test_scene_with_invalid_id_returns_none(self):
    """Test that invalid scene ID returns None."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    scene = cache_mgr.sceneWithID('invalid-uid')

    assert scene is None

  def test_scene_with_camera_id(self):
    """Test retrieving scene by camera ID."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    mock_scene.uid = 'scene-1'
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr._cached_scenes_by_cameraID = {'cam-1': mock_scene}
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    cache_mgr._cache_refreshed = 0

    scene = cache_mgr.sceneWithCameraID('cam-1')

    assert scene is not None
    assert scene.uid == 'scene-1'

  def test_scene_with_invalid_camera_id_returns_none(self):
    """Test that invalid camera ID returns None."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    scene = cache_mgr.sceneWithCameraID('invalid-cam-id')

    assert scene is None

  def test_scene_with_sensor_id(self):
    """Test retrieving scene by sensor ID."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    mock_scene.uid = 'scene-1'
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr._cached_scenes_by_sensorID = {'sensor-1': mock_scene}
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    cache_mgr._cache_refreshed = 0

    scene = cache_mgr.sceneWithSensorID('sensor-1')

    assert scene is not None
    assert scene.uid == 'scene-1'

  def test_scene_with_invalid_sensor_id_returns_none(self):
    """Test that invalid sensor ID returns None."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    scene = cache_mgr.sceneWithSensorID('invalid-sensor-id')

    assert scene is None


class TestCacheManagerInvalidation:
  """Test cache invalidation."""

  def test_refresh_state_is_per_instance(self):
    """Multiple CacheManager instances must not share epoch or in-flight flags."""
    first = CacheManager.__new__(CacheManager)
    second = CacheManager.__new__(CacheManager)
    first._refreshLock()
    second._refreshLock()

    first._refresh_in_progress = True
    first._cache_epoch = 7

    assert second._refresh_in_progress is False
    assert second._cache_epoch == 0
    assert CacheManager.__dict__.get('_refresh_in_progress') is None
    assert CacheManager.__dict__.get('_cache_epoch') is None

  def test_invalidate_bumps_only_this_instance_epoch(self):
    """invalidate() must not supersede another manager's in-flight refresh."""
    first = CacheManager.__new__(CacheManager)
    second = CacheManager.__new__(CacheManager)
    first._refreshLock()
    second._refreshLock()
    first.cached_scenes_by_uid = {}
    first.cached_child_transforms_by_uid = {}
    second_scene = Mock(spec=Scene)
    second.cached_scenes_by_uid = {'scene-2': second_scene}
    second.cached_child_transforms_by_uid = {}
    second_epoch = second._cache_epoch

    first.invalidate()

    assert first._cache_epoch == 1
    assert second._cache_epoch == second_epoch
    assert second.cached_scenes_by_uid == {'scene-2': second_scene}

  def test_invalidate_clears_cache(self):
    """Test that invalidate clears the scene cache and secondary indexes."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    mock_remote_child = Mock(spec=Scene)
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr._cached_scenes_by_cameraID = {'camera-1': mock_scene}
    cache_mgr._cached_scenes_by_sensorID = {'sensor-1': mock_scene}
    cache_mgr.cached_child_transforms_by_uid = {'remote-child-1': mock_remote_child}

    cache_mgr.invalidate()

    assert cache_mgr.cached_scenes_by_uid is None
    assert cache_mgr._cached_scenes_by_cameraID == {}
    assert cache_mgr._cached_scenes_by_sensorID == {}
    assert cache_mgr.cached_child_transforms_by_uid == {'remote-child-1': mock_remote_child}

  def test_invalidate_preserves_old_cache(self):
    """Test that invalidate preserves old cache for sensor restoration."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    original_cache = {'scene-1': mock_scene}
    cache_mgr.cached_scenes_by_uid = original_cache.copy()
    cache_mgr.cached_child_transforms_by_uid = {}

    cache_mgr.invalidate()

    # Old cache should be preserved
    assert hasattr(cache_mgr, '_old_scene_cache')
    assert cache_mgr._old_scene_cache is not None

  def test_check_refresh_recreates_cache(self):
    """Test that checkRefresh recreates cache when None."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = None
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    cache_mgr.checkRefresh()

    assert cache_mgr.cached_scenes_by_uid is not None


class TestCacheManagerSceneReuse:
  """Test which scenes survive an invalidate() by being reused."""

  def test_scene_needs_full_reuse_returns_none_when_no_cache(self):
    """No old cache means nothing to reuse."""
    cache_mgr = CacheManager.__new__(CacheManager)

    if hasattr(cache_mgr, '_old_scene_cache'):
      delattr(cache_mgr, '_old_scene_cache')

    assert cache_mgr._sceneNeedsFullReuse('scene-uid') is None

  def test_scene_needs_full_reuse_returns_none_for_tracker_owning_scene(self):
    """A scene that owns a tracker is rebuilt, even when it has sensor values."""
    cache_mgr = CacheManager.__new__(CacheManager)

    old_scene = Mock()
    old_scene.sensors = {'sensor-1': Mock(value=42)}
    cache_mgr._old_scene_cache = {'scene-uid': old_scene}

    assert cache_mgr._sceneNeedsFullReuse('scene-uid') is None

  def test_scene_needs_full_reuse_returns_none_for_unknown_uid(self):
    """A uid missing from the old cache has no scene to reuse."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._old_scene_cache = {'other-uid': SimpleNamespace(sensors={})}

    assert cache_mgr._sceneNeedsFullReuse('scene-uid') is None

  def test_scene_needs_full_reuse_returns_old_scene_when_no_tracker(self):
    """A scene with no ``tracker`` attribute (e.g. AnalyticsScene) is always
    reused, since it owns no tracked-object identity of its own and instead
    needs its ingestion/region/dwell state preserved across the frequent
    invalidate() calls REST config changes trigger."""
    cache_mgr = CacheManager.__new__(CacheManager)

    old_scene = SimpleNamespace(sensors={})
    cache_mgr._old_scene_cache = {'scene-uid': old_scene}

    assert cache_mgr._sceneNeedsFullReuse('scene-uid') is old_scene


def _tracker_scene(uid, name):
  """Stand-in for a Controller Scene that owns a tracker."""
  scene = Mock()
  scene.uid = uid
  scene.name = name
  scene.cameras = {}
  scene.sensors = {}
  scene.tracker = Mock()
  return scene


def _trackerless_scene(uid, name):
  """Stand-in for an AnalyticsScene, which has no tracker attribute."""
  return SimpleNamespace(uid=uid, name=name, cameras={}, sensors={},
                         updateScene=Mock())


def _scene_data(uid, name):
  return {'uid': uid, 'name': name, 'cameras': []}


def _bare_manager(scene_factory=_tracker_scene):
  cache_mgr = CacheManager.__new__(CacheManager)
  cache_mgr._refreshLock()
  cache_mgr.cached_scenes_by_uid = {}
  cache_mgr.cached_child_transforms_by_uid = {}
  cache_mgr.camera_parameters = {}
  cache_mgr.tracker_config_data = {}
  cache_mgr.reid_config_data = {}
  cache_mgr.pose_adjustment_config_data = {}
  scene_cls = Mock()
  scene_cls.deserialize.side_effect = lambda data: scene_factory(data['uid'], data['name'])
  cache_mgr._scene_cls = scene_cls
  cache_mgr.data_source = Mock()
  return cache_mgr, scene_cls


def _rebuild(cache_mgr, found):
  """Apply results the way a refresh after invalidate() does."""
  cache_mgr.invalidate()
  return cache_mgr._applySceneResults(found)


class TestCacheManagerSceneRetirement:
  """Scenes that leave the cache are handed back for teardown."""

  def test_replaced_tracker_scene_is_retired(self):
    cache_mgr, scene_cls = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    old_scene = cache_mgr.cached_scenes_by_uid['a']

    retired = _rebuild(cache_mgr, [_scene_data('a', 'A')])

    assert scene_cls.deserialize.call_count == 2
    assert cache_mgr.cached_scenes_by_uid['a'] is not old_scene
    assert retired == [old_scene]
    old_scene.updateScene.assert_not_called()

  def test_scene_without_tracker_is_reused_not_retired(self):
    cache_mgr, scene_cls = _bare_manager(_trackerless_scene)
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    old_scene = cache_mgr.cached_scenes_by_uid['a']

    retired = _rebuild(cache_mgr, [_scene_data('a', 'A')])

    assert scene_cls.deserialize.call_count == 1
    assert cache_mgr.cached_scenes_by_uid['a'] is old_scene
    old_scene.updateScene.assert_called_once()
    assert retired == []

  def test_deleted_scene_is_retired_after_invalidate(self):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A'), _scene_data('b', 'B')])
    old_a = cache_mgr.cached_scenes_by_uid['a']
    old_b = cache_mgr.cached_scenes_by_uid['b']

    retired = _rebuild(cache_mgr, [_scene_data('a', 'A')])

    assert len(retired) == 2
    assert {id(scene) for scene in retired} == {id(old_a), id(old_b)}
    assert set(cache_mgr.cached_scenes_by_uid) == {'a'}

  def test_deleted_scene_is_retired_without_invalidate(self):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A'), _scene_data('b', 'B')])
    kept = cache_mgr.cached_scenes_by_uid['a']
    deleted = cache_mgr.cached_scenes_by_uid['b']

    retired = cache_mgr._applySceneResults([_scene_data('a', 'A')])

    assert retired == [deleted]
    assert cache_mgr.cached_scenes_by_uid == {'a': kept}
    kept.updateScene.assert_called_once()

  def test_scene_in_both_deleted_set_and_old_cache_is_retired_once(self):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A'), _scene_data('b', 'B')])
    deleted = cache_mgr.cached_scenes_by_uid['b']
    cache_mgr._old_scene_cache = {'b': deleted}

    retired = cache_mgr._applySceneResults([_scene_data('a', 'A')])

    assert retired == [deleted]

  def test_apply_results_does_not_tear_down_inline(self):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A'), _scene_data('b', 'B')])
    deleted = cache_mgr.cached_scenes_by_uid['b']

    with patch.object(cache_mgr, '_teardownScene') as teardown:
      cache_mgr._applySceneResults([_scene_data('a', 'A')])

    teardown.assert_not_called()
    deleted.tracker.join.assert_not_called()

  def test_nothing_is_retired_on_first_load(self):
    cache_mgr, _ = _bare_manager()

    retired = cache_mgr._applySceneResults([_scene_data('a', 'A')])

    assert retired == []


def _wait(event, timeout=5):
  assert event.wait(timeout), "timed out waiting for background teardown"


def _wait_for_calls(mock, count, timeout=5):
  deadline = time.monotonic() + timeout
  while mock.call_count < count and time.monotonic() < deadline:
    time.sleep(0.01)
  assert mock.call_count >= count, "timed out waiting for background teardown"


class TestCacheManagerTeardown:
  """_teardownScene() joins the tracker, then decides about the registries."""

  @pytest.fixture
  def registries(self):
    with patch('scene_common.cache_manager.CameraRegistry') as camera, \
         patch('scene_common.cache_manager.TrackedObjectRegistry') as tracked:
      yield SimpleNamespace(camera=camera.getInstance.return_value,
                            tracked=tracked.getInstance.return_value)

  def test_registries_are_cleared_after_the_join(self, registries):
    cache_mgr, _ = _bare_manager()
    scene = _tracker_scene('a', 'A')
    calls = []
    scene.tracker.join.side_effect = lambda *args: calls.append('join')
    registries.camera.removeScene.side_effect = lambda name: calls.append('camera')
    registries.tracked.removeScene.side_effect = lambda name: calls.append('tracked')

    cache_mgr._teardownScene(scene)

    assert calls == ['join', 'camera', 'tracked']
    registries.camera.removeScene.assert_called_once_with('A')
    registries.tracked.removeScene.assert_called_once_with('A')

  def test_scene_without_tracker_still_clears_registries(self, registries):
    cache_mgr, _ = _bare_manager()

    cache_mgr._teardownScene(_trackerless_scene('a', 'A'))

    registries.camera.removeScene.assert_called_once_with('A')

  def test_none_scene_is_a_noop(self, registries):
    cache_mgr, _ = _bare_manager()

    cache_mgr._teardownScene(None)

    registries.camera.removeScene.assert_not_called()

  def test_same_name_rebuild_keeps_registries(self, registries):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    old_scene = cache_mgr.cached_scenes_by_uid['a']
    retired = _rebuild(cache_mgr, [_scene_data('a', 'A')])
    assert retired == [old_scene]

    cache_mgr._teardownScene(old_scene)

    old_scene.tracker.join.assert_called_once()
    registries.camera.removeScene.assert_not_called()
    registries.tracked.removeScene.assert_not_called()

  def test_rename_clears_the_old_name(self, registries):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    old_scene = cache_mgr.cached_scenes_by_uid['a']
    retired = _rebuild(cache_mgr, [_scene_data('a', 'A-renamed')])
    assert retired == [old_scene]

    cache_mgr._teardownScene(old_scene)

    registries.camera.removeScene.assert_called_once_with('A')
    registries.tracked.removeScene.assert_called_once_with('A')

  def test_deleted_scene_clears_its_name(self, registries):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A'), _scene_data('b', 'B')])
    retired = cache_mgr._applySceneResults([_scene_data('a', 'A')])

    cache_mgr._teardownScene(retired[0])

    registries.camera.removeScene.assert_called_once_with('B')

  def test_same_name_scene_created_during_the_join_is_not_wiped(self, registries):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    old_scene = cache_mgr.cached_scenes_by_uid['a']
    cache_mgr.cached_scenes_by_uid.pop('a')

    def create_same_name_scene(*args):
      cache_mgr.cached_scenes_by_uid['z'] = _tracker_scene('z', 'A')

    old_scene.tracker.join.side_effect = create_same_name_scene

    cache_mgr._teardownScene(old_scene)

    registries.camera.removeScene.assert_not_called()
    registries.tracked.removeScene.assert_not_called()

  def test_name_held_by_scene_awaiting_rebuild_is_kept(self, registries):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    cache_mgr.invalidate()
    assert cache_mgr.cached_scenes_by_uid is None

    cache_mgr._teardownScene(_tracker_scene('retired', 'A'))
    registries.camera.removeScene.assert_not_called()

    cache_mgr._teardownScene(_tracker_scene('retired', 'unrelated'))
    registries.camera.removeScene.assert_called_once_with('unrelated')

  def test_failing_join_is_logged_and_registries_are_still_cleared(self, registries):
    cache_mgr, _ = _bare_manager()
    scene = _tracker_scene('uid-1', 'A')
    scene.tracker.join.side_effect = RuntimeError("join failed")

    with patch('scene_common.cache_manager.log.error') as log_error:
      cache_mgr._teardownScene(scene)

    log_error.assert_called_once()
    message = log_error.call_args.args[0]
    assert 'uid-1' in message and 'A' in message and 'join failed' in message
    registries.camera.removeScene.assert_called_once_with('A')
    registries.tracked.removeScene.assert_called_once_with('A')

  def test_failing_registry_clear_is_logged_not_raised(self, registries):
    cache_mgr, _ = _bare_manager()
    scene = _tracker_scene('uid-1', 'A')
    registries.camera.removeScene.side_effect = RuntimeError("clear failed")

    with patch('scene_common.cache_manager.log.error') as log_error:
      cache_mgr._teardownScene(scene)

    scene.tracker.join.assert_called_once()
    log_error.assert_called_once()
    assert 'uid-1' in log_error.call_args.args[0]


class TestCacheManagerRefreshTeardown:
  """refreshScenes() tears retired scenes down in the background."""

  @pytest.fixture(autouse=True)
  def registries(self):
    with patch('scene_common.cache_manager.CameraRegistry') as camera, \
         patch('scene_common.cache_manager.TrackedObjectRegistry') as tracked:
      yield SimpleNamespace(camera=camera.getInstance.return_value,
                            tracked=tracked.getInstance.return_value)

  @staticmethod
  def _manager_with_old_scenes(*uids):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data(uid, uid.upper()) for uid in uids])
    old_scenes = dict(cache_mgr.cached_scenes_by_uid)
    cache_mgr.invalidate()
    return cache_mgr, old_scenes

  def test_refresh_returns_while_a_join_is_blocked_and_join_runs_without_the_lock(
      self, registries):
    cache_mgr, old_scenes = self._manager_with_old_scenes('a')
    cache_mgr.data_source.getScenes.return_value = {
      'results': [_scene_data('a', 'A-renamed')]}
    join_started, release_join = threading.Event(), threading.Event()
    lock_was_free = []

    def blocked_join(*args):
      acquired = cache_mgr._lock.acquire(blocking=False)
      lock_was_free.append(acquired)
      if acquired:
        cache_mgr._lock.release()
      join_started.set()
      release_join.wait(5)

    old_scenes['a'].tracker.join.side_effect = blocked_join

    try:
      cache_mgr.refreshScenes()

      _wait(join_started)
      assert lock_was_free == [True]
      assert cache_mgr.sceneWithID('a') is not old_scenes['a']
      registries.camera.removeScene.assert_not_called()
    finally:
      release_join.set()
    _wait_for_calls(registries.tracked.removeScene, 1)
    registries.camera.removeScene.assert_called_once_with('A')

  def test_deleted_scene_is_torn_down_without_a_preceding_invalidate(self, registries):
    cache_mgr, _ = _bare_manager()
    cache_mgr._applySceneResults([_scene_data('a', 'A'), _scene_data('b', 'B')])
    deleted = cache_mgr.cached_scenes_by_uid['b']
    cache_mgr.data_source.getScenes.return_value = {'results': [_scene_data('a', 'A')]}

    cache_mgr.refreshScenes(force=True)

    _wait_for_calls(registries.tracked.removeScene, 1)
    deleted.tracker.join.assert_called_once()
    registries.camera.removeScene.assert_called_once_with('B')

  def test_deleted_scene_is_torn_down_after_invalidate(self, registries):
    cache_mgr, old_scenes = self._manager_with_old_scenes('a', 'b')
    cache_mgr.data_source.getScenes.return_value = {'results': [_scene_data('a', 'A')]}

    cache_mgr.refreshScenes()

    for scene in old_scenes.values():
      _wait_for_calls(scene.tracker.join, 1)
    _wait_for_calls(registries.tracked.removeScene, 1)
    registries.camera.removeScene.assert_called_once_with('B')

  def test_failing_teardown_does_not_stop_the_others(self, registries):
    cache_mgr, old_scenes = self._manager_with_old_scenes('a', 'b')
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    old_scenes['a'].tracker.join.side_effect = RuntimeError("boom")

    with patch('scene_common.cache_manager.log.error') as log_error:
      cache_mgr.refreshScenes()
      _wait_for_calls(registries.tracked.removeScene, 2)

    old_scenes['b'].tracker.join.assert_called_once()
    log_error.assert_called_once()
    assert 'boom' in log_error.call_args.args[0]
    assert cache_mgr.allScenes() == []

  def test_trackerless_scene_is_never_torn_down(self, registries):
    cache_mgr, _ = _bare_manager(_trackerless_scene)
    cache_mgr._applySceneResults([_scene_data('a', 'A')])
    cache_mgr.invalidate()
    cache_mgr.data_source.getScenes.return_value = {'results': [_scene_data('a', 'A')]}

    with patch.object(cache_mgr, '_teardownScene') as teardown:
      cache_mgr.refreshScenes()

    teardown.assert_not_called()


class TestCacheManagerRefreshCameras:
  """Test camera refresh functionality."""

  def test_refresh_cameras_processes_all_cameras(self):
    """Test that _refreshCameras processes camera data."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.data_source = Mock()
    cache_mgr.camera_parameters = {}

    scene_data = {
      'cameras': [
        {
          'uid': 'cam-1',
          'intrinsics': {'cx': 320, 'cy': 240},
          'distortion': {}
        }
      ]
    }

    cache_mgr._refreshCameras(scene_data)

    # Should not raise any errors

  def test_refresh_cameras_with_no_cameras(self):
    """Test _refreshCameras with empty camera list."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.data_source = Mock()
    cache_mgr.camera_parameters = {}

    scene_data = {'cameras': []}

    cache_mgr._refreshCameras(scene_data)

    # Should not raise any errors

  def test_refresh_scenes_for_cam_params(self):
    """Test refreshScenesForCamParams updates camera parameters."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()

    mock_scene = Mock(spec=Scene)
    mock_camera = Mock()
    mock_camera.cameraID = 'cam-1'
    mock_camera.pose = Mock()
    mock_camera.pose.resolution = [640, 480]

    mock_scene.cameras = {'cam-1': mock_camera}
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    mock_scene.tracker = None
    mock_scene.name = 'scene-1'
    cache_mgr.camera_parameters = {}
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr._cache_refreshed = 0

    jdata = {
      'id': 'cam-1',
      'intrinsics': {'cx': 320, 'cy': 240, 'fx': 500, 'fy': 500}
    }

    cache_mgr.refreshScenesForCamParams(jdata)

    # Should not raise any errors

  def test_refresh_scenes_for_cam_params_tolerates_invalidated_cache(self):
    """After invalidate(), refreshScenesForCamParams must not touch None.values()."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.cached_scenes_by_uid = None
    cache_mgr.camera_parameters = {}

    cache_mgr.refreshScenesForCamParams({
      'id': 'cam-1',
      'intrinsics': {'cx': 320, 'cy': 240, 'fx': 500, 'fy': 500},
    })

    assert cache_mgr.cached_scenes_by_uid is None


class TestCacheManagerEdgeCases:
  """Test edge cases and error conditions."""

  def test_multiple_refresh_calls_are_idempotent(self):
    """Test that multiple refresh calls don't cause issues."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    cache_mgr.refreshScenes()
    count_before = len(cache_mgr.cached_scenes_by_uid)

    cache_mgr.refreshScenes()
    count_after = len(cache_mgr.cached_scenes_by_uid)

    assert count_before == count_after

  def test_cache_access_without_initialization(self):
    """Test cache access methods handle uninitialized state."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = None
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.data_source = mock_data_source

    # Should handle gracefully
    scenes = list(cache_mgr.allScenes())

    assert len(scenes) == 0

  def test_concurrent_cache_access(self):
    """Test cache can be accessed without errors."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene, 'scene-2': mock_scene}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    # Simulate concurrent access
    scenes1 = list(cache_mgr.allScenes())
    scenes2 = list(cache_mgr.allScenes())

    assert len(scenes1) == len(scenes2)

  def test_concurrent_refresh_is_single_flight(self):
    """Concurrent refreshScenes callers share one in-flight REST fetch."""
    fetch_started = threading.Event()
    waiter_blocked = threading.Event()
    release_fetch = threading.Event()
    mock_data_source = Mock()

    def blocking_get_scenes():
      fetch_started.set()
      assert release_fetch.wait(timeout=5), "timed out waiting to release getScenes"
      return {'results': []}

    mock_data_source.getScenes.side_effect = blocking_get_scenes

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._refresh_done = threading.Condition(cache_mgr._lock)
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.camera_parameters = {}
    cache_mgr.data_source = mock_data_source

    original_wait = cache_mgr._refresh_done.wait

    def wait_and_signal(timeout=None):
      waiter_blocked.set()
      return original_wait(timeout)

    cache_mgr._refresh_done.wait = wait_and_signal

    errors = []

    def worker():
      try:
        cache_mgr.refreshScenes()
      except Exception as exc:
        errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
      thread.start()

    assert fetch_started.wait(timeout=5), "leader never started getScenes"
    assert waiter_blocked.wait(timeout=5), "waiter never blocked on in-flight refresh"
    release_fetch.set()
    for thread in threads:
      thread.join(timeout=5)
      assert not thread.is_alive()

    assert not errors
    assert mock_data_source.getScenes.call_count == 1

  def test_invalidate_discards_stale_in_flight_refresh(self):
    """invalidate() bumps generation so an older in-flight fetch does not apply."""
    fetch_started = threading.Event()
    release_fetch = threading.Event()
    mock_data_source = Mock()
    stale_results = {
      'results': [
        {
          'uid': 'scene-stale',
          'name': 'stale',
          'map': None,
          'cameras': [],
          'sensors': [],
        }
      ]
    }
    fresh_results = {
      'results': [
        {
          'uid': 'scene-fresh',
          'name': 'fresh',
          'map': None,
          'cameras': [],
          'sensors': [],
        }
      ]
    }
    responses = [stale_results, fresh_results]

    def ordered_get_scenes():
      result = responses.pop(0)
      if result is stale_results:
        fetch_started.set()
        assert release_fetch.wait(timeout=5), "timed out waiting to release stale getScenes"
      return result

    mock_data_source.getScenes.side_effect = ordered_get_scenes

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._refresh_done = threading.Condition(cache_mgr._lock)
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.cached_child_transforms_by_uid = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.reid_config_data = {}
    cache_mgr.pose_adjustment_config_data = {}
    cache_mgr.camera_parameters = {}
    cache_mgr.data_source = mock_data_source

    errors = []

    def stale_refresh():
      try:
        cache_mgr.refreshScenes()
      except Exception as exc:
        errors.append(exc)

    stale_thread = threading.Thread(target=stale_refresh)
    stale_thread.start()
    assert fetch_started.wait(timeout=5), "stale refresh never started getScenes"

    cache_mgr.invalidate()
    release_fetch.set()
    stale_thread.join(timeout=5)
    assert not stale_thread.is_alive()
    assert not errors
    assert cache_mgr.cached_scenes_by_uid is None

    with patch('controller.scene.Scene.deserialize') as mock_deserialize:
      fresh_scene = MagicMock(spec=Scene)
      fresh_scene.uid = 'scene-fresh'
      fresh_scene.cameras = {}
      fresh_scene.sensors = {}
      mock_deserialize.return_value = fresh_scene

      cache_mgr.refreshScenes()

    assert list(cache_mgr.cached_scenes_by_uid.keys()) == ['scene-fresh']
    assert mock_data_source.getScenes.call_count == 2

  def test_waiter_after_invalidate_does_not_share_discarded_refresh(self):
    """A waiter joining after invalidate must not treat a discarded fetch as done."""
    fetch_started = threading.Event()
    invalidate_done = threading.Event()
    release_fetch = threading.Event()
    mock_data_source = Mock()
    responses = [
      {
        'results': [
          {
            'uid': 'scene-stale',
            'name': 'stale',
            'map': None,
            'cameras': [],
            'sensors': [],
          }
        ]
      },
      {
        'results': [
          {
            'uid': 'scene-fresh',
            'name': 'fresh',
            'map': None,
            'cameras': [],
            'sensors': [],
          }
        ]
      },
    ]

    def ordered_get_scenes():
      result = responses.pop(0)
      if fetch_started.is_set() is False:
        fetch_started.set()
        assert invalidate_done.wait(timeout=5), "timed out waiting for invalidate before release"
        assert release_fetch.wait(timeout=5), "timed out waiting to release stale getScenes"
      return result

    mock_data_source.getScenes.side_effect = ordered_get_scenes

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._refresh_done = threading.Condition(cache_mgr._lock)
    cache_mgr.cached_scenes_by_uid = {'scene-old': Mock(spec=Scene)}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.cached_child_transforms_by_uid = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.reid_config_data = {}
    cache_mgr.pose_adjustment_config_data = {}
    cache_mgr.camera_parameters = {}
    cache_mgr.data_source = mock_data_source

    errors = []

    def leader():
      try:
        cache_mgr.refreshScenes()
      except Exception as exc:
        errors.append(exc)

    leader_thread = threading.Thread(target=leader)
    leader_thread.start()
    assert fetch_started.wait(timeout=5), "leader never started getScenes"

    cache_mgr.invalidate()
    invalidate_done.set()

    with patch('controller.scene.Scene.deserialize') as mock_deserialize:
      fresh_scene = MagicMock(spec=Scene)
      fresh_scene.uid = 'scene-fresh'
      fresh_scene.cameras = {}
      fresh_scene.sensors = {}
      mock_deserialize.return_value = fresh_scene

      def waiter():
        try:
          # Joins after invalidate while the superseded fetch is still in flight.
          cache_mgr.refreshScenes()
        except Exception as exc:
          errors.append(exc)

      waiter_thread = threading.Thread(target=waiter)
      waiter_thread.start()
      # Allow the waiter to observe in-flight state after invalidate.
      assert waiter_thread.is_alive() or mock_data_source.getScenes.call_count >= 1
      release_fetch.set()
      leader_thread.join(timeout=5)
      waiter_thread.join(timeout=5)
      assert not leader_thread.is_alive()
      assert not waiter_thread.is_alive()

    assert not errors
    assert list(cache_mgr.cached_scenes_by_uid.keys()) == ['scene-fresh']
    assert mock_data_source.getScenes.call_count == 2

  def test_force_refresh_does_not_share_stale_in_flight_fetch(self):
    """force=True waits for in-flight work, then performs a new fetch."""
    fetch_started = threading.Event()
    waiter_blocked = threading.Event()
    release_fetch = threading.Event()
    mock_data_source = Mock()
    responses = [
      {
        'results': [
          {
            'uid': 'scene-stale',
            'name': 'stale',
            'map': None,
            'cameras': [],
            'sensors': [],
          }
        ]
      },
      {
        'results': [
          {
            'uid': 'scene-fresh',
            'name': 'fresh',
            'map': None,
            'cameras': [],
            'sensors': [],
          }
        ]
      },
    ]

    def ordered_get_scenes():
      result = responses.pop(0)
      if not fetch_started.is_set():
        fetch_started.set()
        assert release_fetch.wait(timeout=5), "timed out waiting to release stale getScenes"
      return result

    mock_data_source.getScenes.side_effect = ordered_get_scenes

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._refresh_done = threading.Condition(cache_mgr._lock)
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.reid_config_data = {}
    cache_mgr.pose_adjustment_config_data = {}
    cache_mgr.camera_parameters = {}
    cache_mgr.data_source = mock_data_source

    original_wait = cache_mgr._refresh_done.wait

    def wait_and_signal(timeout=None):
      waiter_blocked.set()
      return original_wait(timeout)

    cache_mgr._refresh_done.wait = wait_and_signal

    errors = []

    def leader():
      try:
        cache_mgr.refreshScenes()
      except Exception as exc:
        errors.append(exc)

    with patch('controller.scene.Scene.deserialize') as mock_deserialize:
      def make_scene(data):
        scene = MagicMock(spec=Scene)
        scene.uid = data['uid']
        scene.name = data['name']
        scene.cameras = {}
        scene.sensors = {}
        scene.tracker = None
        return scene

      mock_deserialize.side_effect = make_scene

      leader_thread = threading.Thread(target=leader)
      leader_thread.start()
      assert fetch_started.wait(timeout=5), "leader never started getScenes"

      def forced_waiter():
        try:
          cache_mgr.refreshScenes(force=True)
        except Exception as exc:
          errors.append(exc)

      force_thread = threading.Thread(target=forced_waiter)
      force_thread.start()
      assert waiter_blocked.wait(timeout=5), "forced waiter never blocked"
      release_fetch.set()
      leader_thread.join(timeout=5)
      force_thread.join(timeout=5)
      assert not leader_thread.is_alive()
      assert not force_thread.is_alive()

    assert not errors
    assert list(cache_mgr.cached_scenes_by_uid.keys()) == ['scene-fresh']
    assert mock_data_source.getScenes.call_count == 2

  def test_invalidate_preserves_old_cache_across_repeated_calls(self):
    """A second invalidate before refresh must not wipe the preserved scene cache."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    mock_scene = Mock(spec=Scene)
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.cached_child_transforms_by_uid = {}

    cache_mgr.invalidate()
    first_old = cache_mgr._old_scene_cache
    cache_mgr.invalidate()

    assert cache_mgr._old_scene_cache is first_old
    assert cache_mgr._old_scene_cache == {'scene-1': mock_scene}
