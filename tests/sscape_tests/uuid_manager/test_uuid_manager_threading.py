#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for UUIDManager shared state.

These stress concurrent readers and writers of active_ids and ReID feature maps
so unprotected shared mutable state fails loudly under free-threaded Python.
"""

import concurrent.futures
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from controller.moving_object import ReidState
from controller.uuid_manager import UUIDManager
import controller.uuid_manager as uuid_manager_mod

TEST_NAME = "NEX-T28250"


@pytest.fixture(autouse=True)
def mock_vdms_db():
  mock_vdms_db = MagicMock()
  mock_vdms_db.retentionEnabled.return_value = False
  with patch('controller.uuid_manager.create_reid_database',
             return_value=mock_vdms_db):
    yield mock_vdms_db
  with uuid_manager_mod._PURGE_OWNER_LOCK:
    uuid_manager_mod._PURGE_OWNER = None


def _make_object(rv_id, category="person"):
  obj = SimpleNamespace(
    rv_id=rv_id,
    category=category,
    gid=None,
    similarity=None,
    reid_state=ReidState.PENDING_COLLECTION,
    reid=None,
    reid_provenance=None,
    boundingBoxPixels=None,
    chain_data=None,
    when=0.0,
    metadata={},
  )
  return obj


class TestUUIDManagerConcurrentAccess:
  """Positive and negative concurrency coverage for ReID shared maps."""

  def test_concurrent_active_ids_readers_and_writers(self, mock_vdms_db):
    """Many threads may read/write active_ids without corrupting the dict."""
    manager = UUIDManager()
    stop = threading.Event()
    errors = []

    def writer(start, count):
      try:
        for i in range(start, start + count):
          with manager.active_ids_lock:
            manager.active_ids[f"rv-{i}"] = [f"gid-{i}", 0.9]
      except Exception as exc:  # noqa: BLE001 - collect any race failure
        errors.append(exc)

    def reader():
      try:
        while not stop.is_set():
          with manager.active_ids_lock:
            _ = list(manager.active_ids.items())
            _ = [v[0] for v in manager.active_ids.values()]
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    readers = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for t in readers:
      t.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(writer, i * 200, 200) for i in range(8)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    stop.set()
    for t in readers:
      t.join(timeout=2.0)

    assert not errors, f"Concurrent access raised: {errors}"
    with manager.active_ids_lock:
      assert len(manager.active_ids) == 1600

  def test_concurrent_feature_map_mutations(self, mock_vdms_db):
    """Feature map gather/prune must not race into torn dict state."""
    manager = UUIDManager()
    manager.reid_enabled = True
    embedding = np.ones(8, dtype=np.float32)
    errors = []

    def gather(i):
      try:
        obj = _make_object(f"rv-{i % 50}")
        obj.reid = embedding.tobytes()
        # Force queryable path without bbox via vetted provenance
        obj.reid_provenance = {'vetted': True}
        with patch.object(manager, '_extractReidEmbedding', return_value=embedding):
          with patch.object(manager, 'isQueryableObservation', return_value=True):
            with patch.object(manager, 'mayContributeEnrollmentEmbedding', return_value=True):
              with patch.object(manager, 'isEnrollableObservation', return_value=False):
                with patch.object(manager, '_ensureReIDDimensions', return_value=True):
                  manager.gatherQualityVisualFeatures(obj)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def prune():
      try:
        tracked = [SimpleNamespace(id=f"rv-{i}") for i in range(0, 50, 2)]
        manager.pruneInactiveTracks(tracked)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
      futures = [pool.submit(gather, i) for i in range(400)]
      futures += [pool.submit(prune) for _ in range(40)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"Feature map races: {errors}"
    # Surviving maps must remain plain dicts (not torn / non-iterable).
    with manager.active_ids_lock:
      assert isinstance(manager.quality_features, dict)
      assert isinstance(manager.enrollment_features, dict)
      assert isinstance(manager.active_query, dict)

  def test_has_pending_reid_enrollment_is_thread_safe(self, mock_vdms_db):
    """Hierarchy readers must not observe half-updated enrollment state."""
    manager = UUIDManager()
    with manager.active_ids_lock:
      manager.quality_features['rv-1'] = [np.ones(4)]
      manager.active_ids['rv-1'] = [None, None]

    assert manager.hasPendingReidEnrollment('rv-1') is True
    assert manager.hasPendingReidEnrollment('missing') is False

  def test_is_new_tracker_id_consistent_under_contention(self, mock_vdms_db):
    """isNewTrackerID must not raise while writers mutate active_ids."""
    manager = UUIDManager()
    errors = []
    obj = _make_object('rv-shared')

    def flip():
      try:
        for i in range(1000):
          with manager.active_ids_lock:
            if i % 2 == 0:
              manager.active_ids['rv-shared'] = [None, None]
            else:
              manager.active_ids.pop('rv-shared', None)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def check():
      try:
        for _ in range(1000):
          manager.isNewTrackerID(obj)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=flip), threading.Thread(target=check)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    assert not errors, f"isNewTrackerID race: {errors}"
