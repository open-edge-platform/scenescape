# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import threading

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

  def test_scene_configuration_preserves_tracker_order_and_optional_settings(self):
    cache_mgr = CacheManager.__new__(CacheManager)
    keys = ("max_unreliable_time", "non_measurement_time_dynamic", "non_measurement_time_static",
            "effective_object_update_rate", "time_chunking_enabled", "time_chunking_rate_fps",
            "suspended_track_timeout_secs")
    cache_mgr.tracker_config_data = dict(zip(keys, range(1, 8)))
    cache_mgr.tracker_config_data["persist_attributes"] = {"person": ["color"]}
    cache_mgr.reid_config_data = {"enabled": True}
    cache_mgr.pose_adjustment_config_data = {"person": ["pedestrian"]}
    data = {"uid": "scene"}
    cache_mgr._configureSceneData(data)
    assert data["tracker_config"] == list(range(1, 8))
    assert data["persist_attributes"] == {"person": ["color"]}
    assert data["reid_config_data"] == {"enabled": True}
    assert data["pose_adjustment_config_data"] == {"person": ["pedestrian"]}

  def test_existing_scene_is_updated_without_reconstruction(self):
    scene = SimpleNamespace(updateScene=Mock())
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.cached_scenes_by_uid = {"scene": scene}
    cache_mgr._scene_cls = SimpleNamespace(deserialize=Mock())
    data = {"uid": "scene", "name": "updated"}
    assert cache_mgr._sceneFromData(data) is scene
    scene.updateScene.assert_called_once_with(data)
    cache_mgr._scene_cls.deserialize.assert_not_called()

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


class TestCacheManagerSensorRestoration:
  """Test sensor cache restoration functionality."""

  @pytest.mark.parametrize("has_tracker,sensor_value,replace", [
    (True, None, True),
    (True, 42, False),
    (False, None, False),
  ])
  def test_refresh_tears_down_only_replaced_scene(self, has_tracker, sensor_value, replace):
    events = []
    tracker = Mock()
    tracker.join.side_effect = lambda: events.append("join")
    old_scene = SimpleNamespace(
      uid="scene-uid", name="scene-name", cameras={},
      sensors={"sensor-1": SimpleNamespace(value=sensor_value)},
      updateScene=Mock(),
    )
    if has_tracker:
      old_scene.tracker = tracker
    replacement = SimpleNamespace(uid=old_scene.uid, name=old_scene.name, cameras={}, sensors={})

    def deserialize(data):
      assert events == ["join", "cameras", "objects"]
      return replacement

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._old_scene_cache = {old_scene.uid: old_scene}
    cache_mgr.tracker_config_data = {}
    cache_mgr.reid_config_data = {}
    cache_mgr._scene_cls = SimpleNamespace(deserialize=Mock(side_effect=deserialize))
    with patch("scene_common.cache_manager.CameraRegistry.getInstance") as cameras, \
         patch("scene_common.cache_manager.TrackedObjectRegistry.getInstance") as objects:
      cameras.return_value.removeScene.side_effect = lambda name: events.append("cameras")
      objects.return_value.removeScene.side_effect = lambda name: events.append("objects")
      cache_mgr._applySceneResults([{"uid": old_scene.uid, "name": old_scene.name}])

      if replace:
        tracker.join.assert_called_once_with()
        cameras.return_value.removeScene.assert_called_once_with(old_scene.name)
        objects.return_value.removeScene.assert_called_once_with(old_scene.name)
        assert cache_mgr.cached_scenes_by_uid[old_scene.uid] is replacement
        old_scene.updateScene.assert_not_called()
      else:
        tracker.join.assert_not_called()
        cameras.return_value.removeScene.assert_not_called()
        objects.return_value.removeScene.assert_not_called()
        cache_mgr._scene_cls.deserialize.assert_not_called()
        assert cache_mgr.cached_scenes_by_uid[old_scene.uid] is old_scene
        old_scene.updateScene.assert_called_once()
    assert cache_mgr._old_scene_cache is None

  def test_repeated_replacement_joins_each_retired_tracker_once(self):
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.tracker_config_data = {}
    cache_mgr.reid_config_data = {}
    scenes = [SimpleNamespace(
      uid="scene-uid", name="scene-name", cameras={}, sensors={}, tracker=Mock(),
    ) for _ in range(4)]
    cache_mgr._scene_cls = SimpleNamespace(deserialize=Mock(side_effect=scenes[1:]))
    with patch("scene_common.cache_manager.CameraRegistry.getInstance"), \
         patch("scene_common.cache_manager.TrackedObjectRegistry.getInstance"):
      for previous in scenes[:-1]:
        cache_mgr.cached_scenes_by_uid = {}
        cache_mgr._old_scene_cache = {previous.uid: previous}
        cache_mgr._applySceneResults([{"uid": previous.uid, "name": previous.name}])
        previous.tracker.join.assert_called_once_with()
    assert cache_mgr.cached_scenes_by_uid[scenes[-1].uid] is scenes[-1]
    scenes[-1].tracker.join.assert_not_called()

  def test_restore_sensor_cache_copies_values(self):
    """Test that sensor cache values are properly restored."""
    cache_mgr = CacheManager.__new__(CacheManager)

    # Create mock old and new sensors
    old_sensor = Mock()
    old_sensor.value = 42
    old_sensor.lastValue = 41
    old_sensor.lastWhen = 1234567890

    new_sensor = Mock()
    new_sensor.value = None
    new_sensor.lastValue = None
    new_sensor.lastWhen = None

    old_scene = Mock()
    old_scene.sensors = {'sensor-1': old_sensor}

    new_scene = Mock()
    new_scene.sensors = {'sensor-1': new_sensor}

    cache_mgr._restoreSensorCache('scene-uid', old_scene, new_scene)

    assert new_sensor.value == 42
    assert new_sensor.lastValue == 41
    assert new_sensor.lastWhen == 1234567890

  def test_sensor_needs_restoring_returns_none_when_no_cache(self):
    """Test that sensorNeedsRestoring returns None when no old cache."""
    cache_mgr = CacheManager.__new__(CacheManager)

    if hasattr(cache_mgr, '_old_scene_cache'):
      delattr(cache_mgr, '_old_scene_cache')

    result = cache_mgr._sensorNeedsRestoring('scene-uid')

    assert result is None

  def test_sensor_needs_restoring_returns_old_scene(self):
    """Test that sensorNeedsRestoring returns old scene when it has sensors
    with cached values worth restoring."""
    cache_mgr = CacheManager.__new__(CacheManager)

    old_scene = Mock()
    old_scene.sensors = {'sensor-1': Mock(value=42)}
    cache_mgr._old_scene_cache = {'scene-uid': old_scene}

    result = cache_mgr._sensorNeedsRestoring('scene-uid')

    assert result == old_scene

  def test_sensor_needs_restoring_returns_none_when_no_sensor_values(self):
    """Test that sensorNeedsRestoring returns None when the old scene has no
    sensors, or none with a cached value, so a fresh Scene is deserialized
    instead of silently reusing stale tracked-object identities."""
    cache_mgr = CacheManager.__new__(CacheManager)

    old_scene = Mock()
    old_scene.sensors = {}
    cache_mgr._old_scene_cache = {'scene-uid': old_scene}

    result = cache_mgr._sensorNeedsRestoring('scene-uid')

    assert result is None

  def test_sensor_needs_restoring_returns_old_scene_when_no_tracker(self):
    """Test that a scene with no ``tracker`` attribute (e.g. AnalyticsScene)
    is always reused, since it owns no tracked-object identity of its own
    and instead needs its ingestion/region/dwell state preserved across the
    frequent invalidate() calls REST config changes trigger."""
    cache_mgr = CacheManager.__new__(CacheManager)

    old_scene = SimpleNamespace(sensors={})
    cache_mgr._old_scene_cache = {'scene-uid': old_scene}

    result = cache_mgr._sensorNeedsRestoring('scene-uid')

    assert result is old_scene


class TestCacheManagerRefreshCameras:
  """Test camera refresh functionality."""

  @pytest.mark.parametrize("metadata", [
    {'intrinsics': {'cx': 320, 'cy': 240, 'fx': 700, 'fy': 710}},
    {'distortion': {'k1': 0.1}},
    {'resolution': [1920, 1080]},
    {'resolution': {'width': 1920, 'height': 1080}},
  ])
  def test_optics_are_persisted_independently_of_frame_size(self, metadata):
    """Same-size focal changes and resolution-only messages must reach REST."""
    cache_mgr = CacheManager.__new__(CacheManager)
    camera = SimpleNamespace(cameraID='cam-1')
    cache_mgr.cached_scenes_by_uid = {
      'scene-1': SimpleNamespace(cameras={'cam-1': camera}),
    }
    cache_mgr._lock = threading.RLock()
    cache_mgr.camera_parameters = {'cam-1': {'resolution': [640, 480]}}
    cache_mgr.data_source = Mock()
    cache_mgr.checkRefresh = Mock()
    cache_mgr.refreshScenes = Mock()
    cache_mgr.refreshScenesForCamParams({'id': 'cam-1', **metadata})
    payload = dict(metadata)
    resolution = payload.pop('resolution', [640, 480])
    if isinstance(resolution, list):
      resolution = dict(zip(('width', 'height'), resolution))
    payload['resolution'] = resolution
    if 'distortion' in payload:
      payload['distortion'] = {'k1': 0.1, 'k2': 0, 'p1': 0, 'p2': 0, 'k3': 0}
    cache_mgr.data_source.updateCamera.assert_called_once_with('cam-1', payload)
    cache_mgr.refreshScenes.assert_called_once_with(force=True)

  @pytest.mark.parametrize("distortion", [
    {'k1': 0.1},
    [0.1, 0, 0, 0],
    [0.1, 0, 0, 0, 0, 0.4, 0.5, 0.6],
    {'k1': 0.1, 'k2': 0, 'p1': 0, 'p2': 0, 'k3': 0,
     'k4': 0.4, 'k5': 0.5, 'k6': 0.6, 's1': 1, 's2': 2,
     's3': 3, 's4': 4, 'taux': 0.2, 'tauy': 0.3},
  ])
  def test_distortion_roundtrip_does_not_repeat_writes_or_refreshes(self, distortion):
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.camera_parameters = {}
    cache_mgr.cached_scenes_by_uid = {
      'scene': SimpleNamespace(cameras={'cam-1': SimpleNamespace(cameraID='cam-1')})}
    cache_mgr.data_source = Mock()
    cache_mgr.checkRefresh = Mock()
    canonical = {'k1': 0.1, 'k2': 0, 'p1': 0, 'p2': 0, 'k3': 0}
    cache_mgr.refreshScenes = Mock(side_effect=lambda **kw: cache_mgr._refreshCameras({
      'cameras': [{'uid': 'cam-1', 'distortion': canonical}]}))
    message = {'id': 'cam-1', 'distortion': distortion.copy()}
    for _ in range(10):
      cache_mgr.refreshScenesForCamParams(message)
    cache_mgr.data_source.updateCamera.assert_called_once_with(
      'cam-1', {'distortion': canonical})
    cache_mgr.refreshScenes.assert_called_once_with(force=True)
    assert message['distortion'] == distortion
    cache_mgr.refreshScenesForCamParams({'id': 'cam-1'})
    assert cache_mgr.data_source.updateCamera.call_count == 1

  def test_partial_distortion_clears_omitted_coefficients_like_manager(self):
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.camera_parameters = {'cam-1': {
      'distortion': {'k1': 0.1, 'k2': 0.2, 'p1': 0, 'p2': 0, 'k3': 0}}}
    assert cache_mgr.cameraParametersChanged({'id': 'cam-1', 'distortion': {'k1': 0.1}}, 'distortion')
    assert cache_mgr.camera_parameters['cam-1']['distortion']['k2'] == 0
    assert not cache_mgr.cameraParametersChanged({'id': 'cam-1'}, 'distortion')


  @pytest.mark.parametrize("resolution", [[0, 480], [True, 480], [640], None, "640x480"])
  def test_invalid_sensor_resolution_does_not_replace_registered_size(self, resolution):
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr.camera_parameters = {'cam-1': {'resolution': [640, 480]}}
    cache_mgr.data_source = Mock()
    cache_mgr.checkRefresh = Mock()
    cache_mgr.refreshScenesForCamParams({'id': 'cam-1', 'resolution': resolution})
    assert cache_mgr.camera_parameters['cam-1']['resolution'] == [640, 480]
    cache_mgr.data_source.updateCamera.assert_not_called()

  def test_rest_refresh_does_not_replay_stale_mqtt_optics(self):
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.data_source = Mock()
    cache_mgr.camera_parameters = {'cam-1': {'intrinsics': {'fx': 500}}}
    latest = {'uid': 'cam-1', 'intrinsics': {'fx': 900}, 'resolution': [1920, 1080]}
    cache_mgr._refreshCameras({'cameras': [latest]})
    assert cache_mgr.camera_parameters['cam-1']['intrinsics'] == {'fx': 900}
    cache_mgr.data_source.updateCamera.assert_not_called()

  def test_refresh_before_comparing_and_writing_camera_parameters(self):
    cache_mgr = CacheManager.__new__(CacheManager)
    camera = SimpleNamespace(cameraID='cam-1')
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = {
      'scene-1': SimpleNamespace(cameras={'cam-1': camera}),
    }
    cache_mgr.camera_parameters = {'cam-1': {'intrinsics': {'fx': 100}}}
    cache_mgr.data_source = Mock()
    cache_mgr.refreshScenes = Mock()

    def refresh_cache():
      cache_mgr.camera_parameters['cam-1'] = {'intrinsics': {'fx': 400}}

    cache_mgr.checkRefresh = Mock(side_effect=refresh_cache)
    update_camera = cache_mgr.updateCamera

    def update_with_stale_cache(cam, payload=None):
      cache_mgr.camera_parameters['cam-1'] = {'intrinsics': {'fx': 400}}
      return update_camera(cam, payload)

    cache_mgr.updateCamera = update_with_stale_cache
    cache_mgr.refreshScenesForCamParams({
      'id': 'cam-1', 'intrinsics': {'fx': 900},
    })

    cache_mgr.data_source.updateCamera.assert_called_once_with(
      'cam-1', {'intrinsics': {'fx': 900}})
    cache_mgr.checkRefresh.assert_called_once_with()
    cache_mgr.refreshScenes.assert_called_once_with(force=True)

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
    cache_mgr._lock = threading.RLock()
    cache_mgr.cached_scenes_by_uid = None
    cache_mgr.camera_parameters = {}
    cache_mgr.checkRefresh = Mock()

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
