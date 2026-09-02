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

    # Patch once for the whole stress run — concurrent patch.object on the same
    # manager races and can transiently delete methods under free-threading.
    with patch.object(manager, '_extractReidEmbedding', return_value=embedding), \
         patch.object(manager, 'isQueryableObservation', return_value=True), \
         patch.object(manager, 'mayContributeEnrollmentEmbedding', return_value=True), \
         patch.object(manager, 'isEnrollableObservation', return_value=False), \
         patch.object(manager, '_ensureReIDDimensions', return_value=True):

      def gather(i):
        try:
          obj = _make_object(f"rv-{i % 50}")
          obj.reid = embedding.tobytes()
          # Force queryable path without bbox via vetted provenance
          obj.reid_provenance = {'vetted': True}
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

  def test_query_similarity_vs_prune_does_not_corrupt_maps(self, mock_vdms_db):
    """Pool-style querySimilarity must tolerate concurrent pruneInactiveTracks."""
    manager = UUIDManager()
    manager.reid_enabled = True
    manager.minimum_feature_count = 1
    embedding = np.ones(8, dtype=np.float32)
    mock_vdms_db.findMatches.return_value = []
    errors = []

    with manager.active_ids_lock:
      for i in range(40):
        rv_id = f"rv-{i}"
        manager.active_ids[rv_id] = [None, None]
        manager.quality_features[rv_id] = [embedding]
        manager.quality_observation_counts[rv_id] = 1
        manager.active_query[rv_id] = True

    def query(i):
      try:
        obj = _make_object(f"rv-{i % 40}")
        obj.reid = embedding.tobytes()
        manager.querySimilarity(obj)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def prune():
      try:
        # Keep even tracks alive; odd tracks become inactive and flush.
        tracked = [SimpleNamespace(id=f"rv-{i}") for i in range(0, 40, 2)]
        manager.pruneInactiveTracks(tracked)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
      futures = [pool.submit(query, i) for i in range(200)]
      futures += [pool.submit(prune) for _ in range(30)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"querySimilarity vs prune race: {errors}"
    with manager.active_ids_lock:
      assert isinstance(manager.active_ids, dict)
      assert isinstance(manager.quality_features, dict)
      assert isinstance(manager.features_for_database, dict)

  def test_flush_stale_features_vs_health_flip(self, mock_vdms_db):
    """Stale flush and write-health flips must not tear feature maps or crash."""
    manager = UUIDManager()
    manager.reid_enabled = True
    manager.reid_write_healthy = True
    manager.stale_feature_timeout_secs = 0.0
    mock_vdms_db.addEntry.return_value = None
    embedding = np.ones(4, dtype=np.float32)
    errors = []

    with manager.active_ids_lock:
      for i in range(20):
        track_id = f"stale-{i}"
        manager.features_for_database[track_id] = {
          'gid': f'gid-{i}',
          'category': 'person',
          'reid_vectors': [embedding],
          'persist': {},
          'metadata': {},
        }
        manager.features_for_database_timestamps[track_id] = 0.0

    def flush():
      try:
        manager._flushStaleFeatures()
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def flip_health():
      try:
        for _ in range(50):
          manager._disableReidWrites("concurrency test")
          with manager._reid_write_lock:
            manager.reid_enabled = True
            manager.reid_write_healthy = True
            manager.reid_empty_batch_before_confirm = False
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(flush) for _ in range(20)]
      futures += [pool.submit(flip_health) for _ in range(4)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    # Drain pool work started by flush before asserting stability.
    manager.pool.shutdown(wait=True)
    manager.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    assert not errors, f"flush vs health race: {errors}"
    with manager.active_ids_lock:
      assert isinstance(manager.features_for_database, dict)
      assert isinstance(manager.features_for_database_timestamps, dict)

  def test_shutdown_during_in_flight_pool_work(self, mock_vdms_db):
    """shutdown(wait=False) must remain safe while workers are still running."""
    manager = UUIDManager()
    manager.reid_enabled = True
    started = threading.Event()
    release = threading.Event()
    errors = []

    def slow_find_matches(*_args, **_kwargs):
      started.set()
      release.wait(timeout=2.0)
      return []

    mock_vdms_db.findMatches.side_effect = slow_find_matches
    embedding = np.ones(8, dtype=np.float32)
    with manager.active_ids_lock:
      manager.active_ids['rv-slow'] = [None, None]
      manager.quality_features['rv-slow'] = [embedding]
      manager.quality_observation_counts['rv-slow'] = 1
      manager.active_query['rv-slow'] = True

    obj = _make_object('rv-slow')
    future = manager.pool.submit(manager.querySimilarity, obj)
    assert started.wait(timeout=2.0), "worker never started"

    try:
      manager.shutdown()
      # Negative: second shutdown must be a no-op.
      manager.shutdown()
    except Exception as exc:  # noqa: BLE001
      errors.append(exc)
    finally:
      release.set()

    try:
      future.result(timeout=2.0)
    except Exception as exc:  # noqa: BLE001
      # Cancelled/rejected work after shutdown is acceptable; crashes are not.
      if not isinstance(exc, (RuntimeError, concurrent.futures.CancelledError)):
        errors.append(exc)

    assert not errors, f"shutdown vs pool race: {errors}"
    assert manager._shutdown_complete is True

  def test_local_enrollment_allowed_consistent_under_health_contention(self, mock_vdms_db):
    """Unlocked enrollment-policy readers must not raise while writers flip flags."""
    manager = UUIDManager()
    manager.reid_enabled = True
    manager.reid_write_healthy = True
    errors = []
    results = []

    def writer():
      try:
        for i in range(500):
          with manager._reid_write_lock:
            manager.reid_enabled = (i % 2 == 0)
            manager.reid_write_healthy = (i % 3 != 0)
            manager.reid_empty_batch_before_confirm = (i % 5 == 0)
            manager.reid_write_epoch += 1
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(500):
          allowed = manager._localEnrollmentAllowed()
          assert isinstance(allowed, bool)
          results.append(allowed)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader),
               threading.Thread(target=reader)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    assert not errors, f"enrollment policy race: {errors}"
    assert results, "reader never sampled enrollment policy"
