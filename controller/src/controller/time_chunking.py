# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Time-chunked tracker implementation for performance optimization.

OVERVIEW:
Performance enhancement that reduces tracking load by processing only the most recent
detection frame from each camera+category combination within time windows. Instead of
processing every incoming message immediately, buffers them and dispatches only the
latest data at a fixed, configurable rate (frames per second).

IMPLEMENTATION:
- TimeChunkedIntelLabsTracking: Inherits from IntelLabsTracking, overrides trackObjects()
- TimeChunkProcessor: Timer thread that manages buffering and periodic dispatch
- TimeChunkBuffer: Thread-safe storage that keeps only latest frame per camera+category

FEATURES:
- Object Batching: batches objects from all cameras per category into a single tracker call for improved performance

USAGE:
TimeChunkedIntelLabsTracking is configurable via tracker-config.json:
- Set "time_chunking_enabled": true to enable time-chunked tracking
- Set "time_chunking_rate_fps": 15 to set processing rate in frames per second (optional, valid range: [MINIMAL_CHUNKING_RATE_FPS, MAXIMAL_CHUNKING_RATE_FPS], defaults to DEFAULT_CHUNKING_RATE_FPS if not present)
The Scene class will automatically select TimeChunkedIntelLabsTracking when enabled, otherwise uses standard IntelLabsTracking.
"""

import threading
import time
from typing import Any, List

from scene_common import log
from controller.ilabs_tracking import IntelLabsTracking
from controller.tracking import BATCHED_MODE, DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS
from controller.observability import metrics

DEFAULT_CHUNKING_RATE_FPS = 15
MINIMAL_CHUNKING_RATE_FPS = 1
MAXIMAL_CHUNKING_RATE_FPS = 100


class TimeChunkBuffer:
  """Buffer organized by category, then by camera for efficient grouping"""

  def __init__(self):
    self._data = {}  # Structure: {category: {camera_id: (objects, when, already_tracked)}}
    self._lock = threading.Lock()

  def add(self, camera_id: str, category: str, objects: Any, when: float, already_tracked: List[Any]):
    """Store latest message per category->camera - overwrites previous for performance optimization"""
    with self._lock:
      # Initialize category if not exists
      if category not in self._data:
        self._data[category] = {}

      # Store latest frame for this camera in this category
      self._data[category][camera_id] = (objects, when, already_tracked)

  def pop_all(self):
    """Get all data organized by category->camera and clear buffer"""
    with self._lock:
      result = self._data.copy()  # {category: {camera_id: (objects, when, already_tracked)}}
      self._data.clear()
      return result


class TimeChunkProcessor(threading.Thread):
  """Timer thread that processes buffered messages at configurable intervals"""

  def __init__(self, tracker_manager, rate_fps=DEFAULT_CHUNKING_RATE_FPS):
    super().__init__(daemon=True)
    self.buffer = TimeChunkBuffer()
    self.tracker_manager = tracker_manager
    self.interval = float(1.0 / rate_fps)  # Convert FPS to interval in seconds
    self._stop_event = threading.Event()  # Use Event instead of boolean flag

  def add_message(self, camera_id: str, category: str, objects: Any, when: float, already_tracked: List[Any]):
    """Buffer latest frame only - overwrites previous frames per camera+category for performance"""
    self.buffer.add(camera_id, category, objects, when, already_tracked)

  def shutdown(self):
    """Gracefully shutdown the processor thread"""
    self._stop_event.set()

  def run(self):
    """Process buffer at configured interval - organized by category with camera data"""
    while not self._stop_event.is_set():
      if self._stop_event.wait(timeout=self.interval):
        break  # Stop event was set, exit loop

      # {category: {camera_id: (objects, when, already_tracked)}}
      category_data = self.buffer.pop_all()

      # Iterate per category and process each camera separately
      for category, camera_dict in category_data.items():
        if category in self.tracker_manager.trackers:
          tracker = self.tracker_manager.trackers[category]

          # Skip the category if tracker is still processing previous batch
          if not tracker.queue.empty():
            log.warning(
                f"Tracker work queue is not empty ({tracker.queue.qsize()}). Dropping {len(camera_dict)} messages for category: {category}")
            metrics_attributes = {
                "category": category,
                "reason": "tracker_busy"
            }
            metrics.inc_dropped(metrics_attributes)
            continue

          # Create aggregated lists: list of lists where each inner list contains objects from one camera
          objects_per_camera = []
          latest_when = 0
          all_already_tracked = []

          # Sort camera data by timestamp (when) to ensure earliest detections come first
          sorted_camera_items = sorted(camera_dict.items(), key=lambda x: x[1][1])  # Sort by 'when' (index 1 in tuple)

          for camera_id, (objects, when, already_tracked) in sorted_camera_items:
            objects_per_camera.append(objects)  # Keep objects from each camera in separate list
            latest_when = max(latest_when, when)
            all_already_tracked.extend(already_tracked)

          # Single enqueue for aggregated camera data in this category
          if objects_per_camera:
            tracker.queue.put((objects_per_camera, latest_when, all_already_tracked, BATCHED_MODE))

    log.info("TimeChunkProcessor thread exiting")


class TimeChunkedIntelLabsTracking(IntelLabsTracking):
  """Time-chunked version of IntelLabsTracking."""

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, time_chunking_rate_fps, suspended_track_timeout_secs=DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS):
    # Call parent constructor to initialize IntelLabsTracking
    super().__init__(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, time_chunking_rate_fps, suspended_track_timeout_secs)
    self.time_chunking_rate_fps = time_chunking_rate_fps
    self.suspended_track_timeout_secs = suspended_track_timeout_secs
    log.info(f"Initialized TimeChunkedIntelLabsTracking {self.__str__()} with chunking rate: {self.time_chunking_rate_fps} fps")

  def trackObjects(self, objects, already_tracked_objects, when, categories,
                   ref_camera_frame_rate, max_unreliable_time,
                   non_measurement_time_dynamic, non_measurement_time_static,
                   use_tracker=True):
    """Override trackObjects to use time chunking"""

    if not use_tracker:
      raise NotImplementedError(
          "Non-tracker mode is not supported in TimeChunkedIntelLabsTracking")

    # Create IntelLabs trackers if not already created
    self._createIlabsTrackers(categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)

    if len(objects) == 0:
      return

    if not categories:
      categories = self.trackers.keys()

    # Extract camera_id from objects - required for time chunking
    try:
      camera_id = objects[0].camera.cameraID
    except (AttributeError, IndexError):
      log.warning("No camera ID found in objects, skipping time chunking processing")
      return

    for category in categories:
      # Use time chunking
      self.time_chunk_processor.add_message(
          camera_id, category, objects, when, already_tracked_objects)

  def _createIlabsTrackers(self, categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    """Create IntelLabs tracker object for each category"""

    # create time chunk processor for frames buffering
    if not hasattr(self, 'time_chunk_processor'):
      self.time_chunk_processor = TimeChunkProcessor(self, self.time_chunking_rate_fps)
      self.time_chunk_processor.start()

    # delegate tracking to IntelLabsTracking
    for category in categories:
      if category not in self.trackers:
        tracker = IntelLabsTracking(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, self.time_chunking_rate_fps, self.suspended_track_timeout_secs)
        self.trackers[category] = tracker
        tracker.start()
        log.info(f"Started IntelLabs tracker {tracker.__str__()} thread for category {category}")
    return

  def join(self):
    # First, stop the time chunk processor and wait for it to process all pending messages
    if hasattr(self, 'time_chunk_processor'):
      self.time_chunk_processor.shutdown()
      self.time_chunk_processor.join()

    super().join()
    return
