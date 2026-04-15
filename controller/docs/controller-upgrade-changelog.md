<!-- SPDX-FileCopyrightText: (C) 2026 Nokia -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Controller Upgrade: SceneScape 2025.2 Enhancement

Author: Nokia VPOD (Emerging Products, BLR)
Status: Active
Scope: Complete technical reference for all enhancements applied to the Intel SceneScape 2025.2 controller
Last Updated: 2026-03-18

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture: Before and After](#2-architecture-before-and-after)
3. [Change Taxonomy](#3-change-taxonomy)
4. [Critical Bug Fixes](#4-critical-bug-fixes)
5. [Multi-Process Worker Architecture](#5-multi-process-worker-architecture)
6. [Async MQTT Publishing](#6-async-mqtt-publishing)
7. [Thread-Safe Cache Manager](#7-thread-safe-cache-manager)
8. [Scene-Aware Time Chunking](#8-scene-aware-time-chunking)
9. [Background Database Operations](#9-background-database-operations)
10. [Tracking and Safety Improvements](#10-tracking-and-safety-improvements)
11. [Performance Optimizations](#11-performance-optimizations)
12. [Configuration Changes](#12-configuration-changes)
13. [Preserved Baseline Features](#13-preserved-baseline-features)
14. [Suspended Track Timeout: Production Decision](#14-suspended-track-timeout-production-decision)
15. [Production Hardening Fixes](#15-production-hardening-fixes)
16. [Edge Cases and Known Considerations](#16-edge-cases-and-known-considerations)
17. [Production Logging Strategy](#17-production-logging-strategy)
18. [Files Changed Reference](#18-files-changed-reference)
19. [Verification](#19-verification)
20. [Intel Upstream Integration (2026-03-18)](#20-intel-upstream-integration-2026-03-18)

---

## 1. Executive Summary

This document records all enhancements applied to the Intel SceneScape 2025.2 controller.
It serves as the definitive reference for code review, team knowledge transfer, and
technical presentations.

**Baseline**: Intel SceneScape 2025.2 controller (single-threaded, 669-line scene_controller.py)
**Enhanced**: Multi-process architecture (1516-line scene_controller.py)
**Strategy**: Multi-process architecture as base, with all 2025.2 baseline features preserved

### What Changed (At a Glance)

| Dimension | Before | After |
|-----------|--------|-------|
| Processing model | Single-threaded MQTT callbacks | Multi-process workers (1 per scene) |
| MQTT publish | Synchronous on callback thread | Async publish thread with bounded queue |
| Cache lookups | HTTP-triggering on MQTT thread | Dict-only `_fast` methods + background refresh |
| Time chunking | Flat per-camera buffer, 50ms | Scene-aware 2-level buffer, 200ms |
| Database updates | Inline HTTP on MQTT callback | Background threads with serialization lock |
| Crash recovery | None (single crash kills controller) | Auto-recreate broken worker processes |
| Monitoring | None | Publish watchdog, staleness cleanup, heartbeat |
| Total code | ~2,900 lines | ~4,700 lines (+62%) |

### Key Metrics

| File | Lines Before | Lines After | Change |
|------|-------------|-------------|--------|
| `scene_controller.py` | 669 | 1,575 | +906 (complete rewrite) |
| `time_chunking.py` | 209 | 565 | +356 (complete redesign) |
| `cache_manager.py` | 190 | 333 | +143 (thread-safe rewrite) |
| `ilabs_tracking.py` | 243 | 372 | +129 (profiling + optimizations) |
| `tracking.py` | 252 | 291 | +39 (safety + monitoring) |
| `scene.py` | 531 | 583 | +52 (bugfix + profiling) |
| `uuid_manager.py` | 299 | 306 | +7 (pool shutdown + persistence) |

---

## 2. Architecture: Before and After

### 2.1 Before: Single-Threaded Baseline

All processing — JSON parsing, NTP sync, HTTP cache refresh, C++ tracking, and MQTT
publishing — ran sequentially on the paho MQTT callback thread. Any blocking operation
(HTTP timeout, slow tracking, publish contention) stalled all message processing.

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
|                                                |
|  onConnect()                                   |
|    |-- refreshScenes()                <-- HTTP |
|    +-- updateSubscriptions()          <-- HTTP |
+-----------------------------------------------+

Problems:
  [P1] HTTP calls on MQTT thread --> paho deadlock ("dead-but-alive")
  [P2] No parallelism across scenes (GIL-bound)
  [P3] Slow tracking blocks all cameras
  [P4] No backpressure control
  [P5] Single crash kills everything
```

### 2.2 After: Multi-Process Architecture

The MQTT callback thread is now lightweight: capture payload, overwrite buffer, route to worker.
Heavy work (tracking, publish) runs in isolated ProcessPoolExecutor workers. HTTP operations
run in background threads. A publish watchdog and staleness monitor provide self-healing.

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

### 2.3 Thread and Process Map

```
Main Process:
  +-- MQTT Callback Thread (paho network loop)
  +-- Background Periodic Cache Refresh Thread (daemon)
  +-- Async Publish Thread (daemon)
  +-- Publish Watchdog Thread (daemon)
  +-- Staleness Cleanup Thread (daemon)
  +-- DB Update Threads (daemon, spawned on-demand)
  +-- OnConnect Setup Thread (daemon, spawned on-demand)

Worker Processes (1 per scene, spawned via ProcessPoolExecutor):
  +-- Each has its own SceneController instance (_is_worker=True)
  +-- Each has its own CacheManager, Scene, Tracker instances
  +-- Process isolation: no GIL contention with main process
```

---

## 3. Change Taxonomy

Every change is classified by category, severity, and file location.

### 3.1 Bug Fixes

| ID | Severity | File : Line | Summary |
|----|----------|-------------|---------|
| BF-1 | **CRITICAL** | `scene.py:168` | Multi-category tripwire/region event loss |
| BF-2 | MEDIUM | `scene.py:275` | Mutable default argument (`already_tracked_objects=[]`) |
| BF-3 | LOW | `tracking.py:134` | `raise NotImplemented` (singleton, not exception) |
| BF-4 | LOW | `moving_object.py` | `classDict.update('')` (no-op, likely typo) |

### 3.2 Architectural Changes

| ID | Impact | File(s) | Summary |
|----|--------|---------|---------|
| ARCH-1 | HIGH | `scene_controller.py:276-362` | ProcessPoolExecutor per scene |
| ARCH-2 | HIGH | `scene_controller.py:466-566` | Async MQTT publish thread |
| ARCH-3 | HIGH | `cache_manager.py:36-110` | Lock-free HTTP cache architecture |
| ARCH-4 | HIGH | `time_chunking.py:86-451` | Scene-aware time chunking redesign |
| ARCH-5 | HIGH | `scene_controller.py:1320-1341` | Background database operations |

### 3.3 Safety and Reliability

| ID | Impact | File : Line | Summary |
|----|--------|-------------|---------|
| SAFE-1 | HIGH | `tracking.py:156-162` | Thread ownership assertion |
| SAFE-2 | HIGH | `tracking.py:72-73` | Cross-category object assertion |
| SAFE-3 | HIGH | `scene_controller.py:344-362` | Worker crash auto-recovery |
| SAFE-4 | MEDIUM | `tracking.py:40` | Daemon threads (auto-cleanup) |
| SAFE-5 | MEDIUM | `tracking.py:196-224` | Exception handling in tracker run() |
| SAFE-6 | MEDIUM | `scene_controller.py:20` | faulthandler (SIGSEGV traceback) |
| SAFE-7 | MEDIUM | `scene_controller.py:202-203` | Semaphore admission control |

### 3.4 Monitoring and Observability

| ID | Impact | File : Line | Summary |
|----|--------|-------------|---------|
| MON-1 | MEDIUM | `scene_controller.py:364-397` | Publish watchdog (30s health) |
| MON-2 | MEDIUM | `scene_controller.py:399-429` | Staleness cleanup (60s orphan removal) |
| MON-3 | LOW | `tracking.py:213-217` | Tracker heartbeat (30s liveness) |
| MON-4 | LOW | `ilabs_tracking.py` | PROFILE_UPDATE, PROFILE_TRACK, PROFILE_TRACK_BATCHED |
| MON-5 | LOW | `scene.py:182-189` | PROFILE_PROCESS, PROFILE_PROCESS_TOTAL |

### 3.5 Performance Optimizations

| ID | Impact | File : Line | Summary |
|----|--------|-------------|---------|
| OPT-1 | MEDIUM | `ilabs_tracking.py:156-193` | `from_tracked_object_fast()` O(1) lookup |
| OPT-2 | MEDIUM | `ilabs_tracking.py:37` | Process noise tuned for 10 FPS |
| OPT-3 | LOW | `uuid_manager.py:34` | Bounded thread pool (max_workers=4) |
| OPT-4 | LOW | `cache_manager.py:263-278` | `_fast` lookup methods (no HTTP) |

### 3.6 Preserved Baseline Features (Merged Back)

| ID | Impact | File : Line | Summary |
|----|--------|-------------|---------|
| PRES-1 | HIGH | `ilabs_tracking.py:146-150` | UUID preservation (existing GID check) |
| PRES-2 | HIGH | `ilabs_tracking.py:248-250, 295-297` | All active tracks for pruning |
| PRES-3 | MEDIUM | `uuid_manager.py:302-305` | UUID persistence in assignID |
| PRES-4 | MEDIUM | Multiple files | Suspended track timeout (C++ compatibility) |

---

## 4. Critical Bug Fixes

### 4.1 BF-1: Multi-Category Tripwire/Region Event Loss

**Severity**: CRITICAL
**Affected**: Any scene using multi-class detectors (person+vehicle, carton+basket)

#### Problem

When a camera detects multiple object categories in a single frame (e.g., both `person` and
`vehicle`), only the LAST category's tripwire/region events were published. Events from all
earlier categories were silently lost.

#### Root Cause

`self.events = {}` was reset inside `_updateEvents()`, which was called once PER detection type
inside the `processCameraData()` loop. Each iteration wiped events accumulated by previous
categories.

#### Before (`scene.py` baseline)

```python
def processCameraData(self, jdata, when=None, ignoreTimeFlag=False):
    # ... camera setup ...
    for detection_type, detections in jdata['objects'].items():
        objects = self._createSceneObjects(detection_type, detections)
        self._finishProcessing(detection_type, when, objects)
    return True

def _updateEvents(self, detectionType, now):
    self.events = {}                    # <-- BUG: Resets on every category
    now_str = get_iso_time(now)
    curObjects = self.tracker.currentObjects(detectionType)
    for region in self.regions:
        # ... accumulate region/tripwire events into self.events ...
```

**Execution trace for frame with `{person: [...], vehicle: [...]}` detections**:
1. Loop iteration 1: `detection_type=person` -> `_updateEvents` -> `self.events = {}` -> accumulate person events
2. Loop iteration 2: `detection_type=vehicle` -> `_updateEvents` -> `self.events = {}` -> **PERSON EVENTS WIPED** -> accumulate vehicle events
3. Result: Only vehicle events survive

#### After (`scene.py:167-168`)

```python
def processCameraData(self, jdata, when=None, ignoreTimeFlag=False):
    # ... camera setup ...
    # Reset events once per frame so all detection types accumulate.
    self.events = {}                    # <-- FIX: Reset ONCE before loop
    for detection_type, detections in jdata['objects'].items():
        objects = self._createSceneObjects(detection_type, detections)
        self._finishProcessing(detection_type, when, objects, camera_id=camera_id)
    return True

def _updateEvents(self, detectionType, now):
    # NO self.events = {} here -- events accumulate across categories
    now_str = get_iso_time(now)
    curObjects = self.tracker.currentObjects(detectionType)
    # ... events from ALL categories preserved ...
```

---

### 4.2 BF-2: Mutable Default Argument

**Severity**: MEDIUM
**File**: `scene.py:275-277`

#### Before

```python
def _finishProcessing(self, detectionType, when, objects, already_tracked_objects=[]):
    #                                                       ^^^^^^^^^^^^^^^^^^^^^^^^^
    #                                    BUG: Shared mutable list across all calls
```

#### After

```python
def _finishProcessing(self, detectionType, when, objects, already_tracked_objects=None,
                      camera_id=None):
    if already_tracked_objects is None:
        already_tracked_objects = []
```

Python mutable defaults are created once at function definition time and shared across all
calls. Appending to the list in one call would unexpectedly affect subsequent calls.

---

### 4.3 BF-3: Wrong Exception Type

**Severity**: LOW
**File**: `tracking.py:134, 138`

#### Before

```python
raise NotImplemented    # Returns the NotImplemented singleton (used for binary ops)
return                  # Unreachable
```

#### After

```python
raise NotImplementedError    # Correct: raises an actual exception
```

---

### 4.4 BF-4: No-Op classDict.update

**Severity**: LOW
**File**: `moving_object.py`

```python
# Before:
classDict.update('')    # No-op: str has no key-value pairs for dict.update()

# After: Removed entirely
```

---

## 5. Multi-Process Worker Architecture

**Files**: `scene_controller.py:76-84, 89-255, 276-362, 920-999`
**Problem**: Python's GIL prevents parallel C++ tracking across scenes on a single thread.
Under load (18+ cameras), the single MQTT callback thread becomes a bottleneck.

### 5.1 ProcessPoolExecutor Per Scene

Each scene gets a dedicated `ProcessPoolExecutor(max_workers=1)`, created on-demand.
Worker processes are isolated: each has its own `SceneController` instance with independent
CacheManager, Scene, and Tracker state.

```
scene_controller.py:276   _get_or_create_executor(scene_uid)
scene_controller.py:344   _recreate_scene_executor(scene_uid)  # crash recovery
scene_controller.py:174   self._scene_executors = {}
scene_controller.py:178   self._mp_ctx = multiprocessing.get_context("spawn")
```

Module-level picklable functions enable ProcessPoolExecutor:

```python
# scene_controller.py:74-84
_worker_controller = None

def _init_worker_process(config):
    global _worker_controller
    _worker_controller = SceneController(**config, _is_worker=True)

def _worker_handle_message(topic_str, payload, t_callback_enter):
    return _worker_controller._processMovingObjectMessage(
        topic_str, payload, t_callback_enter)
```

### 5.2 Overwrite-Based Freshness Buffer

At most one pending frame per camera exists. New frames atomically overwrite stale ones.

```python
# scene_controller.py:209-210
self._latest_frame = {}               # {camera_id: (topic, payload, timestamp)}
self._latest_frame_lock = threading.Lock()
```

```
Camera A sends Frame 1 --> _latest_frame["camA"] = Frame 1
Camera A sends Frame 2 --> _latest_frame["camA"] = Frame 2  (Frame 1 overwritten)
Worker picks up Frame 2 --> processes latest data
```

This prevents unbounded queue growth: no matter how fast frames arrive, at most 1 is buffered.

### 5.3 Semaphore Admission Control

```python
# scene_controller.py:202-203
MAX_INFLIGHT_MESSAGES = int(os.environ.get('CONTROLLER_MAX_INFLIGHT', '20'))
self._inflight_semaphore = threading.Semaphore(MAX_INFLIGHT_MESSAGES)
```

Non-blocking acquire: if 20 messages are already in-flight, new messages are dropped (the
overwrite buffer ensures the latest frame is still available when a slot opens).

### 5.4 Worker Crash Recovery

```python
# scene_controller.py:986-993
except BrokenProcessPool as e:
    log.error(f"[BROKEN_POOL] scene={scene_uid}, recreating executor: {e}")
    self._recreate_scene_executor(scene_uid)   # Auto-recovery
    self._inflight_semaphore.release()         # Release semaphore on failure
```

A single worker crash does not kill the controller. The executor is automatically recreated
and processing resumes on the next frame.

---

## 6. Async MQTT Publishing

**Files**: `scene_controller.py:466-566`
**Problem**: Synchronous MQTT publish on the worker thread adds latency to the tracking
critical path. The paho MQTT client is NOT thread-safe — concurrent publish from multiple
workers corrupts the SSL connection.

### 6.1 Dedicated Publish Thread

```python
# scene_controller.py:181-197
self._publish_queue = queue.Queue(maxsize=ASYNC_PUBLISH_QUEUE_SIZE)  # default 1000
self._publish_shutdown = threading.Event()
self._publish_thread = threading.Thread(
    target=self._publish_thread_loop, name="AsyncPublish", daemon=True)
self._publish_thread.start()
```

All `publish()` calls route through `_async_publish()` (line 545), which places messages on
the bounded queue. The dedicated thread drains the queue under `_publish_lock`.

### 6.2 Thread-Safe Publish Lock

```python
# scene_controller.py:167
self._publish_lock = threading.Lock()

# scene_controller.py:491-492 (inside _publish_thread_loop)
with self._publish_lock:
    self.pubsub.publish(topic, payload)
```

All MQTT publish calls are serialized through this lock, preventing SSL corruption.

### 6.3 Publish Watchdog

```python
# scene_controller.py:364-397
def _publish_watchdog_loop(self):
    """Monitor publish thread health every 30 seconds. Auto-restart if dead."""
```

If the publish thread dies silently (e.g., unhandled exception), the watchdog detects it
within 30 seconds and restarts it. Without this, a dead publish thread causes permanent
detection loss with no error indication.

### 6.4 Staleness Cleanup

```python
# scene_controller.py:399-429
def _staleness_cleanup_loop(self):
    """Remove orphaned pending work entries every 60 seconds."""
```

Prevents memory leak from futures that complete but whose done-callbacks fail to execute.

---

## 7. Thread-Safe Cache Manager

**File**: `cache_manager.py:36-110, 263-278, 281-317`
**Problem**: The baseline `CacheManager` made HTTP calls during cache lookups. When called
from the MQTT callback thread, these HTTP calls blocked paho's network loop, causing
"dead-but-alive" stalls where the controller appeared connected but stopped processing.

### 7.1 The Deadlock Pattern (Before)

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

### 7.2 Lock-Free HTTP Architecture (After)

`refreshScenes()` is redesigned into 3 phases that never hold the lock during HTTP:

```python
# cache_manager.py:36-110
def refreshScenes(self):
    # HTTP fetch OUTSIDE lock (lines 48-59)
    try:
        result = self.data_source.getScenes()        # HTTP, no lock held
    except requests.exceptions.Timeout:
        log.error("[CACHE_REFRESH_TIMEOUT] ...")
        return                                        # Graceful: use stale cache
    except requests.exceptions.RequestException:
        log.error("[CACHE_REFRESH_ERROR] ...")
        return

    # Camera param sync OUTSIDE lock (lines 67-70)
    for scene_data in found:
        self._refreshCameras(scene_data)              # HTTP, no lock held

    # In-memory cache update INSIDE lock (lines 72-109)
    with self._lock:                                  # Fast: dict ops only
        for scene_data in found:
            self.cached_scenes_by_uid[scene.uid] = scene
            self._cached_scenes_by_cameraID[cam_id] = scene
```

### 7.3 Fast Lookup Methods

New `_fast` suffixed methods do dict-only lookups — safe to call from the MQTT callback thread:

```python
# cache_manager.py:263-278
def sceneWithCameraID_fast(self, cameraID):    # Dict-only, no HTTP
def sceneWithSensorID_fast(self, sensorID):    # Dict-only, no HTTP
def sceneWithID_fast(self, sceneID):           # Dict-only, no HTTP
def sceneWithRemoteChildID_fast(self, childID): # Dict-only, no HTTP
```

All MQTT callback thread code uses `_fast` methods. The original methods (with `checkRefresh()`)
remain available for contexts where HTTP is safe.

### 7.4 Background Periodic Refresh

```python
# cache_manager.py:281-317
def startPeriodicRefresh(self, interval=None):
    """Start daemon thread that refreshes cache at configurable interval."""
```

Replaces on-demand `checkRefresh()` that blocked the MQTT thread. Cache freshness is now
decoupled from the message processing hot path.

---

## 8. Scene-Aware Time Chunking

**File**: `time_chunking.py:86-451`
**Problem**: The baseline `TimeChunkBuffer` grouped frames per-camera with no scene context.
Cameras from the same scene could be dispatched in different batches, breaking spatial
coherence for multi-camera tracking.

### 8.1 Before: Flat Camera Buffer

```
Baseline TimeChunkBuffer:
  {category: {camera_id: (objects, when, already_tracked)}}

  Timer fires every 50ms --> dispatch ALL buffered cameras
  No concept of scene grouping
  time.sleep() drifts under load
```

### 8.2 After: Scene-Aware Two-Level Buffer

```
SceneAwareCategoryBuffer:
  {scene_id: {camera_id: (objects, when, already_tracked)}}

  Scene completeness check: triggers when all cameras for a scene arrive
  Dynamic camera count: resolved from CacheManager at runtime
  Stale timeout: partial scenes dispatched after configurable timeout
```

```python
# time_chunking.py:86-187
class SceneAwareCategoryBuffer:
    def update(self, camera_id, scene_id, objects, when, already_tracked):
        # Overwrite semantics: latest frame per camera always wins
        # Notify on_scene_complete when all cameras for scene arrive

    def pop_complete_scenes(self):   # Event-driven fast path
    def pop_stale_scenes(self, max_age_sec):  # Timeout fallback
```

### 8.3 Hybrid Dispatch Strategy

```python
# time_chunking.py:190-451
class TimeChunkProcessor(threading.Thread):
    # Fixed-rate scheduling via time.monotonic() (no drift)
    # threading.Condition for early wake on scene completion
    # Stale timeout for partial scenes

    # Dispatch priority:
    #   1. Complete scenes (all cameras arrived) --> immediate
    #   2. Scheduled timer (200ms) --> dispatch complete + stale partials
    #   3. Stale timeout --> partial scenes that waited too long
```

### 8.4 Module-Level Cache Manager Injection

```python
# time_chunking.py:62-65
def set_cache_manager(cache_manager):
    global _cache_manager
    _cache_manager = cache_manager

# Called from scene_controller.py:134
set_cache_manager(self.cache_manager)
```

Worker processes derive `scene_id` from CacheManager for correct scene grouping.

---

## 9. Background Database Operations

**File**: `scene_controller.py:1320-1341, 1356-1383`
**Problem**: `handleDatabaseMessage()` and `onConnect()` executed HTTP-heavy operations
(REST API calls to update subscriptions, object classes, cameras) directly on the MQTT
callback thread, causing paho deadlocks.

### 9.1 handleDatabaseMessage: Before and After

```python
# BEFORE: All HTTP work on MQTT callback thread
def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
        self.updateSubscriptions()       # <-- HTTP blocks MQTT thread
        self.updateObjectClasses()       # <-- HTTP blocks MQTT thread
        self.updateCameras()             # <-- HTTP blocks MQTT thread

# AFTER: Lightweight callback, heavy work in daemon thread
def handleDatabaseMessage(self, client, userdata, message):   # line 1320
    command = str(message.payload.decode("utf-8"))
    if command == "update":
        threading.Thread(target=self._databaseUpdateAsync,
                        name="DBUpdate", daemon=True).start()

def _databaseUpdateAsync(self):                                # line 1329
    with self._db_update_lock:          # Serialize concurrent updates
        self.updateSubscriptions()
        self._sync_workers_to_scenes()  # Sync worker pool to new scenes
        self.updateObjectClasses()
        self.updateCameras()
        self.updateRegulateCache()
        self.updateTRSMatrix()
```

### 9.2 onConnect: Before and After

```python
# BEFORE: Blocks paho's network loop during initial setup
def onConnect(self, client, userdata, flags, rc):
    self.updateSubscriptions()           # <-- HTTP blocks MQTT thread
    self.updateObjectClasses()           # <-- HTTP blocks MQTT thread
    self.updateTRSMatrix()               # <-- HTTP blocks MQTT thread

# AFTER: Subscribe immediately, defer HTTP to background
def onConnect(self, client, userdata, flags, rc):              # line 1356
    topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    self.pubsub.addCallback(topic, self.handleDatabaseMessage)  # Lightweight
    threading.Thread(target=self._onConnectAsync,
                    name="OnConnectSetup", daemon=True).start()

def _onConnectAsync(self):                                      # line 1373
    with self._db_update_lock:
        self.updateSubscriptions()
        self._sync_workers_to_scenes()
        self.updateObjectClasses()
        self.updateTRSMatrix()
```

---

## 10. Tracking and Safety Improvements

### 10.1 Daemon Threads

**File**: `tracking.py:40`

```python
# Before:  super().__init__()         # Non-daemon: blocks process exit
# After:   super().__init__(daemon=True)  # Auto-cleanup on process exit
```

Prevents zombie tracker threads from keeping worker processes alive after shutdown.

### 10.2 Thread Ownership Assertion

**File**: `tracking.py:156-162`

```python
def _assert_owner_thread(self):
    tid = current_thread().ident
    if self._owner_thread_id is None:
        self._owner_thread_id = tid
    assert tid == self._owner_thread_id, \
        f"Tracker state accessed by thread {tid}, but owned by {self._owner_thread_id}"
```

In the multi-process architecture, each tracker's mutable state must only be accessed by its
owning thread. This assertion catches data race bugs at runtime instead of producing
silent corruption.

### 10.3 Cross-Category Safety Assertion

**File**: `tracking.py:72-73`

```python
assert all(obj.category == category for obj in new_objects), \
    f"Cross-category objects in trackObjects for {category}"
```

Catches bugs where objects from different categories (e.g., `person` and `vehicle`) are
accidentally enqueued together.

### 10.4 Exception Handling in Tracker Run Loop

**File**: `tracking.py:196-224`

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
    items_processed += 1
```

### 10.5 Tracker Heartbeat

**File**: `tracking.py:213-217`

```python
now = time.time()
if now - last_heartbeat > 30.0:
    log.info(f"[TRACKER_HEARTBEAT] thread={self.__str__()}, "
             f"items_processed={items_processed}, queue_size={self.queue.qsize()}")
    last_heartbeat = now
```

Detects stuck tracker threads. If heartbeat stops appearing in logs, the tracker is blocked.

### 10.6 Faulthandler

**File**: `scene_controller.py:20`

```python
faulthandler.enable()  # Prints Python traceback on SIGSEGV/SIGFPE/SIGABRT
```

Critical for debugging C++ tracker crashes that produce segfaults instead of Python exceptions.

### 10.7 Graceful Shutdown

**File**: `scene_controller.py:431-464`

```python
def shutdown(self):
    # 1. Signal monitoring threads to stop
    # 2. Drain async publish queue (5s timeout)
    # 3. Shutdown all scene executors (wait for in-flight work)
    # 4. Shutdown tracker threads (uuid_manager cleanup)
```

Ensures clean exit: no orphaned processes, no lost messages in the publish queue.

---

## 11. Performance Optimizations

### 11.1 O(1) Object Conversion

**File**: `ilabs_tracking.py:156-193`

The baseline `from_tracked_object()` performed O(n) linear scans per tracked object to match
C++ tracker output back to SceneScape objects. With N tracked objects per category, this was
O(N^2) per tracking call.

```python
# Before: O(n) per tracked object
for obj in objects:
    if sscape_object.rv_id == tracked_object.id:  # Linear scan
        break

# After: O(1) via pre-built hash maps
def from_tracked_object_fast(self, tracked_object, objects_by_uuid,
                             tracker_by_uuid, tracker_by_rv_id):
    sscape_object = tracker_by_rv_id.get(tracked_object.id)   # O(1) lookup
```

Pre-built hash maps (`objects_by_uuid`, `tracker_by_uuid`, `tracker_by_rv_id`) are constructed
once per `trackCategoryBatched()` call and shared across all tracked object conversions.

### 11.2 Process Noise Tuning

**File**: `ilabs_tracking.py:37`

```python
# Before:  tracker_config.default_process_noise = 1e-4   # Tuned for 30 FPS
# After:   tracker_config.default_process_noise = 5e-4   # Tuned for 10 FPS
```

The Kalman filter process noise scales with `dt^2`. At 10 FPS (`dt=0.1s`), the effective noise
is `5e-4 * 0.01 = 5e-6`, comparable to Intel's original `1e-4 * 0.0011 = 1.1e-7` at 30 FPS.
The higher base value compensates for the larger inter-frame gap, balancing smooth tracks with
responsive adaptation to direction changes.

### 11.3 Bounded UUID Thread Pool

**File**: `uuid_manager.py:34`

```python
# Before:  self.pool = concurrent.futures.ThreadPoolExecutor()        # Unbounded
# After:   self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)  # Bounded
```

Prevents excessive thread creation under heavy ReID load. 4 threads is sufficient for
concurrent similarity queries without overwhelming the VDMS database.

---

## 12. Configuration Changes

### 12.1 Tracker Config (`config/tracker-config.json`)

| Parameter | Before | After | Time Equivalent | Rationale |
|-----------|--------|-------|-----------------|-----------|
| `baseline_frame_rate` | 30 | 10 | N/A | Matched to Triton pipeline FPS |
| `max_unreliable_frames` | 10 | 5 | 0.33s -> 0.5s | Tighter threshold at 10 FPS |
| `non_measurement_frames_dynamic` | 8 | 20 | 0.27s -> 2.0s | Longer tolerance for moving objects |
| `non_measurement_frames_static` | 16 | 30 | 0.53s -> 3.0s | Longer tolerance for static objects |
| `time_chunking_interval_milliseconds` | 50 | 200 | N/A | Better batching efficiency at 10 FPS |
| `suspended_track_timeout_secs` | N/A | 60.0 | N/A | Memory cleanup (see Section 14) |

**Note**: The time equivalents shift because `time = frames / frame_rate`. At 10 FPS, 20
frames = 2.0 seconds. At 30 FPS, 8 frames = 0.27 seconds. The longer timeouts accommodate
the larger inter-frame gaps at 10 FPS.

### 12.2 New Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONTROLLER_MAX_WORKERS` | 0 (unlimited) | Cap on worker processes |
| `CONTROLLER_MAX_INFLIGHT` | 20 | Semaphore admission control |
| `CONTROLLER_ASYNC_PUBLISH_QUEUE_SIZE` | 1000 | Async publish queue depth |
| `CONTROLLER_ASYNC_PUBLISH_ENABLED` | true | Toggle async publish on/off |
| `CONTROLLER_STARTUP_GRACE_SEC` | 5.0 | Grace period for stale frames at startup |

### 12.3 New Runtime Dependency

```
requests==2.32.3    # For cache_manager.py HTTP error handling
```

### 12.4 Entry Point Additions (`controller-cmd`)

```python
# New CLI flags:
--profile              # Enable cProfile profiling
--profile-output PATH  # Output path (default: /dev/shm/controller_profile.stats)
```

---

## 13. Preserved Baseline Features

These features are present in the Intel SceneScape 2025.2 baseline. They were carefully
preserved in the enhanced controller to prevent regression.

### 13.1 PRES-1: UUID Preservation in from_tracked_object

**File**: `ilabs_tracking.py:146-150`
**Risk if lost**: Objects lose their UUID when transitioning between tracking states, breaking
ReID continuity.

```python
# Simplified approach (loses UUID on state transitions):
sscape_object.setGID(uuid)

# Preserved baseline behavior (checks existing mapping first):
existing_gid = self.uuid_manager.active_ids.get(sscape_object.rv_id, [None])[0]
if existing_gid is None:
    sscape_object.setGID(uuid)       # New object: assign tracker UUID
else:
    sscape_object.setGID(existing_gid)  # Known object: keep existing UUID
```

### 13.2 PRES-2: All Active Tracks for Pruning

**File**: `ilabs_tracking.py:248-250` (trackCategory) and `ilabs_tracking.py:295-297` (trackCategoryBatched)
**Risk if lost**: UUID mappings pruned too early, objects get new identities when re-detected.

```python
# Without full track state coverage (reliable only):
tracked_objects = self.tracker.get_reliable_tracks()
self.uuid_manager.pruneInactiveTracks(tracked_objects)

# Preserved baseline behavior (all track states):
tracked_objects = self.tracker.get_reliable_tracks()
all_active_tracks = (tracked_objects +
                    self.tracker.get_unreliable_tracks() +
                    self.tracker.get_suspended_tracks())
self.uuid_manager.pruneInactiveTracks(all_active_tracks)
```

**Why all three states matter**:

```
Object enters scene          --> reliable track
Object partially occluded    --> unreliable track    UUID must persist
Object fully occluded        --> suspended track     UUID must persist
Object reappears             --> reliable track      UUID must match original
```

Without including unreliable and suspended tracks in the prune check, the UUID mapping
is removed as soon as an object becomes unreliable, and a NEW UUID is assigned when
the same object becomes reliable again.

### 13.3 PRES-3: UUID Persistence in assignID

**File**: `uuid_manager.py:302-305`
**Risk if lost**: Objects without database matches lose identity mapping.

```python
# End of assignID():
with self.active_ids_lock:
    if self.active_ids.get(sscape_object.rv_id, [None])[0] is None:
        self.active_ids[sscape_object.rv_id] = [sscape_object.gid, None]
```

Ensures objects retain their tracker-assigned UUID in `active_ids` even when no
database similarity match exists.

### 13.4 PRES-4: Suspended Track Timeout

**Files**: `tracking.py:25`, `ilabs_tracking.py:25-27,56-60`, `scene.py:79-83`,
`cache_manager.py:94`, `time_chunking.py:462-465`, `tracker-config.json`
**Risk if lost**: Unbounded memory growth from accumulated suspended tracks.

Full parameter chain:

```
tracker-config.json: {"suspended_track_timeout_secs": 60.0}
    |
    v
scene_controller.py: extractTrackerConfigData()
    |
    v
cache_manager.py: tracker_config_data.get("suspended_track_timeout_secs", 60.0)
    |
    v
scene.py: self.suspended_track_timeout_secs --> _setTracker args
    |
    v
ilabs_tracking.py: tracker_config.suspended_track_timeout_secs = value
    |
    v
C++ TrackManager: cleanupOldSuspendedTracks() in predict()
```

See [Section 14](#14-suspended-track-timeout-production-decision) for full production rationale.

---

## 14. Suspended Track Timeout: Production Decision

### Decision: KEEP

The Intel SceneScape 2025.2 C++ build does not include suspended track timeout support.
This codebase adds it. This section documents the complete reasoning.

### What It Does

The `suspended_track_timeout_secs` parameter (default 60.0s) configures the C++ `TrackManager`
to automatically clean up tracks that remain in "suspended" state (detection lost) for longer
than the configured duration. The cleanup runs inside `TrackManager::predict()` by iterating
`mSuspensionTimes` (`std::unordered_map<int, double>`) and removing expired entries.

### Performance Impact

| Aspect | Cost | Justification |
|--------|------|---------------|
| CPU per predict() | Microseconds | Single O(n) scan, typically <50 entries |
| Memory per track | ~100 bytes | Hashmap entry: int key + double timestamp |
| Multi-process interaction | None | Runs inside per-worker C++ tracker |
| Async publish interaction | None | Cleanup in tracking path, not publish path |
| Time chunking interaction | None | Runs inside tracker.predict() |

### Why It Must Be Kept

1. **Memory safety**: Without timeout, suspended tracks accumulate indefinitely in 24/7
   deployments. Each lost detection creates a suspended track. This is unbounded memory growth.

2. **C++ code compatibility**: This codebase's `robot_vision` C++ build includes the feature:
   - `TrackManager.cpp`: `cleanupOldSuspendedTracks()` in both `predict()` overloads
   - `TrackManager.hpp`: `mSuspendedTrackMaxAgeSecs`, `mSuspensionTimes`
   - `tracking.cpp` (pybind11): `suspended_track_timeout_secs` property

3. **UUID continuity**: The `all_active_tracks` pattern (PRES-2) depends on suspended tracks
   being available for the prune check. Removing timeout would either cause memory growth
   (no cleanup) or UUID loss (no suspended tracks in prune).

4. **Zero performance trade-off**: This is purely a cleanup mechanism. It does not affect
   tracking accuracy, detection latency, or throughput.

### C++ Implementation

`suspended_track_timeout_secs` is implemented in the C++ `TrackManager` via
`cleanupOldSuspendedTracks()`, `mSuspensionTimes`, and the `mSuspendedTrackMaxAgeSecs` config
field. The pybind11 binding exposes it as `suspended_track_timeout_secs` on `TrackManagerConfig`.
`getSuspendedTracks()` and `getUnreliableTracks()` are available on both `TrackManager` and
`MultipleObjectTracker`.

### Future Removal Criteria

Remove ONLY when all conditions are met:
1. C++ `TrackManager` drops `cleanupOldSuspendedTracks()` and `mSuspensionTimes`
2. pybind11 bindings drop `suspended_track_timeout_secs` property
3. Alternative memory cleanup mechanism is implemented in C++
4. UUID preservation logic is updated to work without suspended tracks in pruning

---

## 15. Production Hardening Fixes

These fixes were applied during production readiness review after the initial integration.
They address race conditions, null safety, resource management, and correctness issues
discovered through deep code analysis.

### 15.1 Concurrency & Race Condition Fixes

#### PH-1: Sole-Owner Re-Submission Pattern (CRITICAL)

**File**: `scene_controller.py:934-1098`
**Problem**: Both the MQTT callback thread and the worker done-callback could submit work
for the same camera simultaneously, causing duplicate submissions and semaphore accounting errors.

**Before** (race-prone):

```
MQTT Thread:               Done Callback:
  check pending_work         check pending_work
  entry is "done"            entry is "done"
  remove entry               remove entry        <-- RACE
  submit new work            submit new work     <-- DOUBLE SUBMIT
```

**After** (sole-owner):

```python
# scene_controller.py:964-971
# _processIncomingDetection: returns immediately if ANY entry exists
with self._pending_work_lock:
    if camera_id in self._pending_work:
        return    # Let _handle_work_complete handle re-submission

# scene_controller.py:1038-1098
# _handle_work_complete: sole owner of re-submission and cleanup
def _handle_work_complete(self, camera_id, scene_uid):
    self._inflight_semaphore.release()
    frame = self._get_latest_frame(camera_id)
    if frame is not None:
        # Re-submit with store-before-callback pattern
        ...
    else:
        # Clean up entry so MQTT thread can submit next time
        with self._pending_work_lock:
            self._pending_work.pop(camera_id, None)
```

The MQTT thread NEVER removes or replaces entries in `_pending_work`. Only the done callback
does. This eliminates all double-submission races.

#### PH-2: Store-Before-Callback Race Fix (CRITICAL)

**File**: `scene_controller.py:1002-1011, 1070-1080`
**Problem**: If `executor.submit()` returns a future that completes before `add_done_callback()`
is called, CPython fires the callback synchronously on the current thread. If the future
isn't stored in `_pending_work` yet, the callback finds no entry to clean up.

```python
# WRONG ORDER:
future = executor.submit(...)
future.add_done_callback(...)  # Callback fires NOW (synchronous) before store
_pending_work[cam] = future    # Too late — callback already ran, entry orphaned

# CORRECT ORDER (current implementation):
future = executor.submit(...)
_pending_work[cam] = future    # Store FIRST
future.add_done_callback(...)  # Safe — callback finds the entry
```

#### PH-3: Child Scene Transform Lock Protection (HIGH)

**File**: `scene_controller.py:1548-1549, 1555-1556`
**Problem**: `cached_child_transforms_by_uid` was directly mutated from the DB update thread
without holding `cache_manager._lock`, racing with `sceneWithRemoteChildID_fast()` reads.

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

Also fixed the `'None'` string literal default (was returning the string `'None'` instead of
the `None` sentinel when the key was missing).

### 15.2 Null Safety Fixes

#### PH-4: from_tracked_object Null Guard (CRITICAL)

**File**: `ilabs_tracking.py:131-133` (slow path), `ilabs_tracking.py:169-171` (fast path)
**Problem**: If a tracked object's UUID doesn't match any SceneScape object (e.g., UUID
invalidated between frames), the code would either crash or silently return a broken object.

```python
# After: Both paths return None with warning
log.warning(f"No sscape_object found for tracked UUID {uuid}, track_id={tracked_object.id}")
return None

# Callers filter None results:
tracks_from_detections = [t for t in (self.from_tracked_object(tracked_object, objects)
                     for tracked_object in tracked_objects) if t is not None]
```

#### PH-5: refreshScenesForCamParams Null Crash Guard (CRITICAL)

**File**: `cache_manager.py:155-156`
**Problem**: After `invalidate()`, `cached_scenes_by_uid` is `None`. If
`refreshScenesForCamParams()` runs before the next `refreshScenes()` completes, it crashes
with `AttributeError: 'NoneType' object has no attribute 'values'`.

```python
# After:
with self._lock:
    if self.cached_scenes_by_uid is None:
        return   # Skip — next periodic refresh will repopulate
```

#### PH-6: Camera Refresh Distortion Null Guard (HIGH)

**File**: `cache_manager.py:125-132`
**Problem**: `_refreshCameras()` assumed `camera_parameters[uid].get('distortion')` always
returned a dict, but it can be `None` if distortion data hasn't been sent yet. This caused
`NoneType has no attribute '__getitem__'` crashes.

```python
# Before:
distortion_values = {
    dist_coeff: self.camera_parameters[camera['uid']].get('distortion')[dist_coeff]  # Crashes if None
    for dist_coeff in supported_distortion_values
}

# After:
distortion = self.camera_parameters[camera['uid']].get('distortion')
if distortion is not None:
    distortion_values = {
        dist_coeff: distortion.get(dist_coeff)
        for dist_coeff in supported_distortion_values
    }
```

Also wrapped the entire camera refresh loop in `try/except` to prevent one bad camera from
blocking refresh of all subsequent cameras (line 114-142).

### 15.3 Resource Management Fixes

#### PH-7: Cache Periodic Refresh Shutdown (HIGH)

**File**: `scene_controller.py:431-464` (shutdown method)
**Problem**: `shutdown()` stopped the publish thread and executors but did NOT stop the
background cache refresh thread, leaving it running after shutdown.

```python
# After: Added to shutdown()
if hasattr(self, 'cache_manager'):
    self.cache_manager.stopPeriodicRefresh()
```

#### PH-8: Executor Shutdown Outside Lock (HIGH)

**File**: `scene_controller.py` (shutdown method)
**Problem**: Calling `executor.shutdown(wait=True)` while holding `_scene_executor_lock`
blocks all other threads that need to acquire the lock (e.g., workers completing via callback).

```python
# After: Collect under lock, shutdown outside
with self._scene_executor_lock:
    executors_to_shutdown = list(self._scene_executors.items())
    self._scene_executors.clear()
for scene_uid, executor in executors_to_shutdown:
    executor.shutdown(wait=True, cancel_futures=False)
```

#### PH-9: Fatal Exit via os._exit() (MEDIUM)

**File**: `scene_controller.py` (onConnect handler)
**Problem**: `exit(1)` raises SystemExit, which can be caught by paho's internal exception
handling, preventing actual process termination during fatal connection failures.

```python
# Before:  exit(1)      # SystemExit exception, catchable
# After:   os._exit(1)  # Immediate process termination, uncatchable
```

### 15.4 Correctness Fixes

#### PH-10: UUID Preservation in from_tracked_object_fast (CRITICAL)

**File**: `ilabs_tracking.py:176-181`
**Problem**: The fast path (`from_tracked_object_fast`) used in batched mode was missing
the `existing_gid` check that exists in the slow path, causing objects to get NEW UUIDs
every time they transition between reliable/unreliable/suspended states.

```python
# Before (fast path): Always assigned new UUID
sscape_object.setGID(uuid)

# After (fast path): Matches slow path behavior
existing_gid = self.uuid_manager.active_ids.get(sscape_object.rv_id, [None])[0]
if existing_gid is None:
    sscape_object.setGID(uuid)
else:
    sscape_object.setGID(existing_gid)
```

#### PH-11: Cache Invalidation Clears Lookup Dicts (HIGH)

**File**: `cache_manager.py:323-328`
**Problem**: `invalidate()` set `cached_scenes_by_uid = None` but left
`_cached_scenes_by_cameraID` and `_cached_scenes_by_sensorID` intact. Fast lookup methods
would return stale scenes that no longer exist.

```python
# After:
def invalidate(self):
    with self._lock:
        self.cached_scenes_by_uid = None
        self._cached_scenes_by_cameraID = {}    # Clear stale lookups
        self._cached_scenes_by_sensorID = {}    # Clear stale lookups
```

#### PH-12: Monotonic Arrival Time for Staleness Detection (MEDIUM)

**File**: `time_chunking.py` (SceneAwareCategoryBuffer)
**Problem**: Staleness detection used frame timestamps from MQTT messages, which can have
NTP skew. Monotonic clock is immune to clock adjustments.

```python
# After: 4-element tuple with monotonic arrival time
arrival = time.monotonic()
self._data[scene_id][camera_id] = (objects, when, already_tracked, arrival)
```

#### PH-13: publishEvents Called Once Per Frame (MEDIUM)

**File**: `scene_controller.py` (handleMovingObjectMessage path)
**Problem**: `publishEvents()` was called inside the per-detection-type loop, publishing
events from intermediate states before all categories had been processed.

```python
# Before: Events published N times (once per detection type)
for detection_type, detections in jdata['objects'].items():
    scene.processCameraData(...)
    self.publishEvents(...)    # Called inside loop

# After: Events published once per frame
scene.processCameraData(jdata, ...)   # Processes all detection types
self.publishEvents(scene, ...)         # Called once after all categories
```

#### PH-14: Suspended Track Timeout Validation (MEDIUM)

**File**: `ilabs_tracking.py:55`
**Problem**: Upper bound validation was missing — any positive value was accepted, including
unreasonable values like 999999 that would cause memory issues.

```python
# Before:  if suspended_track_timeout_secs is not None and suspended_track_timeout_secs > 0:
# After:   if suspended_track_timeout_secs is not None and 0 < suspended_track_timeout_secs < 3600:
```

---

## 16. Edge Cases and Known Considerations

### 16.1 Invalidate-Then-Lookup Race

**Scenario**: Thread A calls `invalidate()`, setting `cached_scenes_by_uid = None`. Thread B
calls `sceneWithCameraID_fast()` before the next `refreshScenes()` completes.

**Behavior**: `_fast` methods return `None` because lookup dicts are cleared during invalidation.
Callers already handle `None` (skip processing, log warning, try again on next frame).

**Not a bug**: This is expected behavior. Cache invalidation is rare (only on database updates),
and the background refresh thread repopulates within `REFRESH_TIME` seconds.

### 16.2 Worker Crash with Pending Frames

**Scenario**: Worker process segfaults (C++ tracker crash) while processing a frame.

**Behavior**:
1. `BrokenProcessPool` exception raised in `_handle_work_complete` or `_processIncomingDetection`
2. Semaphore released (no leak)
3. `_recreate_scene_executor()` creates a fresh executor
4. The frame that was being processed is lost
5. Next frame from the overwrite buffer is processed normally

**Acceptable**: The overwrite buffer ensures the latest frame is always available. Losing one
frame during a crash is expected (the frame's data was in a process that segfaulted).

### 16.3 Publish Queue Full

**Scenario**: Downstream consumers slow down. Publish thread cannot drain the queue fast enough.
Queue reaches `maxsize` (default 1000).

**Behavior**: `_async_publish()` drops new messages with `log.warning`. No backpressure to workers.

**Acceptable**: At 10 FPS per camera with 18 cameras, 1000 messages = ~5.5 seconds of backlog.
If the queue is consistently full, the system is overwhelmed and dropping is the correct response.

### 16.4 Store-Before-Callback Synchronous Completion

**Scenario**: Worker completes almost instantly. `executor.submit()` returns an already-done future.
`add_done_callback()` fires the callback synchronously on the current thread.

**Behavior**: The store-before-callback pattern (PH-2) ensures `_pending_work` has the entry when
the callback fires. The callback removes the entry and optionally re-submits.

**Not a bug**: This is explicitly handled. CPython guarantees `add_done_callback` on a done
future calls the callback immediately in the calling thread.

### 16.5 Time Chunking with Single Camera

**Scenario**: A scene has only one camera. The "all cameras arrived" event triggers immediately.

**Behavior**: The event-driven fast path dispatches immediately (within the same MQTT callback),
bypassing the 200ms timer. Single-camera scenes see near-zero batching latency.

### 16.6 Suspended Track Timeout Expiry

**Scenario**: An object disappears from all cameras for >60 seconds, then reappears.

**Behavior**:
1. Track moves: reliable → unreliable → suspended (UUID preserved throughout)
2. After 60s: C++ `cleanupOldSuspendedTracks()` removes the track
3. `pruneInactiveTracks()` removes the UUID mapping from `active_ids`
4. Object reappears → new UUID assigned (this is expected: after 60s, treating it as a new object
   is the correct semantic)

### 16.7 getCamera Result Discarded in _refreshCameras

**Scenario**: `_refreshCameras()` calls `self.data_source.getCamera(camera['uid'])` after an
update, assigning to the local `camera` variable. The result is not used to update `scene_data`.

**Impact**: LOW. The updated camera data is picked up on the next `refreshScenes()` cycle
(within `REFRESH_TIME` seconds). This is a pre-existing baseline behavior.

### 16.8 object_classes Dict Concurrent Access

**Scenario**: The DB update thread calls `updateObjectClasses()`, modifying the global
`object_classes` dict. Worker processes are using `object_classes` to create `MovingObject` instances.

**Why safe**: Workers run in separate processes (ProcessPoolExecutor with `spawn` context).
Each worker has a process-isolated copy of `object_classes`. Within the main process, CPython's
GIL guarantees atomic dict reads/writes for single operations.

**Caveat**: If Python moves to free-threading (PEP 703), this assumption breaks. Adding a lock
would be appropriate if free-threading is adopted.

---

## 17. Production Logging Strategy

### 17.1 Design Principle

All per-frame `PROFILE_*` markers and diagnostic logs use `log.debug`. Production deployments
run at `INFO` level for clean logs. Engineers enable `CONTROLLER_LOG_LEVEL=DEBUG` for performance
analysis.

### 17.2 Log Level Policy

| Level | Usage | Examples |
|-------|-------|---------|
| `log.error` | Failures requiring attention | `[TRACKER_EXCEPTION]`, `[CACHE_REFRESH_ERROR]`, `[BROKEN_POOL]` |
| `log.warning` | Degraded but self-healing | `[PUBLISH_QUEUE_FULL]`, null UUID warning, `[NO_WORKER]` |
| `log.info` | Startup, periodic health, rare events | `[TRACKER_HEARTBEAT]` (30s), `[CACHE]` start/stop, `[ROUTE]` (rate-limited) |
| `log.debug` | Per-frame diagnostics | `[PROFILE_*]`, `[ADMISSION_DROP]`, `[LATENCY]`, `DISCARDING PAST DATA` |

### 17.3 Rate-Limited Logging

```python
# scene_controller.py:956-958
self._route_log_count += 1
if self._route_log_count <= 5 or self._route_log_count % 1000 == 0:
    log.info(f"[ROUTE] camera={camera_id} scene={scene_uid} ...")
```

First 5 ROUTE messages logged at INFO (confirms routing is working at startup), then
every 1000th message (periodic health check).

### 17.4 Downgraded Log Lines

| File | Log Marker | Before | After | Reason |
|------|-----------|--------|-------|--------|
| `scene_controller.py` | `PROFILE_LAG_SPLIT` | `log.info` | `log.debug` | Per-frame |
| `scene_controller.py` | `PROFILE_MAIN` | `log.info` | `log.debug` | Per-frame |
| `scene_controller.py` | `LATENCY` | `log.info` | `log.debug` | Per-frame |
| `scene_controller.py` | `ADMISSION_DROP` | `log.info` | `log.debug` | Per-frame |
| `ilabs_tracking.py` | `PROFILE_UPDATE` | `log.info` | `log.debug` | Per-frame |
| `ilabs_tracking.py` | `PROFILE_ENTRY` | `log.info` | `log.debug` | Per-frame |
| `ilabs_tracking.py` | `PROFILE_TRACK` | `log.info` | `log.debug` | Per-frame |
| `ilabs_tracking.py` | `PROFILE_TRACK_BATCHED` | `log.info` | `log.debug` | Per-frame |
| `time_chunking.py` | Per-dispatch log | `log.info` | `log.debug` | Per-dispatch |
| `time_chunking.py` | Per-frame scene_id | `log.info` | `log.debug` | Per-frame |
| `scene.py` | `PROFILE_PROCESS` | `log.info` | `log.debug` | Per-frame |
| `scene.py` | `PROFILE_FINISH` | `log.info` | `log.debug` | Per-frame |
| `scene.py` | `DISCARDING PAST DATA` | `log.info` | `log.debug` | Per-frame |
| `scene.py` | Object mesh error | `log.info` | `log.warning` | Error condition |
| `tracking.py` | Queue not empty | `log.info` | `log.debug` | Per-frame |

---

## 18. Files Changed Reference

| File | Action | Before | After | Category |
|------|--------|--------|-------|----------|
| `src/controller-cmd` | Enhanced | 64 | 82 | Entry point |
| `src/controller/scene_controller.py` | Rewritten | 669 | 1,575 | ARCH-1,2,5, PH-1,2,3 |
| `src/controller/cache_manager.py` | Rewritten | 190 | 333 | ARCH-3, PH-5,6,11 |
| `src/controller/time_chunking.py` | Redesigned | 209 | 565 | ARCH-4, PH-12 |
| `src/controller/ilabs_tracking.py` | Enhanced | 243 | 372 | OPT-1, PRES-1,2, PH-4,10 |
| `src/controller/scene.py` | Bugfix + Enhanced | 531 | 583 | BF-1, BF-2, PH-13 |
| `src/controller/tracking.py` | Enhanced | 252 | 291 | SAFE-1,2,3,4,5 |
| `src/controller/uuid_manager.py` | Enhanced | 299 | 306 | OPT-3, PRES-3 |
| `src/controller/moving_object.py` | Minor fix | 390 | 390 | BF-4 |
| `src/controller/vdms_adapter.py` | Comment | 149 | 152 | Documentation |
| `src/controller/child_scene_controller.py` | Comment | 77 | 78 | Documentation |
| `config/tracker-config.json` | Retuned | N/A | N/A | CONF-1 |
| `requirements-runtime.txt` | +1 dep | N/A | N/A | CONF-2 |

### Diff Summary (vs baseline HEAD)

```
 controller/config/tracker-config.json              |   10 +-
 controller/requirements-runtime.txt                |    1 +
 controller/src/controller-cmd                      |   38 +-
 controller/src/controller/cache_manager.py         |  323 ++++--
 controller/src/controller/child_scene_controller.py|    3 +-
 controller/src/controller/ilabs_tracking.py        |  187 +++-
 controller/src/controller/moving_object.py         |    4 +-
 controller/src/controller/scene.py                 |   72 +-
 controller/src/controller/scene_controller.py      | 1144 ++++++++++++++++++--
 controller/src/controller/time_chunking.py         |  628 ++++++++---
 controller/src/controller/tracking.py              |   71 +-
 controller/src/controller/uuid_manager.py          |   17 +-
 controller/src/controller/vdms_adapter.py          |    3 +
 13 files changed, 2078 insertions(+), 423 deletions(-)
```

### Baseline Preservation Audit

**Zero accidental removals detected.** All 29 baseline methods in `scene_controller.py` are
preserved. All methods, imports, and classes across all files are accounted for. Every
removal is intentional and replaced by a better implementation.

---

## 19. Verification

### 19.1 Syntax Check

All modified Python files pass `py_compile` syntax verification. Runtime verification requires
the Docker environment with full dependencies (`scene_common`, `robot_vision`, `open3d`, `vdms`).

### 19.2 Feature Presence Checklist

| Feature | File | Verification |
|---------|------|-------------|
| ProcessPoolExecutor per scene | `scene_controller.py:276` | `_get_or_create_executor` |
| faulthandler enabled | `scene_controller.py:20` | `faulthandler.enable()` |
| `_fast` lookup methods | `cache_manager.py:267-283` | 4 methods |
| SceneAwareCategoryBuffer | `time_chunking.py:86` | Class definition |
| `from_tracked_object_fast` | `ilabs_tracking.py:156` | Method definition |
| `_assert_owner_thread` | `tracking.py:156` | Method definition |
| daemon=True threads | `tracking.py:40` | `super().__init__(daemon=True)` |
| Suspended track timeout | `ilabs_tracking.py:55` | `tracker_config.suspended_track_timeout_secs` |
| UUID preservation (slow) | `ilabs_tracking.py:146-150` | `existing_gid` check |
| UUID preservation (fast) | `ilabs_tracking.py:176-181` | `existing_gid` check |
| All active tracks pruning | `ilabs_tracking.py:248-250` | `reliable + unreliable + suspended` |
| active_ids persistence | `uuid_manager.py:302-305` | `active_ids[rv_id] = [gid, None]` |
| Async publish thread | `scene_controller.py:466` | `_publish_thread_loop` |
| Publish watchdog | `scene_controller.py:364` | `_publish_watchdog_loop` |
| Semaphore admission | `scene_controller.py:202-203` | `_inflight_semaphore` |
| Background DB updates | `scene_controller.py:1329` | `_databaseUpdateAsync` |
| Worker crash recovery | `scene_controller.py:344` | `_recreate_scene_executor` |
| Graceful shutdown | `scene_controller.py:431` | `shutdown()` method |
| Sole-owner re-submission | `scene_controller.py:1038` | `_handle_work_complete` |
| Store-before-callback | `scene_controller.py:1007-1011` | Store then callback |
| Null UUID guard | `ilabs_tracking.py:131-133` | Returns None with warning |
| Cache invalidation cleanup | `cache_manager.py:323-328` | Clears all lookup dicts |
| Monotonic staleness | `time_chunking.py` | `time.monotonic()` arrival |
| Child transform lock | `scene_controller.py:1548` | `with cache_manager._lock` |
| Production logging | All files | `log.debug` for per-frame markers |

### 19.3 Production Hardening Checklist

| Fix ID | Severity | Issue | Status |
|--------|----------|-------|--------|
| PH-1 | CRITICAL | Sole-owner re-submission race | FIXED |
| PH-2 | CRITICAL | Store-before-callback race | FIXED |
| PH-3 | HIGH | Child transform lock | FIXED |
| PH-4 | CRITICAL | from_tracked_object null guard | FIXED |
| PH-5 | CRITICAL | refreshScenesForCamParams null crash | FIXED |
| PH-6 | HIGH | Camera refresh distortion null | FIXED |
| PH-7 | HIGH | Cache refresh shutdown | FIXED |
| PH-8 | HIGH | Executor shutdown outside lock | FIXED |
| PH-9 | MEDIUM | os._exit for fatal errors | FIXED |
| PH-10 | CRITICAL | UUID preservation in fast path | FIXED |
| PH-11 | HIGH | Cache invalidation stale lookups | FIXED |
| PH-12 | MEDIUM | Monotonic arrival time | FIXED |
| PH-13 | MEDIUM | publishEvents once per frame | FIXED |
| PH-14 | MEDIUM | Suspended track timeout validation | FIXED |

---

## 20. Intel Upstream Integration (2026-03-18)

Intel's `main` branch accumulated 25 controller commits since the `2025.2` tag we forked from.
These were ported to scenescape-triton in 4 phases ordered by risk, without modifying any VPOD
architectural code paths. All analytics-only code is gated by `ControllerMode.isAnalyticsOnly()`
which defaults to `False` — zero new code executes in default (production) mode.

**Reference**: Intel upstream at `/home/test/sufiyan/scenescape` (`origin/main`)

### 20.1 Phase 1: Bug Fixes and Code Cleanup

| ID | File | Change | Motivation |
|----|------|--------|------------|
| UP-1 | `moving_object.py:21` | `np.RankWarning` → `getattr(np.exceptions, 'RankWarning', None) or np.RankWarning` | Forward-compatible with NumPy 2.x (which moved `RankWarning` to `np.exceptions`) while still working on NumPy 1.26.4. Intel upstream uses `np.exceptions.RankWarning` directly; we adapted for broader compatibility. |
| UP-2 | `detections_builder.py:99` | Added `len(aobj.vectors) > 0` guard before `aobj.vectors[0]` access | Prevents `IndexError` when a tracked object has an empty vectors list (e.g., suspended track that lost all detection vectors). |
| UP-3 | `TrackManager.cpp` | Removed `#include <iostream>` and four `std::cout` lines from `updateTrackerConfig()` | Removes C++ debug prints that polluted container logs on every frame rate update. |
| UP-4 | `ObjectMatching.cpp` | Removed standalone `#include <iostream>` | Unused include cleanup. |
| UP-5 | `gated_hungarian_bigraph_matcher.hpp` | `std::bind1st(compare_fun_, cost_thresh_)` → `[this](T value) { return compare_fun_(cost_thresh_, value); }` | `std::bind1st` removed in C++17. Required for the CMake C++17 upgrade (Phase 4). |
| UP-6 | `observability/metrics.py:177` | Added `self.counter_add(instrument["name"], 0)` after counter creation | Initializes OTel counters to zero at startup so dashboards show metrics immediately, not only after first increment. |

### 20.2 Phase 2: Dependency Update

| ID | File | Change | Motivation |
|----|------|--------|------------|
| UP-7 | `requirements-runtime.txt` | `orjson` `3.11.3` → `3.11.5` | Bug fixes and performance improvements in the JSON serialization library. |

### 20.3 Phase 3: New Features (Additive, Flag-Gated)

#### 20.3.1 ControllerMode Singleton

New file: `controller/src/controller/controller_mode.py`

```python
class ControllerMode:
  _initialized = False
  _analytics_only = False

  @classmethod
  def initialize(cls, analytics_only=False): ...

  @classmethod
  def isAnalyticsOnly(cls): ...
```

Static namespace providing a global mode flag. All downstream code checks
`ControllerMode.isAnalyticsOnly()` to decide whether to run the tracker or consume
pre-tracked scene data from an upstream controller. Defaults to `False` (tracker enabled).

**Worker process note**: Worker processes spawned via `ProcessPoolExecutor` do not inherit
the main process class state. `isAnalyticsOnly()` returns `False` (correct default behavior)
without logging warnings in worker contexts.

#### 20.3.2 HTTP Healthcheck Endpoint

| File | Change |
|------|--------|
| `controller-cmd` | New `HealthCheckHandler` class (BaseHTTPRequestHandler), `start_health_server()` function, `--healthcheck_port` CLI arg (env: `CONTROLLER_HEALTHCHECK_PORT`, default `0` = disabled) |

Returns HTTP 200 on `/healthz`. Runs on a daemon thread when port > 0. Provides
Kubernetes liveness/readiness probe support independent of MQTT connectivity.

#### 20.3.3 Analytics-Only Mode

Allows a downstream controller to receive already-tracked objects from an upstream controller
via MQTT scene data topics, then process events (tripwires, regions) and publish without
running its own tracker. Enables a federated analytics architecture.

| File | Change |
|------|--------|
| `controller-cmd` | `--analytics-only` CLI arg (env: `CONTROLLER_ENABLE_ANALYTICS_ONLY`), `ControllerMode.initialize()` call |
| `scene.py` | Gate `_setTracker()` with `if not ControllerMode.isAnalyticsOnly()`; new `updateTrackedObjects()`, `getTrackedObjects()`, `_deserializeTrackedObjects()` methods; `tracked_objects_cache`, `object_history_cache` attributes; early returns in `processCameraData()` and `_finishProcessing()` |
| `scene_controller.py` | Gate `extractTrackerConfigData()`, `publishSceneDetections()`, `publishRegulatedDetections()` with mode checks; new `handleSceneDataMessage()` method; subscribe to `DATA_SCENE` instead of `DATA_CAMERA` in analytics-only mode; null-check `scene.tracker is not None` in `updateObjectClasses()` |

**Safety**: All analytics-only code paths are gated by `ControllerMode.isAnalyticsOnly()`.
In default mode (our production configuration), zero new code executes.

#### 20.3.4 ReID Configuration Pipeline

Plumbs a `reid_config_data` parameter from CLI through the entire initialization chain:

```
controller-cmd (--reid_config_file)
  → SceneController (self.reid_config_data)
    → CacheManager (reid_config_data={})
      → Scene (reid_config_data=None)
        → IntelLabsTracking / TimeChunkedIntelLabsTracking (reid_config_data)
          → Tracking (reid_config_data)
            → UUIDManager (reid_config_data)
```

| File | Change |
|------|--------|
| `controller-cmd` | `--reid_config_file` argument added |
| `scene_controller.py` | `extractReidConfigData()` method, `self.reid_config_data` attribute |
| `cache_manager.py` | `reid_config_data={}` parameter, propagated in `refreshScenes()` |
| `scene.py` | `reid_config_data=None` constructor param, passed to `_setTracker()` |
| `tracking.py` | `reid_config_data=None` in `__init__()`, passed to `UUIDManager` |
| `ilabs_tracking.py` | `reid_config_data=None` param, stored and forwarded to `super()` |
| `time_chunking.py` | `reid_config_data=None` param, forwarded to per-category trackers |
| `uuid_manager.py` | `reid_config_data=None` param, stored as `self.reid_config_data` |

New file: `config/reid-config.json` — default ReID configuration template.

**Status**: The `--reid_config_file` argument is defined but not yet wired to `SceneController`
constructor (matches Intel upstream). This is scaffolding for future ReID pipeline activation.

#### 20.3.5 Semantic ReID Refactor

Restructures ReID data from a flat embedding vector to a structured dict, supporting
multi-model ReID and semantic metadata (age, gender, clothing color).

**MovingObject changes** (`moving_object.py`):

| Before | After |
|--------|-------|
| `self.reidVector = None` (flat ndarray) | `self.reid = {}` (dict: `{embedding_vector, model_name}`) |
| N/A | `self.metadata = {}` (semantic attributes dict) |
| `_decodeReIDVector()` handles base64 only | Handles both new dict format and legacy base64/list format |

Backward-compatible `@property` preserves existing callers:

```python
@property
def reidVector(self):
    return self.reid.get('embedding_vector', None)
```

This property is used by `uuid_manager.py` (6 call sites) which still references
`sscape_object.reidVector` for feature gathering and similarity queries.

**Detection output changes** (`detections_builder.py`):

| Before | After |
|--------|-------|
| `obj_dict['reid'] = aobj.reidVector` | `obj_dict['metadata']['reid'] = aobj.reid` |

ReID data now nested under `metadata` key alongside other semantic attributes.

**Database API rename**:

| File | Before | After |
|------|--------|-------|
| `reid.py` | `addEntry(gid, track_id, category, reid_vectors)` | `addEntry(gid, track_id, category, reid_vectors, **metadata)` |
| `reid.py` | `findSimilarityScores(category, reid_vectors)` | `findMatches(category, reid_vectors, **constraints)` |
| `vdms_adapter.py` | Same rename as above | Same rename as above |
| `uuid_manager.py:194` | `self.reid_database.findSimilarityScores(...)` | `self.reid_database.findMatches(...)` |

**Schema update** (`metadata.schema.json`):

New definitions: `semantic_metadata_attribute` (label, confidence, model_name),
`semantic_metadata` (extensible dict), and `metadata` field added to `detection` definition.

### 20.4 Phase 4: C++ Build Modernization

| ID | File | Change | Motivation |
|----|------|--------|------------|
| UP-8 | `CMakeLists.txt` | `cmake_minimum_required` 3.8 → 3.21; `CXX_STANDARD` 14 → 17; modern imported targets (`Eigen3::Eigen`, `opencv::opencv`, `OpenMP::OpenMP_CXX`); `CMAKE_CURRENT_SOURCE_DIR` usage; conditional `BUILD_PYTHON_BINDINGS` option | Modern CMake practices, C++17 required for `std::bind1st` removal (UP-5). |
| UP-9 | `cmake/security_options.cmake` | **New file**: `scenescape::security_options` INTERFACE target with hardening flags (skipped in Debug) | Reusable security hardening module. |
| UP-10 | `cmake/opencv.cmake` | **New file**: `opencv::opencv` INTERFACE target normalizing inconsistent OpenCV CMake interfaces | Handles `opencv_world` vs `OpenCV_LIBS` variants across installations. |
| UP-11 | `robot_vision/Makefile` | New `cpp-tests` target: `-DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=OFF` + CTest | Standalone C++ unit testing without Python/pybind11 dependencies. |

### 20.5 Deployment Fix

| ID | File | Change | Motivation |
|----|------|--------|------------|
| UP-12 | `kubernetes/Makefile:110` | `sudo -v` → `sudo -n true` | `sudo -v` requires a TTY for password prompts. `sudo -n true` works in non-interactive shells (CI, scripted builds). |

### 20.6 Deployment Verification (Live Cluster)

All changes verified on the running 26-camera deployment:

| Check | Result |
|-------|--------|
| Controller pod status | Running 1/1, no restarts |
| Time chunking enabled | `SETTING TRACKER TYPE time_chunked_intel_labs` for all 5 scenes |
| Early dispatch working | Tracker threads at ~9.5 dispatches/sec (exceeds 5 FPS timer ceiling, confirming event-driven early dispatch) |
| No drift warnings | Queue sizes 0 across all tracker threads |
| Zero drops | `ASYNC_PUBLISH_STATS: drops=0, failures=0` |
| Default mode behavior | All `ControllerMode.isAnalyticsOnly()` checks return `False`, no analytics-only code executes |
| C++ tracker | PROFILE_HUNGARIAN output confirms 100+ tracks per batch (multi-camera scene batching) |
| cam7/cam9 fix | Separate issue: test DLStreamer image replaced with production image, both now Running 1/1 |

### 20.7 Explicitly Not Ported

| Intel Commit | Reason |
|--------------|--------|
| `8d8eb2a9` Debian base image | We use Ubuntu 24.04 with Nokia registry |
| `9fe7f2e5` Time-based config params | Our `time_chunking.py` computes time values at parse time; config format change adds no value |
| `48e6a0d0` Dockerfile dependency mgmt | Dockerfile-only, our Dockerfile is different |
| `e1aa04ad` Trivy scan fixes | Dockerfile-only |
| `e271176c` RUNTIME_OS_IMAGE | Makefile-only, our build system is different |

### 20.8 Files Added/Modified (Upstream Integration Only)

| File | Action | Phase | Category |
|------|--------|-------|----------|
| `src/controller/controller_mode.py` | **New** | 3 | Analytics-only mode |
| `src/robot_vision/cmake/security_options.cmake` | **New** | 4 | C++ build |
| `src/robot_vision/cmake/opencv.cmake` | **New** | 4 | C++ build |
| `config/reid-config.json` | **New** | 3 | ReID config |
| `src/controller/moving_object.py` | Modified | 1, 3 | RankWarning fix + semantic ReID |
| `src/controller/detections_builder.py` | Modified | 1, 3 | Empty vectors guard + ReID output |
| `src/controller/scene.py` | Modified | 3 | Analytics-only + ReID config |
| `src/controller/scene_controller.py` | Modified | 3 | Analytics-only + ReID config |
| `src/controller/tracking.py` | Modified | 3 | ReID config plumbing |
| `src/controller/ilabs_tracking.py` | Modified | 3 | ReID config plumbing |
| `src/controller/time_chunking.py` | Modified | 3 | ReID config plumbing |
| `src/controller/cache_manager.py` | Modified | 3 | ReID config plumbing |
| `src/controller/uuid_manager.py` | Modified | 3 | ReID config + findMatches rename |
| `src/controller/reid.py` | Modified | 3 | API rename + metadata params |
| `src/controller/vdms_adapter.py` | Modified | 3 | API rename + metadata params |
| `src/controller-cmd` | Modified | 3 | Healthcheck + analytics-only + ReID args |
| `src/controller/observability/metrics.py` | Modified | 1 | OTel counter init |
| `src/schema/metadata.schema.json` | Modified | 3 | Semantic metadata definitions |
| `src/robot_vision/CMakeLists.txt` | Modified | 4 | CMake 3.21, C++17 |
| `src/robot_vision/Makefile` | Modified | 4 | cpp-tests target |
| `src/robot_vision/include/rv/apollo/gated_hungarian_bigraph_matcher.hpp` | Modified | 1 | bind1st → lambda |
| `src/robot_vision/src/rv/tracking/TrackManager.cpp` | Modified | 1 | Remove debug prints |
| `src/robot_vision/src/rv/tracking/ObjectMatching.cpp` | Modified | 1 | Remove unused include |
| `requirements-runtime.txt` | Modified | 2 | orjson bump |
| `kubernetes/Makefile` | Modified | Deploy | sudo -n true |
