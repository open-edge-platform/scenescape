# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Time Chunking Implementation for SceneScape Controller

PURPOSE:
Synchronizes object tracking across multiple categories (person, vehicle, etc.) by buffering
messages for 100ms windows and dispatching them simultaneously to all tracker threads.

USAGE:
1. Create processor instance in SceneController:
   self.time_chunk_processor = TimeChunkProcessor(self.tracking_manager, interval_ms=100)
   
2. Start the processor thread:
   self.time_chunk_processor.start()
   
3. Replace direct tracker queue calls with buffered calls:
   # OLD: tracker.queue.put((objects, when, already_tracked))
   # NEW: self.time_chunk_processor.add_message(category, objects, when, already_tracked)
   
4. Stop processor on shutdown:
   self.time_chunk_processor.stop()

INTEGRATION EXAMPLE:
In scene_controller.py trackObjects() method, replace:
    for category in categories:
        if not tracker.queue.empty():
            continue
        tracker.queue.put((objects, when, already_tracked))

With:
    for category in categories:
        new_objects = [obj for obj in objects if obj.category == category]
        self.time_chunk_processor.add_message(category, new_objects, when, already_tracked)

BEHAVIOR:
- Collects messages over configurable time windows (default 100ms)
- Dispatches synchronized batches to existing tracker threads
- Preserves existing tracker interface (no changes to tracker code needed)
- Only sends to trackers that aren't busy (same logic as v1.4)
"""

import threading
import time
from typing import Dict, Any, List


class TimeChunkBuffer:
    """Simple buffer that stores latest message per category"""
    
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()
    
    def add(self, category: str, objects: List[Any], when: float, already_tracked: List[Any]):
        """Store latest message for category"""
        with self._lock:
            self._data[category] = (objects, when, already_tracked)
    
    def pop_all(self):
        """Get all messages and clear buffer"""
        with self._lock:
            result = self._data.copy()
            self._data.clear()
            return result


class TimeChunkProcessor(threading.Thread):
    """Timer thread that processes buffered messages at configurable intervals"""
    
    def __init__(self, tracker_manager, interval_ms=100):
        super().__init__(daemon=True)
        self.buffer = TimeChunkBuffer()
        self.tracker_manager = tracker_manager
        self.interval = interval_ms / 1000.0  # Convert to seconds
        self._stop = False
        
    def add_message(self, category: str, objects: List[Any], when: float, already_tracked: List[Any]):
        """Buffer a message for batch processing"""
        self.buffer.add(category, objects, when, already_tracked)
        
    def run(self):
        """Process buffer at configured interval"""
        while not self._stop:
            time.sleep(self.interval)
            messages = self.buffer.pop_all()
            
            # Send to existing tracker queues
            for category, (objects, when, already_tracked) in messages.items():
                if category in self.tracker_manager.trackers:
                    tracker = self.tracker_manager.trackers[category]
                    if tracker.queue.empty():  # Only if not busy
                        tracker.queue.put((objects, when, already_tracked))
    
    def stop(self):
        """Stop the processor"""
        self._stop = True

