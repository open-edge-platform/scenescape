#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for QdrantDatabase shared client use."""

import concurrent.futures
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from controller.qdrant_adapter import QdrantDatabase

TEST_NAME = "NEX-T28256"


@pytest.fixture
def qdrant_db():
  db = QdrantDatabase(dimensions=4, use_tls=False)
  client = MagicMock()

  def slow_upsert(**_kwargs):
    time.sleep(0.001)
    return True

  def slow_query_points(**_kwargs):
    time.sleep(0.001)
    return MagicMock(points=[])

  client.upsert.side_effect = slow_upsert
  client.query_points.side_effect = slow_query_points
  client.get_collections.return_value = MagicMock()
  db.client = client
  db.connected = True
  db._schema_ready = True
  return db, client


class TestQdrantDatabaseConcurrentAccess:
  def test_concurrent_add_entry_serialized_by_lock(self, qdrant_db):
    """Many addEntry callers must not raise under concurrent upserts."""
    db, client = qdrant_db
    errors = []
    vectors = [np.ones(4, dtype=np.float32)]

    def writer(i):
      try:
        db.addEntry(
          uuid=f"gid-{i}",
          rvid=f"rv-{i}",
          object_type="person",
          reid_vectors=vectors,
        )
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
      futures = [pool.submit(writer, i) for i in range(60)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"addEntry race: {errors}"
    assert client.upsert.call_count == 60

  def test_connect_overlapping_add_entry(self, qdrant_db):
    """connect() under lock must remain safe while writers use the client."""
    db, client = qdrant_db
    errors = []
    stop = threading.Event()
    vectors = [np.ones(4, dtype=np.float32)]

    def writer():
      try:
        while not stop.is_set():
          try:
            db.addEntry(
              uuid="gid-live",
              rvid="rv-live",
              object_type="person",
              reid_vectors=vectors,
            )
          except RuntimeError as exc:
            if "not connected" not in str(exc).lower():
              raise
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def connector():
      try:
        for _ in range(20):
          with patch.object(db, '_createClient', return_value=client), \
               patch.object(db, '_initializeSchemaOnConnect', MagicMock()):
            db.connect("localhost")
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    readers = [threading.Thread(target=writer, daemon=True) for _ in range(3)]
    for t in readers:
      t.start()

    connector()
    stop.set()
    for t in readers:
      t.join(timeout=2.0)

    assert not errors, f"connect vs addEntry race: {errors}"

  def test_concurrent_find_matches(self, qdrant_db):
    """findMatches must tolerate concurrent queries against one client."""
    db, _client = qdrant_db
    errors = []
    vectors = [np.ones(4, dtype=np.float32)]

    def querier(i):
      try:
        scores = db.findMatches("person", vectors)
        assert isinstance(scores, list)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(querier, i) for i in range(40)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"findMatches race: {errors}"
