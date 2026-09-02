#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency tests for ChainData unlocked fields and CacheManager camera params."""

import concurrent.futures
import threading
from unittest.mock import MagicMock

import pytest

from scene_common.cache_manager import CacheManager
from scene_common.chain_data import ChainData
from scene_common.geometry import Point

TEST_NAME = "NEX-T28257"


class TestChainDataUnlockedFieldRaces:
  def test_unlocked_fields_under_contention(self):
    """Document/regression: analytics mutates regions/sensors/locations without _lock."""
    chain = ChainData(regions={}, publishedLocations=[Point(0, 0)], persist={})
    errors = []

    def writer(prefix):
      try:
        for i in range(300):
          key = f"{prefix}-{i % 10}"
          chain.regions[key] = {'entered': f't{i}'}
          chain.active_sensors.add(key)
          chain.publishedLocations.insert(0, Point(float(ord(prefix[0])), float(i)))
          if len(chain.publishedLocations) > 5:
            del chain.publishedLocations[5:]
          if i % 7 == 0:
            chain.active_sensors.discard(key)
            chain.regions.pop(key, None)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(300):
          _ = list(chain.regions.items())
          _ = set(chain.active_sensors)
          locs = list(chain.publishedLocations[:2])
          assert isinstance(locs, list)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=writer, args=("a",)),
               threading.Thread(target=writer, args=("b",)),
               threading.Thread(target=reader),
               threading.Thread(target=reader)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()

    assert not errors, f"ChainData unlocked field race: {errors}"
    assert isinstance(chain.regions, dict)
    assert isinstance(chain.active_sensors, set)
    assert isinstance(chain.publishedLocations, list)


class TestCacheManagerCameraParametersConcurrency:
  def test_camera_parameters_changed_vs_locked_lookup(self):
    """Unlocked cameraParametersChanged vs locked scene lookups."""
    cache_mgr = CacheManager.__new__(CacheManager)
    cache_mgr._lock = threading.RLock()
    cache_mgr._refresh_done = threading.Condition(cache_mgr._lock)
    cache_mgr.cached_scenes_by_uid = {}
    cache_mgr._cached_scenes_by_cameraID = {}
    cache_mgr._cached_scenes_by_sensorID = {}
    cache_mgr.cached_child_transforms_by_uid = {}
    cache_mgr.camera_parameters = {}
    cache_mgr.tracker_config_data = {}
    cache_mgr.data_source = MagicMock()
    cache_mgr._cacheNeedsRefresh = MagicMock(return_value=False)
    cache_mgr._refresh_in_progress = False
    cache_mgr._cache_epoch = 0
    errors = []

    def writer():
      try:
        for i in range(400):
          cache_mgr.cameraParametersChanged(
            {'id': f'cam-{i % 5}', 'intrinsics': {'fx': float(i), 'fy': 1.0}},
            'intrinsics')
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(400):
          with cache_mgr._lock:
            _ = dict(cache_mgr.camera_parameters)
          _ = cache_mgr.camera_parameters.get('cam-0', {}).get('intrinsics')
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(writer) for _ in range(2)]
      futures += [pool.submit(reader) for _ in range(4)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"camera_parameters race: {errors}"
    assert isinstance(cache_mgr.camera_parameters, dict)
    # Negative: unchanged parameters must not report a change.
    assert cache_mgr.cameraParametersChanged(
      {'id': 'cam-0', 'intrinsics': cache_mgr.camera_parameters['cam-0']['intrinsics']},
      'intrinsics') is False
