# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Time-chunked tracker implementation for performance optimization.

OVERVIEW:
Performance enhancement that reduces tracking load by processing only the most recent
detection frame from each camera+category combination within time windows. Instead of
processing every incoming message immediately, buffers them and dispatches only the
latest data every 50ms (default interval, configurable).

IMPLEMENTATION:
- TimeChunkedIntelLabsTracking: Inherits from IntelLabsTracking, overrides trackObjects()
- TimeChunkProcessor: Timer thread that manages buffering and periodic dispatch
- TimeChunkBuffer: Thread-safe storage that keeps only latest frame per camera+category

FEATURES:
- Object Batching (optional): When object_batching_enabled is true, batches objects from
  all cameras per category into a single tracker call. Default is false (stream each
  camera separately within the time chunk).

USAGE:
TimeChunkedIntelLabsTracking is configurable via tracker-config.json:
- Set "time_chunking_enabled": true to enable time-chunked tracking
- Set "time_chunking_interval_milliseconds": 50 to set processing interval (optional, defaults to 50ms if not present)
- Set "object_batching_enabled": true to aggregate cameras into one batched tracker call (optional, defaults to false)
The Scene class will automatically select TimeChunkedIntelLabsTracking when enabled, otherwise uses standard IntelLabsTracking.

Example tracker-config.json:
{
    "max_unreliable_frames": 10,
    "non_measurement_frames_dynamic": 8,
    "non_measurement_frames_static": 16,
    "baseline_frame_rate": 30,
    "time_chunking_enabled": true,
    "time_chunking_interval_milliseconds": 50,
    "object_batching_enabled": false
}
"""

import threading
import time
from typing import Any, List

from scene_common import log
from controller.ilabs_tracking import IntelLabsTracking
from controller.tracking import BATCHED_MODE, STREAMING_MODE, DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS
from controller.observability import metrics

DEFAULT_CHUNKING_INTERVAL_MS = 50  # Default interval in milliseconds


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

  def __init__(self, tracker_manager, interval_ms=DEFAULT_CHUNKING_INTERVAL_MS,
               object_batching_enabled=False):
    super().__init__(daemon=True)
    self.buffer = TimeChunkBuffer()
    self.tracker_manager = tracker_manager
    self.interval = interval_ms / 1000.0  # Convert to seconds
    self.object_batching_enabled = object_batching_enabled
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

          if self.object_batching_enabled:
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
          else:
            # Default: process each camera's data for this category separately
            for camera_id, (objects, when, already_tracked) in camera_dict.items():
              tracker.queue.put((objects, when, already_tracked, STREAMING_MODE))
    log.info("TimeChunkProcessor thread exiting")


class TimeChunkedIntelLabsTracking(IntelLabsTracking):
  """Time-chunked version of IntelLabsTracking."""

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic,
               non_measurement_time_static, baseline_frame_rate=30,
               suspended_track_timeout_secs=DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS,
               time_chunking_interval_milliseconds=DEFAULT_CHUNKING_INTERVAL_MS,
               object_batching_enabled=False):
    # Call parent constructor to initialize IntelLabsTracking
    super().__init__(
        max_unreliable_time,
        non_measurement_time_dynamic,
        non_measurement_time_static,
        baseline_frame_rate=baseline_frame_rate,
        suspended_track_timeout_secs=suspended_track_timeout_secs,
    )
    self.time_chunking_interval_milliseconds = time_chunking_interval_milliseconds
    self.object_batching_enabled = object_batching_enabled
    self.suspended_track_timeout_secs = suspended_track_timeout_secs
    log.info(f"Initialized TimeChunkedIntelLabsTracking {self.__str__()} with chunking interval: "
             f"{self.time_chunking_interval_milliseconds} ms, "
             f"object_batching_enabled={self.object_batching_enabled}")

  def trackObjects(self, objects, already_tracked_objects, when, categories,
                   ref_camera_frame_rate, max_unreliable_time,
                   non_measurement_time_dynamic, non_measurement_time_static,
                   use_tracker=True, camera_id=None):
    """Override trackObjects to use time chunking"""

    if not use_tracker:
      raise NotImplementedError(
          "Non-tracker mode is not supported in TimeChunkedIntelLabsTracking")

    # Create IntelLabs trackers if not already created
    self._createIlabsTrackers(categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)

    if not categories:
      categories = self.trackers.keys()

    # Prefer explicit camera_id from caller, fallback to objects payload.
    if camera_id is None:
      try:
        camera_id = objects[0].camera.cameraID
      except (AttributeError, IndexError):
        log.warning("No camera ID found in objects, skipping time chunking processing")
        return

    for category in categories:
      self._updateRefCameraFrameRate(ref_camera_frame_rate, category)

      # Use time chunking
      self.time_chunk_processor.add_message(
          camera_id, category, objects, when, already_tracked_objects)

  def _createIlabsTrackers(self, categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    """Create IntelLabs tracker object for each category"""

    # create time chunk processor for frames buffering
    if not hasattr(self, 'time_chunk_processor'):
      log.debug(f"[TIMECHUNK_INIT] Creating new TimeChunkProcessor for {self.__str__()} "
                f"(interval={self.time_chunking_interval_milliseconds}ms, "
                f"object_batching_enabled={self.object_batching_enabled})")
      self.time_chunk_processor = TimeChunkProcessor(
          self, self.time_chunking_interval_milliseconds,
          object_batching_enabled=self.object_batching_enabled)
      self.time_chunk_processor.start()

    # delegate tracking to IntelLabsTracking
    for category in categories:
      if category not in self.trackers:
        log.debug(f"[TIMECHUNK_INIT] Creating new IntelLabsTracking thread for category={category}")
        tracker = IntelLabsTracking(
            max_unreliable_time,
            non_measurement_time_dynamic,
            non_measurement_time_static,
            baseline_frame_rate=int(self.ref_camera_frame_rate),
            suspended_track_timeout_secs=self.suspended_track_timeout_secs,
        )
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
