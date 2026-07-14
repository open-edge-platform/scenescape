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
    cache_manager.refreshScenes = Mock()
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
