#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency / free-threading regression tests for time-chunked tracking."""

import concurrent.futures
import queue
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controller.time_chunking import (
  TimeChunkProcessor,
  TimeChunkedIntelLabsTracking,
)

TEST_NAME = "NEX-T28253"


class TestTimeChunkProcessorThreading:
  def test_add_message_while_processor_drains(self):
    """MQTT-style add_message must be safe while the processor thread drains."""
    tracker = MagicMock()
    tracker.queue = queue.Queue()
    manager = SimpleNamespace(trackers={"person": tracker})
    processor = TimeChunkProcessor(manager, rate_fps=50)
    errors = []

    processor.start()
    try:
      def producer(cam_id):
        try:
          for i in range(200):
            processor.add_message(
              cam_id, "person", [SimpleNamespace(oid=i)], float(i), [])
        except Exception as exc:  # noqa: BLE001
          errors.append(exc)

      with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(producer, f"cam-{i}") for i in range(8)]
        for fut in concurrent.futures.as_completed(futures):
          fut.result()
    finally:
      processor.shutdown()
      processor.join(timeout=2.0)

    assert not errors, f"TimeChunkProcessor race: {errors}"
    # Negative: shutdown must stop the thread.
    assert not processor.is_alive()


class TestTimeChunkedTrackerCreateRace:
  @patch('controller.time_chunking.IntelLabsTracking')
  @patch('controller.tracking.UUIDManager')
  def test_concurrent_create_ilabs_trackers(self, mock_uuid_cls, mock_ilabs_cls):
    """Concurrent category creation must not crash or lose tracker entries."""
    mock_uuid_cls.return_value = MagicMock()

    def make_tracker(*_args, **_kwargs):
      tracker = MagicMock()
      tracker.uuid_manager = MagicMock()
      tracker.queue = queue.Queue()
      tracker.start = MagicMock()
      return tracker

    mock_ilabs_cls.side_effect = make_tracker

    parent = TimeChunkedIntelLabsTracking.__new__(TimeChunkedIntelLabsTracking)
    parent.trackers = {}
    parent.uuid_manager = MagicMock()
    parent.reid_config_data = {}
    parent.time_chunking_rate_fps = 30
    parent.suspended_track_timeout_secs = 1.0
    # Avoid real TimeChunkProcessor thread during create stress.
    parent.time_chunk_processor = MagicMock()
    errors = []

    categories = ["person", "vehicle", "bicycle", "person", "vehicle"]

    def create_some(idx):
      try:
        cats = [categories[idx % len(categories)], categories[(idx + 1) % len(categories)]]
        parent._createIlabsTrackers(cats, 1.0, 1.0, 1.0)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
      futures = [pool.submit(create_some, i) for i in range(40)]
      for fut in concurrent.futures.as_completed(futures):
        fut.result()

    assert not errors, f"_createIlabsTrackers race: {errors}"
    assert set(parent.trackers.keys()) >= {"person", "vehicle", "bicycle"}
    for category, tracker in parent.trackers.items():
      assert tracker is not None
      tracker.start.assert_called()
