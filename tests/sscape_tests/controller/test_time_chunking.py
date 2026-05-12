# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for scene-aware time chunking.

Tests verify:
1. Complete scenes dispatch immediately
2. Partial scenes dispatch after timeout
3. No mixed-scene batches
4. Overwrite semantics preserved
5. Backward compatibility (no scene_id provided)
"""

import time
import unittest
import sys
import types
from unittest.mock import Mock, MagicMock, patch
from queue import Queue

sys.modules.setdefault("robot_vision", types.SimpleNamespace(tracking=types.SimpleNamespace()))
sys.modules.setdefault("cv2", types.SimpleNamespace())
sys.modules.setdefault("open3d", types.SimpleNamespace())
sys.modules.setdefault("vdms", types.SimpleNamespace())
if "scipy" not in sys.modules:
  scipy_module = types.ModuleType("scipy")
  spatial_module = types.ModuleType("scipy.spatial")
  transform_module = types.ModuleType("scipy.spatial.transform")

  class _DummyRotation:
    pass

  transform_module.Rotation = _DummyRotation
  spatial_module.transform = transform_module
  scipy_module.spatial = spatial_module
  sys.modules["scipy"] = scipy_module
  sys.modules["scipy.spatial"] = spatial_module
  sys.modules["scipy.spatial.transform"] = transform_module
if "fast_geometry" not in sys.modules:
  fast_geometry = types.ModuleType("fast_geometry")

  class _DummyPoint:
    def __init__(self, *args):
      if len(args) == 1 and isinstance(args[0], (tuple, list)):
        args = args[0]
      padded = list(args) + [0.0, 0.0, 0.0]
      self.x, self.y, self.z = padded[:3]

  class _DummyShape:
    def __init__(self, *args, **kwargs):
      pass

  fast_geometry.Point = _DummyPoint
  fast_geometry.Line = _DummyShape
  fast_geometry.Rectangle = _DummyShape
  fast_geometry.Polygon = _DummyShape
  fast_geometry.Size = _DummyShape
  sys.modules["fast_geometry"] = fast_geometry

from controller.time_chunking import (
    SceneAwareCategoryBuffer,
    TimeChunkProcessor,
    TimeChunkedIntelLabsTracking,
    DEFAULT_CHUNKING_INTERVAL_MS
)


class TestSceneAwareCategoryBuffer(unittest.TestCase):
  """Test SceneAwareCategoryBuffer correctness."""

  def setUp(self):
    # Provide a static camera count function for testing (6 cameras per scene)
    self.buffer = SceneAwareCategoryBuffer(
        "person",
        get_scene_camera_count=lambda scene_id: 6)

  def test_overwrite_semantics(self):
    """Test that update() overwrites previous frames for same camera."""
    # Add frame 1 for cam_1 in scene_1
    self.buffer.update("cam_1", "scene_1", ["obj1"], 100.0, [])

    # Add frame 2 for cam_1 in scene_1 (should overwrite)
    self.buffer.update("cam_1", "scene_1", ["obj2"], 101.0, [])

    # Pop and verify only latest frame present
    complete = self.buffer.pop_complete_scenes()
    self.assertEqual(len(complete), 0)  # Not complete yet

    # Add remaining cameras to complete scene
    for i in range(2, 7):
      self.buffer.update(f"cam_{i}", "scene_1", [f"obj{i}"], 100.0 + i, [])

    complete = self.buffer.pop_complete_scenes()
    self.assertEqual(len(complete), 1)
    self.assertIn("scene_1", complete)
    scene_data = complete["scene_1"]

    # Verify cam_1 has latest data (obj2 at 101.0)
    self.assertEqual(scene_data["cam_1"][0], ["obj2"])
    self.assertEqual(scene_data["cam_1"][1], 101.0)

  def test_pop_complete_scenes(self):
    """Test that pop_complete_scenes() returns only scenes with all cameras."""
    # Add complete scene_1 (6 cameras)
    for i in range(1, 7):
      self.buffer.update(f"cam_{i}", "scene_1", [f"obj{i}"], 100.0 + i, [])

    # Add partial scene_2 (5 cameras)
    for i in range(7, 12):
      self.buffer.update(f"cam_{i}", "scene_2", [f"obj{i}"], 200.0 + i, [])

    # Pop complete scenes
    complete = self.buffer.pop_complete_scenes()

    # Verify only scene_1 returned
    self.assertEqual(len(complete), 1)
    self.assertIn("scene_1", complete)
    self.assertEqual(len(complete["scene_1"]), 6)

    # Verify scene_2 still buffered
    self.assertEqual(self.buffer.scene_count(), 1)
    self.assertEqual(self.buffer.camera_count(), 5)

  def test_pop_stale_scenes(self):
    """Test that pop_stale_scenes() returns scenes older than timeout."""
    now = time.time()

    # Add partial scene with old timestamp
    for i in range(1, 4):
      self.buffer.update(f"cam_{i}", "scene_1", [f"obj{i}"], now - 0.5, [])

    # Add partial scene with recent timestamp
    for i in range(4, 6):
      self.buffer.update(f"cam_{i}", "scene_2", [f"obj{i}"], now - 0.05, [])

    # Pop stale scenes (timeout 0.2 seconds)
    stale = self.buffer.pop_stale_scenes(0.2)

    # Verify only scene_1 returned (0.5s old > 0.2s timeout)
    self.assertEqual(len(stale), 1)
    self.assertIn("scene_1", stale)
    self.assertEqual(len(stale["scene_1"]), 3)

    # Verify scene_2 still buffered (0.05s old < 0.2s timeout)
    self.assertEqual(self.buffer.scene_count(), 1)
    self.assertEqual(self.buffer.camera_count(), 2)

  def test_no_mixed_scene_batches(self):
    """Test that cameras from different scenes are never mixed."""
    # Add cameras from two scenes
    for i in range(1, 4):
      self.buffer.update(f"cam_{i}", "scene_1", [f"obj1_{i}"], 100.0, [])
    for i in range(4, 7):
      self.buffer.update(f"cam_{i}", "scene_2", [f"obj2_{i}"], 200.0, [])

    # Pop all (via stale with 0 timeout)
    stale = self.buffer.pop_stale_scenes(0.0)

    # Verify two separate scene batches
    self.assertEqual(len(stale), 2)
    self.assertIn("scene_1", stale)
    self.assertIn("scene_2", stale)

    # Verify no mixing (each scene has only its cameras)
    scene_1_cameras = set(stale["scene_1"].keys())
    scene_2_cameras = set(stale["scene_2"].keys())
    self.assertEqual(scene_1_cameras, {"cam_1", "cam_2", "cam_3"})
    self.assertEqual(scene_2_cameras, {"cam_4", "cam_5", "cam_6"})

  def test_empty_buffer_operations(self):
    """Test that operations on empty buffer don't crash."""
    # Pop from empty buffer
    complete = self.buffer.pop_complete_scenes()
    self.assertEqual(len(complete), 0)

    stale = self.buffer.pop_stale_scenes(0.2)
    self.assertEqual(len(stale), 0)

    # Verify counts
    self.assertEqual(self.buffer.scene_count(), 0)
    self.assertEqual(self.buffer.camera_count(), 0)


@patch('controller.time_chunking._get_scene_camera_count', return_value=6)
class TestTimeChunkProcessor(unittest.TestCase):
  """Test TimeChunkProcessor dispatch logic."""

  def setUp(self):
    # Create mock tracker manager
    self.tracker_manager = Mock()
    self.tracker_manager.trackers = {}

    # Create mock tracker with queue
    self.mock_tracker = Mock()
    self.mock_tracker.queue = Queue()
    self.tracker_manager.trackers["person"] = self.mock_tracker

    # Create processor (but don't start thread)
    self.processor = TimeChunkProcessor(
        self.tracker_manager,
        interval_ms=100,
        partial_scene_timeout_sec=0.2
    )

  def test_complete_scene_immediate_dispatch(self, _mock_camera_count):
    """Test that complete scenes are dispatched immediately (not waiting for timeout)."""
    # Add complete scene (6 cameras)
    for i in range(1, 7):
      self.processor.add_message(
          f"cam_{i}", "scene_1", "person", [f"obj{i}"], time.time(), []
      )

    # Dispatch manually (without timer)
    self.processor._dispatch_category("person")

    # Verify one batch dispatched
    self.assertEqual(self.mock_tracker.queue.qsize(), 1)

    # Verify batch contents
    objects_per_camera, latest_when, already_tracked, mode = self.mock_tracker.queue.get()
    self.assertEqual(len(objects_per_camera), 6)
    self.assertEqual(self.processor._complete_scene_dispatches, 1)
    self.assertEqual(self.processor._partial_scene_dispatches, 0)

  def test_partial_scene_timeout_dispatch(self, _mock_camera_count):
    """Test that partial scenes are dispatched after timeout."""
    now = time.time()

    # Add partial scene (5 cameras) with old timestamp
    for i in range(1, 6):
      self.processor.add_message(
          f"cam_{i}", "scene_1", "person", [f"obj{i}"], now - 0.5, []
      )

    # Dispatch manually
    self.processor._dispatch_category("person")

    # Verify one batch dispatched (via timeout fallback)
    self.assertEqual(self.mock_tracker.queue.qsize(), 1)

    # Verify partial dispatch
    objects_per_camera, _, _, _ = self.mock_tracker.queue.get()
    self.assertEqual(len(objects_per_camera), 5)
    self.assertEqual(self.processor._complete_scene_dispatches, 0)
    self.assertEqual(self.processor._partial_scene_dispatches, 1)

  def test_no_dispatch_if_tracker_busy(self, _mock_camera_count):
    """Test that dispatch is skipped if tracker queue is not empty."""
    # Add item to tracker queue (simulate busy)
    self.mock_tracker.queue.put(("dummy", 0, [], True))

    # Add complete scene
    for i in range(1, 7):
      self.processor.add_message(
          f"cam_{i}", "scene_1", "person", [f"obj{i}"], time.time(), []
      )

    # Try to dispatch
    self.processor._dispatch_category("person")

    # Verify no new dispatch (queue still has only original item)
    self.assertEqual(self.mock_tracker.queue.qsize(), 1)
    self.assertEqual(self.processor._skip_count, 1)

  def test_multiple_scenes_dispatched_separately(self, _mock_camera_count):
    """Test that multiple complete scenes are dispatched as separate batches."""
    now = time.time()

    # Add two complete scenes
    for i in range(1, 7):
      self.processor.add_message(
          f"cam_{i}", "scene_1", "person", [f"obj1_{i}"], now, []
      )
    for i in range(7, 13):
      self.processor.add_message(
          f"cam_{i}", "scene_2", "person", [f"obj2_{i}"], now, []
      )

    # Dispatch manually
    self.processor._dispatch_category("person")

    # Verify two separate batches dispatched
    self.assertEqual(self.mock_tracker.queue.qsize(), 2)
    self.assertEqual(self.processor._dispatch_count, 2)
    self.assertEqual(self.processor._complete_scene_dispatches, 2)

  def test_no_scene_starvation_with_complete_and_stale_scenes(self, _mock_camera_count):
    """Verify one hot scene does not starve another partial scene."""
    now = time.time()

    # scene_1 is complete and should dispatch immediately.
    for i in range(1, 7):
      self.processor.add_message(
          f"cam_{i}", "scene_1", "person", [f"obj1_{i}"], now, []
      )

    # scene_2 is partial and old enough for timeout fallback.
    for i in range(7, 10):
      self.processor.add_message(
          f"cam_{i}", "scene_2", "person", [f"obj2_{i}"], now - 1.0, []
      )

    self.processor._dispatch_category("person")

    self.assertEqual(self.mock_tracker.queue.qsize(), 2)

    batch1, _, _, _ = self.mock_tracker.queue.get()
    batch2, _, _, _ = self.mock_tracker.queue.get()
    dispatched_sizes = sorted([len(batch1), len(batch2)])
    self.assertEqual(dispatched_sizes, [3, 6])
    self.assertEqual(self.processor._complete_scene_dispatches, 1)
    self.assertEqual(self.processor._partial_scene_dispatches, 1)


class TestTimeChunkedIntelLabsTracking(unittest.TestCase):
  """Test TimeChunkedIntelLabsTracking integration."""

  def test_backward_compatibility_no_scene_id(self):
    """Test that trackObjects works without scene_id (backward compatibility)."""
    # Create tracker
    tracker = TimeChunkedIntelLabsTracking(
        max_unreliable_time=0.5,
        non_measurement_time_dynamic=0.3,
        non_measurement_time_static=0.6,
        time_chunking_interval_milliseconds=100
    )

    # Mock objects with camera
    mock_camera = Mock()
    mock_camera.cameraID = "cam_1"
    mock_obj = Mock()
    mock_obj.camera = mock_camera
    mock_obj.category = "person"

    # Call trackObjects without scene_id (should use fallback)
    tracker.trackObjects(
        objects=[mock_obj],
        already_tracked_objects=[],
        when=time.time(),
        categories=["person"],
        ref_camera_frame_rate=10,
        max_unreliable_time=0.5,
        non_measurement_time_dynamic=0.3,
        non_measurement_time_static=0.6,
        use_tracker=True
        # scene_id NOT provided
    )

    # Verify no crash and processor created
    self.assertIsNotNone(tracker.time_chunk_processor)

    # Cleanup
    tracker.time_chunk_processor.shutdown()
    tracker.time_chunk_processor.join(timeout=1)

  def test_scene_id_passed_through(self):
    """Test that scene_id is correctly passed to buffer."""
    # Create tracker
    tracker = TimeChunkedIntelLabsTracking(
        max_unreliable_time=0.5,
        non_measurement_time_dynamic=0.3,
        non_measurement_time_static=0.6,
        time_chunking_interval_milliseconds=100
    )

    # Mock objects with camera
    mock_camera = Mock()
    mock_camera.cameraID = "cam_1"
    mock_obj = Mock()
    mock_obj.camera = mock_camera
    mock_obj.category = "person"

    # Call trackObjects with explicit scene_id
    tracker.trackObjects(
        objects=[mock_obj],
        already_tracked_objects=[],
        when=time.time(),
        categories=["person"],
        ref_camera_frame_rate=10,
        max_unreliable_time=0.5,
        non_measurement_time_dynamic=0.3,
        non_measurement_time_static=0.6,
        use_tracker=True,
        scene_id="test_scene_123"
    )

    # Verify scene_id used (check buffer structure)
    buffer = tracker.time_chunk_processor._buffers.get("person")
    self.assertIsNotNone(buffer)
    self.assertIn("test_scene_123", buffer._data)

    # Cleanup
    tracker.time_chunk_processor.shutdown()
    tracker.time_chunk_processor.join(timeout=1)


  def test_zero_detection_frame_with_camera_id(self):
    """Test that zero-detection frames are buffered when camera_id is provided explicitly."""
    # Create tracker
    tracker = TimeChunkedIntelLabsTracking(
        max_unreliable_time=0.5,
        non_measurement_time_dynamic=0.3,
        non_measurement_time_static=0.6,
        time_chunking_interval_milliseconds=100
    )

    # Call trackObjects with empty objects but explicit camera_id
    tracker.trackObjects(
        objects=[],
        already_tracked_objects=[],
        when=time.time(),
        categories=["person"],
        ref_camera_frame_rate=10,
        max_unreliable_time=0.5,
        non_measurement_time_dynamic=0.3,
        non_measurement_time_static=0.6,
        use_tracker=True,
        scene_id="test_scene_456",
        camera_id="cam_empty"
    )

    # Verify zero-detection frame was buffered (not dropped)
    buffer = tracker.time_chunk_processor._buffers.get("person")
    self.assertIsNotNone(buffer)
    self.assertIn("test_scene_456", buffer._data)
    self.assertIn("cam_empty", buffer._data["test_scene_456"])

    # Verify the buffered objects list is empty
    cam_data = buffer._data["test_scene_456"]["cam_empty"]
    self.assertEqual(cam_data[0], [])  # empty objects

    # Cleanup
    tracker.time_chunk_processor.shutdown()
    tracker.time_chunk_processor.join(timeout=1)


if __name__ == '__main__':
  unittest.main()
