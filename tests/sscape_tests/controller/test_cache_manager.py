# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading
import unittest
from unittest.mock import Mock, patch

from controller.cache_manager import CacheManager


class TestCacheManagerRefreshGating(unittest.TestCase):

  def _build_cache_manager(self):
    cache_manager = CacheManager.__new__(CacheManager)
    cache_manager._lock = threading.Lock()
    cache_manager.cached_scenes_by_uid = {"scene-1": object()}
    cache_manager._cache_refreshed = 100.0
    cache_manager._refresh_in_progress = False
    cache_manager._refresh_dirty = False
    cache_manager._dirty_since = None
    cache_manager._refresh_debounce_sec = 0.1

    def clear_dirty_on_refresh():
      # Mirror successful refreshScenes() clearing pre-existing dirty marks.
      cache_manager._refresh_dirty = False
      cache_manager._dirty_since = None

    cache_manager.refreshScenes = Mock(side_effect=clear_dirty_on_refresh)
    return cache_manager

  def test_check_refresh_skips_dirty_refresh_during_debounce(self):
    cache_manager = self._build_cache_manager()
    cache_manager._refresh_dirty = True
    cache_manager._dirty_since = 100.0

    with patch("controller.cache_manager.get_epoch_time", return_value=100.05):
      cache_manager.checkRefresh()

    cache_manager.refreshScenes.assert_not_called()

  def test_check_refresh_triggers_dirty_refresh_after_debounce(self):
    cache_manager = self._build_cache_manager()
    cache_manager._refresh_dirty = True
    cache_manager._dirty_since = 100.0

    with patch("controller.cache_manager.get_epoch_time", return_value=100.2):
      cache_manager.checkRefresh()

    cache_manager.refreshScenes.assert_called_once_with()

  def test_check_refresh_force_bypasses_periodic_and_dirty_gates(self):
    cache_manager = self._build_cache_manager()

    with patch("controller.cache_manager.get_epoch_time", return_value=100.01):
      cache_manager.checkRefresh(force=True)

    cache_manager.refreshScenes.assert_called_once_with()

  def test_check_refresh_force_while_in_progress_marks_dirty(self):
    cache_manager = self._build_cache_manager()
    cache_manager._refresh_in_progress = True

    with patch("controller.cache_manager.get_epoch_time", return_value=200.0):
      cache_manager.checkRefresh(force=True)

    cache_manager.refreshScenes.assert_not_called()
    self.assertTrue(cache_manager._refresh_dirty)
    self.assertEqual(cache_manager._dirty_since, 200.0)

  def test_check_refresh_followup_only_when_dirty_during_attempt(self):
    """Follow-up refresh runs only if dirty was marked after the attempt started."""
    cache_manager = self._build_cache_manager()
    cache_manager._refresh_dirty = True
    cache_manager._dirty_since = 100.0
    call_count = {"n": 0}

    def refresh_then_dirty_midway():
      call_count["n"] += 1
      if call_count["n"] == 1:
        # Concurrent markDirty after attempt_started (100.2)
        cache_manager._refresh_dirty = True
        cache_manager._dirty_since = 100.3
      else:
        cache_manager._refresh_dirty = False
        cache_manager._dirty_since = None

    cache_manager.refreshScenes = Mock(side_effect=refresh_then_dirty_midway)

    with patch("controller.cache_manager.get_epoch_time", return_value=100.2):
      cache_manager.checkRefresh()

    self.assertEqual(cache_manager.refreshScenes.call_count, 2)

  def test_periodic_refresh_loop_uses_gated_check_refresh(self):
    cache_manager = self._build_cache_manager()
    cache_manager._refresh_interval = 0.01
    cache_manager._refresh_stop = threading.Event()
    cache_manager.checkRefresh = Mock(side_effect=lambda force=False: cache_manager._refresh_stop.set())

    cache_manager._periodicRefreshLoop()

    cache_manager.checkRefresh.assert_called_once_with(force=True)


class TestCacheManagerDirtyPreservation(unittest.TestCase):

  def test_refresh_scenes_preserves_dirty_marked_during_refresh(self):
    """markDirty during an in-flight refresh must not be wiped on completion."""
    cache_manager = CacheManager.__new__(CacheManager)
    cache_manager._lock = threading.Lock()
    cache_manager.cached_scenes_by_uid = {}
    cache_manager._cached_scenes_by_cameraID = {}
    cache_manager._cached_scenes_by_sensorID = {}
    cache_manager.tracker_config_data = {}
    cache_manager.camera_parameters = {}
    cache_manager._refresh_dirty = False
    cache_manager._dirty_since = None
    cache_manager.data_source = Mock()
    cache_manager._refreshCameras = Mock()

    times = iter([100.0, 160.0])  # refresh_started, cache_refreshed

    def get_scenes_and_dirty():
      # Simulate markDirty arriving after refresh_started was captured.
      cache_manager._refresh_dirty = True
      cache_manager._dirty_since = 150.0
      return {"results": []}

    cache_manager.data_source.getScenes.side_effect = get_scenes_and_dirty

    with patch("controller.cache_manager.get_epoch_time", side_effect=lambda: next(times)):
      cache_manager.refreshScenes()

    self.assertTrue(cache_manager._refresh_dirty)
    self.assertEqual(cache_manager._dirty_since, 150.0)

  def test_refresh_scenes_clears_dirty_older_than_refresh_start(self):
    cache_manager = CacheManager.__new__(CacheManager)
    cache_manager._lock = threading.Lock()
    cache_manager.cached_scenes_by_uid = {}
    cache_manager._cached_scenes_by_cameraID = {}
    cache_manager._cached_scenes_by_sensorID = {}
    cache_manager.tracker_config_data = {}
    cache_manager.camera_parameters = {}
    cache_manager._refresh_dirty = True
    cache_manager._dirty_since = 50.0  # older than refresh start
    cache_manager.data_source = Mock()
    cache_manager.data_source.getScenes.return_value = {"results": []}
    cache_manager._refreshCameras = Mock()

    with patch("controller.cache_manager.get_epoch_time", side_effect=[100.0, 110.0]):
      cache_manager.refreshScenes()

    self.assertFalse(cache_manager._refresh_dirty)
    self.assertIsNone(cache_manager._dirty_since)

  def test_refresh_scenes_builds_scenes_outside_lock(self):
    """Scene.deserialize/updateScene must not run while the cache lock is held."""
    cache_manager = CacheManager.__new__(CacheManager)
    cache_manager._lock = threading.Lock()
    cache_manager.cached_scenes_by_uid = {}
    cache_manager._cached_scenes_by_cameraID = {}
    cache_manager._cached_scenes_by_sensorID = {}
    cache_manager.tracker_config_data = {}
    cache_manager.camera_parameters = {}
    cache_manager._refresh_dirty = False
    cache_manager._dirty_since = None
    cache_manager.data_source = Mock()
    cache_manager._refreshCameras = Mock()

    scene_data = {"uid": "s1", "name": "Scene1", "cameras": {}, "sensors": {}}
    cache_manager.data_source.getScenes.return_value = {"results": [scene_data]}

    scene_mock = Mock()
    scene_mock.uid = "s1"
    scene_mock.cameras = {"cam1": Mock()}
    scene_mock.sensors = {}

    lock_held_during_deserialize = []

    def deserialize_side_effect(_data):
      lock_held_during_deserialize.append(cache_manager._lock.locked())
      return scene_mock

    with patch("controller.cache_manager.get_epoch_time", return_value=100.0):
      with patch("controller.cache_manager.Scene.deserialize", side_effect=deserialize_side_effect):
        cache_manager.refreshScenes()

    self.assertEqual(lock_held_during_deserialize, [False])
    self.assertIs(cache_manager.cached_scenes_by_uid["s1"], scene_mock)
    self.assertIs(cache_manager._cached_scenes_by_cameraID["cam1"], scene_mock)
