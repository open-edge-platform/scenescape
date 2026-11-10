#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import queue
from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
  import robot_vision as rv
  _has_rv_tracking = hasattr(rv, 'tracking')
except ImportError:
  _has_rv_tracking = False

if not _has_rv_tracking:
  pytest.skip("robot_vision.tracking not available", allow_module_level=True)
from controller.time_chunking import TimeChunkProcessor


def _dropped_count(mock_metrics):
  """Total added to the dropped-messages counter across inc_dropped calls."""
  total = 0
  for call in mock_metrics.inc_dropped.call_args_list:
    total += call.kwargs.get("count", call.args[1] if len(call.args) > 1 else 1)
  return total


def test_busy_tracker_drop_counts_every_camera_message():
  """A chunk dropped for a busy tracker counts one dropped message per camera."""
  busy_queue = queue.Queue()
  busy_queue.put("previous batch still in progress")
  manager = SimpleNamespace(trackers={"person": SimpleNamespace(queue=busy_queue)})
  processor = TimeChunkProcessor(manager, rate_fps=100)
  cameras = ("cam0", "cam1", "cam2")
  for camera_id in cameras:
    processor.add_message(camera_id, "person", [], 1.0, [])

  # One dispatch interval, then stop; run() is called directly, without the thread.
  with patch("controller.time_chunking.metrics") as mock_metrics, \
       patch.object(processor._stop_event, "wait", side_effect=[False, True]):
    processor.run()

  assert _dropped_count(mock_metrics) == len(cameras)
  assert busy_queue.qsize() == 1, "the dropped chunk must not be enqueued"
