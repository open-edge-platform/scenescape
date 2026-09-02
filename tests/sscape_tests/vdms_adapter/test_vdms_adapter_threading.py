#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for VDMSDatabase shared client use."""

import concurrent.futures
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from controller.vdms_adapter import VDMSDatabase

TEST_NAME = "NEX-T28254"


@pytest.fixture
def vdms_db():
  with patch('controller.vdms_adapter.vdms.vdms') as mock_vdms:
    client = MagicMock()
    mock_vdms.return_value = client

    def slow_query(query, blob=None):
      # Simulate overlapping client use; lock should serialize callers.
      time.sleep(0.001)
      responses = []
      for item in query:
        query_type = next(iter(item))
        responses.append({query_type: {"status": 0}})
      return responses, []

    client.query.side_effect = slow_query
    client.connect = MagicMock()
    db = VDMSDatabase()
    db._initializeSchemaOnConnect = MagicMock()
    yield db, client


class TestVDMSDatabaseConcurrentAccess:
  def test_concurrent_send_query_serialized_by_lock(self, vdms_db):
    """Many sendQuery callers must not raise or tear responses."""
    db, client = vdms_db
    errors = []
    results = []

    def worker(i):
      try:
        response, blob = db.sendQuery([{"FindEntity": {"class": f"c-{i}"}}])
        assert isinstance(response, list)
        assert isinstance(blob, list)
        results.append(response)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
      futures = [pool.submit(worker, i) for i in range(80)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"sendQuery race: {errors}"
    assert len(results) == 80
    assert client.query.call_count == 80

  def test_connect_overlapping_send_query(self, vdms_db):
    """connect() overlapping sendQuery must not crash the client wrapper."""
    db, client = vdms_db
    errors = []
    stop = threading.Event()

    def querier():
      try:
        while not stop.is_set():
          db.sendQuery([{"FindEntity": {"class": "probe"}}])
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def connector():
      try:
        for _ in range(30):
          db.connect("localhost")
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    readers = [threading.Thread(target=querier, daemon=True) for _ in range(4)]
    for t in readers:
      t.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
      futures = [pool.submit(connector) for _ in range(4)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    stop.set()
    for t in readers:
      t.join(timeout=2.0)

    # connect() is currently unlocked; this test documents that overlapping
    # use must still not crash the wrapper under free-threading.
    assert not errors, f"connect vs sendQuery race: {errors}"

  def test_concurrent_add_entry_uses_lock(self, vdms_db):
    """addEntry paths that call sendQuery must remain race-safe under load."""
    db, _client = vdms_db
    db.dimensions = 4
    db._schema_ready = True
    db.similarity_metric = "IP"
    errors = []

    vectors = [np.ones(4, dtype=np.float32) for _ in range(2)]

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

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(writer, i) for i in range(40)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"addEntry race: {errors}"
