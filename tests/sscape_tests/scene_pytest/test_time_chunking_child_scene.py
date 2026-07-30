#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch, MagicMock

import pytest

try:
  import robot_vision as rv
  _has_rv_tracking = hasattr(rv, 'tracking')
except ImportError:
  _has_rv_tracking = False

if not _has_rv_tracking:
  pytest.skip("robot_vision.tracking not available", allow_module_level=True)
from controller.time_chunking import TimeChunkedIntelLabsTracking

class _ChildSceneSource:
  """Mimics a child Scene object used as 'camera' on MovingObject."""

  def __init__(self, uid):
    self.uid = uid

class _FakeMovingObject:
  """Minimal MovingObject stand-in with a configurable camera attribute."""

  def __init__(self, camera):
    self.camera = camera
    self.category = "person"

def test_time_chunking_accepts_child_scene_source():
  """trackObjects enqueues work when source has uid instead of cameraID."""
  tracker = TimeChunkedIntelLabsTracking(
    max_unreliable_time=0.2,
    non_measurement_time_dynamic=0.2,
    non_measurement_time_static=0.2,
    time_chunking_rate_fps=20,
  )

  child_uid = "child-scene-uid-1234"
  obj = _FakeMovingObject(_ChildSceneSource(child_uid))

  try:
    with patch.object(
      tracker, '_createIlabsTrackers'
    ):
      mock_processor = MagicMock()
      tracker.time_chunk_processor = mock_processor

      tracker.trackObjects(
        [obj], [], 1.0, ["person"],
        ref_camera_frame_rate=20,
        max_unreliable_time=0.2,
        non_measurement_time_dynamic=0.2,
        non_measurement_time_static=0.2,
      )

      mock_processor.add_message.assert_called_once()
      call_args = mock_processor.add_message.call_args
      assert call_args[0][0] == child_uid, (
        f"Expected camera_id={child_uid}, got {call_args[0][0]}"
      )
  finally:
    tracker.join()

def test_time_chunking_no_warning_for_child_scene_source():
  """No warning emitted when source has uid instead of cameraID."""
  tracker = TimeChunkedIntelLabsTracking(
    max_unreliable_time=0.2,
    non_measurement_time_dynamic=0.2,
    non_measurement_time_static=0.2,
    time_chunking_rate_fps=20,
  )

  obj = _FakeMovingObject(_ChildSceneSource("child-uid-5678"))

  try:
    with patch.object(tracker, '_createIlabsTrackers'), \
         patch("controller.time_chunking.log") as mock_log:
      tracker.time_chunk_processor = MagicMock()

      tracker.trackObjects(
        [obj], [], 1.0, ["person"],
        ref_camera_frame_rate=20,
        max_unreliable_time=0.2,
        non_measurement_time_dynamic=0.2,
        non_measurement_time_static=0.2,
      )

      mock_log.warning.assert_not_called()
  finally:
    tracker.join()
