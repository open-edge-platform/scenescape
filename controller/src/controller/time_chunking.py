# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

"""
Time-chunked tracker implementation with scene-aware buffering and hybrid dispatch.

OVERVIEW:
Performance enhancement that reduces tracking load by processing only the most recent
detection frame from each camera within fixed time windows. Uses a simple overwrite
hashmap per category that guarantees:
1. Always processes the freshest frame per camera
2. All active cameras are batched together at each interval
3. Predictable timing with configurable interval (default 200ms)
4. Early dispatch when all cameras for a scene arrive (event-driven fast path)

DESIGN (Hybrid Sample-and-Hold with Event-Driven Dispatch):
- MQTT callbacks continuously overwrite the latest frame per camera in a dict
- When all cameras for a scene arrive (count derived from CacheManager), dispatch immediately
- Timer thread dispatches remaining partial scenes at fixed intervals (scheduled wake)
- Fixed-rate scheduling via time.monotonic() prevents timer drift under load
- If tracker is slow, we simply skip that interval (fresher data will come)

CAMERA COUNT RESOLUTION:
The expected camera count per scene is derived dynamically at runtime from CacheManager
(len(scene.cameras)), not from a static config value. This auto-adapts when cameras are
added or removed without requiring config changes. If the CacheManager lookup fails
(scene not yet cached), early dispatch is skipped and the timer handles it.

USAGE:
TimeChunkedIntelLabsTracking is configurable via tracker-config.json:
- Set "time_chunking_enabled": true to enable time-chunked tracking
- Set "time_chunking_interval_milliseconds": 200 for 200ms batching interval

Example tracker-config.json:
{
  "max_unreliable_frames": 10,
  "non_measurement_frames_dynamic": 20,
  "non_measurement_frames_static": 30,
  "baseline_frame_rate": 10,
  "time_chunking_enabled": true,
  "time_chunking_interval_milliseconds": 200
}
"""

import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from scene_common import log
from controller.ilabs_tracking import IntelLabsTracking
from controller.tracking import BATCHED_MODE

DEFAULT_CHUNKING_INTERVAL_MS = 200  # Default interval - 5 batches/sec
DEFAULT_PARTIAL_SCENE_TIMEOUT_SEC = 0.2  # Timeout for incomplete scenes

# Global cache_manager instance for scene_id lookup (set by scene_controller at startup)
_cache_manager = None

def set_cache_manager(cache_manager):
  """Set the global cache_manager instance for scene_id derivation."""
  global _cache_manager
  _cache_manager = cache_manager

def _get_scene_camera_count(scene_id):
  """Look up actual camera count for a scene from CacheManager.

  Returns the number of cameras registered for this scene, or None if the
  scene is not (yet) in the cache. Uses _fast (dict-only) lookup — safe to
  call from any thread without triggering HTTP.

  Lock safety: acquires only _cache_manager._lock (Lock). Callers holding
  buffer._lock must ensure consistent lock ordering (buffer._lock acquired
  first, then _cache_manager._lock via this function).
  """
  if _cache_manager is not None:
    scene = _cache_manager.sceneWithID_fast(scene_id)
    if scene is not None and hasattr(scene, 'cameras'):
      count = len(scene.cameras)
      if count > 0:
        return count
  return None

class SceneAwareCategoryBuffer:
  """Scene-aware overwrite hashmap that groups cameras by scene.

  Groups frames by scene to enable per-scene batching, preserving spatial coherence
  and improving OpenMP parallelism in the tracker.

  Design:
  - update(): Stores latest frame per camera, grouped by scene (overwrites previous).
    Calls on_scene_complete callback when a scene reaches its expected camera count
    (derived dynamically from CacheManager via get_scene_camera_count).
  - pop_complete_scenes(): Returns scenes with all expected cameras
  - pop_stale_scenes(): Returns scenes older than timeout (partial scene fallback)

  Invariants preserved:
  - Overwrite semantics: Latest frame only per camera
  - Fairness: All cameras processed within timeout via stale fallback
  - Freshness: No queue buildup, always latest data

  Lock ordering (prevents deadlock):
  - _lock is released BEFORE calling on_scene_complete callback
  - Caller (TimeChunkProcessor) acquires _dispatch_condition after _lock is released
  - _get_scene_camera_count acquires _cache_manager._lock inside _lock (consistent ordering)
  """

  def __init__(self, category: str,
               get_scene_camera_count: Optional[Callable[[str], Optional[int]]] = None,
               on_scene_complete: Optional[Callable] = None):
    self.category = category
    self._get_scene_camera_count = get_scene_camera_count
    self._on_scene_complete = on_scene_complete
    # Two-level dict: {scene_id: {camera_id: (objects, when, already_tracked, arrival_monotonic)}}
    self._data: Dict[str, Dict[str, tuple]] = defaultdict(dict)
    self._lock = threading.Lock()

  def update(self, camera_id: str, scene_id: str, objects: Any, when: float, already_tracked: List[Any]):
    """Store latest frame for this camera in its scene - overwrites any previous frame.

    If this frame completes a scene (camera count matches CacheManager's scene.cameras),
    the on_scene_complete callback is invoked AFTER releasing the buffer lock to prevent
    lock ordering issues. If camera count lookup fails, no early dispatch is triggered
    (the scheduled timer will handle it).
    """
    notify = False
    arrival = time.monotonic()
    with self._lock:
      self._data[scene_id][camera_id] = (objects, when, already_tracked, arrival)
      if self._get_scene_camera_count is not None:
        expected = self._get_scene_camera_count(scene_id)
        if expected is not None and len(self._data[scene_id]) >= expected:
          notify = True

    # Notify outside lock to prevent lock ordering deadlock:
    # buffer._lock -> _dispatch_condition would conflict with
    # _dispatch_condition -> buffer._lock in the dispatch path
    if notify and self._on_scene_complete is not None:
      self._on_scene_complete()

  def pop_complete_scenes(self) -> Dict[str, Dict[str, tuple]]:
    """Atomically pop scenes where all cameras have arrived.

    Camera count per scene is resolved dynamically from CacheManager.
    If count lookup fails for a scene, that scene is skipped (timer will catch it).

    Returns dict of {scene_id: {camera_id: (objects, when, already_tracked, arrival_monotonic)}}
    """
    with self._lock:
      complete = {}
      for scene_id, cameras in list(self._data.items()):
        if self._get_scene_camera_count is not None:
          expected = self._get_scene_camera_count(scene_id)
          if expected is not None and len(cameras) >= expected:
            complete[scene_id] = cameras
            del self._data[scene_id]
      return complete

  def pop_stale_scenes(self, max_age_sec: float) -> Dict[str, Dict[str, tuple]]:
    """Atomically pop scenes older than max_age (timeout fallback for partial scenes).

    Returns dict of {scene_id: {camera_id: (objects, when, already_tracked, arrival)}}
    Uses monotonic arrival time (not message timestamp) for staleness to avoid
    clock skew between camera and controller producing false stale detections.
    """
    now = time.monotonic()
    with self._lock:
      stale = {}
      for scene_id, cameras in list(self._data.items()):
        if not cameras:
          continue
        # Use monotonic arrival time for staleness (immune to clock skew)
        oldest_arrival = min(arrival for (_, _, _, arrival) in cameras.values())
        if now - oldest_arrival > max_age_sec:
          stale[scene_id] = cameras
          del self._data[scene_id]
      return stale

  def scene_count(self) -> int:
    """Get count of scenes currently buffered."""
    with self._lock:
      return len(self._data)

  def camera_count(self) -> int:
    """Get total count of cameras across all scenes."""
    with self._lock:
      return sum(len(cameras) for cameras in self._data.values())


class TimeChunkProcessor(threading.Thread):
  """Hybrid timer+event dispatch thread for scene-aware batching.

  Design principles:
  1. Fixed-rate scheduling via time.monotonic() prevents timer drift under load (M1)
  2. Event-driven early dispatch when all cameras arrive for a scene (H1)
  3. Scheduled dispatch handles partial scenes via stale timeout (fairness)
  4. If tracker busy, skip interval - buffer continues accumulating fresher data

  Dispatch modes:
  - Early wake (Condition.notify): dispatches only complete scenes (fast path)
  - Scheduled wake (timer expiry): dispatches both complete and stale partial scenes

  Lock ordering (consistent, no deadlock risk):
  1. _dispatch_condition — acquired in run() wait and _notify_scene_complete()
  2. _buffers_lock — acquired in category iteration
  3. buffer._lock — acquired in pop_complete_scenes()/update()
  4. _cache_manager._lock — acquired inside buffer._lock via _get_scene_camera_count()
  """

  def __init__(self, tracker_manager, interval_ms: int = DEFAULT_CHUNKING_INTERVAL_MS,
               partial_scene_timeout_sec: float = DEFAULT_PARTIAL_SCENE_TIMEOUT_SEC):
    super().__init__(daemon=True)
    self.tracker_manager = tracker_manager
    self.interval_sec = interval_ms / 1000.0
    self.partial_scene_timeout_sec = partial_scene_timeout_sec
    self._stop_event = threading.Event()

    # Condition variable for hybrid timer+event dispatch (H1)
    # Early wake: _notify_scene_complete() calls notify() when a scene completes
    # Scheduled wake: wait(timeout=remaining) expires at the next fixed-rate tick
    self._dispatch_condition = threading.Condition()

    # One buffer per category
    self._buffers: Dict[str, SceneAwareCategoryBuffer] = {}
    self._buffers_lock = threading.Lock()

    # Metrics
    self._effective_fps = 1000.0 / interval_ms
    self._dispatch_count = 0
    self._skip_count = 0
    self._complete_scene_dispatches = 0
    self._partial_scene_dispatches = 0
    self._early_dispatches = 0
    self._scheduled_dispatches = 0
    self._drift_warnings = 0

    log.info(f"[TIME_CHUNK] Initialized with interval={interval_ms}ms, "
             f"max_output_fps={self._effective_fps:.1f}, "
             f"camera_count=dynamic (from CacheManager), "
             f"mode=hybrid_event_timer")

  def _notify_scene_complete(self):
    """Called by buffer when a scene reaches expected camera count.

    Wakes the dispatch thread via Condition.notify() so it can dispatch
    the complete scene immediately instead of waiting for the next scheduled tick.
    """
    with self._dispatch_condition:
      self._dispatch_condition.notify()

  def _get_or_create_buffer(self, category: str) -> SceneAwareCategoryBuffer:
    """Get buffer for category, creating if needed."""
    with self._buffers_lock:
      if category not in self._buffers:
        self._buffers[category] = SceneAwareCategoryBuffer(
            category,
            get_scene_camera_count=_get_scene_camera_count,
            on_scene_complete=self._notify_scene_complete)
        log.info(f"[TIME_CHUNK] Created scene-aware buffer for category: {category}")
      return self._buffers[category]

  def add_message(self, camera_id: str, scene_id: str, category: str, objects: Any,
                  when: float, already_tracked: List[Any]):
    """Called by trackObjects - stores latest frame in hashmap (overwrites previous)."""
    buffer = self._get_or_create_buffer(category)
    buffer.update(camera_id, scene_id, objects, when, already_tracked)

  def shutdown(self):
    """Signal thread to stop and wake it from any wait."""
    self._stop_event.set()
    with self._dispatch_condition:
      self._dispatch_condition.notify()

  def run(self):
    """Hybrid dispatch loop: fixed-rate timer with event-driven early wakeup.

    Fixed-rate scheduling (M1):
    - Uses time.monotonic() to schedule ticks at exact intervals
    - Calculates remaining time before each wait to prevent drift
    - If behind by >1 interval, skips forward to prevent burst dispatches

    Event-driven dispatch (H1):
    - Condition.wait(timeout=remaining) allows early wakeup on scene completion
    - Early wake dispatches only complete scenes (fast path)
    - Scheduled wake dispatches both complete and stale partial scenes
    """
    log.info(f"[TIME_CHUNK] Dispatch thread started, interval={self.interval_sec*1000:.0f}ms, "
             f"mode=hybrid_event_timer")

    next_scheduled = time.monotonic() + self.interval_sec

    while not self._stop_event.is_set():
      now = time.monotonic()
      remaining = next_scheduled - now

      # Determine if this is a scheduled wake or we need to wait
      is_scheduled_wake = remaining <= 0

      if not is_scheduled_wake:
        # Wait for either: early wake (scene complete) or scheduled tick
        with self._dispatch_condition:
          self._dispatch_condition.wait(timeout=remaining)

        if self._stop_event.is_set():
          break

        # Check if we reached the scheduled time or were woken early
        now = time.monotonic()
        is_scheduled_wake = now >= next_scheduled

      if is_scheduled_wake:
        # Scheduled tick: dispatch complete + stale partial scenes
        self._scheduled_dispatches += 1

        # Advance to next tick (fixed-rate scheduling)
        next_scheduled += self.interval_sec

        # Catch-up: if behind by >1 interval, skip forward to prevent burst dispatches
        now_after = time.monotonic()
        if now_after > next_scheduled + self.interval_sec:
          skipped = int((now_after - next_scheduled) / self.interval_sec)
          next_scheduled = now_after + self.interval_sec
          self._drift_warnings += 1
          if self._drift_warnings <= 10 or self._drift_warnings % 100 == 0:
            log.warning(f"[TIME_CHUNK_DRIFT] Dispatch fell behind by {skipped} interval(s), "
                       f"skipping forward (total_drift_warnings={self._drift_warnings})")

        # Full dispatch: complete scenes + stale partial scenes
        with self._buffers_lock:
          categories = list(self._buffers.keys())

        for category in categories:
          self._dispatch_category(category)
      else:
        # Early wake: dispatch only complete scenes (fast path)
        self._early_dispatches += 1

        with self._buffers_lock:
          categories = list(self._buffers.keys())

        for category in categories:
          self._dispatch_category_complete_only(category)

    # Final drain on shutdown: flush all remaining buffered scenes once so
    # late frames are not dropped when tests/application stop the tracker.
    with self._buffers_lock:
      categories = list(self._buffers.keys())

    for category in categories:
      self._dispatch_category(category)

    log.info(f"[TIME_CHUNK] Dispatch thread exiting. "
             f"dispatches={self._dispatch_count}, skips={self._skip_count}, "
             f"complete_scenes={self._complete_scene_dispatches}, "
             f"partial_scenes={self._partial_scene_dispatches}, "
             f"early_wakes={self._early_dispatches}, "
             f"scheduled_wakes={self._scheduled_dispatches}, "
             f"drift_warnings={self._drift_warnings}")

  def _dispatch_category_complete_only(self, category: str):
    """Fast path for early wakes: dispatch only complete scenes for a category."""
    with self._buffers_lock:
      buffer = self._buffers.get(category)
    if buffer is None:
      return

    tracker = self.tracker_manager.trackers.get(category)
    if tracker is None:
      return

    # Check if tracker is busy
    if not tracker.queue.empty():
      return

    complete_scenes = buffer.pop_complete_scenes()

    for scene_id, camera_dict in complete_scenes.items():
      self._dispatch_scene(category, scene_id, camera_dict, is_complete=True)

  def _dispatch_category(self, category: str):
    """Dispatch buffered cameras for one category to tracker, grouped by scene."""
    with self._buffers_lock:
      buffer = self._buffers.get(category)
    if buffer is None:
      return

    # Check if tracker exists for this category
    tracker = self.tracker_manager.trackers.get(category)
    if tracker is None:
      return

    # Check if tracker is busy (queue not empty)
    # If busy, skip this interval - buffer will accumulate fresher data
    if not tracker.queue.empty():
      cam_count = buffer.camera_count()
      if cam_count > 0:
        self._skip_count += 1
        log.debug(f"[TIME_CHUNK] Tracker busy, skipping dispatch for {category} "
                 f"({cam_count} cameras buffered, will use fresher data next interval)")
      return

    # Pop complete scenes first (optimal batching)
    complete_scenes = buffer.pop_complete_scenes()

    # Pop stale scenes (timeout fallback for partial scenes)
    stale_scenes = buffer.pop_stale_scenes(self.partial_scene_timeout_sec)

    # Dispatch complete scenes
    for scene_id, camera_dict in complete_scenes.items():
      self._dispatch_scene(category, scene_id, camera_dict, is_complete=True)

    # Dispatch stale partial scenes
    for scene_id, camera_dict in stale_scenes.items():
      self._dispatch_scene(category, scene_id, camera_dict, is_complete=False)

  def _dispatch_scene(self, category: str, scene_id: str, camera_dict: Dict[str, tuple], is_complete: bool):
    """Dispatch one scene's cameras as a batch to tracker."""
    if not camera_dict:
      return  # Nothing to dispatch

    tracker = self.tracker_manager.trackers.get(category)
    if tracker is None:
      return

    # Build batch for tracker
    objects_per_camera = []
    latest_when = 0
    all_already_tracked = []

    # Sort by timestamp for deterministic ordering
    sorted_items = sorted(camera_dict.items(), key=lambda x: x[1][1])

    # Track seen fusion objects to prevent duplicates when same child scene object
    # appears in multiple cameras' already_tracked lists
    seen_fusion_oids = set()

    for camera_id, (objects, when, already_tracked, *_rest) in sorted_items:
      objects_per_camera.append(objects)
      latest_when = max(latest_when, when)

      # Deduplicate already_tracked objects by oid to prevent duplicate track IDs
      # when same fusion object appears from multiple cameras in same scene
      for obj in already_tracked:
        if hasattr(obj, 'oid') and obj.oid in seen_fusion_oids:
          continue  # Skip duplicate fusion object
        all_already_tracked.append(obj)
        if hasattr(obj, 'oid'):
          seen_fusion_oids.add(obj.oid)

    # Dispatch to tracker queue
    tracker.queue.put((objects_per_camera, latest_when, all_already_tracked, BATCHED_MODE))
    self._dispatch_count += 1

    if is_complete:
      self._complete_scene_dispatches += 1
    else:
      self._partial_scene_dispatches += 1

    scene_type = "complete" if is_complete else "partial"
    log.debug(f"[TIME_CHUNK] Dispatched {scene_type} scene: category={category}, scene_id={scene_id}, "
              f"cameras={len(objects_per_camera)}, dispatch#{self._dispatch_count}")


class TimeChunkedIntelLabsTracking(IntelLabsTracking):
  """Time-chunked version of IntelLabsTracking.

  Overrides trackObjects() to buffer frames instead of immediate processing.
  The TimeChunkProcessor dispatches batches at fixed intervals with early
  dispatch when all cameras for a scene arrive.
  """

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic,
               non_measurement_time_static, baseline_frame_rate=10,
               suspended_track_timeout_secs=60.0,
               time_chunking_interval_milliseconds=DEFAULT_CHUNKING_INTERVAL_MS):
    super().__init__(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static,
                     baseline_frame_rate=baseline_frame_rate,
                     suspended_track_timeout_secs=suspended_track_timeout_secs)
    self.time_chunking_interval_ms = time_chunking_interval_milliseconds
    self.time_chunk_processor = None  # Created lazily in _createIlabsTrackers

    effective_fps = 1000.0 / self.time_chunking_interval_ms
    log.info(f"Initialized TimeChunkedIntelLabsTracking with interval={time_chunking_interval_milliseconds}ms "
             f"(max output FPS: {effective_fps:.1f})")

    if effective_fps < 10:
      log.warning(f"[FPS_WARN] Chunking interval {time_chunking_interval_milliseconds}ms limits output to "
                  f"{effective_fps:.1f} FPS. Cameras at 10 FPS will have ~{int((1 - effective_fps/10) * 100)}% "
                  f"frames discarded via overwrite (this is expected behavior).")

  def trackObjects(self, objects, already_tracked_objects, when, categories,
                   ref_camera_frame_rate, max_unreliable_time,
                   non_measurement_time_dynamic, non_measurement_time_static,
                   use_tracker=True, scene_id=None, camera_id=None):
    """Override trackObjects to use time chunking with scene-aware hashmap buffer."""

    if not use_tracker:
      raise NotImplementedError(
          "Non-tracker mode is not supported in TimeChunkedIntelLabsTracking")

    # Create trackers if needed
    self._createIlabsTrackers(categories, max_unreliable_time,
                              non_measurement_time_dynamic, non_measurement_time_static)

    if not categories:
      categories = self.trackers.keys()

    # Use explicit camera_id if provided, otherwise extract from objects
    if camera_id is None:
      try:
        camera_id = objects[0].camera.cameraID
      except (AttributeError, IndexError):
        log.warning("No camera ID found in objects and no camera_id provided, skipping time chunking")
        return

    # Use scene_id if provided, otherwise derive from camera using cache_manager.
    # Uses _fast (dict-only) lookup to avoid triggering HTTP refresh on the worker
    # hot path. The background refresh thread keeps the cache populated.
    if scene_id is None:
      global _cache_manager
      if _cache_manager is not None:
        try:
          scene = _cache_manager.sceneWithCameraID_fast(camera_id)
          if scene and hasattr(scene, 'uid') and scene.uid:
            scene_id = scene.uid
            log.debug(f"[TIME_CHUNK] Derived scene_id={scene_id[:8]}... from camera {camera_id}")
          else:
            scene_id = f"scene_{camera_id}"
            log.warning(f"[TIME_CHUNK] Scene object has no uid, using fallback: {scene_id}")
        except Exception as e:
          scene_id = f"scene_{camera_id}"
          log.error(f"[TIME_CHUNK] Error deriving scene_id: {e}, using fallback: {scene_id}")
      else:
        scene_id = f"scene_{camera_id}"
        log.warning(f"[TIME_CHUNK] No cache_manager available, using fallback: {scene_id}")
    else:
      log.debug(f"[TIME_CHUNK] Received scene_id={scene_id[:8]}... for camera {camera_id}")

    # Buffer frame for each category
    for category in categories:
      self._updateRefCameraFrameRate(ref_camera_frame_rate, category)
      self.time_chunk_processor.add_message(
          camera_id, scene_id, category, objects, when, already_tracked_objects)

  def _createIlabsTrackers(self, categories, max_unreliable_time,
                           non_measurement_time_dynamic, non_measurement_time_static):
    """Create tracker threads and start the time chunk processor."""

    # Create time chunk processor if needed (once)
    if self.time_chunk_processor is None:
      self.time_chunk_processor = TimeChunkProcessor(
          self, self.time_chunking_interval_ms)
      self.time_chunk_processor.start()
      log.info(f"[TIME_CHUNK] Started TimeChunkProcessor thread")

    # Create tracker thread for each category
    for category in categories:
      if category not in self.trackers:
        tracker = IntelLabsTracking(max_unreliable_time, non_measurement_time_dynamic,
                                    non_measurement_time_static,
                                    baseline_frame_rate=self.ref_camera_frame_rate)
        self.trackers[category] = tracker
        tracker.start()
        log.info(f"Started IntelLabs tracker thread for category: {category}")

  def join(self):
    """Gracefully shutdown time chunk processor and tracker threads."""
    if self.time_chunk_processor is not None:
      self.time_chunk_processor.shutdown()
      self.time_chunk_processor.join()
      log.info("[TIME_CHUNK] TimeChunkProcessor joined")

    super().join()
