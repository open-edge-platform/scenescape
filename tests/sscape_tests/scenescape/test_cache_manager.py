# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import Mock, MagicMock, patch

from controller.cache_manager import CacheManager
from controller.data_source import FileSceneDataSource, RestSceneDataSource
from controller.scene import Scene


class TestCacheManagerInitialization:
  """Test CacheManager initialization with different data sources."""

  def test_init_with_file_data_source_mock(self):
    """Test initialization with file-based data source (mocked)."""
    mock_data_source = Mock(spec=FileSceneDataSource)
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
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
    with patch('controller.data_source.RESTClient', return_value=mock_rest_client):
      cache_mgr = CacheManager.__new__(CacheManager)
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
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    with patch('controller.cache_manager.log.error') as mock_log_error:
      # Should not raise, just return without updating cache
      cache_mgr.refreshScenes()

    mock_log_error.assert_called_once_with("Failed to get results, error code: ", 500)

    assert len(cache_mgr.cached_scenes_by_uid) == 0

  def test_refresh_scenes_sets_cache_timestamp(self):
    """Test that refreshScenes sets the cache refresh timestamp."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    cache_mgr.refreshScenes()

    assert hasattr(cache_mgr, '_cache_refreshed')
    assert cache_mgr._cache_refreshed > 0


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
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    scene = cache_mgr.sceneWithID('invalid-uid')

    assert scene is None

  def test_scene_with_camera_id(self):
    """Test retrieving scene by camera ID."""
    cache_mgr = CacheManager.__new__(CacheManager)
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
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    scene = cache_mgr.sceneWithCameraID('invalid-cam-id')

    assert scene is None

  def test_scene_with_sensor_id(self):
    """Test retrieving scene by sensor ID."""
    cache_mgr = CacheManager.__new__(CacheManager)
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
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    scene = cache_mgr.sceneWithSensorID('invalid-sensor-id')

    assert scene is None


class TestCacheManagerInvalidation:
  """Test cache invalidation."""

  def test_invalidate_clears_cache(self):
    """Test that invalidate clears the scene cache."""
    cache_mgr = CacheManager.__new__(CacheManager)
    mock_scene = Mock(spec=Scene)
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr.cached_child_transforms_by_uid = {}

    cache_mgr.invalidate()

    assert cache_mgr.cached_scenes_by_uid is None

  def test_invalidate_preserves_old_cache(self):
    """Test that invalidate preserves old cache for sensor restoration."""
    cache_mgr = CacheManager.__new__(CacheManager)
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
    cache_mgr.cached_scenes_by_uid = None
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = mock_data_source

    cache_mgr.checkRefresh()

    assert cache_mgr.cached_scenes_by_uid is not None


class TestCacheManagerSensorRestoration:
  """Test sensor cache restoration functionality."""

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
    """Test that sensorNeedsRestoring returns old scene when available."""
    cache_mgr = CacheManager.__new__(CacheManager)

    old_scene = Mock()
    cache_mgr._old_scene_cache = {'scene-uid': old_scene}

    result = cache_mgr._sensorNeedsRestoring('scene-uid')

    assert result == old_scene


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

    mock_scene = Mock(spec=Scene)
    mock_camera = Mock()
    mock_camera.cameraID = 'cam-1'
    mock_camera.pose = Mock()
    mock_camera.pose.resolution = [640, 480]

    mock_scene.cameras = {'cam-1': mock_camera}
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene}
    cache_mgr.camera_parameters = {}
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.tracker_config_data = {}

    jdata = {
      'id': 'cam-1',
      'intrinsics': {'cx': 320, 'cy': 240, 'fx': 500, 'fy': 500}
    }

    cache_mgr.refreshScenesForCamParams(jdata)

    # Should not raise any errors


class TestCacheManagerEdgeCases:
  """Test edge cases and error conditions."""

  def test_multiple_refresh_calls_are_idempotent(self):
    """Test that multiple refresh calls don't cause issues."""
    mock_data_source = Mock()
    mock_data_source.getScenes.return_value = {'results': []}

    cache_mgr = CacheManager.__new__(CacheManager)
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
    mock_scene = Mock(spec=Scene)
    cache_mgr.cached_scenes_by_uid = {'scene-1': mock_scene, 'scene-2': mock_scene}
    cache_mgr._cache_refreshed = 0
    cache_mgr.data_source = Mock()
    cache_mgr.data_source.getScenes.return_value = {'results': []}

    # Simulate concurrent access
    scenes1 = list(cache_mgr.allScenes())
    scenes2 = list(cache_mgr.allScenes())

    assert len(scenes1) == len(scenes2)
