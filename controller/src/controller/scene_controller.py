# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

import faulthandler
import orjson
import os
import queue
import threading
import time
from collections import defaultdict
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import ntplib

# Enable faulthandler for debugging stalls (prints traceback on SIGSEGV/SIGFPE/SIGABRT)
faulthandler.enable()

from controller.cache_manager import CacheManager
from controller.child_scene_controller import ChildSceneController
from controller.detections_builder import (buildDetectionsDict,
                                           buildDetectionsList,
                                           computeCameraBounds)
from controller.scene import Scene
from scene_common import log
from scene_common.geometry import Point, Region, Tripwire
from scene_common.mqtt import PubSub
from scene_common.schema import SchemaValidation
from scene_common.timestamp import adjust_time, get_epoch_time, get_iso_time
from scene_common.transform import applyChildTransform
from controller.observability import metrics
from controller.time_chunking import DEFAULT_CHUNKING_INTERVAL_MS
AVG_FRAMES = 100

# Dynamic worker allocation: one ProcessPoolExecutor per scene, created on-demand.
# Architectural invariant: Each scene's tracker state must be owned by a single worker process
# to prevent cross-process state corruption. Workers are created when scenes appear and
# shut down when scenes are removed. No manual worker count tuning required.
def _validated_env_int(name, default, minimum=0):
  """Read an integer environment variable with validation."""
  raw = os.environ.get(name, str(default))
  try:
    value = int(raw)
  except ValueError:
    log.warning(f"[CONFIG] Invalid {name}={raw!r}, using default {default}")
    return default
  if value < minimum:
    log.warning(f"[CONFIG] {name}={value} below minimum {minimum}, using {minimum}")
    return minimum
  return value

# Maximum worker processes (0 = no cap, workers scale with scene count).
# Each scene gets exactly one dedicated worker process.
DEFAULT_MAX_WORKER_PROCESSES = _validated_env_int('CONTROLLER_MAX_WORKERS', 0, minimum=0)

# Async MQTT publish configuration
# Bounded queue prevents memory issues under sustained load
ASYNC_PUBLISH_QUEUE_SIZE = _validated_env_int('CONTROLLER_ASYNC_PUBLISH_QUEUE_SIZE', 1000, minimum=1)
# Enable/disable async publish (allows reverting via env var)
ASYNC_PUBLISH_ENABLED = os.environ.get('CONTROLLER_ASYNC_PUBLISH_ENABLED', 'true').lower() == 'true'

# Monitoring thresholds (module-level constants for tuning without code changes)
WATCHDOG_CHECK_INTERVAL_SECS = 30.0
STALENESS_CLEANUP_INTERVAL_SECS = 60.0
PUBLISH_QUEUE_HIGH_WATER_RATIO = 0.8
SLOW_PUBLISH_THRESHOLD_MS = 50
CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 10
HEALTH_LOG_INTERVAL_SECS = 30.0

# --- Multiprocessing worker functions (module-level for picklability) ---
_worker_controller = None

def _init_worker_process(config):
  """Initializer for ProcessPoolExecutor workers. Creates a process-local SceneController."""
  global _worker_controller
  _worker_controller = SceneController(**config, _is_worker=True)
  log.info(f"Worker process {os.getpid()} initialized")

def _worker_handle_message(topic_str, payload, t_callback_enter):
  """Entry point for message processing in worker process."""
  return _worker_controller._processMovingObjectMessage(topic_str, payload, t_callback_enter)


class SceneController:

  def __init__(self, rewrite_bad_time, rewrite_all_time, max_lag, mqtt_broker,
               mqtt_auth, rest_url, rest_auth, client_cert, root_cert, ntp_server,
               tracker_config_file, schema_file, visibility_topic, data_source,
               _is_worker=False):
    self._is_worker = _is_worker
    self.cert = client_cert
    self.root_cert = root_cert
    self.rewrite_bad_time = rewrite_bad_time
    self.rewrite_all_time = rewrite_all_time
    self.max_lag = max_lag
    self._startup_time = time.time()
    self._startup_grace_sec = float(os.environ.get('CONTROLLER_STARTUP_GRACE_SEC', '5.0'))
    self.regulate_cache = {}
    self.broker = mqtt_broker
    self.mqtt_auth = mqtt_auth
    # Save constructor args needed by _build_worker_config()
    self._rest_url = rest_url
    self._rest_auth = rest_auth
    self._schema_file = schema_file
    self._data_source = data_source
    self.tracker_config_data = {}
    self.tracker_config_file = tracker_config_file
    if tracker_config_file is not None:
      self.extractTrackerConfigData(tracker_config_file)

    self.last_time_sync = None
    self.ntp_server = ntp_server
    self.ntp_client = ntplib.NTPClient()
    self.time_offset = 0

    # Initialize regulate rate tracking (used by calculateRate)
    self.regulate_last = None
    self.regulate_rate = 1.0

    self.schema_val = SchemaValidation(schema_file)

    self.pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
    if not _is_worker:
      self.pubsub.onConnect = self.onConnect
    self.pubsub.connect()
    if _is_worker:
      self.pubsub.loopStart()

    self.cache_manager = CacheManager(data_source, rest_url, rest_auth, root_cert, self.tracker_config_data)

    # Start background cache refresh for both main process and workers,
    # instead of blocking on-demand refreshes.
    self.cache_manager.startPeriodicRefresh()
    # Do an immediate synchronous refresh so the cache is populated before
    # any messages arrive (avoids UNKNOWN SENDER on first messages).
    self.cache_manager.checkRefresh()

    if _is_worker:
      self._initWorkerState()

    self.visibility_topic = visibility_topic
    log.info(f"Publishing camera visibility info on {self.visibility_topic} topic.")

    self._ntp_sync_lock = threading.Lock()  # Protects NTP time_offset/last_time_sync state
    # Lock for thread-safe MQTT publish operations.
    # Paho MQTT client is NOT thread-safe for concurrent publish() calls.
    # Without this lock, SSL connection corrupts under high load (8+ cameras)
    self._publish_lock = threading.Lock()
    # Lock to serialize database update operations (handleDatabaseMessage, onConnect)
    # These run on background threads and must not overlap
    self._db_update_lock = threading.Lock()

    # Dynamic worker allocation: one executor per scene, created on-demand.
    # Protected by _scene_executor_lock for all reads/writes.
    self._scene_executors = {}        # {scene_uid: ProcessPoolExecutor}
    self._scene_executor_lock = threading.Lock()
    self._max_workers = DEFAULT_MAX_WORKER_PROCESSES  # 0 = unlimited
    self._worker_crashes = 0
    self._worker_crashes_lock = threading.Lock()
    self._route_log_count = 0
    self._mp_ctx = multiprocessing.get_context("spawn")
    self._worker_config = self._build_worker_config()

    # Async MQTT publish: dedicated thread with bounded queue
    # Removes publish latency from worker critical path
    self._async_publish_enabled = ASYNC_PUBLISH_ENABLED
    if self._async_publish_enabled:
      self._publish_queue = queue.Queue(maxsize=ASYNC_PUBLISH_QUEUE_SIZE)
      self._publish_shutdown = threading.Event()
      self._publish_thread = threading.Thread(
          target=self._publish_thread_loop,
          name="AsyncPublishThread",
          daemon=True
      )
      self._publish_thread.start()
      self._publish_queue_drops = 0  # Counter for monitoring
      log.info(f"Async MQTT publish enabled (queue_size={ASYNC_PUBLISH_QUEUE_SIZE})")
    else:
      self._publish_queue = None
      log.info("Async MQTT publish disabled (sync mode)")

    # Semaphore-based admission control
    # Bounds total in-flight work to prevent queue buildup and high queue_ms latency
    # Set to expected max cameras - prevents unbounded queue growth
    MAX_INFLIGHT_MESSAGES = _validated_env_int('CONTROLLER_MAX_INFLIGHT', 20, minimum=1)
    self._inflight_semaphore = threading.Semaphore(MAX_INFLIGHT_MESSAGES)

    # Overwrite-based freshness buffer to prevent backlog accumulation.
    # Architectural invariant: At most 1 pending frame per camera (latest wins).
    self._latest_frame = {}           # {camera_id: (topic_str, payload, t_callback_enter)}
    self._latest_frame_lock = threading.Lock()
    self._pending_work = {}           # {camera_id: Future} - track in-flight work
    self._pending_work_lock = threading.Lock()

    if not _is_worker:
      self._initMainProcessState()
    else:
      log.info(f"Worker process {os.getpid()} SceneController initialized (publish-only mode)")
    return

  def _initMainProcessState(self):
    """Initialize monitoring threads and watchdogs for the main (non-worker) process.

    Starts the publish watchdog and staleness cleanup background threads.
    Must only be called in the main process, not in worker processes.
    """
    # Workers are created on-demand; no fixed pool at startup.
    log.info(f"Dynamic worker allocation enabled (max_workers={self._max_workers or 'unlimited'})")

    # Monitoring threads detect dead-but-alive stalls where threads stop
    # processing but the process continues running.
    self._monitoring_shutdown = threading.Event()

    # Async publish thread watchdog: detects and restarts stuck publish threads
    # to prevent silent data loss. Main process only — workers cannot directly
    # share publish thread state across process boundaries.
    if ASYNC_PUBLISH_ENABLED:
      self._publish_watchdog_thread = threading.Thread(
          target=self._publish_watchdog_loop,
          name="PublishWatchdog",
          daemon=True
      )
      self._publish_watchdog_thread.start()
      log.info("Async publish watchdog started")

    # Staleness cleanup: periodically removes orphaned _pending_work entries
    # to prevent memory leaks from futures that completed without cleanup.
    self._staleness_cleanup_thread = threading.Thread(
        target=self._staleness_cleanup_loop,
        name="StalenessCleanup",
        daemon=True
    )
    self._staleness_cleanup_thread.start()
    log.info("Pending work staleness cleanup started")

  def _initWorkerState(self):
    """Initialize state needed only in worker processes.

    Loads scenes and Object Library class settings from cache, then subscribes
    to database update notifications so runtime Object Library changes are
    propagated to this worker process.
    """
    # Workers run in separate processes (multiprocessing.spawn) and need their own
    # copy of the module-level object_classes dict.
    self.scenes = self.cache_manager.allScenes()
    self.updateObjectClasses()
    # Subscribe to database updates so Object Library changes at runtime
    # are propagated to this worker process.
    topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    self.pubsub.addCallback(topic, self._workerHandleDatabaseMessage)
    log.info(f"[WORKER_INIT] pid={os.getpid()} object_classes loaded, subscribed to {topic}")

  def _build_worker_config(self):
    """Return a picklable dict of constructor args for worker process initialization."""
    return {
      'rewrite_bad_time': self.rewrite_bad_time,
      'rewrite_all_time': self.rewrite_all_time,
      'max_lag': self.max_lag,
      'mqtt_broker': self.broker,
      'mqtt_auth': self.mqtt_auth,
      'rest_url': self._rest_url,
      'rest_auth': self._rest_auth,
      'client_cert': self.cert,
      'root_cert': self.root_cert,
      'ntp_server': self.ntp_server,
      'tracker_config_file': self.tracker_config_file,
      'schema_file': self._schema_file,
      'visibility_topic': self.visibility_topic,
      'data_source': self._data_source,
    }

  def _get_or_create_executor(self, scene_uid):
    """Get executor for scene, creating one if needed.

    Called from background threads (_databaseUpdateAsync, _onConnectAsync)
    and from _get_executor_for_scene on MQTT thread (lazy fallback).
    Thread-safe via _scene_executor_lock.

    Returns (executor, created) tuple. created=True if new executor was spawned.
    Returns (None, False) if max_workers cap reached.
    """
    with self._scene_executor_lock:
      if scene_uid in self._scene_executors:
        return self._scene_executors[scene_uid], False

      # Check cap
      if self._max_workers > 0 and len(self._scene_executors) >= self._max_workers:
        log.warning(f"[WORKER_CAP] Cannot create worker for scene={scene_uid}, "
                    f"at max_workers={self._max_workers}")
        return None, False

      executor = ProcessPoolExecutor(
          max_workers=1,
          mp_context=self._mp_ctx,
          initializer=_init_worker_process,
          initargs=(self._worker_config,)
      )
      self._scene_executors[scene_uid] = executor
      log.info(f"[WORKER_CREATED] scene={scene_uid}, total_workers={len(self._scene_executors)}")
      return executor, True

  def _get_executor_for_scene(self, scene_uid):
    """Get executor for scene. Lazy-creates if not yet created (startup race).

    Returns None if scene_uid is None or cap reached.
    """
    if scene_uid is None:
      return None
    with self._scene_executor_lock:
      executor = self._scene_executors.get(scene_uid)
    if executor is not None:
      return executor
    # Lazy creation for startup race (messages arrive before _sync_workers_to_scenes)
    executor, _ = self._get_or_create_executor(scene_uid)
    return executor

  def _sync_workers_to_scenes(self):
    """Create workers for new scenes, shut down workers for removed scenes.

    Called from background thread (holds _db_update_lock). Safe to spawn processes here.
    """
    current_scene_uids = {scene.uid for scene in self.scenes}

    # Create workers for new scenes
    for uid in current_scene_uids:
      self._get_or_create_executor(uid)

    # Shut down workers for removed scenes
    with self._scene_executor_lock:
      removed = set(self._scene_executors.keys()) - current_scene_uids
      for uid in removed:
        executor = self._scene_executors.pop(uid)
        log.info(f"[WORKER_REMOVED] scene={uid}, shutting down executor")
        # Non-blocking shutdown — let pending work finish
        executor.shutdown(wait=False, cancel_futures=False)

    log.info(f"[WORKER_SYNC] active_workers={len(self._scene_executors)}, "
             f"scenes={len(current_scene_uids)}")

  def _recreate_scene_executor(self, scene_uid):
    """Recreate executor for a scene after crash."""
    with self._scene_executor_lock:
      old_executor = self._scene_executors.get(scene_uid)
      if old_executor:
        try:
          old_executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
          log.warning(f"[WORKER_RECREATE_SHUTDOWN_ERROR] scene={scene_uid}, error={e}")

      new_executor = ProcessPoolExecutor(
          max_workers=1,
          mp_context=self._mp_ctx,
          initializer=_init_worker_process,
          initargs=(self._worker_config,)
      )
      self._scene_executors[scene_uid] = new_executor
    log.info(f"[WORKER_RECOVERED] scene={scene_uid}")
    return new_executor

  def _publish_watchdog_loop(self):
    """Monitor async publish thread health and restart if dead.

    Checks every 30 seconds if the publish thread is alive. If dead, attempts
    to restart it. This prevents silent publish thread death from causing
    permanent detection loss.
    """
    log.info("[WATCHDOG_PUBLISH] Publish watchdog thread started")
    check_interval = WATCHDOG_CHECK_INTERVAL_SECS

    while not self._monitoring_shutdown.is_set():
      try:
        time.sleep(check_interval)

        if not self._publish_thread.is_alive():
          log.error("[WATCHDOG_PUBLISH_DEAD] Async publish thread is dead, attempting restart")

          # Attempt to restart the publish thread
          self._publish_thread = threading.Thread(
              target=self._publish_thread_loop,
              name="AsyncPublish",
              daemon=True
          )
          self._publish_thread.start()
          log.info("[WATCHDOG_PUBLISH_RESTART] Async publish thread restarted")
        else:
          # Thread is alive - log periodic health check
          qsize = self._publish_queue.qsize() if self._publish_queue else 0
          log.debug(f"[WATCHDOG_PUBLISH_OK] Async publish thread alive, queue_depth={qsize}")

      except Exception as e:
        log.error(f"[WATCHDOG_PUBLISH_ERROR] Watchdog error: {type(e).__name__}: {e}")

    log.info("[WATCHDOG_PUBLISH] Publish watchdog thread exiting")

  def _staleness_cleanup_loop(self):
    """Periodic cleanup of stale _pending_work entries to prevent memory leak.

    Scans _pending_work every 60 seconds for futures that are done but were
    never cleaned up (leaked due to exception in cleanup path). Releases any
    leaked resources and logs warnings.
    """
    log.info("[WATCHDOG_STALENESS] Staleness cleanup thread started")
    check_interval = STALENESS_CLEANUP_INTERVAL_SECS

    while not self._monitoring_shutdown.is_set():
      try:
        time.sleep(check_interval)

        stale_cameras = []
        with self._pending_work_lock:
          for camera_id, future in list(self._pending_work.items()):
            if future.done():
              # This future completed but _handle_work_complete failed to clean up.
              # The semaphore was already released by _handle_work_complete (its first action),
              # so we only clean the dict entry here — do NOT release semaphore again.
              stale_cameras.append(camera_id)
              del self._pending_work[camera_id]

        if stale_cameras:
          log.warning(f"[WATCHDOG_STALENESS_CLEANUP] Cleaned up {len(stale_cameras)} stale pending_work entries: {stale_cameras}")
        else:
          log.debug(f"[WATCHDOG_STALENESS_OK] No stale entries found, pending_work_size={len(self._pending_work)}")

      except Exception as e:
        log.error(f"[WATCHDOG_STALENESS_ERROR] Staleness cleanup error: {type(e).__name__}: {e}")

    log.info("[WATCHDOG_STALENESS] Staleness cleanup thread exiting")

  def shutdown(self):
    """Gracefully shutdown the controller and its worker processes."""
    log.info("Shutting down SceneController...")

    # Stop monitoring threads first to prevent false alarms during shutdown.
    if hasattr(self, '_monitoring_shutdown'):
      self._monitoring_shutdown.set()
      log.info("Monitoring threads shutdown signal sent")

    # Stop periodic cache refresh thread before shutting down executors.
    # Must stop before iterating cached_scenes_by_uid to prevent concurrent modification.
    if hasattr(self, 'cache_manager'):
      self.cache_manager.stopPeriodicRefresh()

    # Shutdown async publish thread (drain queue)
    if hasattr(self, '_publish_queue') and self._publish_queue is not None:
      self._publish_shutdown.set()
      self._publish_thread.join(timeout=5.0)
      remaining = self._publish_queue.qsize()
      if remaining > 0:
        log.warning(f"Async publish shutdown with {remaining} messages undelivered")
      log.info("Async publish thread shutdown complete")

    # Collect executors under lock, shutdown outside lock.
    # executor.shutdown(wait=True) blocks until worker finishes — must not hold lock during wait.
    if hasattr(self, '_scene_executors'):
      with self._scene_executor_lock:
        executors_to_shutdown = list(self._scene_executors.items())
        self._scene_executors.clear()
      for scene_uid, executor in executors_to_shutdown:
        executor.shutdown(wait=True, cancel_futures=False)
        log.info(f"Worker executor for scene={scene_uid} shutdown complete")

    # Shutdown tracker threads (each Scene has its own tracker with per-category threads).
    # Cache refresh thread is already stopped, so cached_scenes_by_uid is stable.
    if hasattr(self, 'cache_manager') and hasattr(self.cache_manager, 'cached_scenes_by_uid'):
      scenes = self.cache_manager.cached_scenes_by_uid
      if scenes is not None:
        for scene in scenes.values():
          if hasattr(scene, 'tracker'):
            log.info(f"Shutting down tracker threads for scene {scene.name}")
            scene.tracker.join()
            log.info(f"Tracker threads shutdown complete for scene {scene.name}")
    return

  def _publish_thread_loop(self):
    """Dedicated thread for async MQTT publishing.

    Drains _publish_queue and publishes messages. This removes publish latency
    from the worker critical path. Uses _publish_lock for thread-safe Paho access.
    """
    log.info(f"Async publish thread started (pid={os.getpid()})")
    messages_published = 0
    publish_failures = 0
    consecutive_failures = 0
    last_log_time = time.time()
    last_health_log = time.time()
    queue_size_threshold = int(ASYNC_PUBLISH_QUEUE_SIZE * PUBLISH_QUEUE_HIGH_WATER_RATIO)

    while not self._publish_shutdown.is_set():
      try:
        # Block with timeout to allow shutdown check
        topic, payload = self._publish_queue.get(timeout=0.1)
        t_dequeue = time.time_ns()

        # Check queue depth and warn if approaching capacity
        qsize = self._publish_queue.qsize()
        if qsize > queue_size_threshold:
          log.warning(f"[MQTT_QUEUE_HIGH] depth={qsize}/{ASYNC_PUBLISH_QUEUE_SIZE} ({qsize*100//ASYNC_PUBLISH_QUEUE_SIZE}% full)")

        with self._publish_lock:
          self.pubsub.publish(topic, payload)

        t_published = time.time_ns()
        publish_ms = (t_published - t_dequeue) / 1e6
        messages_published += 1
        consecutive_failures = 0  # Reset on success

        # Log stats every 10 seconds
        now = time.time()
        if now - last_log_time > 10.0:
          log.info(f"[ASYNC_PUBLISH_STATS] published={messages_published}, queue_depth={qsize}, drops={self._publish_queue_drops}, failures={publish_failures}")
          last_log_time = now

        # Log health check every 30 seconds
        if now - last_health_log > HEALTH_LOG_INTERVAL_SECS:
          mqtt_connected = self.pubsub.client.is_connected() if hasattr(self.pubsub.client, 'is_connected') else True
          log.info(f"[MQTT_HEALTH] connected={mqtt_connected}, queue={qsize}/{ASYNC_PUBLISH_QUEUE_SIZE}, consecutive_failures={consecutive_failures}")
          last_health_log = now

        # Log slow publishes
        if publish_ms > SLOW_PUBLISH_THRESHOLD_MS:
          log.warning(f"[ASYNC_PUBLISH_SLOW] publish_ms={publish_ms:.1f}")

        self._publish_queue.task_done()
      except queue.Empty:
        continue
      except Exception as e:
        publish_failures += 1
        consecutive_failures += 1
        log.error(f"[ASYNC_PUBLISH_ERROR] error={type(e).__name__}: {e}, consecutive_failures={consecutive_failures}")

        # Alert on sustained failure pattern (likely MQTT disconnection)
        if consecutive_failures >= CONSECUTIVE_FAILURE_ALERT_THRESHOLD:
          log.error(f"[MQTT_CONNECTION_CRITICAL] {consecutive_failures} consecutive publish failures - MQTT broker may be unreachable")

        # Still task_done to prevent queue deadlock
        self._publish_queue.task_done()

    # Drain remaining on shutdown
    log.info("Async publish thread draining queue...")
    while not self._publish_queue.empty():
      try:
        topic, payload = self._publish_queue.get_nowait()
        with self._publish_lock:
          self.pubsub.publish(topic, payload)
        self._publish_queue.task_done()
      except queue.Empty:
        break
      except Exception as e:
        log.error(f"[ASYNC_PUBLISH_DRAIN_ERROR] {e}")

    log.info(f"Async publish thread exiting (total published={messages_published})")

  def _async_publish(self, topic, payload):
    """Queue a message for async publishing. Non-blocking, fire-and-forget.

    If async publish is disabled or queue is full, falls back to sync publish.
    Returns immediately - does not wait for actual MQTT publish.
    """
    if not self._async_publish_enabled or self._publish_queue is None:
      # Fallback to sync publish
      with self._publish_lock:
        self.pubsub.publish(topic, payload)
      return

    try:
      self._publish_queue.put_nowait((topic, payload))
    except queue.Full:
      # Queue overflow - log and fall back to sync publish
      self._publish_queue_drops += 1
      if self._publish_queue_drops % 100 == 1:  # Log every 100th drop
        log.warning(f"[ASYNC_PUBLISH_DROP] queue full, total_drops={self._publish_queue_drops}")
      # Sync fallback to ensure delivery
      with self._publish_lock:
        self.pubsub.publish(topic, payload)

  def extractTrackerConfigData(self, tracker_config_file):
    if not os.path.exists(tracker_config_file) and not os.path.isabs(tracker_config_file):
      script = os.path.realpath(__file__)
      tracker_config_file = os.path.join(os.path.dirname(script), tracker_config_file)
    with open(tracker_config_file) as json_file:
      tracker_config = orjson.loads(json_file.read())
      baseline_fps = tracker_config["baseline_frame_rate"]
      self.tracker_config_data["baseline_frame_rate"] = baseline_fps
      self.tracker_config_data["max_unreliable_time"] = tracker_config["max_unreliable_frames"] / baseline_fps
      self.tracker_config_data["non_measurement_time_dynamic"] = tracker_config["non_measurement_frames_dynamic"] / baseline_fps
      self.tracker_config_data["non_measurement_time_static"] = tracker_config["non_measurement_frames_static"] / baseline_fps
      self._extractTimeChunkingEnabled(tracker_config)
      self._extractTimeChunkingInterval(tracker_config)
      self.tracker_config_data["suspended_track_timeout_secs"] = tracker_config.get("suspended_track_timeout_secs", 60.0)

      if "persist_attributes" in tracker_config:
        if isinstance(tracker_config["persist_attributes"], dict):
          self.tracker_config_data["persist_attributes"] = tracker_config["persist_attributes"]
        else:
          log.error("Invalid persist_attributes format in tracker config file")
          self.tracker_config_data["persist_attributes"] = {}
    return

  def _extractTimeChunkingEnabled(self, tracker_config):
    """Extract and validate time_chunking_enabled flag"""
    if "time_chunking_enabled" not in tracker_config:
      log.warning("Time chunking enabled flag missing in tracker config file, disabling time chunking.")
      self.tracker_config_data["time_chunking_enabled"] = False
      return

    try:
      self.tracker_config_data["time_chunking_enabled"] = bool(tracker_config["time_chunking_enabled"])
      log.info(f"Time chunking enabled: {self.tracker_config_data['time_chunking_enabled']}")
    except (ValueError, TypeError):
      raise ValueError("Invalid value for time_chunking_enabled in tracker config file.")
    return

  def _extractTimeChunkingInterval(self, tracker_config):
    """Extract and validate time_chunking_interval_milliseconds."""
    if "time_chunking_interval_milliseconds" not in tracker_config:
      self.tracker_config_data["time_chunking_interval_milliseconds"] = DEFAULT_CHUNKING_INTERVAL_MS
      log.warning(f"Time chunking interval not specified in tracker config file, will use default interval of {DEFAULT_CHUNKING_INTERVAL_MS} ms.")
      return

    try:
      interval_int = int(tracker_config["time_chunking_interval_milliseconds"])
      if interval_int <= 0:
        raise ValueError("Time chunking interval must be positive.")
      self.tracker_config_data["time_chunking_interval_milliseconds"] = interval_int
      log.info(f"Time chunking interval (ms): {interval_int}")
    except (ValueError, TypeError):
      raise ValueError(f"Invalid value for time_chunking_interval_milliseconds in tracker config file")
    return

  def loopForever(self):
    try:
      return self.pubsub.loopForever()
    finally:
      self.shutdown()

  def publishDetections(self, scene, objects, ts, otype, jdata, camera_id):
    if not hasattr(scene, 'lastPubCount'):
      scene.lastPubCount = {}

    if not hasattr(scene, 'last_published_detection'):
      scene.last_published_detection = defaultdict(lambda: None)
    metric_attributes = {
      "camera": camera_id if camera_id is not None else "unknown",
      "category": otype,
      "scene": scene.name
    }
    metrics.record_object_count(len(objects), metric_attributes)
    self.publishSceneDetections(scene, objects, otype, jdata)
    self.publishRegulatedDetections(scene, objects, otype, jdata, camera_id)
    self.publishRegionDetections(scene, objects, otype, jdata)
    return

  def shouldPublish(self, last, now, max_delay):
    return last is None or now - last >= max_delay

  def publishSceneDetections(self, scene, objects, otype, jdata):
    t_start = time.time_ns()

    jdata['objects'] = buildDetectionsList(objects, scene, self.visibility_topic == 'unregulated')
    t_build = time.time_ns()

    olen = len(jdata['objects'])
    cid = scene.name + "/" + otype
    if olen > 0 or cid not in scene.lastPubCount or scene.lastPubCount[cid] > 0:
      if 'debug_hmo_start_time' in jdata:
        jdata['debug_hmo_processing_time'] = get_epoch_time() - jdata['debug_hmo_start_time']
      # Convert numpy types to native Python types for JSON serialization
      jstr = orjson.dumps(jdata, option=orjson.OPT_SERIALIZE_NUMPY)
      t_json = time.time_ns()

      new_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene.uid,
                                     thing_type=otype)
      self._async_publish(new_topic, jstr)
      t_mqtt = time.time_ns()

      self.publishExternalDetections(scene, otype, jstr)
      scene.lastPubCount[cid] = olen

      build_ms = (t_build - t_start) / 1e6
      json_ms = (t_json - t_build) / 1e6
      mqtt_ms = (t_mqtt - t_json) / 1e6
      log.debug(f"[PROFILE_PUB_SCENE] objs={olen}, build_ms={build_ms:.3f}, json_ms={json_ms:.3f}, mqtt_ms={mqtt_ms:.3f}")
    return

  def publishExternalDetections(self, scene, otype, jstr):
    now = get_epoch_time()
    if self.shouldPublish(scene.last_published_detection[otype], now, 1/scene.external_update_rate):
      scene.last_published_detection[otype] = get_epoch_time()
      scene_hierarchy_topic = PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=scene.uid,
                                                 thing_type=otype)
      self._async_publish(scene_hierarchy_topic, jstr)
    return

  def publishRegulatedDetections(self, scene_obj, msg_objects, otype, jdata, camera_id):
    update_rate = self.calculateRate()
    scene_uid = scene_obj.uid

    if scene_uid not in self.regulate_cache:
      self.regulate_cache[scene_uid] = {
        'objects': {},
        'rate': {},
        'last': None
      }
    scene = self.regulate_cache[scene_uid]
    scene['objects'][otype] = jdata['objects']
    if camera_id is not None:
      scene['rate'][camera_id] = jdata.get('rate', None)

    now = get_epoch_time()
    if self.shouldPublish(scene['last'], now, 1/scene_obj.regulated_rate):
      # If we're doing Regulated visibility, then we need to compute for all
      # the objects in the cache
      objects = []
      is_regulated = self.visibility_topic == 'regulated'

      msg_objects_lookup = {}
      if is_regulated:
        for obj in msg_objects:
          msg_objects_lookup[obj.gid] = obj

      for key in scene['objects']:
        for obj in scene['objects'][key]:
          if is_regulated:
            aobj = msg_objects_lookup.get(obj['id'], None)
            if aobj is not None:
              computeCameraBounds(scene_obj, aobj, obj)
          objects.append(obj)
      new_jdata = {
        'timestamp': jdata['timestamp'],
        'objects': objects,
        'id': jdata['id'],
        'name': jdata['name'],
        'scene_rate': round(1 / update_rate, 1),
        'rate': scene['rate'],
      }
      jstr = orjson.dumps(new_jdata, option=orjson.OPT_SERIALIZE_NUMPY)
      topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
      self._async_publish(topic, jstr)
      scene['last'] = now

    return

  def publishRegionDetections(self, scene, objects, otype, jdata):
    for rname in scene.regions:
      robjects = []
      for obj in objects:
        if rname in obj.chain_data.regions:
          robjects.append(obj)
      jdata['objects'] = buildDetectionsList(robjects, scene)
      olen = len(jdata['objects'])
      rid = scene.name + "/" + rname + "/" + otype
      if olen > 0 or rid not in scene.lastPubCount or scene.lastPubCount[rid] > 0:
        jstr = orjson.dumps(jdata, option=orjson.OPT_SERIALIZE_NUMPY)
        new_topic = PubSub.formatTopic(PubSub.DATA_REGION, scene_id=scene.uid,
                                       region_id=rname, thing_type=otype)
        self._async_publish(new_topic, jstr)
        scene.lastPubCount[rid] = olen
    return

  def publishEvents(self, scene, ts_str):
    for event_type in scene.events:
      for _, region in scene.events[event_type]:
        etype = None
        metadata = None

        if isinstance(region, Tripwire):
          etype = 'tripwire'
          metadata = region.serialize()

        elif isinstance(region, Region):
          etype = 'region'
          metadata = region.serialize()
          metadata['fromSensor'] = (region.singleton_type != None)

        event_data = {
          'timestamp': ts_str,
          'scene_id': scene.uid,
          'scene_name': scene.name,
          etype + '_id': region.uuid,
          etype + '_name': region.name,
        }
        detections_dict, num_objects = self._buildAllRegionObjsList(scene, region, event_data)
        self._buildEnteredObjsList(region, event_data, detections_dict)
        self._buildExitedObjsList(scene, region, event_data)

        log.debug("EVENT DATA", event_data)
        if hasattr(region, 'value'):
          event_data['value'] = region.value
        event_data['metadata'] = metadata
        if not isinstance(region, Tripwire) or num_objects > 0:
          event_topic = PubSub.formatTopic(PubSub.EVENT,
                                           region_type=etype, event_type=event_type,
                                           scene_id=scene.uid, region_id=region.uuid)
          self._async_publish(event_topic, orjson.dumps(event_data, option=orjson.OPT_SERIALIZE_NUMPY))

    self._clearSensorValuesOnExit(scene)

    return

  def _buildAllRegionObjsList(self, scene, region, event_data):
    counts = {}
    num_objects = 0
    all_objects = []
    for otype, objects in region.objects.items():
      counts[otype] = len(objects)
      num_objects += counts[otype]
      all_objects += objects
    event_data['counts'] = counts
    detections_dict = buildDetectionsDict(all_objects, scene)
    event_data['objects'] = list(detections_dict.values())
    return detections_dict, num_objects

  def _buildEnteredObjsList(self, region, event_data, detections_dict):
    entered = getattr(region, 'entered', {})
    event_data['entered'] = []
    for entered_list in entered.values():
      for item in entered_list:
        entered_obj = detections_dict[item.gid]
        event_data['entered'].extend([entered_obj])

  def _buildExitedObjsList(self, scene, region, event_data):
    exited = getattr(region, 'exited', {})
    event_data['exited'] = []
    exited_dict = {}
    for exited_list in exited.values():
      exited_objs = []
      for exited_obj, dwell in exited_list:
        exited_dict[exited_obj.gid] = dwell
        exited_objs.extend([exited_obj])
      exited_objs = buildDetectionsList(exited_objs, scene)
      exited_data = [{'object': exited_obj, 'dwell': exited_dict[exited_obj['id']]} for exited_obj in exited_objs]
      event_data['exited'].extend(exited_data)
    return

  def _clearSensorValuesOnExit(self, scene):
    """Clears the environmental sensor values accumulated by the exiting object"""
    for event_type in scene.events:
      for region_name, region in scene.events[event_type]:
        if hasattr(region, 'exited'):
          for detectionType in region.exited:
            for exit_data in region.exited[detectionType]:
              obj = exit_data[0]
              if region.singleton_type == "environmental":
                obj.chain_data.sensors.pop(region_name, None)
        region.exited = {}
        region.entered = {}
    return

  # Message handling
  def handleSensorMessage(self, client, userdata, message):
    """
    Handle a sensor message such as this
    MQTT Topic: scenescape/data/sensor/02:42:ac:11:00:05.1
        {"timestamp": "2018-09-12T19:03:49.600z",
         "subtype": "humidity",
         "value": "21.7",
         "id": "02:42:ac:11:00:05.1",
         "status": "green" }
    """
    message = message.payload.decode('utf-8')
    jdata = orjson.loads(message)

    if not self.schema_val.validateMessage("singleton", jdata, check_format=True):
      return

    sensor_id = jdata['id']
    scene = self.cache_manager.sceneWithSensorID(sensor_id)
    if scene is None:
      return

    if self.rewrite_all_time:
      ts = get_epoch_time()
      jdata['timestamp'] = get_iso_time(ts)
    else:
      ts = get_epoch_time(jdata['timestamp'])

    if not scene.processSensorData(jdata, when=ts):
      log.error("Sensor fail", sensor_id)
      self.cache_manager.invalidate()
      return

    jdata['scene_id'] = scene.uid
    jdata['scene_name'] = scene.name

    self.publishEvents(scene, jdata['timestamp'])
    return

  def _route_message(self, topic_str):
    """Determine which scene this message belongs to.

    Returns scene_uid (str) or None if scene cannot be determined.
    """
    try:
      topic = PubSub.parseTopic(topic_str)
      scene = None
      if 'camera_id' in topic:
        scene = self.cache_manager.sceneWithCameraID(topic['camera_id'])
      elif 'scene_id' in topic:
        _, scene = self._resolveChildSenderAndParentScene(topic['scene_id'])
      if scene is not None:
        return scene.uid
    except Exception:
      pass
    return None

  def handleMovingObjectMessage(self, client, userdata, message):
    """MQTT callback - routes message to deterministic worker process.

    Overwrite-based freshness prevents backlog accumulation under sustained load:
    - At most 1 in-flight task per camera
    - New frames overwrite old frames in buffer
    - Worker always processes freshest data
    - No backlog accumulation (queue depth bounded to N cameras)
    """
    t_callback_enter = time.time_ns()

    # Capture message data immediately (message object may not be valid after callback returns)
    topic_str = message.topic
    payload = message.payload

    self._processIncomingDetection(topic_str, payload, t_callback_enter)

  def _processIncomingDetection(self, topic_str, payload, t_callback_enter):
    """Common processing path for MQTT detection messages.

    Design: The MQTT callback thread must never block for more than a few
    microseconds. Heavy operations (process creation, executor submit) happen
    OUTSIDE any lock that guards per-camera state.

    Flow:
      1. Store latest frame in overwrite buffer (under _latest_frame_lock, fast)
      2. Check pending work (under _pending_work_lock, fast dict check only)
      3. Acquire semaphore (non-blocking)
      4. Peek latest frame, get executor and submit (NO lock held — may spawn process)
      5. Consume frame from overwrite buffer only after successful submit
      6. Store Future in _pending_work (under _pending_work_lock, fast)
    """
    # Extract camera_id for per-camera buffer management
    topic = PubSub.parseTopic(topic_str)
    camera_id = topic.get('camera_id', topic.get('scene_id', 'unknown'))

    # Determine which scene this message belongs to
    scene_uid = self._route_message(topic_str)

    # Routing verification diagnostic log (rate-limited to reduce log volume).
    self._route_log_count += 1
    if self._route_log_count <= 5 or self._route_log_count % 1000 == 0:
      log.info(f"[ROUTE] camera={camera_id} scene={scene_uid} pid_main={os.getpid()} msg#{self._route_log_count}")

    # OVERWRITE: Store only the latest frame per camera (atomic)
    with self._latest_frame_lock:
      self._latest_frame[camera_id] = (topic_str, payload, t_callback_enter)

    # Quick check under lock — is there already pending work for this camera?
    # If ANY entry exists (running or done), return immediately. The done callback
    # (_handle_work_complete) is solely responsible for re-submission and cleanup.
    # This eliminates the race where both MQTT thread and callback thread submit
    # concurrently for the same camera.
    with self._pending_work_lock:
      if camera_id in self._pending_work:
        return

    # Semaphore admission control (no lock held)
    if not self._inflight_semaphore.acquire(blocking=False):
      log.debug(f"[ADMISSION_DROP] camera={camera_id}, workers_saturated, dropping to prevent queue buildup")
      metric_attributes = {
          "topic": topic_str,
          "camera": camera_id,
          "reason": "admission_control"
      }
      metrics.inc_dropped(metric_attributes)
      return

    # Peek frame and executor (NO lock held — executor creation may be slow).
    # Do not remove buffered frame until submit succeeds.
    frame = self._get_latest_frame(camera_id, remove=False)
    if frame is None:
      self._inflight_semaphore.release()
      return

    executor = self._get_executor_for_scene(scene_uid)
    if executor is None:
      self._inflight_semaphore.release()
      log.warning(f"[NO_WORKER] camera={camera_id}, scene={scene_uid}, dropping")
      metric_attributes = {"camera": camera_id, "reason": "no_worker"}
      metrics.inc_dropped(metric_attributes)
      return

    failure = self._submit_frame_to_worker(
        executor,
        frame,
        camera_id,
        scene_uid,
        worker_crash_log_tag="WORKER_CRASH",
        submit_error_log_tag="SUBMIT_ERROR"
    )
    if failure is not None:
      self._inflight_semaphore.release()
      metric_attributes = {"camera": camera_id, "reason": failure}
      metrics.inc_dropped(metric_attributes)
      return

  def _get_latest_frame(self, camera_id, remove=True):
    """Atomically get latest frame for a camera.

    Args:
      camera_id: camera or scene identifier used for buffering.
      remove: when True, remove the frame from buffer; otherwise return a peek.
    """
    with self._latest_frame_lock:
      if camera_id in self._latest_frame:
        frame = self._latest_frame[camera_id]
        if remove:
          del self._latest_frame[camera_id]
        return frame
      return None

  def _remove_frame_if_unchanged(self, camera_id, frame):
    """Remove buffered frame only if it is still the same object.

    This avoids deleting a newer frame that overwrote the buffer while submit
    was in progress.
    """
    with self._latest_frame_lock:
      if self._latest_frame.get(camera_id) is frame:
        del self._latest_frame[camera_id]

  def _clear_pending_work(self, camera_id):
    """Remove pending work entry for a camera if present."""
    with self._pending_work_lock:
      self._pending_work.pop(camera_id, None)

  def _submit_frame_to_worker(self, executor, frame, camera_id, scene_uid,
                              worker_crash_log_tag, submit_error_log_tag):
    """Submit a frame to a worker and register completion callback.

    Returns:
      None on success, or one of "worker_crash" / "submit_error" on failure.
    """
    try:
      future = executor.submit(
          _worker_handle_message,
          frame[0], frame[1], frame[2]
      )
      # Consume buffered frame only when submit succeeds.
      # If a newer frame overwrote it, keep the newer one in the buffer.
      self._remove_frame_if_unchanged(camera_id, frame)
      with self._pending_work_lock:
        self._pending_work[camera_id] = future
      # Store-before-callback prevents races on very fast worker completion.
      future.add_done_callback(
          lambda f, cam=camera_id, suid=scene_uid: self._handle_work_complete(cam, suid)
      )
      return None
    except BrokenProcessPool as e:
      with self._worker_crashes_lock:
        self._worker_crashes += 1
        crashes = self._worker_crashes
      log.error(f"[{worker_crash_log_tag}] scene={scene_uid}, camera={camera_id}, total_crashes={crashes}, error={e}")
      self._recreate_scene_executor(scene_uid)
      return "worker_crash"
    except Exception as e:
      log.error(f"[{submit_error_log_tag}] scene={scene_uid}, camera={camera_id}, error={type(e).__name__}: {e}")
      return "submit_error"

  def _handle_work_complete(self, camera_id, scene_uid):
    """Called when worker completes — sole owner of re-submission for this camera.

    Design: _processIncomingDetection never submits if _pending_work has an entry.
    This callback is the only path that re-submits or cleans up, eliminating the
    race where both MQTT thread and callback thread submit concurrently.

    Flow:
      1. Release semaphore (work done)
      2. Check overwrite buffer for newer frame
      3. If frame: re-acquire semaphore, get executor, submit (NO lock during submit)
      4. Store new future under lock (brief)
      5. If no frame or can't submit: clean up entry so MQTT thread can submit next time
    """
    self._inflight_semaphore.release()

    # Peek buffered frame first; consume only after successful re-submit.
    frame = self._get_latest_frame(camera_id, remove=False)

    if frame is not None:
      # Newer data arrived during processing — re-submit
      if not self._inflight_semaphore.acquire(blocking=False):
        self._clear_pending_work(camera_id)
        return

      executor = self._get_executor_for_scene(scene_uid)
      if executor is None:
        self._inflight_semaphore.release()
        self._clear_pending_work(camera_id)
        return

      failure = self._submit_frame_to_worker(
          executor,
          frame,
          camera_id,
          scene_uid,
          worker_crash_log_tag="WORKER_CRASH_RESUBMIT",
          submit_error_log_tag="RESUBMIT_ERROR"
      )
      if failure is not None:
        self._inflight_semaphore.release()
        self._clear_pending_work(camera_id)
    else:
      # No newer frame — remove entry so _processIncomingDetection can submit next time
      self._clear_pending_work(camera_id)

  def _resolveMessageTime(self, jdata, now):
    """Resolve the processing time for a message and keep its payload consistent.

    When rewrite_all_time is set, the message is restamped to `now`; otherwise
    the embedded timestamp is used. The returned value is the epoch time used
    for processing, and jdata['timestamp'] is guaranteed to match it.
    """
    if self.rewrite_all_time:
      jdata['timestamp'] = get_iso_time(now)
      return now
    return get_epoch_time(jdata['timestamp'])

  def _logLagDecomposition(self, jdata, lag):
    """Log the upstream vs MQTT split of a message's lag, when available.

    debug_processing_time = T_postinference - T_capture (set in sscape_adapter.py:226)
    """
    upstream_proc_s = jdata.get('debug_processing_time', None)
    if upstream_proc_s is None:
      return
    upstream_ms = upstream_proc_s * 1000
    mqtt_ms = (lag - upstream_proc_s) * 1000
    total_lag_ms = lag * 1000
    log.debug(f"[PROFILE_LAG_SPLIT] cam={jdata['id']}, "
              f"upstream_ms={upstream_ms:.1f}, mqtt_ms={mqtt_ms:.1f}, "
              f"total_ms={total_lag_ms:.1f}")

  def _applyLagPolicy(self, jdata, lag, now):
    """Decide how to handle a frame whose lag exceeds max_lag.

    Returns the processing time to use, or None if the frame should be dropped.
    Accepted frames are restamped to `now` so jdata['timestamp'] stays consistent
    with the processing time (avoids publishing stale timestamps downstream).

    During the startup grace period stale frames are accepted: the overwrite
    buffer keeps only the latest frame per camera, so stale ones are naturally
    replaced by fresh frames within one frame interval.
    """
    in_grace = (time.time() - self._startup_time) < self._startup_grace_sec
    if in_grace:
      log.debug(f"Startup grace: accepting stale frame from {jdata.get('id', 'unknown')} (lag={lag:.2f}s)")
    elif not self.rewrite_bad_time:
      log.warning("FELL BEHIND by {}. SKIPPING {}".format(lag, jdata.get('id', 'unknown')))
      return None
    jdata['timestamp'] = get_iso_time(now)
    return now

  def _logWorkerRoute(self, sender_id, scene):
    """Rate-limited worker-side routing diagnostic.

    Logs the first 5 messages, then every 1000th, to verify the worker receives
    the correct scenes.
    """
    if not hasattr(self, '_worker_route_log_count'):
      self._worker_route_log_count = 0
    self._worker_route_log_count += 1
    if self._worker_route_log_count <= 5 or self._worker_route_log_count % 1000 == 0:
      log.info(f"[ROUTE_WORKER] camera={sender_id} scene={scene.uid} worker_pid={os.getpid()} msg#{self._worker_route_log_count}")

  def _processMessageCore(self, topic_str, jdata, now_with_offset, t_handler_start, t_parse):
    """Core message processing: validate, route, and run detection pipeline.

    This function contains the computational core of message handling. It does NOT:
    - Acquire locks (_ntp_sync_lock, _publish_lock)
    - Publish to MQTT
    - Mutate metrics counters

    It DOES access (read-mostly, with their own internal locks):
    - self.schema_val (read-only validation)
    - self.cache_manager (RLock-protected lookups)
    - Scene objects (mutated during processCameraData — will be process-local in multiprocessing)

    Args:
      topic_str: raw MQTT topic string
      jdata: pre-parsed JSON message dict
      now_with_offset: current epoch time with NTP offset applied
      t_handler_start: handler start timestamp (ns)
      t_parse: post-parse timestamp (ns)

    Returns:
      dict with keys: scene, detection_types, camera_id, jdata, msg_when
      None if the message should be skipped (validation fail, updatecamera, lag drop, unknown sender)
    """
    topic = PubSub.parseTopic(topic_str)

    if 'camera_id' in topic and not self.schema_val.validateMessage("detector", jdata):
      return None

    now = now_with_offset
    if 'updatecamera' in jdata:
      return None

    jdata['debug_hmo_start_time'] = now
    jdata['_profile_handler_start'] = t_handler_start
    jdata['_profile_parse_done'] = t_parse
    self.cache_manager.refreshScenesForCamParams(jdata)

    msg_when = self._resolveMessageTime(jdata, now)

    lag = abs(now - msg_when)
    self._logLagDecomposition(jdata, lag)

    if lag > self.max_lag:
      msg_when = self._applyLagPolicy(jdata, lag, now)
      if msg_when is None:
        return None

    camera_id = None
    if topic['_topic_id'] == PubSub.DATA_EXTERNAL:
      detection_types = [topic['thing_type']]
      sender_id = topic['scene_id']
      success, scene = self._handleChildSceneObject(sender_id, jdata, detection_types[0], msg_when)
    else:
      detection_types = list(jdata['objects'].keys())
      camera_id = sender_id = topic['camera_id']
      sender = self.cache_manager.sceneWithCameraID(sender_id)
      if sender is None:
        log.error("UNKNOWN SENDER", sender_id)
        return None
      scene = sender

      self._logWorkerRoute(sender_id, scene)

      # If no detection types in the message, add empty arrays for all tracked types
      # This must be done BEFORE processCameraData so the tracker processes them
      if not detection_types:
        detection_types = list(scene.tracker.trackers.keys())
        for dtype in detection_types:
          jdata['objects'][dtype] = []

      success = scene.processCameraData(jdata, when=msg_when)

    if not success:
      log.error("Camera fail", sender_id, scene.name)
      self.cache_manager.invalidate()
      return None

    return {
      'scene': scene,
      'detection_types': detection_types,
      'camera_id': camera_id,
      'jdata': jdata,
      'msg_when': msg_when,
    }

  def _processMovingObjectMessage(self, topic_str, payload, t_callback_enter):
    """Wrapper: handles timing, locks, metrics, and publishing around the core processor.

    This is the entry point called by the ThreadPoolExecutor. It:
    1. Records timing and queue wait
    2. Acquires NTP lock for time sync
    3. Delegates to _processMessageCore for computation
    4. Publishes results via MQTT (with _publish_lock)

    In multiprocessing, this method runs inside the worker process; the main process
    only buffers/routes messages and submits work to the per-scene worker pool.
    """
    t_handler_start = time.time_ns()

    # Log queue wait time (time between callback entry and worker start)
    queue_wait_ms = (t_handler_start - t_callback_enter) / 1e6

    # Parse payload once — used for metrics and passed to core
    if isinstance(payload, memoryview):
      payload = payload.tobytes()
    if isinstance(payload, (bytes, bytearray)):
      jdata = orjson.loads(payload)
    elif isinstance(payload, str):
      jdata = orjson.loads(payload)
    elif isinstance(payload, dict):
      jdata = payload
    else:
      raise TypeError(f"Unsupported payload type: {type(payload).__name__}")
    camera_id_tmp = jdata.get('id', 'unknown')

    metric_attributes = {
        "topic": topic_str,
        "camera": camera_id_tmp,
    }
    metrics.inc_messages(metric_attributes)

    # Log the queue wait metric - this shows GIL contention impact
    # queue_ms > 100ms indicates thread pool backup due to GIL
    if queue_wait_ms > 50:  # Log if notable delay (GIL contention indicator)
      log.debug(f"[LATENCY] camera={camera_id_tmp}, queue_ms={queue_wait_ms:.1f}")

    t_parse = time.time_ns()

    with metrics.time_mqtt_handler(metric_attributes):
      # NTP sync under lock — shared mutable state
      now = get_epoch_time()
      with self._ntp_sync_lock:
        self.time_offset, self.last_time_sync = adjust_time(now, self.ntp_server, self.ntp_client,
                                                        self.last_time_sync, self.time_offset,
                                                        ntplib.NTPException)
      now_with_offset = now + self.time_offset

      # Core processing (no locks, no publish)
      result = self._processMessageCore(topic_str, jdata, now_with_offset, t_handler_start, t_parse)
      if result is None:
        # Message was skipped (validation, lag, unknown sender, etc.)
        if queue_wait_ms > 50 and jdata.get('id'):
          metric_attributes["reason"] = "fell_behind"
          metrics.inc_dropped(metric_attributes)
        return

      t_process_done = time.time_ns()

      scene = result['scene']
      detection_types = result['detection_types']
      camera_id = result['camera_id']
      jdata = result['jdata']
      msg_when = result['msg_when']

      # Publishing phase — requires _publish_lock (MQTT not thread-safe)
      jdata['id'] = scene.uid
      jdata['name'] = scene.name
      t_before_publish = time.time_ns()
      for detection_type in detection_types:
        jdata['unique_detection_count'] = scene.tracker.getUniqueIDCount(detection_type)
        self.publishDetections(scene, scene.tracker.currentObjects(detection_type),
                              msg_when, detection_type, jdata, camera_id)
      t_after_publish = time.time_ns()

      # Publish events ONCE after all detection types (events span all categories).
      # Publishing inside the loop would duplicate event messages.
      self.publishEvents(scene, jdata['timestamp'])
      t_after_events = time.time_ns()

      parse_ms = (t_parse - t_handler_start) / 1e6
      process_ms = (t_process_done - t_parse) / 1e6
      publish_ms = (t_after_publish - t_before_publish) / 1e6
      events_ms = (t_after_events - t_after_publish) / 1e6
      total_ms = (t_after_events - t_handler_start) / 1e6
      log.debug(f"[PROFILE_MAIN] camera={camera_id}, "
                f"parse_ms={parse_ms:.3f}, process_ms={process_ms:.3f}, "
                f"publish_ms={publish_ms:.3f}, events_ms={events_ms:.3f}, "
                f"total_ms={total_ms:.3f}")
      return

  def _resolveChildSenderAndParentScene(self, sender_id):
    """Resolve a child sender id to (sender_scene, parent_scene).

    Returns:
      (sender, parent_scene) where either entry may be None if resolution fails.
      Logs resolution failures consistently for all callers.
    """
    sender = self.cache_manager.sceneWithID(sender_id)
    if sender is None:
      sender = self.cache_manager.sceneWithRemoteChildID(sender_id)
      if sender is None:
        log.error("UNKNOWN SENDER")
        return None, None

    if not hasattr(sender, 'parent') or sender.parent is None:
      log.error("UNKNOWN PARENT", sender_id)
      return sender, None

    scene = self.cache_manager.sceneWithID(sender.parent)
    if scene is None:
      log.error(f"Parent scene not found in cache for sender {sender_id}")
      return sender, None

    return sender, scene

  def _handleChildSceneObject(self, sender_id, jdata, detection_type, msg_when):
    sender, scene = self._resolveChildSenderAndParentScene(sender_id)
    if sender is None:
      return False, None
    if scene is None:
      return False, sender

    success = scene.processSceneData(jdata, sender, sender.cameraPose,
                                     detection_type, when=msg_when)
    return success, scene

  def updateCameras(self):
    for scene in self.scenes:
      for camera in scene.cameras:
        cam = scene.cameras[camera]
        if not hasattr(cam, "pose"):
          self.cache_manager.updateCamera(cam)
    return

  def updateRegulateCache(self):
    # Clean up regulate cache entries for removed scenes and cameras
    scene_uids = {scene.uid for scene in self.scenes}
    for scene_uid in list(self.regulate_cache.keys()):
      if scene_uid not in scene_uids:
        # Scene was removed - delete entire cache entry
        self.regulate_cache.pop(scene_uid)
      else:
        # Scene still exists - check if cameras were removed
        scene_obj = next((s for s in self.scenes if s.uid == scene_uid), None)
        if scene_obj:
          cache_entry = self.regulate_cache[scene_uid]
          for cam_id in list(cache_entry['rate'].keys()):
            if cam_id not in scene_obj.cameras:
              cache_entry['rate'].pop(cam_id)
    return

  def _workerHandleDatabaseMessage(self, client, userdata, message):
    """Handle database update notifications in worker processes.
    Workers only need to refresh object_classes (Object Library settings)
    since scene subscriptions and camera updates are managed by the main process."""
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      self.cache_manager.markDirty()
      threading.Thread(target=self._workerDatabaseUpdateAsync, name="WorkerDBUpdate", daemon=True).start()
    return

  def _workerDatabaseUpdateAsync(self):
    """Handle worker-side database update notifications.

    Runs in worker processes only, under `_db_update_lock`, to refresh scene
    cache and Object Library class settings used by tracker pipelines.
    """
    with self._db_update_lock:
      try:
        scene_count_before = len(self.scenes) if hasattr(self, 'scenes') and self.scenes else 0
        self.scenes = self.cache_manager.allScenes(force_refresh=True)
        scene_count_after = len(self.scenes)
        self.updateObjectClasses()
        log.info(f"[WORKER_DB_UPDATE] pid={os.getpid()} object_classes refreshed, "
                 f"scenes_before={scene_count_before}, scenes_after={scene_count_after}")
      except Exception as e:
        log.warning("Worker failed to update object classes: %s", e)

  def handleDatabaseMessage(self, client, userdata, message):
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      self.cache_manager.markDirty()
      # Run in background thread to avoid blocking the MQTT callback thread.
      # HTTP calls in updateSubscriptions/updateObjectClasses/etc can take
      # seconds and would block paho's network loop, causing keepalive timeout.
      threading.Thread(target=self._databaseUpdateAsync, name="DBUpdate", daemon=True).start()
    return

  def _databaseUpdateAsync(self):
    """Run database update work in background to avoid blocking MQTT thread."""
    with self._db_update_lock:
      try:
        self._runSceneRefreshPipeline(include_camera_updates=True)
        log.info("[DB_UPDATE] Database update completed successfully")
      except Exception as e:
        log.warning("Failed to update database: %s", e)

  def calculateRate(self):
    now = get_epoch_time()
    if self.regulate_last is None:
      self.regulate_last = now
      return self.regulate_rate
    delta = now - self.regulate_last
    self.regulate_rate *= AVG_FRAMES
    self.regulate_rate += delta
    self.regulate_rate /= AVG_FRAMES + 1
    self.regulate_last = now
    return self.regulate_rate

  # MQTT callbacks
  def onConnect(self, client, userdata, flags, rc):
    log.info("Connected with result code", rc)
    if rc != 0:
      log.error(f"MQTT connection failed with rc={rc}, terminating")
      # os._exit is intentional: this callback runs on paho's network thread,
      # so sys.exit() would only raise SystemExit in that thread and not terminate
      # the process. os._exit() ensures immediate process-wide termination.
      os._exit(1)
    self.subscribed = set()
    # Subscribe to database commands immediately (lightweight, no HTTP)
    topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    self.pubsub.addCallback(topic, self.handleDatabaseMessage)
    log.info("Subscribed to", topic)
    # Run heavy HTTP work (subscriptions, object classes, TRS) in background
    # to avoid blocking paho's MQTT network loop thread
    threading.Thread(target=self._onConnectAsync, name="OnConnectSetup", daemon=True).start()
    # Note: Subscriptions are static after initial setup. Dynamic subscription updates
    # (when scenes/sensors/children are added/deleted/renamed) would require database
    # change notification mechanism to trigger re-subscription.
    return

  def _onConnectAsync(self):
    """Run onConnect setup in background to avoid blocking MQTT thread."""
    with self._db_update_lock:
      try:
        self._runSceneRefreshPipeline(include_camera_updates=False)
        log.info("[ON_CONNECT] Initial setup completed successfully")
      except Exception as e:
        log.warning("Failed to complete onConnect setup: %s", e)

  def _runSceneRefreshPipeline(self, include_camera_updates):
    """Run shared scene refresh steps used by DB update and on-connect setup."""
    self.updateSubscriptions()
    self._sync_workers_to_scenes()
    self.updateObjectClasses()
    if include_camera_updates:
      self.updateCameras()
      self.updateRegulateCache()
    self.updateTRSMatrix()

  def updateObjectClasses(self):
    results = self.cache_manager.data_source.getAssets()
    if results and 'results' in results:
      for scene in self.scenes:
        scene.tracker.updateObjectClasses(results['results'])
    return

  def updateTRSMatrix(self):
    for scene in self.cache_manager.allScenes():
      if scene.trs_xyz_to_lla is not None:
        res = self.cache_manager.data_source.setTRSMatrix(scene.uid, scene.trs_xyz_to_lla)
        if res.errors:
          log.info(
                  "Failed to update trs matrix for scene %s. Errors: %s",
                  scene.name,
                  res.errors,
                )
    return

  def republishEvents(self, client, userdata, message):
    """
    Republishes the child analytics under parent topic that
    enables parent to visualize them.
    """
    topic = PubSub.parseTopic(message.topic)
    msg = orjson.loads(message.payload.decode('utf-8'))

    sender_id = topic['scene_id']
    sender, scene = self._resolveChildSenderAndParentScene(sender_id)
    if sender is None or scene is None:
      return

    event_topic = PubSub.formatTopic(PubSub.EVENT,
                                      region_type=topic['region_type'], event_type=topic['event_type'],
                                      scene_id=scene.uid, region_id=topic['region_id'])

    self.transformObjectsinEvent(msg, sender)

    msg['metadata'] = applyChildTransform(msg['metadata'], sender.cameraPose)
    if 'from_child_scene' not in msg['metadata']:
      msg['metadata']['from_child_scene'] = sender.name
    else:
      msg['metadata']['from_child_scene'] = sender.name + " > " + msg['metadata']['from_child_scene']
    self._async_publish(event_topic, orjson.dumps(msg, option=orjson.OPT_SERIALIZE_NUMPY))
    return

  def transformObjectsinEvent(self, event, sender):
    keys = ['objects', 'entered', 'exited']
    for k in keys:
      if k == 'exited':
        for i, obj in enumerate(event[k]):
          event[k][i]['object']['translation'] = sender.cameraPose.cameraPointToWorldPoint(
                                                            Point(obj['object']['translation'])).asNumpyCartesian.tolist()
      else:
        for i, obj in enumerate(event[k]):
          event[k][i]['translation'] = sender.cameraPose.cameraPointToWorldPoint(
                                                            Point(obj['translation'])).asNumpyCartesian.tolist()
    return

  def updateSubscriptions(self):
    log.debug("UPDATE SUBSCRIPTIONS")
    self.cache_manager.invalidate()
    if not hasattr(self, 'subscribed'):
      self.subscribed = set()
    need_subscribe = set()

    if not hasattr(self, 'subscribed_children'):
      self.subscribed_children = dict()
    need_subscribe_child = dict()

    self.scenes = self.cache_manager.allScenes()
    for scene in self.scenes:
      for camera in scene.cameras:
        need_subscribe.add((PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera),
                            self.handleMovingObjectMessage))
      for sensor in scene.sensors:
        need_subscribe.add((PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor),
                            self.handleSensorMessage))
      if hasattr(scene, 'children'):
        child_scenes = self.cache_manager.data_source.getChildScenes(scene.uid)

        for info in child_scenes.get('results', []):
          if info['child_type'] == 'local':
            child_scene = self.cache_manager.sceneWithID(info['child'])
            if child_scene is None:
              log.warning(f"Child scene {info['child']} not found in cache, skipping")
              continue
            child_scene.retrack = info['retrack']

            need_subscribe.add((PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                                                   scene_id=info['child'], thing_type="+"),
                                self.handleMovingObjectMessage))

            need_subscribe.add((PubSub.formatTopic(PubSub.EVENT, region_type="+",
                                                   event_type="+",
                                                   scene_id=info['child'],
                                                   region_id="+"),
                                self.republishEvents))
          else:
            child_obj = ChildSceneController(self.root_cert, info, self)
            with self.cache_manager._lock:
              self.cache_manager.cached_child_transforms_by_uid[info['remote_child_id']] = Scene.deserialize(info)
            need_subscribe_child[info['remote_child_id']] = child_obj
            need_subscribe.add((PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id=info['remote_child_id']), child_obj.publishStatus))

    # disconnect old children clients
    for old_child, cobj in self.subscribed_children.items():
      if old_child not in need_subscribe_child:
        with self.cache_manager._lock:
          self.cache_manager.cached_child_transforms_by_uid.pop(old_child, None)
      cobj.loopStop()

    # connect to all children
    for new_child, cobj in need_subscribe_child.items():
      log.info(f"Connecting to remote child {new_child}")
      cobj.loopStart()

    self.subscribed_children = need_subscribe_child

    new = need_subscribe - self.subscribed
    old = self.subscribed - need_subscribe
    for topic, callback in old:
      self.pubsub.removeCallback(topic)
      log.info("Unsubscribed from", topic)
    for topic, callback in new:
      self.pubsub.addCallback(topic, callback)
      log.info("Subscribed to", topic)
    self.subscribed = need_subscribe
    return
