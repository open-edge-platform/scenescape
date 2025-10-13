# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Time Chunking Implementation for SceneScape Controller

PURPOSE:
Performance optimization - analyzes only the LAST frame from each camera and category
combination within time chunks. Buffers messages over configurable windows (default 67ms
for 15 FPS cameras) and processes only the most recent data per camera+category for better performance.

USAGE:
1. Create processor instance in SceneController:
   self.time_chunk_processor = TimeChunkProcessor(self.tracking_manager, interval_ms=67)  # Default for 15 FPS

2. Start the processor thread:
   self.time_chunk_processor.start()

3. Replace direct tracker queue calls with buffered calls:
   # OLD: tracker.queue.put((objects, when, already_tracked))
   # NEW: self.time_chunk_processor.add_message(camera_id, category, objects, when, already_tracked)


INTEGRATION EXAMPLE:
In scene_controller.py trackObjects() method, replace:
    for category in categories:
        if not tracker.queue.empty():
            continue
        tracker.queue.put((objects, when, already_tracked))

With:
    for category in categories:
        new_objects = [obj for obj in objects if obj.category == category]
        self.time_chunk_processor.add_message(camera_id, category, new_objects, when, already_tracked)

BEHAVIOR:
- Collects messages over configurable time windows (default 67ms for 15 FPS cameras)
- Keeps ONLY the latest message per camera+category combination (discards older frames)
- Processes only the most recent frame from each camera for each category in chunks
- Dispatches synchronized batches of latest frames to existing tracker threads
- Preserves existing tracker interface (no changes to tracker code needed)
- Only sends to trackers that aren't busy (same logic as v1.4)
"""

import threading
import time
from typing import Dict, Any, List


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

  def __init__(self, tracker_manager, interval_ms=67):  # Default optimized for 15 FPS cameras
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
