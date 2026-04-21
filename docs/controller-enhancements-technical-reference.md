# Controller Enhancements: Technical Reference

**Author:** Mohammed Sufiyan Saqib, Nokia VPOD (Emerging Products, BLR)
**Branch:** `nokia/pr1-controller-2025.2`
**Base:** Intel SceneScape `release-2025.2`
**Date:** April 2026

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Bug Fixes](#2-bug-fixes)
3. [Multi-Process Worker Architecture](#3-multi-process-worker-architecture)
4. [Async MQTT Publishing](#4-async-mqtt-publishing)
5. [Thread-Safe Cache Manager](#5-thread-safe-cache-manager)
6. [Scene-Aware Time Chunking](#6-scene-aware-time-chunking)
7. [Background Database Operations](#7-background-database-operations)
8. [Tracking and Safety Improvements](#8-tracking-and-safety-improvements)
9. [Performance Optimizations](#9-performance-optimizations)
10. [Production Hardening](#10-production-hardening)
11. [Configuration Changes](#11-configuration-changes)
12. [C++ and Python Binding Changes](#12-c-and-python-binding-changes)
13. [Schema and Data Model Changes](#13-schema-and-data-model-changes)

---

## 1. Architecture Overview

### 1.1 Before: Single-Threaded Baseline

All processing ran sequentially on the paho MQTT callback thread. Any blocking
operation (HTTP timeout, slow tracking, publish contention) stalled all message
processing.

```
MQTT Broker
    |
    v
+-----------------------------------------------+
|           MQTT Callback Thread                 |
|           (single thread, sequential)          |
|                                                |
|  handleMovingObjectMessage()                   |
|    |-- JSON parse + schema validate            |
|    |-- NTP sync (network call)                 |
|    |-- cache_manager.refreshScenes()  <-- HTTP |
|    |-- scene.processCameraData()      <-- C++  |
|    |-- publishDetections()            <-- MQTT |
|    +-- publishEvents()                <-- MQTT |
|                                                |
|  handleDatabaseMessage()                       |
|    |-- updateSubscriptions()          <-- HTTP |
|    +-- updateObjectClasses()          <-- HTTP |
+-----------------------------------------------+

Problems:
  HTTP calls on MQTT thread --> paho deadlock ("dead-but-alive")
  No parallelism across scenes (GIL-bound)
  Slow tracking blocks all cameras
  No backpressure control
  Single crash kills everything
```

### 1.2 After: Multi-Process Architecture

The MQTT callback thread is now lightweight: capture payload, overwrite buffer,
route to worker. Heavy work (tracking, publish) runs in isolated
ProcessPoolExecutor workers. HTTP operations run in background threads.

```
MQTT Broker
    |
    v
+---------------------------+
|   MQTT Callback Thread    |  <-- Lightweight: capture + route only
|   (no HTTP, no tracking)  |      No blocking operations
|                           |
|   handleMovingObject -----+--> Overwrite Buffer (_latest_frame)
|   handleDatabase ---------+--> Background Thread (_databaseUpdateAsync)
|   onConnect --------------+--> Background Thread (_onConnectAsync)
+---------------------------+
              |
              |  Semaphore admission control (max 20 in-flight)
              v
+-------------+  +-------------+  +-------------+
| Worker Proc |  | Worker Proc |  | Worker Proc |
| (Scene A)   |  | (Scene B)   |  | (Scene C)   |
|             |  |             |  |             |
| JSON parse  |  | JSON parse  |  | JSON parse  |
| NTP sync    |  | NTP sync    |  | NTP sync    |
| C++ track   |  | C++ track   |  | C++ track   |
| Build msgs  |  | Build msgs  |  | Build msgs  |
+------+------+  +------+------+  +------+------+
       |                |                |
       v                v                v
+----------------------------------------------+
|          Async Publish Thread                 |
|          (bounded queue, max 1000)            |
|          + _publish_lock (thread-safe)        |
|          + Publish Watchdog (30s health check)|
+----------------------------------------------+
              |
              v
         MQTT Broker --> Downstream Consumers
```

### 1.3 Thread and Process Map

```
Main Process:
  +-- MQTT Callback Thread (paho network loop)
  +-- Background Periodic Cache Refresh Thread (daemon, 60s interval)
  +-- Async Publish Thread (daemon)
  +-- Publish Watchdog Thread (daemon, 30s check)
  +-- Staleness Cleanup Thread (daemon, 60s check)
  +-- DB Update Threads (daemon, spawned on-demand)
  +-- OnConnect Setup Thread (daemon, spawned on-demand)

Worker Processes (1 per scene, spawned via ProcessPoolExecutor):
  +-- Each has its own SceneController instance (_is_worker=True)
  +-- Each has its own CacheManager, Scene, Tracker instances
  +-- Process isolation: no GIL contention with main process
```

---

## 2. Bug Fixes

### 2.1 Multi-Category Tripwire/Region Event Loss

`scene.py:180`

When a camera detects multiple object categories in a single frame (e.g., both
`person` and `vehicle`), only the last category's tripwire/region events were
published. Events from all earlier categories were silently lost.

**Root cause:** `self.events = {}` was reset inside `_updateEvents()`, which was
called once per detection type inside the `processCameraData()` loop. Each
iteration wiped events accumulated by previous categories.

**Before:**
```python
def processCameraData(self, jdata, when=None, ignoreTimeFlag=False):
    for detection_type, detections in jdata['objects'].items():
        objects = self._createSceneObjects(detection_type, detections)
        self._finishProcessing(detection_type, when, objects)
    return True

def _updateEvents(self, detectionType, now):
    self.events = {}                    # <-- Resets on every category
    # ... accumulate events ...
```

**After (`scene.py:180-181`):**
```python
def processCameraData(self, jdata, when=None, ignoreTimeFlag=False):
    self.events = {}                    # Reset ONCE before loop
    for detection_type, detections in jdata['objects'].items():
        objects = self._createSceneObjects(detection_type, detections)
        self._finishProcessing(detection_type, when, objects, camera_id=camera_id)
    return True

def _updateEvents(self, detectionType, now):
    # NO self.events = {} here -- events accumulate across categories
```

### 2.2 Mutable Default Argument

`scene.py:287-289`

**Before:**
```python
def _finishProcessing(self, detectionType, when, objects, already_tracked_objects=[]):
    #                                                       ^^^^^^^^^^^^^^^^^^^^^^^^^
    #                           Shared mutable list across all calls — Python gotcha
```

**After:**
```python
def _finishProcessing(self, detectionType, when, objects, already_tracked_objects=None,
                      camera_id=None):
    if already_tracked_objects is None:
        already_tracked_objects = []
```

Python mutable defaults are created once at function definition time. Appending
to the list in one call would affect subsequent calls.

### 2.3 Wrong Exception Type

`tracking.py:136, 140`

```python
# Before:
raise NotImplemented    # Returns the NotImplemented singleton (used for binary ops)

# After:
raise NotImplementedError    # Correct: raises an actual exception
```

### 2.4 No-Op classDict.update

`moving_object.py:304`

```python
# Before:
classDict.update('')    # No-op: str has no key-value pairs for dict.update()

# After: Removed. Code now guards with "if methods:" before calling classDict.update(methods)
```

---

## 3. Multi-Process Worker Architecture

`scene_controller.py`

### 3.1 ProcessPoolExecutor Per Scene

`scene_controller.py:280-308`

Each scene gets a dedicated `ProcessPoolExecutor(max_workers=1)`, created on
demand when the first message for that scene arrives. Worker processes are
isolated: each has its own `SceneController` instance with independent
CacheManager, Scene, and Tracker state.

```python
# scene_controller.py:300-305
executor = ProcessPoolExecutor(
    max_workers=1,
    mp_context=multiprocessing.get_context('spawn'),
    initializer=_init_worker_process,
    initargs=(self._worker_config,))
```

**Why `spawn` not `fork`:** Fork copies the parent process including all its
threads. In Python, forking a multithreaded process is unsafe — mutexes held by
threads in the parent are copied in a locked state to the child, where no thread
will ever unlock them. This causes deadlocks. Spawn starts a fresh Python
interpreter, initializes cleanly, then calls the initializer function.

Module-level picklable functions enable ProcessPoolExecutor:

```python
# scene_controller.py:77-85
_worker_controller = None

def _init_worker_process(config):
    global _worker_controller
    _worker_controller = SceneController(**config, _is_worker=True)

def _worker_handle_message(topic_str, payload, t_callback_enter):
    return _worker_controller._processMovingObjectMessage(
        topic_str, payload, t_callback_enter)
```

Worker config is built by `_build_worker_config()` (`scene_controller.py:261-278`),
which returns a picklable dict of constructor args.

### 3.2 Overwrite-Based Freshness Buffer

`scene_controller.py:213`

At most one pending frame per camera exists. New frames atomically overwrite
stale ones.

```python
# scene_controller.py:213
self._latest_frame = {}    # {camera_id: (topic_str, payload, t_callback_enter)}
```

```
Camera A sends Frame 1 --> _latest_frame["camA"] = Frame 1
Camera A sends Frame 2 --> _latest_frame["camA"] = Frame 2  (Frame 1 overwritten)
Worker picks up Frame 2 --> processes latest data
```

This prevents unbounded queue growth: no matter how fast frames arrive, at most
1 is buffered per camera.

### 3.3 Semaphore Admission Control

`scene_controller.py:206-207`

```python
MAX_INFLIGHT_MESSAGES = _validated_env_int('CONTROLLER_MAX_INFLIGHT', 20, minimum=1)
self._inflight_semaphore = threading.Semaphore(MAX_INFLIGHT_MESSAGES)
```

Non-blocking acquire at `scene_controller.py:1032`: if 20 messages are already
in-flight, new messages are dropped. The overwrite buffer ensures the latest
frame is still available when a slot opens.

### 3.4 Worker Crash Recovery

`scene_controller.py:1070, 348-366`

```python
# scene_controller.py:1070
except BrokenProcessPool as e:
    log.error(f"[BROKEN_POOL] scene={scene_uid}, recreating executor: {e}")
    self._recreate_scene_executor(scene_uid)
    self._inflight_semaphore.release()
```

A single worker crash (e.g., segfault in the C++ tracker) does not kill the
controller. The executor is automatically recreated at `_recreate_scene_executor()`
(`scene_controller.py:348-366`) and processing resumes on the next frame.

### 3.5 Sole-Owner Re-Submission Pattern

`scene_controller.py:964-971, 1038-1098`

Both the MQTT callback thread and the worker done-callback could submit work for
the same camera simultaneously, causing duplicate submissions and semaphore
accounting errors.

**Fix:** The MQTT thread NEVER removes or replaces entries in `_pending_work`.
Only the done callback does.

```python
# scene_controller.py:964-971 — MQTT thread: returns if ANY entry exists
with self._pending_work_lock:
    if camera_id in self._pending_work:
        return    # Let _handle_work_complete handle re-submission

# scene_controller.py:1038-1098 — Done callback: sole owner of re-submission
def _handle_work_complete(self, camera_id, scene_uid):
    self._inflight_semaphore.release()
    frame = self._get_latest_frame(camera_id)
    if frame is not None:
        # Re-submit with store-before-callback pattern
    else:
        # Clean up entry so MQTT thread can submit next time
        with self._pending_work_lock:
            self._pending_work.pop(camera_id, None)
```

### 3.6 Store-Before-Callback Race Fix

`scene_controller.py:1002-1011`

If `executor.submit()` returns a future that completes before
`add_done_callback()` is called, CPython fires the callback synchronously. If
the future isn't stored in `_pending_work` yet, the callback finds no entry.

```python
# WRONG ORDER:
future = executor.submit(...)
future.add_done_callback(...)  # Callback fires NOW before store
_pending_work[cam] = future    # Too late — entry orphaned

# CORRECT ORDER (current implementation):
future = executor.submit(...)
_pending_work[cam] = future    # Store FIRST
future.add_done_callback(...)  # Safe — callback finds the entry
```

### 3.7 Graceful Shutdown

`scene_controller.py:437-476`

```python
def shutdown(self):
    # 1. Signal monitoring threads to stop
    # 2. Stop cache refresh thread
    # 3. Drain async publish queue (5s timeout)
    # 4. Shutdown all scene executors (wait for in-flight work)
    # 5. Shutdown tracker threads (uuid_manager cleanup)
```

Ensures clean exit: no orphaned processes, no lost messages in the publish queue.
Executors are collected under lock, then shut down outside the lock to avoid
blocking callbacks (`scene_controller.py:462-468`).

---

## 4. Async MQTT Publishing

`scene_controller.py:189-196, 561-567`

### 4.1 Dedicated Publish Thread

```python
# scene_controller.py:189-196
self._publish_queue = queue.Queue(maxsize=ASYNC_PUBLISH_QUEUE_SIZE)  # default 1000
self._publish_shutdown = threading.Event()
self._publish_thread = threading.Thread(
    target=self._publish_thread_loop, name="AsyncPublish", daemon=True)
self._publish_thread.start()
```

**Why:** Synchronous MQTT publish on the worker thread adds latency to the
tracking critical path. The paho MQTT client is NOT thread-safe — concurrent
publish from multiple workers corrupts the SSL connection.

All `publish()` calls route through `_async_publish()` (`scene_controller.py:561`),
which places messages on the bounded queue. The dedicated thread drains the
queue under `_publish_lock` (`scene_controller.py:169`).

### 4.2 Publish Watchdog

`scene_controller.py:368-401`

```python
def _publish_watchdog_loop(self):
    """Monitor publish thread health every 30 seconds. Auto-restart if dead."""
```

If the publish thread dies silently (e.g., unhandled exception), the watchdog
detects it within 30 seconds and restarts it. Without this, a dead publish
thread causes permanent detection loss with no error indication.

### 4.3 Staleness Cleanup

`scene_controller.py:403-434`

```python
def _staleness_cleanup_loop(self):
    """Remove orphaned pending work entries every 60 seconds."""
```

Prevents memory leak from futures whose done-callbacks fail to execute.

---

## 5. Thread-Safe Cache Manager

`cache_manager.py`

### 5.1 The Problem

The baseline `CacheManager` made HTTP calls during cache lookups. When called
from the MQTT callback thread, these HTTP calls blocked paho's network loop:

```
MQTT Callback Thread:
  handleMovingObjectMessage()
    --> cache_manager.sceneWithCameraID(id)
      --> checkRefresh()
        --> refreshScenes()
          --> data_source.getScenes()     <-- HTTP call!
            --> blocks waiting for response
              --> paho network loop is THIS thread
                --> DEADLOCK: HTTP response can't arrive
                   because paho can't read the socket
```

### 5.2 Lock-Free HTTP Architecture

`cache_manager.py:37-112`

`refreshScenes()` is redesigned into 3 phases that never hold the lock during
HTTP:

```python
def refreshScenes(self):
    # Phase 1: HTTP fetch OUTSIDE lock (lines 50-60)
    try:
        result = self.data_source.getScenes()        # HTTP, no lock held
    except requests.exceptions.Timeout:
        log.error("[CACHE_REFRESH_TIMEOUT] ...")
        return                                        # Graceful: use stale cache

    # Phase 2: Camera param sync OUTSIDE lock (lines 68-71)
    for scene_data in found:
        self._refreshCameras(scene_data)              # HTTP, no lock held

    # Phase 3: In-memory cache update INSIDE lock (lines 73-112)
    with self._lock:                                  # Fast: dict ops only
        for scene_data in found:
            self.cached_scenes_by_uid[uid] = scene
            self._cached_scenes_by_cameraID[cam_id] = scene
```

The lock (`self._lock`, `cache_manager.py:19`) is held only for fast dictionary
updates. HTTP work completes before the lock is acquired.

### 5.3 Fast Lookup Methods

`cache_manager.py:271-287`

New `_fast` suffixed methods do dict-only lookups — safe to call from the MQTT
callback thread:

```python
def sceneWithCameraID_fast(self, cameraID):     # Line 271 — dict-only, no HTTP
def sceneWithSensorID_fast(self, sensorID):     # Line 275 — dict-only, no HTTP
def sceneWithID_fast(self, sceneID):            # Line 279 — dict-only, no HTTP
def sceneWithRemoteChildID_fast(self, childID): # Line 285 — dict-only, no HTTP
```

All MQTT callback thread code uses `_fast` methods exclusively.

### 5.4 Background Periodic Refresh

`cache_manager.py:289`

```python
def startPeriodicRefresh(self, interval=None):
    """Start daemon thread that refreshes cache every 60 seconds."""
```

Replaces on-demand `checkRefresh()` that blocked the MQTT thread. The interval
is controlled by `REFRESH_TIME = 60` (`cache_manager.py:14`). Cache freshness
is now decoupled from the message processing hot path.

### 5.5 Cache Invalidation Safety

`cache_manager.py:323-328`

`invalidate()` now clears all lookup dicts under the lock, so `_fast` methods
don't return stale results:

```python
def invalidate(self):
    with self._lock:
        self.cached_scenes_by_uid = None
        self._cached_scenes_by_cameraID = {}    # Clear stale lookups
        self._cached_scenes_by_sensorID = {}    # Clear stale lookups
```

### 5.6 Null Safety in refreshScenesForCamParams

`cache_manager.py:155-156`

After `invalidate()`, `cached_scenes_by_uid` is `None`. Added guard to prevent
`AttributeError: 'NoneType' object has no attribute 'values'`:

```python
with self._lock:
    if self.cached_scenes_by_uid is None:
        return
```

### 5.7 Camera Refresh Distortion Null Guard

`cache_manager.py:125-132`

`_refreshCameras()` assumed `camera_parameters[uid].get('distortion')` always
returned a dict, but it can be `None` if distortion data hasn't been sent yet.

```python
# Before:
distortion_values = {
    dist_coeff: self.camera_parameters[camera['uid']].get('distortion')[dist_coeff]
    # Crashes if None ^
}

# After:
distortion = self.camera_parameters[camera['uid']].get('distortion')
if distortion is not None:
    distortion_values = {
        dist_coeff: distortion.get(dist_coeff)
        for dist_coeff in supported_distortion_values
    }
```

---

## 6. Scene-Aware Time Chunking

`time_chunking.py`

### 6.1 The Problem

The baseline `TimeChunkBuffer` grouped frames per-camera with no scene context:

```
Baseline TimeChunkBuffer:
  {category: {camera_id: (objects, when, already_tracked)}}

  Timer fires every 50ms --> dispatch ALL buffered cameras
  No concept of scene grouping
  Cameras from different scenes could be batched together
  time.sleep() drifts under load
```

### 6.2 Scene-Aware Two-Level Buffer

`time_chunking.py:86`

```python
class SceneAwareCategoryBuffer:
```

Two-level dictionary structure (`time_chunking.py:116`):

```python
# {scene_id: {camera_id: (objects, when, already_tracked, arrival_monotonic)}}
self._data: Dict[str, Dict[str, tuple]] = defaultdict(dict)
```

Three key methods:

| Method | Line | Purpose |
|--------|------|---------|
| `update()` | 120 | Store latest frame per camera, grouped by scene. Overwrites previous. |
| `pop_complete_scenes()` | 143 | Returns scenes where all cameras have arrived (event-driven fast path). |
| `pop_stale_scenes()` | 161 | Returns scenes older than timeout (timer fallback for partial scenes). |

### 6.3 Event-Driven Dispatch

`time_chunking.py:120-141`

When `update()` stores a frame and the scene reaches its expected camera count,
it fires `on_scene_complete` — but only AFTER releasing the buffer lock:

```python
def update(self, camera_id, scene_id, objects, when, already_tracked):
    notify = False
    arrival = time.monotonic()
    with self._lock:
        self._data[scene_id][camera_id] = (objects, when, already_tracked, arrival)
        if expected is not None and len(self._data[scene_id]) >= expected:
            notify = True
    # Notify OUTSIDE lock to prevent deadlock
    if notify and self._on_scene_complete is not None:
        self._on_scene_complete()
```

**Lock ordering:** `_lock` is released before `on_scene_complete` acquires
`_dispatch_condition`. This prevents `buffer._lock → _dispatch_condition`
conflicting with `_dispatch_condition → buffer._lock` in the dispatch path.

### 6.4 Camera Count Resolution

`time_chunking.py:62-84`

The expected camera count per scene is derived dynamically from CacheManager:

```python
# time_chunking.py:62
def set_cache_manager(cache_manager):
    global _cache_manager
    _cache_manager = cache_manager

# time_chunking.py:67-84
def _get_scene_camera_count(scene_id):
    scene = _cache_manager.sceneWithID_fast(scene_id)   # Line 79
    if scene is not None and hasattr(scene, 'cameras'):
        count = len(scene.cameras)
        if count > 0:
            return count
    return None
```

Uses `_fast` (dict-only) lookup — safe to call from any thread without
triggering HTTP.

### 6.5 Hybrid Dispatch Model

`time_chunking.py:192`

```python
class TimeChunkProcessor(threading.Thread):
```

Dispatch priority:
1. **Complete scenes** (all cameras arrived) → immediate dispatch via
   `threading.Condition` early wake
2. **Scheduled timer** (200ms) → dispatch complete + stale partial scenes
3. **Stale timeout** → partial scenes that waited too long

Fixed-rate scheduling via `time.monotonic()` (`time_chunking.py:292, 295, 310`):

```python
# time_chunking.py:292
next_scheduled = time.monotonic() + self.interval_sec

# Drift detection and correction (lines 322-328):
# If system fell behind by >1 interval, skip forward to prevent burst dispatches
```

### 6.6 Unit Tests

`test_time_chunking.py` — 371 lines covering:
- SceneAwareCategoryBuffer overwrite semantics
- Scene completion detection with dynamic camera count
- Stale scene timeout dispatch
- Hybrid dispatch priority ordering

---

## 7. Background Database Operations

`scene_controller.py`

### 7.1 handleDatabaseMessage

`scene_controller.py:1426-1447`

**Before:** All HTTP work on MQTT callback thread.

**After:** Lightweight callback spawns daemon thread:

```python
# scene_controller.py:1426
def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
        threading.Thread(target=self._databaseUpdateAsync,
                        name="DBUpdate", daemon=True).start()

# scene_controller.py:1435
def _databaseUpdateAsync(self):
    with self._db_update_lock:          # Serialize concurrent updates
        self.updateSubscriptions()
        self._sync_workers_to_scenes()  # Sync worker pool to new scenes
        self.updateObjectClasses()
        self.updateCameras()
```

The `_db_update_lock` (`scene_controller.py:172`) serializes concurrent
database update operations so they don't overlap.

### 7.2 onConnect

`scene_controller.py:1462-1490`

**Before:** Blocks paho's network loop during initial setup.

**After:** Subscribe immediately (lightweight), defer HTTP to background:

```python
# scene_controller.py:1462
def onConnect(self, client, userdata, flags, rc):
    topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    self.pubsub.addCallback(topic, self.handleDatabaseMessage)
    threading.Thread(target=self._onConnectAsync,
                    name="OnConnectSetup", daemon=True).start()

# scene_controller.py:1480
def _onConnectAsync(self):
    with self._db_update_lock:
        self.updateSubscriptions()
        self._sync_workers_to_scenes()
        self.updateObjectClasses()
        self.updateTRSMatrix()
```

---

## 8. Tracking and Safety Improvements

### 8.1 Daemon Threads

`tracking.py:42`

```python
# Before:  super().__init__()             # Non-daemon: blocks process exit
# After:   super().__init__(daemon=True)   # Auto-cleanup on process exit
```

Prevents zombie tracker threads from keeping worker processes alive after
shutdown.

### 8.2 Thread Ownership Assertion

`tracking.py:163-164`

```python
def _assert_owner_thread(self):
    tid = current_thread().ident
    if self._owner_thread_id is None:
        self._owner_thread_id = tid
    assert tid == self._owner_thread_id, \
        f"Tracker state accessed by thread {tid}, but owned by {self._owner_thread_id}"
```

In the multi-process architecture, each tracker's mutable state must only be
accessed by its owning thread. This assertion catches data race bugs at runtime
instead of producing silent corruption.

### 8.3 Cross-Category Safety Assertion

`tracking.py:74-75`

```python
assert all(obj.category == category for obj in new_objects), \
    f"Cross-category objects in trackObjects for {category}"
```

Catches bugs where objects from different categories (e.g., `person` and
`vehicle`) are accidentally batched together.

### 8.4 Exception Handling in Tracker Run Loop

`tracking.py:196-224`

```python
# Before: No exception handling. Any tracking exception kills the thread silently.
# After:
try:
    with metrics.time_tracking(metrics_attributes):
        self._assert_owner_thread()
        if mode == BATCHED_MODE:
            self.trackCategoryBatched(objects, when, already_tracked_objects)
        else:
            self.trackCategory(objects, when, already_tracked_objects)
        self.curObjects = (self.all_tracker_objects).copy()
except Exception as e:
    log.error(f"[TRACKER_EXCEPTION] category={category}, error={type(e).__name__}: {e}")
finally:
    self.queue.task_done()       # ALWAYS completes task, even on exception
```

### 8.5 Tracker Heartbeat

`tracking.py:217-218`

```python
now = time.time()
if now - last_heartbeat > 30.0:
    log.info(f"[TRACKER_HEARTBEAT] thread={self.__str__()}, "
             f"items_processed={items_processed}, queue_size={self.queue.qsize()}")
    last_heartbeat = now
```

If heartbeat stops appearing in logs, the tracker is blocked.

### 8.6 Faulthandler

`scene_controller.py:20`

```python
faulthandler.enable()  # Prints Python traceback on SIGSEGV/SIGFPE/SIGABRT
```

Needed for debugging C++ tracker crashes that produce segfaults instead of
Python exceptions.

---

## 9. Performance Optimizations

### 9.1 O(1) Object Association

`ilabs_tracking.py:162`

The baseline `from_tracked_object()` performed O(n) linear scans per tracked
object to match C++ tracker output back to SceneScape objects. With N tracked
objects, this was O(N^2) per tracking call.

```python
# Before: O(n) per tracked object — nested loops
for obj in objects:
    if sscape_object.rv_id == tracked_object.id:
        break

# After: O(1) via pre-built hash maps
# ilabs_tracking.py:162
def from_tracked_object_fast(self, tracked_object, objects_by_uuid,
                             tracker_by_uuid, tracker_by_rv_id):
    uuid = tracked_object.attributes['info']
    sscape_object = objects_by_uuid.get(uuid)         # O(1) — line 177
    if sscape_object is None:
        sscape_object = tracker_by_uuid.get(uuid)     # O(1) — line 180
    # ...
    prev_obj = tracker_by_rv_id.get(tracked_object.id) # O(1) — line 194
```

Hash maps are constructed once per `trackCategoryBatched()` call and shared
across all tracked object conversions.

### 9.2 UUID Stability Fix

`ilabs_tracking.py:266-272, 315-317`

Intel's `pruneInactiveTracks()` only considered reliable tracks. When a track
transitioned to unreliable or suspended state (briefly occluded), its UUID
was pruned. When it became reliable again, it got a new UUID.

```python
# Before: Reliable only — UUID lost on state transitions
tracked_objects = self.tracker.get_reliable_tracks()
self.uuid_manager.pruneInactiveTracks(tracked_objects)

# After: All track states — UUID preserved across transitions
# ilabs_tracking.py:266-268
all_active_tracks = (tracked_objects +
                    self.tracker.get_unreliable_tracks() +
                    self.tracker.get_suspended_tracks())
self.uuid_manager.pruneInactiveTracks(all_active_tracks)
```

```
Object enters scene          --> reliable track
Object partially occluded    --> unreliable track    UUID must persist
Object fully occluded        --> suspended track     UUID must persist
Object reappears             --> reliable track      UUID must match original
```

The `existing_gid` check ensures UUID preservation in both fast and slow paths:

```python
# ilabs_tracking.py:152 (slow path), ilabs_tracking.py:202 (fast path)
existing_gid = self.uuid_manager.active_ids.get(sscape_object.rv_id, [None])[0]
if existing_gid is None:
    sscape_object.setGID(uuid)       # New object: assign tracker UUID
else:
    sscape_object.setGID(existing_gid)  # Known object: keep existing UUID
```

### 9.3 Process Noise Tuning

`ilabs_tracking.py:39`

```python
# Before:  tracker_config.default_process_noise = 1e-4   # Tuned for 30 FPS
# After:   tracker_config.default_process_noise = 5e-4   # Tuned for 10 FPS
```

The Kalman filter process noise scales with dt^2. At 10 FPS (dt=0.1s), the
effective noise is 5e-4 * 0.01 = 5e-6, comparable to Intel's original 1e-4 *
0.0011 = 1.1e-7 at 30 FPS.

### 9.4 Bounded UUID Thread Pool

`uuid_manager.py:37`

```python
# Before:  self.pool = concurrent.futures.ThreadPoolExecutor()            # Unbounded
# After:   self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
```

Prevents excessive thread creation under heavy ReID load.

### 9.5 Profiling Instrumentation

`ilabs_tracking.py:106-118, 253-292, 302-352`

All per-frame profiling uses `time.time_ns()` and `log.debug`:

```python
# ilabs_tracking.py:118
log.debug(f"[PROFILE_UPDATE] objs={len(objects)}, conv_ms={t_conv:.3f}, track_ms={t_track:.3f}")

# ilabs_tracking.py:289-292
log.debug(f"[PROFILE_TRACK] objs={len(objects)}, tracks={len(tracked_objects)}, ...")

# ilabs_tracking.py:349-352
log.debug(f"[PROFILE_TRACK_BATCHED] cameras=...")
```

Production runs at `INFO` level for clean logs. Enable with
`CONTROLLER_LOG_LEVEL=DEBUG`.

---

## 10. Production Hardening

### 10.1 Child Scene Transform Lock Protection

`scene_controller.py:1548-1556`

`cached_child_transforms_by_uid` was directly mutated from the DB update thread
without holding `cache_manager._lock`, racing with `sceneWithRemoteChildID_fast()`
reads.

```python
# Before:
self.cache_manager.cached_child_transforms_by_uid[info['remote_child_id']] = Scene.deserialize(info)
self.cache_manager.cached_child_transforms_by_uid.pop(old_child, 'None')  # Also: string 'None', not None

# After:
with self.cache_manager._lock:
    self.cache_manager.cached_child_transforms_by_uid[info['remote_child_id']] = Scene.deserialize(info)
with self.cache_manager._lock:
    self.cache_manager.cached_child_transforms_by_uid.pop(old_child, None)  # Fixed: actual None
```

### 10.2 from_tracked_object Null Guard

`ilabs_tracking.py:131-133, 169-171`

If a tracked object's UUID doesn't match any SceneScape object, the code returns
`None` with a warning instead of crashing:

```python
log.warning(f"No sscape_object found for tracked UUID {uuid}, track_id={tracked_object.id}")
return None

# Callers filter None results:
tracks_from_detections = [t for t in (...) if t is not None]
```

### 10.3 publishEvents Called Once Per Frame

`scene_controller.py`

**Before:** `publishEvents()` was called inside the per-detection-type loop,
publishing events from intermediate states.

**After:** Called once after all categories have been processed:

```python
# Before:
for detection_type, detections in jdata['objects'].items():
    scene.processCameraData(...)
    self.publishEvents(...)    # Inside loop — partial state

# After:
scene.processCameraData(jdata, ...)   # Processes all detection types
self.publishEvents(scene, ...)         # Once after all categories
```

### 10.4 Monotonic Arrival Time for Staleness Detection

`time_chunking.py:129`

Staleness detection uses `time.monotonic()` instead of frame timestamps from
MQTT messages, which can have NTP skew:

```python
arrival = time.monotonic()
self._data[scene_id][camera_id] = (objects, when, already_tracked, arrival)
```

### 10.5 Fatal Exit via os._exit()

`scene_controller.py` (onConnect handler)

```python
# Before:  exit(1)      # SystemExit exception, catchable by paho
# After:   os._exit(1)  # Immediate process termination, uncatchable
```

### 10.6 Rate-Limited Logging

`scene_controller.py:956-958`

```python
self._route_log_count += 1
if self._route_log_count <= 5 or self._route_log_count % 1000 == 0:
    log.info(f"[ROUTE] camera={camera_id} scene={scene_uid} ...")
```

First 5 messages logged at startup (confirms routing works), then every 1000th
message.

---

## 11. Configuration Changes

### 11.1 Tracker Config

`controller/config/tracker-config.json`

| Parameter | Before | After | Rationale |
|-----------|--------|-------|-----------|
| `baseline_frame_rate` | 30 | 10 | Matched to Triton pipeline FPS |
| `max_unreliable_frames` | 10 | 5 | Tighter threshold at 10 FPS (0.5s) |
| `non_measurement_frames_dynamic` | 8 | 20 | 2.0s tolerance for moving objects at 10 FPS |
| `non_measurement_frames_static` | 16 | 30 | 3.0s tolerance for static objects at 10 FPS |
| `time_chunking_interval_milliseconds` | 50 | 200 | 5 batches/sec matches 10 FPS rate |
| `suspended_track_timeout_secs` | N/A | 60.0 | Memory cleanup for long-running deployments |

### 11.2 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONTROLLER_MAX_WORKERS` | 0 (unlimited) | Cap on worker processes |
| `CONTROLLER_MAX_INFLIGHT` | 20 | Semaphore admission control |
| `CONTROLLER_ASYNC_PUBLISH_QUEUE_SIZE` | 1000 | Async publish queue depth |
| `CONTROLLER_ASYNC_PUBLISH_ENABLED` | true | Toggle async publish on/off |
| `CONTROLLER_STARTUP_GRACE_SEC` | 5.0 | Grace period for stale frames at startup |

### 11.3 Entry Point

`controller/src/controller-cmd:68-71`

```
--profile              Enable cProfile profiling
--profile-output PATH  Output path (default: /dev/shm/controller_profile.stats)
```

---

## 12. C++ and Python Binding Changes

### 12.1 New C++ Accessors

`controller/src/robot_vision/include/rv/tracking/MultipleObjectTracker.hpp:87-95`

```cpp
inline std::vector<TrackedObject> getSuspendedTracks()
{
    return mTrackManager.getSuspendedTracks();
}

inline std::vector<TrackedObject> getUnreliableTracks()
{
    return mTrackManager.getUnreliableTracks();
}
```

These were inaccessible from Python in the Intel baseline. Required for the UUID
stability fix (Section 9.2).

### 12.2 Python Bindings

`controller/src/robot_vision/python/src/robot_vision/extensions/tracking.cpp`

```cpp
// Line 242-244 — TrackManager binding
.def("get_suspended_tracks",
     &rv::tracking::TrackManager::getSuspendedTracks)

// Line 330-332 — MultipleObjectTracker binding
.def("get_suspended_tracks",
     &rv::tracking::MultipleObjectTracker::getSuspendedTracks)

// Line 333-335 — MultipleObjectTracker binding
.def("get_unreliable_tracks",
     &rv::tracking::MultipleObjectTracker::getUnreliableTracks)
```

### 12.3 Suspended Track Timeout

`TrackManager.cpp`, `TrackManager.hpp`

The `suspended_track_timeout_secs` parameter configures the C++ `TrackManager`
to clean up tracks that remain in "suspended" state for longer than the configured
duration. `cleanupOldSuspendedTracks()` runs inside `TrackManager::predict()`.

Parameter chain:
```
tracker-config.json: {"suspended_track_timeout_secs": 60.0}
    --> scene_controller.py: extractTrackerConfigData()
    --> cache_manager.py: tracker_config_data
    --> scene.py: _setTracker args
    --> ilabs_tracking.py: tracker_config.suspended_track_timeout_secs
    --> C++ TrackManager: cleanupOldSuspendedTracks() in predict()
```

---

## 13. Schema and Data Model Changes

### 13.1 Metadata Schema Extensions

`controller/src/schema/metadata.schema.json`

New fields added to the detection schema:

| Field | Line | Type | Purpose |
|-------|------|------|---------|
| `reid` | 234 | string (base64) | ReID embedding vector |
| `facemask` | 252 | boolean | Face mask detection |
| `color` | 258 | string | Dominant object color |
| `age` | 264 | string | Age category |
| `hat` | 270 | boolean | Hat detection |
| `gender` | 276 | string | Gender classification |
| `subtype` | 282 | string | Object subtype |

### 13.2 ReID Extraction Path

`controller/src/controller/moving_object.py:112-148`

Changed ReID extraction to read directly from the detection `info` dict:

```python
# moving_object.py:112
self.reid = {}

# moving_object.py:114-116 — Extract from info dict
# moving_object.py:125-148 — _decodeReIDVector() handles both dict and legacy formats
```

Storage format: `{'embedding_vector': base64_array, 'model_name': ...}`

---

