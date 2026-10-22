#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the lifecycle of Tracking: join(), creation after join, frame errors."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controller.time_chunking import TimeChunkedIntelLabsTracking
from controller.tracking import STREAMING_MODE, Tracking

GUARD_SECS = 5


@pytest.fixture(autouse=True)
def mock_reid_database():
  """UUIDManager must not reach for a real ReID backend."""
  database = MagicMock()
  database.retentionEnabled.return_value = False
  with patch('controller.uuid_manager.create_reid_database', return_value=database):
    yield database


def _tracking_class(on_frame):
  """Tracking whose category threads call on_frame(objects) instead of tracking."""

  class _ScriptedTracking(Tracking):

    def __init__(self, max_unreliable_time=None, non_measurement_time_dynamic=None,
                 non_measurement_time_static=None, ref_camera_frame_rate=None,
                 reid_config_data=None):
      super().__init__(reid_config_data=reid_config_data)

    def trackCategory(self, objects, when, tracks):
      on_frame(objects)
      self.all_tracker_objects = list(objects)

  return _ScriptedTracking


def _track(tracker, categories=('person',)):
  objects = [SimpleNamespace(category=category) for category in categories]
  tracker.trackObjects(objects, [], 1.0, list(categories), None, 0.3, 0.3, 0.3)


def _join_within(tracker, **kwargs):
  """Run join() on a helper thread so a hang fails the test instead of blocking it."""
  thread = threading.Thread(target=tracker.join, kwargs=kwargs, daemon=True)
  thread.start()
  thread.join(GUARD_SECS)
  assert not thread.is_alive(), "join() did not return"


def _wait_until(predicate):
  deadline = time.monotonic() + GUARD_SECS
  while not predicate() and time.monotonic() < deadline:
    time.sleep(0.01)
  assert predicate(), "timed out waiting for condition"


class TestTrackingJoin:
  """Test Tracking join behavior with category threads and UUID managers."""

  def test_join_stops_category_threads_and_shuts_down_managers(self):
    tracker = _tracking_class(lambda objects: None)()
    _track(tracker)
    category = tracker.trackers['person']
    assert category.is_alive()

    _join_within(tracker)

    assert not category.is_alive()
    assert category.uuid_manager._shutdown_complete
    assert tracker.uuid_manager._shutdown_complete

  def test_join_drains_queued_frames_before_stopping(self):
    processed = []
    tracker = _tracking_class(processed.append)()
    _track(tracker)
    category = tracker.trackers['person']
    for _ in range(2):
      category.queue.put(([SimpleNamespace(category='person')], 1.0, [], STREAMING_MODE))

    _join_within(tracker)

    assert len(processed) == 3

  def test_join_without_trackers_shuts_down_root_manager(self):
    tracker = _tracking_class(lambda objects: None)()

    _join_within(tracker)

    assert tracker.uuid_manager._shutdown_complete

  def test_second_join_is_a_noop(self):
    tracker = _tracking_class(lambda objects: None)()
    _track(tracker)
    _join_within(tracker)

    with patch.object(tracker.uuid_manager, 'shutdown') as root_shutdown, \
         patch.object(tracker.trackers['person'].queue, 'put') as put:
      _join_within(tracker)

    root_shutdown.assert_not_called()
    put.assert_not_called()

  def test_join_returns_when_a_category_thread_has_died(self):
    tracker = _tracking_class(lambda objects: None)()
    _track(tracker)
    category = tracker.trackers['person']
    category.queue.put((None, None, None, STREAMING_MODE))
    _wait_until(lambda: not category.is_alive())
    # Nobody will ever acknowledge this item, so queue.join() would block forever.
    category.queue.put(([SimpleNamespace(category='person')], 1.0, [], STREAMING_MODE))
    assert category.queue.unfinished_tasks > 0

    _join_within(tracker)

    assert category.uuid_manager._shutdown_complete
    assert tracker.uuid_manager._shutdown_complete

  def test_join_is_bounded_and_logs_when_a_thread_is_stuck(self):
    started, release = threading.Event(), threading.Event()

    def stuck(objects):
      started.set()
      release.wait(GUARD_SECS)

    tracker = _tracking_class(stuck)()
    _track(tracker)
    category = tracker.trackers['person']
    assert started.wait(GUARD_SECS)

    try:
      with patch('controller.tracking.log') as log:
        began = time.monotonic()
        _join_within(tracker, timeout=0.2)
        elapsed = time.monotonic() - began

      assert elapsed < 2
      log.warning.assert_called_once()
      assert 'person' in log.warning.call_args.args[0]
      assert category.uuid_manager._shutdown_complete
      assert tracker.uuid_manager._shutdown_complete
    finally:
      release.set()
    _wait_until(lambda: not category.is_alive())


class TestTrackingAfterJoin:
  """Test Tracking behavior after join has been called."""

  def test_track_objects_after_join_starts_no_thread(self):
    tracker = _tracking_class(lambda objects: None)()
    _track(tracker)
    _join_within(tracker)

    with patch.object(Tracking, 'start') as start:
      _track(tracker, categories=('person', 'car'))

    start.assert_not_called()
    assert set(tracker.trackers) == {'person'}
    assert tracker.trackers['person'].queue.qsize() == 0

  def test_track_objects_on_a_joined_tracker_without_categories_is_a_noop(self):
    tracker = _tracking_class(lambda objects: None)()
    _join_within(tracker)

    with patch.object(Tracking, 'start') as start:
      _track(tracker)

    start.assert_not_called()
    assert tracker.trackers == {}


class TestTrackingFrameErrors:
  """Test Tracking behavior when exceptions occur during frame processing."""

  def test_exception_in_a_frame_does_not_kill_the_thread(self):
    frames = []

    def on_frame(objects):
      frames.append(objects)
      if len(frames) == 1:
        raise RuntimeError("bad frame")

    tracker = _tracking_class(on_frame)()

    with patch('controller.tracking.log') as log:
      _track(tracker)
      category = tracker.trackers['person']
      _wait_until(lambda: len(frames) == 1 and category.queue.unfinished_tasks == 0)

    log.error.assert_called_once()
    assert 'bad frame' in log.error.call_args.args[0]
    assert category.is_alive()

    # The category still accepts and processes later frames.
    _track(tracker)
    _wait_until(lambda: len(frames) == 2 and category.queue.unfinished_tasks == 0)
    _join_within(tracker)
    assert not category.is_alive()


class TestTimeChunkedJoin:
  """Test TimeChunkedIntelLabsTracking join behavior and thread management."""

  @staticmethod
  def _tracker():
    return TimeChunkedIntelLabsTracking(
      max_unreliable_time=0.2,
      non_measurement_time_dynamic=0.2,
      non_measurement_time_static=0.2,
      time_chunking_rate_fps=20,
    )

  def test_join_stops_processor_and_category_threads_and_is_idempotent(self):
    tracker = self._tracker()
    tracker._createIlabsTrackers(['person'], 0.2, 0.2, 0.2)
    processor = tracker.time_chunk_processor
    category = tracker.trackers['person']
    assert processor.is_alive() and category.is_alive()

    _join_within(tracker)

    assert not processor.is_alive()
    assert not category.is_alive()
    assert tracker.uuid_manager._shutdown_complete

    with patch.object(tracker.uuid_manager, 'shutdown') as shutdown:
      _join_within(tracker)
    shutdown.assert_not_called()

  def test_track_objects_after_join_creates_no_processor_or_thread(self):
    tracker = self._tracker()
    _join_within(tracker)
    camera = SimpleNamespace(cameraID='cam-1')
    obj = SimpleNamespace(category='person', camera=camera)

    with patch.object(Tracking, 'start') as start:
      tracker.trackObjects([obj], [], 1.0, ['person'], 20, 0.2, 0.2, 0.2)

    start.assert_not_called()
    assert not hasattr(tracker, 'time_chunk_processor')
    assert tracker.trackers == {}
