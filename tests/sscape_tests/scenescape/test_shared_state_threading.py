#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency regression tests for ProportionCache and ChainData helpers."""

import threading

import pytest

from controller.pose_adjustment.strategies.person.proportion_cache import ProportionCache
from scene_common.chain_data import ChainData
from scene_common.geometry import Point

TEST_NAME = "NEX-T28252"


class TestProportionCacheThreading:
  def test_concurrent_add_and_read(self):
    cache = ProportionCache(max_samples=20, min_observations=1)
    key = ('cam', 'oid', 'person')
    errors = []

    def writer():
      try:
        for i in range(500):
          cache.add_observation(key, {'ratio_ankle_nose_hip': float(i % 10)}, float(i))
          cache.mark_seen(key, float(i))
          if i % 50 == 0:
            cache.prune(float(i) + 100.0)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(500):
          medians = cache.get_medians(key)
          assert isinstance(medians, dict)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader),
               threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    assert not errors, f"ProportionCache race: {errors}"


class TestChainDataThreading:
  def test_merge_and_copy_persist_concurrent(self):
    chain = ChainData(regions={}, publishedLocations=[Point(0, 0)], persist={})
    errors = []

    def merger():
      try:
        for i in range(300):
          chain.mergePersistMissing({f'attr-{i % 10}': i})
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def copier():
      try:
        for _ in range(300):
          snapshot = chain.copyPersist()
          assert isinstance(snapshot, dict)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=merger) for _ in range(3)] + [
      threading.Thread(target=copier) for _ in range(3)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    assert not errors, f"ChainData persist race: {errors}"
    # Negative: empty merge must be a no-op
    before = chain.copyPersist()
    chain.mergePersistMissing({})
    assert chain.copyPersist() == before
