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

USAGE:
Set CONTROLLER_ENABLE_TIME_CHUNKING=true to automatically use time-chunked tracker.
Scene class will select TimeChunkedIntelLabsTracking instead of standard IntelLabsTracking.
"""

import threading
import time
import os
from typing import Dict, Any, List

from scene_common import log
from controller.ilabs_tracking import IntelLabsTracking

class TimeChunkBuffer:
  """Simple buffer that stores latest message per camera+category combination"""

  def __init__(self):
    self._data = {}
    self._lock = threading.Lock()

  def add(self, camera_id: str, category: str, objects: List[Any], when: float, already_tracked: List[Any]):
    """Store latest message for camera+category - overwrites previous for performance optimization"""
    with self._lock:
      # Only keep the MOST RECENT frame per camera+category - discard older frames
      key = f"{camera_id}_{category}"
      self._data[key] = (camera_id, category, objects, when, already_tracked)

  def pop_all(self):
    """Get latest frames from all camera+category combinations and clear buffer - performance optimized"""
    with self._lock:
      result = self._data.copy()  # Only contains latest frame per camera+category
      self._data.clear()
      return result


class TimeChunkProcessor(threading.Thread):
  """Timer thread that processes buffered messages at configurable intervals"""

  def __init__(self, tracker_manager, interval_ms=50):  # Default interval, configurable
    super().__init__(daemon=True)
    self.buffer = TimeChunkBuffer()
    self.tracker_manager = tracker_manager
    self.interval = interval_ms / 1000.0  # Convert to seconds
    self._stop = False

  def add_message(self, camera_id: str, category: str, objects: List[Any], when: float, already_tracked: List[Any]):
    """Buffer latest frame only - overwrites previous frames per camera+category for performance"""
    self.buffer.add(camera_id, category, objects, when, already_tracked)

  def run(self):
    """Process buffer at configured interval - only latest frames per camera+category for performance"""
    while not self._stop:
      time.sleep(self.interval)
      messages = self.buffer.pop_all()  # Contains only latest frame per camera+category

      # Send latest frames to existing tracker queues
      for key, (camera_id, category, objects, when, already_tracked) in messages.items():
        if category in self.tracker_manager.trackers:
          tracker = self.tracker_manager.trackers[category]
          if tracker.queue.empty():  # Only if not busy
            # Process only the most recent frame from each camera+category in the time chunk
            tracker.queue.put((objects, when, already_tracked))


class TimeChunkedIntelLabsTracking(IntelLabsTracking):
  """Time-chunked version of IntelLabsTracking with performance optimization"""

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    # Call parent constructor to initialize IntelLabsTracking
    super().__init__(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)

    # Add time chunking processor (always enabled in this implementation)
    self.time_chunk_processor = TimeChunkProcessor(self)
    self.time_chunk_processor.start()

  def trackObjects(self, objects, already_tracked_objects, when, categories,
                   ref_camera_frame_rate, max_unreliable_time,
                   non_measurement_time_dynamic, non_measurement_time_static,
                   use_tracker=True):
    """Override trackObjects to use time chunking"""

    if not use_tracker:
      raise NotImplementedError("Non-tracker mode is not supported in TimeChunkedIntelLabsTracking")

    # Create trackers first (inherited method)
    self._createTrackers(categories, max_unreliable_time,
                        non_measurement_time_dynamic,
                        non_measurement_time_static)

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
      self.time_chunk_processor.add_message(camera_id, category, new_objects, when, already_tracked_objects)
