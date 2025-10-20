# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
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
- Object Batching: When ENABLE_OBJECT_BATCHING=True, batches objects from all cameras
  per category into a single tracker call for improved performance

USAGE:
Set CONTROLLER_ENABLE_TIME_CHUNKING=true to automatically use time-chunked tracker.
Scene class will select TimeChunkedIntelLabsTracking instead of standard IntelLabsTracking.
Configure ENABLE_OBJECT_BATCHING to control batching behavior.
"""

import threading
import time
import os
from typing import Dict, Any, List

from scene_common import log
from controller.ilabs_tracking import IntelLabsTracking
from controller.observability import metrics

DEFAULT_CHUNKING_INTERVAL_MS = 50  # Default interval in milliseconds
ENABLE_OBJECT_BATCHING = True  # If True, batch objects from all cameras per category for single tracker call


class TimeChunkBuffer:
  """Buffer organized by category, then by camera for efficient grouping"""

  def __init__(self):
    self._data = {}  # Structure: {category: {camera_id: (objects, when, already_tracked)}}
    self._lock = threading.Lock()

  def add(self, camera_id: str, category: str, objects: List[Any], when: float, already_tracked: List[Any]):
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

  def __init__(self, tracker_manager, interval_ms=DEFAULT_CHUNKING_INTERVAL_MS, name=None):  # Default interval, configurable
    super().__init__(daemon=True, name=f"TimeChunkProcessor-{name}")
    self.buffer = TimeChunkBuffer()
    self.tracker_manager = tracker_manager
    self.interval = interval_ms / 1000.0  # Convert to seconds
    self._stop = False

  def add_message(self, camera_id: str, category: str, objects: List[Any], when: float, already_tracked: List[Any]):
    """Buffer latest frame only - overwrites previous frames per camera+category for performance"""
    self.buffer.add(camera_id, category, objects, when, already_tracked)

  def run(self):
    """Process buffer at configured interval - organized by category with camera data"""
    while not self._stop:
      time.sleep(self.interval)
      # {category: {camera_id: (objects, when, already_tracked)}}
      category_data = self.buffer.pop_all()

      # Iterate per category and process each camera separately
      for category, camera_dict in category_data.items():
        if category in self.tracker_manager.trackers:
          tracker = self.tracker_manager.trackers[category]

          # Skip the category if tracker is still processing previous batch
          if not tracker.queue.empty():
            log.info(
                f"Tracker work queue is not empty ({tracker.queue.qsize()}). Dropping {len(camera_dict)} messages for category: {category}")
            metrics_attributes = {
                "category": category,
                "reason": "tracker_busy"
            }
            metrics.inc_dropped(metrics_attributes)
            continue

          if ENABLE_OBJECT_BATCHING:
            # Batch all objects from all cameras for this category into a single tracker call
            all_objects = []
            latest_when = 0
            all_already_tracked = []
            
            for camera_id, (objects, when, already_tracked) in camera_dict.items():
              all_objects.extend(objects)
              latest_when = max(latest_when, when)
              all_already_tracked.extend(already_tracked)
            
            # Single enqueue for all batched objects in this category
            if all_objects:
              tracker.queue.put((all_objects, latest_when, all_already_tracked))
          else:
            # Original behavior: Enqueue each camera's data for this category to be processed by tracker serially
            for camera_id, (objects, when, already_tracked) in camera_dict.items():
              tracker.queue.put((objects, when, already_tracked))


class TimeChunkedIntelLabsTracking(IntelLabsTracking):
  """Time-chunked version of IntelLabsTracking with performance optimization"""

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, name, time_chunking_interval_milliseconds):
    # Call parent constructor to initialize IntelLabsTracking
    super().__init__(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, name=name)
    log.info(f"Initializing TimeChunkedIntelLabsTracking with name '{self.name}' and object batching={'enabled' if ENABLE_OBJECT_BATCHING else 'disabled'}")
    self.time_chunking_interval_milliseconds = time_chunking_interval_milliseconds

  def trackObjects(self, objects, already_tracked_objects, when, categories,
                   ref_camera_frame_rate, max_unreliable_time,
                   non_measurement_time_dynamic, non_measurement_time_static,
                   use_tracker=True):
    """Override trackObjects to use time chunking"""

    if not use_tracker:
      raise NotImplementedError(
          "Non-tracker mode is not supported in TimeChunkedIntelLabsTracking")

    # Create InteleLabs trackers if not already created
    self._createIlabsTrackers(categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)

    if not categories:
      categories = self.trackers.keys()

    # Extract camera_id from objects - required for time chunking
    try:
      camera_id = objects[0].camera.cameraID
    except (AttributeError, IndexError):
      log.warning("No camera ID found in objects, skipping time chunking processing")
      return

    for category in categories:
      self._updateRefCameraFrameRate(ref_camera_frame_rate, category)
      new_objects = [obj for obj in objects if obj.category == category]

      # Use time chunking
      self.time_chunk_processor.add_message(
          camera_id, category, new_objects, when, already_tracked_objects)

  def _createIlabsTrackers(self, categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    """Create IntelLabs tracker object for each category"""
    for category in categories:
      if category not in self.trackers:
        name = f"{self.name}-{category}"
        # create time chunk processor for frames buffering
        self.time_chunk_processor = TimeChunkProcessor(self, self.time_chunking_interval_milliseconds, name=name)
        self.time_chunk_processor.start()
        # delegate tracking to IntelLabsTracking
        tracker = IntelLabsTracking(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, name=name)
        self.trackers[category] = tracker
        tracker.start()
    return

