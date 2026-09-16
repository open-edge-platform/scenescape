# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import collections
import concurrent.futures
import threading
import math

import numpy as np

from scene_common.reid_constants import (
  COSINE_SIMILARITY_TOLERANCE,
  DEFAULT_CONFIG_SIMILARITY_METRIC,
  DEFAULT_MINIMUM_BBOX_AREA,
  QUERY_K_NEIGHBORS,
  SUPPORTED_CONFIG_SIMILARITY_METRICS,
  is_higher_better_metric,
  is_similarity_match,
  is_upstream_enrollment_claim,
  is_vetted_provenance,
  normalize_config_similarity_metric,
  normalize_similarity_score,
  pick_best_metric_value,
  resolve_database_similarity_metric,
)
from controller.reid_registry import create_reid_database
from controller.reid_env import get_reid_purge_interval_secs
from controller.reid import (
  ReidNoValidVectorsError,
  ReidPartialWriteError,
  ReidWriteSupersededError,
)
from controller.moving_object import ReidState, MovingObject
from controller.latency_metrics import MatchLatencyTracker
from scene_common.camera_registry import CameraRegistry
from scene_common.tracking_object_registry import TrackedObjectRegistry
from controller.observability import metrics

from scene_common import log
from scene_common.timestamp import get_epoch_time

DEFAULT_SIMILARITY_THRESHOLD_L2 = 40.0
DEFAULT_SIMILARITY_THRESHOLD_COSINE = 0.5
DEFAULT_MINIMUM_FEATURE_COUNT = 12
DEFAULT_FEATURE_SLICE_SIZE = 10
DEFAULT_MAX_QUERY_TIME = 4
DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED = 10
DEFAULT_STALE_FEATURE_TIMEOUT_SECS = 5.0
DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS = 1.0
DEFAULT_SIMILARITY_METRIC = DEFAULT_CONFIG_SIMILARITY_METRIC
SUPPORTED_SIMILARITY_METRICS = SUPPORTED_CONFIG_SIMILARITY_METRICS

# One purge worker per process: category trackers each construct a UUIDManager,
# but they share one ReID store and must not each schedule DeleteExpired /
# filter-deletes against it.
_PURGE_OWNER_LOCK = threading.Lock()
_PURGE_OWNER = None


class UUIDManager:
  def _normalizeSimilarityMetric(self, metric):
    normalized_metric = normalize_config_similarity_metric(
      metric, default=DEFAULT_SIMILARITY_METRIC)
    if str(metric).strip().upper() != normalized_metric and (
        str(metric).strip().upper() not in SUPPORTED_SIMILARITY_METRICS):
      log.warning(
        f"Unsupported similarity_metric '{metric}', "
        f"supported values are {sorted(SUPPORTED_SIMILARITY_METRICS)}; "
        f"falling back to {DEFAULT_SIMILARITY_METRIC}")
    return normalized_metric

  def _resolveDatabaseSimilarityMetric(self, configured_metric):
    """Translate controller-facing similarity metric to the backend descriptor metric."""
    return resolve_database_similarity_metric(configured_metric)

  def _resolveDefaultSimilarityThreshold(self, similarity_metric):
    """Return the default threshold for the configured similarity metric."""
    if self._normalizeSimilarityMetric(similarity_metric) == "COSINE":
      return DEFAULT_SIMILARITY_THRESHOLD_COSINE
    return DEFAULT_SIMILARITY_THRESHOLD_L2

  def _validateSimilarityThreshold(self, similarity_threshold, similarity_metric):
    """Normalize and validate the configured threshold for the active metric."""
    try:
      normalized_threshold = float(similarity_threshold)
    except (TypeError, ValueError) as err:
      raise ValueError(
        f"similarity_threshold must be a finite numeric value, got {similarity_threshold}") from err

    if not math.isfinite(normalized_threshold):
      raise ValueError(
        f"similarity_threshold must be a finite numeric value, got {similarity_threshold}")

    normalized_metric = self._normalizeSimilarityMetric(similarity_metric)
    if normalized_metric == "COSINE":
      if normalized_threshold < -1.0 or normalized_threshold > 1.0:
        raise ValueError(
          "similarity_threshold for COSINE must be within [-1.0, 1.0]")
      return normalized_threshold

    if normalized_threshold < 0.0:
      raise ValueError("similarity_threshold for L2 must be non-negative")
    return normalized_threshold

  def __init__(self, database=None, reid_config_data=None):
    self.active_ids = {}
    self.active_ids_lock = threading.Lock()
    self.active_query = {}
    self.features_for_database = {}
    self.features_for_database_timestamps = {}  # Track when features were added
    # Embeddings this scope may query the shared database with: its own camera crops plus
    # crops another scope vetted before forwarding them.
    self.quality_features = {}
    # Frame/observation count toward the query threshold (includes exact repeats).
    self.quality_observation_counts = {}
    # Embeddings this scope may contribute to the shared database: local camera crops
    # plus vetted forwarded crops (exact-deduped).
    self.enrollment_features = {}
    # Local-camera subset of enrollment_features; preserved on exact rematch when
    # forwarded query evidence is skipped as already stored.
    self.local_enrollment_features = {}
    self.unique_id_count = 0
    self.stale_feature_timer = None
    self.purge_timer = None
    self.purge_interval_secs = None
    self._owns_purge_timer = False
    self.scene_id = None
    self._shutdown_complete = False

    self.unique_id_count_lock = threading.Lock()
    # ReID embedding dimensions are inferred from the first observed embedding.
    if reid_config_data is None:
      reid_config_data = {}
    self._inferred_dimensions = None
    self._dimensions_lock = threading.Lock()
    self.reid_database = create_reid_database(database, dimensions=None)

    self.pool = concurrent.futures.ThreadPoolExecutor()
    self.similarity_query_times = collections.deque(
      maxlen=DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED)
    self.similarity_query_times_lock = threading.Lock()
    # Per-match latency: elapsed time from a track's first appearance to its
    # match/no-match decision. See MatchLatencyTracker for details.
    self.match_latency_tracker = MatchLatencyTracker()

    self.reid_enabled = True
    # When False, hierarchy publish drops will_enroll (unless already confirmed)
    # and local enrollment stops so a parent may sole-enroll without a dual-writer race.
    self.reid_write_healthy = True
    # True after at least one successful addEntry; will_enroll waits on this so
    # parents are not asked to skip writes before the child has proven it can.
    self.reid_write_confirmed = False
    # Bumped when write-health clears / empty-batch handoff / reid disable so
    # in-flight pool workers drop superseded writes.
    self.reid_write_epoch = 0
    # Serializes enrollment workers so epoch/health checks cannot race addEntry.
    self._reid_write_lock = threading.Lock()
    # True after an empty/invalid batch before the first confirmed write — publish
    # passthrough and stop local enrollment so a parent can sole-enroll instead of
    # forever withholding or racing a continuing child writer.
    self.reid_empty_batch_before_confirm = False
    # Sticky flag: once any object tracked by this (per-category) instance
    # has produced a valid decoded embedding, this category is confirmed to
    # support ReID (e.g. "person"), unlike categories such as "apriltag"
    # that never carry a .reid field. Never reset -- individual frames/
    # objects only carry a decoded embedding sparsely/intermittently, so a
    # per-frame check is not a reliable "does this category do ReID" signal.
    self._category_has_embeddings = False
    self._category = None
    self._applyReidConfig(reid_config_data)
    self._rescheduleStaleFeatureTimer()
    return

  def _localEnrollmentAllowed(self):
    """True when this process may still stage/flush local ReID database writes."""
    return (
      self.reid_enabled
      and self.reid_write_healthy
      and not self.reid_empty_batch_before_confirm
    )

  def _disableReidWrites(self, reason):
    """Stop local enrollment and drop in-flight workers (parent may sole-enroll)."""
    with self._reid_write_lock:
      if self.reid_enabled:
        log.error(f"Disabling reid writes: {reason}")
      self.reid_enabled = False
      self.reid_write_epoch += 1
    return

  def _incrementUniqueIdCount(self):
    """Thread-safe increment for unique_id_count."""
    with self.unique_id_count_lock:
      self.unique_id_count += 1
      new_count = self.unique_id_count
    return new_count

  def updateReidConfig(self, reid_config_data=None):
    """Update runtime ReID configuration without recreating the UUID manager."""
    old_interval = self.stale_feature_check_interval_secs
    self._applyReidConfig(reid_config_data)

    # Timer cadence changes require rescheduling the stale feature timer.
    if old_interval != self.stale_feature_check_interval_secs:
      self._rescheduleStaleFeatureTimer()

  def _applyReidConfig(self, reid_config_data=None):
    """Apply ReID config values with defaults."""
    if reid_config_data is None:
      reid_config_data = {}

    self.stale_feature_timeout_secs = reid_config_data.get(
      'stale_feature_timeout_secs', DEFAULT_STALE_FEATURE_TIMEOUT_SECS)
    self.stale_feature_check_interval_secs = reid_config_data.get(
      'stale_feature_check_interval_secs', DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS)
    self.minimum_feature_count = reid_config_data.get(
      'feature_accumulation_threshold', DEFAULT_MINIMUM_FEATURE_COUNT)
    self.similarity_metric = self._normalizeSimilarityMetric(reid_config_data.get(
      'similarity_metric', DEFAULT_SIMILARITY_METRIC))
    configured_similarity_threshold = reid_config_data.get('similarity_threshold')
    if configured_similarity_threshold is None:
      configured_similarity_threshold = self._resolveDefaultSimilarityThreshold(
        self.similarity_metric)
    self.similarity_threshold = self._validateSimilarityThreshold(
      configured_similarity_threshold, self.similarity_metric)
    self.minimum_bbox_area = reid_config_data.get(
      'minimum_bbox_area', DEFAULT_MINIMUM_BBOX_AREA)
    self.feature_slice_size = reid_config_data.get(
      'feature_slice_size', DEFAULT_FEATURE_SLICE_SIZE)
    if hasattr(self, 'reid_database') and self.reid_database is not None:
      new_db_metric = self._resolveDatabaseSimilarityMetric(self.similarity_metric)
      current_db_metric = getattr(self.reid_database, 'similarity_metric', None)
      schema_ready = getattr(self.reid_database, '_schema_ready', False) is True
      if (schema_ready and
          current_db_metric is not None and
          str(current_db_metric).strip().upper() != new_db_metric):
        raise ValueError(
          f"Cannot change ReID similarity metric from {current_db_metric} to "
          f"{new_db_metric} after schema initialization; restart the controller "
          f"and flush the {self.reid_database._schemaResourceLabel()}.")
      self.reid_database.similarity_metric = new_db_metric

  def _rescheduleStaleFeatureTimer(self):
    """Cancel any existing stale-feature timer and start a new one."""
    timer = getattr(self, 'stale_feature_timer', None)
    if timer is not None:
      timer.cancel()
    self.stale_feature_timer = None
    self._startStaleFeatureTimer()

  def __del__(self):
    """Clean up resources when the UUIDManager is destroyed"""
    self.shutdown()

  def shutdown(self):
    """Explicitly stop the stale feature timer and clean up resources"""
    # shutdown() can be called both explicitly and via __del__. Make it
    # idempotent to avoid duplicate cleanup side effects.
    if getattr(self, '_shutdown_complete', False):
      return
    self._shutdown_complete = True

    if self.stale_feature_timer is not None:
      self.stale_feature_timer.cancel()
      self.stale_feature_timer = None
    self._releasePurgeOwnership()
    if hasattr(self, 'match_latency_tracker') and self.match_latency_tracker is not None:
      self.match_latency_tracker.shutdown()
    if hasattr(self, 'pool') and self.pool is not None:
      self.pool.shutdown(wait=False)
    # Stop contributing this category to the scene-wide tracked-object
    # total immediately, rather than lingering at its last-reported count.
    if getattr(self, '_category', None) is not None:
      TrackedObjectRegistry.getInstance().removeCategory(self.scene_id, self._category)

  def _startStaleFeatureTimer(self):
    """Start a background timer to periodically check for and flush stale features"""
    def check_stale_features():
      """Timer callback: check for features older than timeout and flush them"""
      self._flushStaleFeatures()
      # Reschedule the timer
      self._scheduleTimer(check_stale_features)

    self._scheduleTimer(check_stale_features)

  def _scheduleTimer(self, callback):
    """Create and start a daemon timer with the configured check interval"""
    self.stale_feature_timer = threading.Timer(self.stale_feature_check_interval_secs, callback)
    self.stale_feature_timer.daemon = True
    self.stale_feature_timer.start()

  def _tryAcquirePurgeOwnership(self):
    """Return True if this manager became the process-wide purge owner."""
    global _PURGE_OWNER
    with _PURGE_OWNER_LOCK:
      if _PURGE_OWNER is None:
        _PURGE_OWNER = self
        self._owns_purge_timer = True
        return True
      return False

  def _releasePurgeOwnership(self):
    """Cancel purge timer and release process-wide ownership if held."""
    global _PURGE_OWNER
    if self.purge_timer is not None:
      self.purge_timer.cancel()
      self.purge_timer = None
    if not self._owns_purge_timer:
      return
    with _PURGE_OWNER_LOCK:
      if _PURGE_OWNER is self:
        _PURGE_OWNER = None
      self._owns_purge_timer = False
    return

  def _startPurgeTimer(self):
    """Periodically ask the active ReID backend to drop expired descriptors."""
    if not getattr(self.reid_database, 'retentionEnabled', lambda: False)():
      return
    if self.purge_interval_secs is None:
      self.purge_interval_secs = get_reid_purge_interval_secs()

    def purge_and_reschedule():
      if not self._owns_purge_timer:
        return
      try:
        self.pool.submit(self._purgeExpiredDescriptors)
      except Exception as e:
        log.warning(f"_startPurgeTimer: Failed to submit purge task: {e}")
      if not self._owns_purge_timer:
        return
      self.purge_timer = threading.Timer(
        self.purge_interval_secs, purge_and_reschedule)
      self.purge_timer.daemon = True
      self.purge_timer.start()

    self.purge_timer = threading.Timer(
      self.purge_interval_secs, purge_and_reschedule)
    self.purge_timer.daemon = True
    self.purge_timer.start()

  def _purgeExpiredDescriptors(self):
    """Invoke backend purgeExpired(); failures are logged and swallowed."""
    try:
      deleted = self.reid_database.purgeExpired()
      log.debug(f"_purgeExpiredDescriptors: purgeExpired returned {deleted}")
    except Exception as e:
      log.warning(f"_purgeExpiredDescriptors: purgeExpired failed: {e}")
    return

  def _flushStaleFeatures(self):
    """Check for features older than the configured timeout (from reid-config.json) and flush them to VDMS"""
    if not self.features_for_database_timestamps:
      return

    current_time = get_epoch_time()
    stale_track_ids = []

    for track_id, timestamp in list(self.features_for_database_timestamps.items()):
      age = current_time - timestamp
      if age > self.stale_feature_timeout_secs:
        stale_track_ids.append(track_id)

    if stale_track_ids:
      for track_id in stale_track_ids:
        self.features_for_database_timestamps.pop(track_id, None)
        self._addNewFeaturesToDatabase(track_id)

  def connectDatabase(self):
    self.pool.submit(self.reid_database.connect)
    # Start the process-wide reclaim timer only after a manager intends to use
    # the store. Category trackers call this from run(); the idle root manager
    # does not.
    if (getattr(self.reid_database, 'retentionEnabled', lambda: False)()
        and self._tryAcquirePurgeOwnership()):
      self._startPurgeTimer()
    return

  def _ensureReIDDimensions(self, embedding):
    """
    Infer the ReID embedding dimension from the first observed vector and lazily
    initialize the VDMS descriptor set schema with that dimension.
    On subsequent calls, validate that the embedding dimension is consistent with
    the first observed vector so that mixed-model or mis-configured producers are
    caught early rather than producing silent data corruption in the DB.

    @param   embedding  Decoded ReID embedding (numpy array or list)
    @return  bool       True if the embedding should be used; False if it must be discarded
    """
    # Decoded embeddings from decodeReIDEmbeddingVector are (1, N); reshape(-1)
    # flattens that to (N,) so we get the true element count regardless of shape.
    dim = int(np.asarray(embedding).reshape(-1).shape[0])
    if dim <= 0:
      log.warning(
        f"_ensureReIDDimensions: Skipping empty or zero-length embedding (dim={dim}); "
        "embedding will not be used.")
      return False
    with self._dimensions_lock:
      if self._inferred_dimensions is None:
        log.info(f"Inferred ReID embedding dimensions from first observed vector: {dim}")
        try:
          self.reid_database.ensureSchema(dim)
        except (ValueError, RuntimeError) as err:
          log.error(f"ReID schema initialization failed: {err}")
          return False
        self._inferred_dimensions = dim
        return True
      if dim != self._inferred_dimensions:
        log.warning(
          f"Discarding ReID embedding with inconsistent dimension {dim}; "
          f"expected {self._inferred_dimensions} (inferred from first observed vector). "
          f"Restart the controller to switch ReID models.")
        return False
      return True

  def _extractReidEmbedding(self, sscape_object):
    """
    Extract embedding vector from sscape_object's reid field.
    decodeReIDEmbeddingVector guarantees that embedding_vector is a (1, N)
    numpy array after _decodeReIDVector runs, so no string check is needed here.

    @param   sscape_object  The Scenescape object with detection data
    @return  embedding      The decoded (1, N) ndarray, or None if not available
    """
    try:
      reid = sscape_object.reid
    except AttributeError:
      return None

    if reid is None:
      return None

    # Standard path: dict populated by MovingObject._decodeReIDVector.
    # embedding_vector is always an ndarray (1, N) or None at this point.
    if isinstance(reid, dict):
      return reid.get('embedding_vector', None)

    # Safety net for callers that set reid directly to an ndarray or list.
    if isinstance(reid, (np.ndarray, list)):
      return reid

    return None

  def _extractSemanticMetadata(self, sscape_object):
    """
    Extract semantic metadata attributes from sscape_object.
    Separates generic object properties (confidence, bbox, etc.) from semantic properties.
    Semantic metadata is now organized under a dedicated "metadata" key in the object.
    This includes all semantic attributes describing what an object is (age, gender,
    clothing, etc), separate from internal tracker state.

    Note: Excludes 'reid' key since reid embeddings are used for vector search, not metadata filtering.

    @param   sscape_object  The Scenescape object with detection data
    @return  metadata       Dictionary of semantic attributes (excluding reid)
    """
    if hasattr(sscape_object, 'metadata') and sscape_object.metadata:
      # Filter out 'reid' since it's the embedding vector, not a semantic filter attribute
      metadata = {k: v for k, v in sscape_object.metadata.items() if k != 'reid'}
      log.debug(f"_extractSemanticMetadata: Found {len(metadata)} semantic attributes (excluding reid): {list(metadata.keys())}")
      return metadata
    else:
      log.debug(f"_extractSemanticMetadata: No semantic metadata")
      return {}

  def _extractCameraId(self, sscape_object):
    """
    Extract the camera ID string from a Scenescape object. sscape_object.camera
    holds a Camera or child-Scene object, NOT a plain ID string -- the actual
    identifier is Camera.cameraID or child Scene.uid (mirrors the extraction
    used in TimeChunkedIntelLabsTracking.trackObjects()).

    @param   sscape_object  The current Scenescape object
    @return  str|None       The camera/source ID string, or None if unavailable
    """
    source = getattr(sscape_object, 'camera', None)
    if source is None:
      return None
    return getattr(source, 'cameraID', None) or getattr(source, 'uid', None)

  def pruneInactiveTracks(self, tracked_objects):
    """
    Removes inactive tracks from the active_ids dict.
    Note: Stale feature flushing is now handled by a background timer in _flushStaleFeatures()
    that runs every 1 second and flushes features older than 5 seconds.

    @param  tracked_objects  The objects currently tracked by the tracker
    """
    active_tracks = [tracked_object.id for tracked_object in tracked_objects]

    # Metrics: count of currently active tracked objects/persons, but only
    # for categories confirmed to produce ReID embeddings (e.g. excludes
    # apriltag). Gated on the sticky _category_has_embeddings flag rather
    # than checking each object for a decoded embedding on this exact
    # frame -- embeddings are only attached intermittently per object, so a
    # per-frame check would almost always read as empty even while this
    # category is actively producing embeddings and being matched. Tagged
    # with category so multiple tracked categories (e.g. person + car)
    # don't overwrite each other's values on the same unlabeled series.
    tracked_object_attributes = {'category': self._category} if self._category is not None else None
    category_count = len(active_tracks) if self._category_has_embeddings else 0
    metrics.record_reid_tracked_object_count(category_count, tracked_object_attributes)

    # Report this category's count into the shared registry, then emit the
    # scene-wide total across every category (e.g. person + car combined).
    # Every category-tracker instance does this each cycle, so the total
    # always reflects the latest count from all of them, not just this one.
    if self._category is not None:
      TrackedObjectRegistry.getInstance().updateCategoryCount(
        self.scene_id, self._category, category_count)
      metrics.record_reid_total_tracked_object_count(
        TrackedObjectRegistry.getInstance().getTotalCount(self.scene_id))

    # Normal pruning based on tracker's active tracks
    inactive_tracks = []
    new_active_ids = {}
    with self.active_ids_lock:
      for k, v in self.active_ids.items():
        if k in active_tracks:
          new_active_ids[k] = v
        else:
          inactive_tracks.append((k, v))
      self.active_ids = new_active_ids

    for track_id, data in inactive_tracks:
      self.active_query.pop(track_id, None)
      self.quality_features.pop(track_id, None)
      self.quality_observation_counts.pop(track_id, None)
      self.enrollment_features.pop(track_id, None)
      self.local_enrollment_features.pop(track_id, None)
      self.features_for_database_timestamps.pop(track_id, None)
      # Track never reached a match decision (e.g. reid disabled, insufficient
      # features); discard its start time rather than leaking it forever.
      self.match_latency_tracker.discardTrackStart(track_id)
      self._addNewFeaturesToDatabase(track_id)
    return

  def _addNewFeaturesToDatabase(self, track_id, slice_size=None):
    """
    Add the features when the track is no longer active to reduce the total number of
    queries sent to the database. Also only take a subset of the captured features to
    add to the database otherwise too many features will impede performance of the
    similarity search.

    Features stored with full semantic metadata for flexible querying and future evolution.
    Note: Slice size should be relative to frame rate, but this will only be implemented
    when the tracker is refactored to take into account frame rate.

    @param  track_id    The ID of the track with features to add to the database
    @param  slice_size  The size of the slice to use to reduce the size of the feature list
    """
    if slice_size is None:
      slice_size = self.feature_slice_size
    features = self.features_for_database.pop(track_id, None)
    if not features or not features['reid_vectors']:
      return
    if not self._localEnrollmentAllowed():
      log.warning(
        f"_addNewFeaturesToDatabase: Discarding {len(features['reid_vectors'])} "
        f"features for track {track_id}; local ReID enrollment not allowed "
        f"(enabled={self.reid_enabled}, healthy={self.reid_write_healthy}, "
        f"empty_batch={self.reid_empty_batch_before_confirm})")
      return
    features['reid_vectors'] = features['reid_vectors'][::slice_size]
    persist = features.get('persist', {})
    log.debug(
      f"_addNewFeaturesToDatabase: Adding {len(features['reid_vectors'])} features for track {track_id} to database "
      f"(gid={features['gid']}, category={features['category']}, "
      f"persist_keys={list(persist.keys())})")

    # Extract semantic metadata from stored feature data
    metadata = features.get('metadata', {})
    write_epoch = self.reid_write_epoch

    future = self.pool.submit(
      self._writeReidEntry, write_epoch, features['gid'], track_id,
      features['category'], features['reid_vectors'], persist, metadata)
    future.add_done_callback(self._onReidWriteComplete)

  def _writeReidEntry(self, write_epoch, gid, track_id, category, reid_vectors,
                      persist, metadata):
    """Worker: skip superseded flushes after write-health clears mid-flight."""
    with self._reid_write_lock:
      if (write_epoch != self.reid_write_epoch
          or not self.reid_write_healthy
          or not self.reid_enabled
          or self.reid_empty_batch_before_confirm):
        log.warning(
          f"_writeReidEntry: Skipping superseded ReID write for track {track_id} "
          f"(epoch={write_epoch}, current={self.reid_write_epoch}, "
          f"healthy={self.reid_write_healthy}, enabled={self.reid_enabled}, "
          f"empty_batch={self.reid_empty_batch_before_confirm})")
        raise ReidWriteSupersededError(
          f"superseded ReID write for track {track_id}")
      self.reid_database.addEntry(
        gid, track_id, category, reid_vectors, persist=persist, **metadata)

  def _onReidWriteComplete(self, future):
    """Track whether database writes are succeeding for hierarchy will_enroll claims.

    Write-health is sticky once cleared: a later success must not reclaim
    healthy writes after the parent may already have sole-enrolled under passthrough.
    A first success sets reid_write_confirmed so will_enroll is only claimed after
    the child has proven it can write (confirmed survives later unhealthy so parents
    do not dual-enroll crops already stored). Empty/invalid vector batches before
    the first confirmed write hand off to the parent (passthrough + stop local
    enrollment) instead of forever withholding or racing. Cancelled or superseded
    pool futures leave write-health/confirmed unchanged.
    """
    if future.cancelled():
      log.warning("ReID database write cancelled; leaving write-health unchanged")
      return
    try:
      future.result()
    except ReidWriteSupersededError:
      return
    except ReidNoValidVectorsError as err:
      log.warning(f"ReID database write skipped (no valid vectors): {err}")
      with self._reid_write_lock:
        if not self.reid_write_confirmed:
          self.reid_empty_batch_before_confirm = True
          self.reid_write_epoch += 1
      return
    except concurrent.futures.CancelledError:
      log.warning("ReID database write cancelled; leaving write-health unchanged")
      return
    except ReidPartialWriteError as err:
      with self._reid_write_lock:
        self.reid_write_confirmed = True
        self.reid_empty_batch_before_confirm = False
        if self.reid_write_healthy:
          log.error(
            f"ReID database partial write; confirming stored vectors and "
            f"clearing write-health for hierarchy claims: {err}")
        self.reid_write_healthy = False
        self.reid_write_epoch += 1
      return
    except Exception as err:
      with self._reid_write_lock:
        if self.reid_write_healthy:
          log.error(
            f"ReID database write failed; clearing write-health for hierarchy claims: {err}")
        self.reid_write_healthy = False
        self.reid_write_epoch += 1
      return
    with self._reid_write_lock:
      # Always record a successful write, even if a sibling failure already
      # cleared health — confirmed publish mode prevents parent sole-enroll of
      # crops already stored.
      self.reid_write_confirmed = True
      self.reid_empty_batch_before_confirm = False

  def isNewTrackerID(self, sscape_object):
    """
    Checks if the Tracker ID has been seen before and if it has an ID in the database

    @param  sscape_object  The current Scenescape object
    """
    result = self.active_ids.get(sscape_object.rv_id, None)
    # Track is new only if not yet in active_ids dictionary
    return result is None

  def isEnrollableObservation(self, sscape_object, minimum_bbox_area=None):
    """
    Check whether this scope observed the object via a local camera crop.

    A qualifying pixel-space bounding box marks a detection from a camera on this
    scene. Forwarded embeddings are not locally enrollable by this gate; they may
    still be written through mayContributeEnrollmentEmbedding when vetted (sole
    enrollment on no-match, or cluster enhancement after rematch).

    @param   sscape_object      The Scenescape object to evaluate
    @param   minimum_bbox_area  Optional override for minimum pixel bbox area (px^2)
    @return  bool               True when the embedding is a local enrollable crop
    """
    if minimum_bbox_area is None:
      minimum_bbox_area = self.minimum_bbox_area

    bounding_box_pixels = getattr(sscape_object, 'boundingBoxPixels', None)
    if bounding_box_pixels is None:
      return False
    return bounding_box_pixels.area > minimum_bbox_area

  def isQueryableObservation(self, sscape_object, minimum_bbox_area=None):
    """
    Check whether an embedding may be used to resolve this object's identity.

    Beyond locally observed crops, a scene accepts embeddings a child vetted with its
    own pixel bbox before forwarding them: without those, a parent that re-tracks its
    children has no visual signal at all to merge one person's observations across
    scenes with. An embedding carrying neither a local bbox nor vetted provenance is
    one nobody has vouched for, so it is dropped.

    @param   sscape_object      The Scenescape object to evaluate
    @param   minimum_bbox_area  Optional override for minimum pixel bbox area (px^2)
    @return  bool               True when the embedding may be used for a query
    """
    if self.isEnrollableObservation(sscape_object, minimum_bbox_area):
      return True
    if getattr(sscape_object, 'boundingBoxPixels', None) is not None:
      # Local crop that failed the area gate; forwarding provenance cannot rescue it.
      return False
    return is_vetted_provenance(getattr(sscape_object, 'reid_provenance', None))

  def mayContributeEnrollmentEmbedding(self, sscape_object, minimum_bbox_area=None):
    """
    Check whether an embedding may be stored against a UUID in the shared database.

    Queryable observations may be written unless upstream provenance claims that
    another ReID-enabled scope already enrolled (or will enroll) the crop. Kept as
    a named write-path helper so call sites read as enrollment policy.
    Local enrollment also stops when local enrollment is not allowed
    (unhealthy, empty-batch handoff, or reid disabled) so a parent
    sole-enrolling under passthrough is not racing a continuing child writer.

    @param   sscape_object      The Scenescape object to evaluate
    @param   minimum_bbox_area  Optional override for minimum pixel bbox area (px^2)
    @return  bool               True when the embedding may be written for a UUID
    """
    if not self._localEnrollmentAllowed():
      return False
    if not self.isQueryableObservation(sscape_object, minimum_bbox_area):
      return False
    if is_upstream_enrollment_claim(getattr(sscape_object, 'reid_provenance', None)):
      return False
    return True

  def _isExactRematchScore(self, similarity):
    """True when a rematch score means the query vector(s) are already stored."""
    if similarity is None:
      return False
    try:
      score = float(similarity)
    except (TypeError, ValueError):
      return False
    if not math.isfinite(score):
      return False
    if self._isHigherBetterMetric():
      return math.isclose(score, 1.0, rel_tol=0.0, abs_tol=COSINE_SIMILARITY_TOLERANCE)
    return score <= COSINE_SIMILARITY_TOLERANCE

  def _hasExactEnrollmentEmbedding(self, embeddings, reid_embedding):
    """True when reid_embedding is already present as an exact float32 vector."""
    candidate = np.asarray(reid_embedding, dtype=np.float32).reshape(-1)
    for existing in embeddings:
      if np.array_equal(np.asarray(existing, dtype=np.float32).reshape(-1), candidate):
        return True
    return False

  def _appendUniqueEnrollmentEmbedding(self, embeddings, reid_embedding):
    """Append reid_embedding unless an exact duplicate is already in the list."""
    if self._hasExactEnrollmentEmbedding(embeddings, reid_embedding):
      return False
    embeddings.append(reid_embedding)
    return True

  def gatherQualityVisualFeatures(self, sscape_object, minimum_bbox_area=None):
    """
    This function gathers quality visual features for identifying newly detected objects.
    It currently only uses re-id vectors but can be expanded to include more features.

    Usable embeddings go to quality_features (similarity query; exact duplicates
    omitted so majority vote is not biased). A separate observation count still
    tracks frames toward the query threshold, including repeats of the same vector.
    Embeddings this scene may write also go to enrollment_features (exact-deduped).

    @param  sscape_object          The Scenescape object to gather features from
    @param  minimum_bbox_area      Optional override for minimum pixel bbox area (px^2)
    """
    reid_embedding = self._extractReidEmbedding(sscape_object)
    if reid_embedding is None or not self.reid_enabled:
      return

    if not self._ensureReIDDimensions(reid_embedding):
      return

    if not self.isQueryableObservation(sscape_object, minimum_bbox_area):
      log.debug(
        f"gatherQualityVisualFeatures: Rejected embedding for rv_id={sscape_object.rv_id} "
        f"(no usable pixel bbox and no vetted provenance)")
      return

    self.quality_observation_counts[sscape_object.rv_id] = (
      self.quality_observation_counts.get(sscape_object.rv_id, 0) + 1)
    quality = self.quality_features.setdefault(sscape_object.rv_id, [])
    self._appendUniqueEnrollmentEmbedding(quality, reid_embedding)
    if self.mayContributeEnrollmentEmbedding(sscape_object, minimum_bbox_area):
      enrollment = self.enrollment_features.setdefault(sscape_object.rv_id, [])
      if self._appendUniqueEnrollmentEmbedding(enrollment, reid_embedding):
        if self.isEnrollableObservation(sscape_object, minimum_bbox_area):
          local = self.local_enrollment_features.setdefault(sscape_object.rv_id, [])
          self._appendUniqueEnrollmentEmbedding(local, reid_embedding)
          log.debug(
            f"gatherQualityVisualFeatures: Accepted local embedding for rv_id={sscape_object.rv_id} "
            f"(area={sscape_object.boundingBoxPixels.area:.4f} px^2)")
        else:
          log.debug(
            f"gatherQualityVisualFeatures: Accepted forwarded embedding for rv_id={sscape_object.rv_id} "
            f"(enroll/enhance, provenance={getattr(sscape_object, 'reid_provenance', None)})")
    return

  def _appendEnrollmentEmbedding(self, sscape_object, reid_embedding):
    """
    Add an embedding to the pending database entry for this track (local or vetted
    forwarded), matching multi-camera cluster accumulation after rematch. Exact
    duplicates already pending for the track are skipped.

    @param  sscape_object   The Scenescape object the embedding was taken from
    @param  reid_embedding  The decoded embedding to store
    """
    if not self.mayContributeEnrollmentEmbedding(sscape_object):
      return
    if self.isEnrollableObservation(sscape_object):
      local = self.local_enrollment_features.setdefault(sscape_object.rv_id, [])
      self._appendUniqueEnrollmentEmbedding(local, reid_embedding)
    entry = self.features_for_database.get(sscape_object.rv_id)
    if entry is not None:
      self._appendUniqueEnrollmentEmbedding(entry['reid_vectors'], reid_embedding)
    return

  def pickBestID(self, sscape_object):
    """
    Checks if there is a value for the database ID corresponding to the active track for a
    Scenescape object in the active tracks dictionary. If one does exist, we set the gid and
    similarity of the object to the values in the dictionary. Also updates reid_state if a
    query has been made.

    Also stores semantic metadata for future database storage.

    @param  sscape_object  The current Scenescape object
    """
    # LOOKUP ID IN DICT
    result = self.active_ids.get(sscape_object.rv_id, None)
    # DATABASE ID IS NOT NULL (query has been made and completed)
    if result and result[0] is not None:
      sscape_object.gid = result[0]
      sscape_object.similarity = result[1]

      # Update reid_state based on similarity (whether it was a match or not)
      if sscape_object.reid_state == ReidState.PENDING_COLLECTION:
        # Only update if query has been made (indicated by non-None result[0])
        if result[1] is not None:
          # result[1] has a similarity score, so this was a match
          sscape_object.reid_state = ReidState.MATCHED
        else:
          # result[1] is None, so no match found
          sscape_object.reid_state = ReidState.QUERY_NO_MATCH

      reid_embedding = self._extractReidEmbedding(sscape_object)

      if reid_embedding is not None and self._ensureReIDDimensions(reid_embedding):
        self._appendEnrollmentEmbedding(sscape_object, reid_embedding)
    # DATABASE ID IS NULL (query not yet made or active_ids not yet initialized)
    else:
      sscape_object.similarity = None
    return

  def haveSufficientVisualFeatures(self, sscape_object, minimum_feature_count=None):
    """
    Checks if there are enough visual features to send a query to the database

    @param   sscape_object          The current Scenescape object
    @param   minimum_feature_count  The number of features to collect
    @return  bool                   Returns True if the total number of collected features
                                    for a tracker ID is greater than the minimum value;
                                    otherwise, returns False
    """
    if minimum_feature_count is None:
      minimum_feature_count = self.minimum_feature_count
    count = self.quality_observation_counts.get(sscape_object.rv_id, 0)
    return count >= minimum_feature_count

  def querySimilarity(self, sscape_object):
    """
    Query the database for a match and update the active_ids dictionary. This function is
    mainly used as a wrapper to run the query in its own thread.

    @param  sscape_object  The current Scenescape object
    """
    # Mark that we're about to attempt a query (transition from PENDING_COLLECTION)
    # This allows downstream logic to distinguish "never queried" from "query made"
    start_time = get_epoch_time()
    similarity_scores = self.sendSimilarityQuery(sscape_object)
    database_id, similarity, query_vector_scores = self.parseQueryResults(similarity_scores)
    with self.active_ids_lock:
      # Make sure object is still in active_ids before updating since there is a chance
      # that the similiarity search does not complete until after the object leaves
      if sscape_object.rv_id in self.active_ids:
        self.updateActiveDict(
          sscape_object, database_id, similarity, query_timestamp=start_time,
          query_vector_scores=query_vector_scores)
      else:
        active_snapshot, _ = self._activeIdsSnapshot()
        if database_id is None:
          self._incrementUniqueIdCount()
        # Track left the scene before updateActiveDict could run, but a real
        # match decision was still computed here -- record its latency now
        # rather than silently dropping the measurement.
        camera_count = self._getTotalCameraCount()
        self.match_latency_tracker.recordMatchLatency(
          sscape_object.rv_id, camera_count=camera_count, category=sscape_object.category)
        log.warning(
          f"Track {sscape_object.rv_id} left scene before ID query finished "
          f"query_result_gid={database_id} similarity={similarity} "
          f"active_ids_snapshot={active_snapshot}")
    return

  def sendSimilarityQuery(self, sscape_object, max_query_time=DEFAULT_MAX_QUERY_TIME):
    """
    Sends a 2-tier hybrid search query to the database:
    - TIER 1: Filter by metadata constraints (exact-match on semantic attributes)
    - TIER 2: Vector similarity search on filtered candidates

    Stores the time taken for query completion. If exceeds threshold, disables re-id queries.

    @param   sscape_object  The sscape_object for which similarity scores are to be found
    @return  scores         The similarity scores for the given sscape_object
    """
    reid_vectors = self.quality_features.get(sscape_object.rv_id)

    # Extract semantic metadata for TIER 1 filtering
    metadata_constraints = self._extractSemanticMetadata(sscape_object)

    log.debug(f"sendSimilarityQuery: tracker_id={sscape_object.rv_id}, category={sscape_object.category}, num_vectors={len(reid_vectors) if reid_vectors else 0}, metadata_constraints={list(metadata_constraints.keys())}")

    start_time = get_epoch_time()
    # Pass metadata as constraints for TIER 1 filtering in findMatches
    log.debug(f"sendSimilarityQuery: Calling reid_database.findMatches for track {sscape_object.rv_id}")
    try:
      scores = self.reid_database.findMatches(
        sscape_object.category, reid_vectors,
        k_neighbors=QUERY_K_NEIGHBORS, **metadata_constraints)
      query_time = get_epoch_time() - start_time
      log.debug(f"sendSimilarityQuery: Query completed for track {sscape_object.rv_id} in {query_time:.3f}s, scores={scores}")
    except Exception as e:
      query_time = get_epoch_time() - start_time
      log.error(f"sendSimilarityQuery: Query failed for track {sscape_object.rv_id} after {query_time:.3f}s: {e}")
      scores = []

    with self.similarity_query_times_lock:
      self.similarity_query_times.append(query_time)
      average_query_time = sum(self.similarity_query_times) / len(self.similarity_query_times)
    if average_query_time > max_query_time:
      self._disableReidWrites(
        "average query time exceeding the maximum threshold")

    return scores

  def parseQueryResults(self, similarity_scores, threshold=None):
    """
    Check database for any similar objects and return an ID and similarity score.
    Uses a majority-vote strategy: a candidate UUID must appear in at least half of the
    per-vector best matches that pass the metric-specific threshold test to be accepted.
    When multiple candidates qualify, the one with the best metric value is returned
    according to descriptor semantics (highest for IP/COSINE, lowest for L2).

    Also returns per-vector scores against the winning UUID (parallel to the query
    vector list) so enrollment can skip only exact hits and still enhance with
    near-duplicate views from the same query window.

    @param   similarity_scores  The similarity scores obtained from the database query
    @param   threshold          Similarity threshold interpreted according to metric semantics:
                  - L2-style distance: lower is better, candidate must be < threshold
                  - IP-style score: higher is better, candidate must be > threshold
    @return  database_id           Matched database ID, or None
    @return  similarity            Best score for the matched UUID, or None
    @return  query_vector_scores   Per-query-vector score vs the matched UUID (or None
                                   entries); None when there is no match
    """
    if threshold is None:
      threshold = self.similarity_threshold

    if not self._hasValidSimilarityScoreShape(similarity_scores):
      log.warning(
        "parseQueryResults: Invalid similarity_scores shape; expected list[list[entity]]. "
        f"Received type={type(similarity_scores)}")
      return None, None, None

    if similarity_scores:
      metric_candidates = [self._findBestMetricCandidate(entities)
                           for entities in similarity_scores]
      qualifying_candidates = [(uuid, metric_value) for (uuid, metric_value) in
                               metric_candidates if
                               metric_value is not None and
                               self._isSimilarityMatch(metric_value, threshold)]
      if qualifying_candidates:
        counter = collections.Counter(item[0] for item in qualifying_candidates)
        most_common_uuid, count = counter.most_common(1)[0]
        if count >= (len(metric_candidates) / 2):
          similarity = self._pickBestMetricValue(
            [item[1] for item in qualifying_candidates if item[0] == most_common_uuid])
          query_vector_scores = [
            self._bestScoreForUuid(entities, most_common_uuid)
            for entities in similarity_scores]
          return most_common_uuid, similarity, query_vector_scores

    return None, None, None

  def _bestScoreForUuid(self, entities, target_uuid):
    """Best metric score among entities for target_uuid, or None if absent."""
    if not entities or target_uuid is None:
      return None
    metric = getattr(self.reid_database, 'similarity_metric', None)
    best = None
    for entity in entities:
      if str(entity.get('uuid')) != str(target_uuid):
        continue
      score = normalize_similarity_score(entity.get('_distance'), metric)
      if score is None:
        continue
      if best is None:
        best = score
      elif is_higher_better_metric(metric):
        if score > best:
          best = score
      elif score < best:
        best = score
    return best

  def _hasValidSimilarityScoreShape(self, similarity_scores):
    """Validate that query results follow the strict list-of-lists contract."""
    if not similarity_scores:
      return True

    if not isinstance(similarity_scores, list):
      return False

    return all(isinstance(item, list) for item in similarity_scores)

  def _isHigherBetterMetric(self):
    """Return True when the configured descriptor metric uses higher-is-better semantics."""
    metric = getattr(self.reid_database, 'similarity_metric', None)
    if metric is None:
      return False
    return is_higher_better_metric(metric)

  def _isSimilarityMatch(self, metric_value, threshold):
    """Evaluate threshold semantics according to the active descriptor metric."""
    metric = getattr(self.reid_database, 'similarity_metric', None)
    return is_similarity_match(metric_value, threshold, metric)

  def _pickBestMetricValue(self, metric_values):
    """Pick best metric value according to descriptor metric semantics."""
    metric = getattr(self.reid_database, 'similarity_metric', None)
    return pick_best_metric_value(metric_values, metric)

  def _findBestMetricCandidate(self, entities):
    """
    Find the best candidate uuid and metric value according to descriptor semantics.

    The best match is selected from the provided entities based on the configured
    descriptor metric semantics: higher values are better for higher-is-better
    metrics, and lower values are better otherwise.

    Structure of entities:
    [{'uuid': <UUID>, 'rvid': <TRACKER_ID>, '_distance': <SIMILARITY_SCORE>}, ...]
    """
    metric = getattr(self.reid_database, 'similarity_metric', None)
    is_higher_better = is_higher_better_metric(metric)
    if entities:
      filtered_entities = []
      for entity in entities:
        metric_value = normalize_similarity_score(entity.get('_distance'), metric)
        if metric_value is None:
          if is_higher_better and entity.get('_distance') is not None:
            log.warning(
              f"Ignoring out-of-range IP similarity score {entity.get('_distance')} "
              f"for uuid={entity.get('uuid')}")
          continue
        if entity.get('uuid') is None:
          log.warning(
            f"Ignoring candidate with missing uuid (distance={metric_value}); "
            "cannot attribute this match to an identity")
          continue
        filtered_entities.append({**entity, '_distance': metric_value})

      if not filtered_entities:
        return (None, None)

      if is_higher_better:
        best_entity = max(filtered_entities, key=lambda x: x['_distance'])
      else:
        best_entity = min(filtered_entities, key=lambda x: x['_distance'])
      return (best_entity['uuid'], best_entity['_distance'])
    return (None, None)

  def _activeGidIndex(self):
    """
    Build an index of non-null gids to active rv_ids.
    Must be called while holding self.active_ids_lock.
    """
    gid_index = {}
    for rv_id, values in self.active_ids.items():
      gid = values[0]
      if gid is not None:
        gid_index.setdefault(gid, []).append(rv_id)
    return gid_index

  def _logLiveGidIntegrity(self, source, rv_id):
    """
    Log whether any live active tracks currently share the same gid.
    Must be called while holding self.active_ids_lock.
    """
    gid_index = self._activeGidIndex()
    duplicate_gids = {gid: rv_ids for gid, rv_ids in gid_index.items() if len(rv_ids) > 1}
    if duplicate_gids:
      log.error(
        f"live-gid-collision "
        f"source={source} rv_id={rv_id} duplicate_gids={duplicate_gids} "
        f"active_ids_snapshot={self.active_ids}"
      )
    else:
      pass

  def _activeIdsSnapshot(self):
    """
    Return a compact snapshot of active rv_id->gid and duplicate gid holders.
    Must be called while holding self.active_ids_lock.
    """
    snapshot = {rv_id: values[0] for rv_id, values in self.active_ids.items()}
    gid_index = self._activeGidIndex()
    duplicate_gids = {gid: rv_ids for gid, rv_ids in gid_index.items() if len(rv_ids) > 1}
    return snapshot, duplicate_gids

  def _queryEmbeddingIsExactHit(self, rv_id, reid_embedding, query_vector_scores, similarity):
    """True when reid_embedding's aligned query score is exact (or aggregate fallback)."""
    if query_vector_scores is not None:
      quality = self.quality_features.get(rv_id, [])
      candidate = np.asarray(reid_embedding, dtype=np.float32).reshape(-1)
      for idx, vec in enumerate(quality):
        if idx >= len(query_vector_scores):
          break
        if np.array_equal(np.asarray(vec, dtype=np.float32).reshape(-1), candidate):
          return self._isExactRematchScore(query_vector_scores[idx])
      return False
    return self._isExactRematchScore(similarity)

  def _enrollmentVectorsForMatch(self, rv_id, similarity, query_vector_scores):
    """
    Build the pending write list after a rematch.

    Always keep local camera crops. Skip query vectors with no score against the
    matched UUID (absent from the neighbor list) so they cannot pollute another
    identity's cluster. Skip exact per-vector hits; near matches still enhance.
    When per-vector scores are unavailable, fall back to aggregate exact → locals
    only.
    """
    reid_vectors = []
    for local_vec in self.local_enrollment_features.get(rv_id, []):
      self._appendUniqueEnrollmentEmbedding(reid_vectors, local_vec)

    enrollment = self.enrollment_features.get(rv_id, [])
    if query_vector_scores is not None:
      quality = self.quality_features.get(rv_id, [])
      for idx, vec in enumerate(quality):
        score = query_vector_scores[idx] if idx < len(query_vector_scores) else None
        if score is None or self._isExactRematchScore(score):
          continue
        if not self._hasExactEnrollmentEmbedding(enrollment, vec):
          continue
        self._appendUniqueEnrollmentEmbedding(reid_vectors, vec)
      return reid_vectors

    if self._isExactRematchScore(similarity):
      return reid_vectors
    for vec in enrollment:
      self._appendUniqueEnrollmentEmbedding(reid_vectors, vec)
    return reid_vectors

  def _getTotalCameraCount(self):
    """
    Return the current total camera count for this UUIDManager's scene,
    from the shared CameraRegistry (see camera_registry.py). True and
    dynamic -- reflects additions and deletions immediately, since Scene
    writes into the registry directly whenever its camera list changes.

    @return  int  Current camera count for this scene, or 0 if this
                  UUIDManager hasn't been assigned a scene_id yet
    """
    return CameraRegistry.getInstance().getCameraCount(self.scene_id)

  def updateActiveDict(self, sscape_object, database_id, similarity, query_timestamp=None,
                       query_vector_scores=None):
    """
    Updates the dictionary tracking the active tracker IDs and their corresponding database
    IDs. Also creates an entry in the features_for_database dictionary with semantic metadata
    to be added to the database when the track leaves the scene.

    @param  sscape_object         The current Scenescape object
    @param  database_id           The ID from the database (or newly generated if no match)
    @param  similarity            The similarity score from the database (None if no match)
    @param  query_timestamp       When the query was initiated
    @param  query_vector_scores   Per-query-vector scores vs the matched UUID (optional)
    """
    if query_timestamp is None:
      query_timestamp = get_epoch_time()
    # Record the end-to-end per-match latency now that a real decision has
    # been reached for this track (matched or not).
    camera_count = self._getTotalCameraCount()
    self.match_latency_tracker.recordMatchLatency(
      sscape_object.rv_id, query_timestamp, camera_count=camera_count, category=sscape_object.category)
    previous_gid = sscape_object.gid
    gid_index = self._activeGidIndex()
    current_holders = gid_index.get(database_id, []) if database_id is not None else []
    matched_new_id = (
      database_id is not None
      and self.isNewID(database_id)
      and similarity is not None
    )
    database_id_collision = database_id is not None and bool(current_holders)

    if database_id is not None and current_holders:
      log.warning(
        f"updateActiveDict candidate-gid-already-live "
        f"rv_id={sscape_object.rv_id} candidate_gid={database_id} "
        f"current_holders={current_holders} similarity={similarity}"
      )

    # MATCH FOUND - YES + DB ID ALREADY IN DICT - NO
    if matched_new_id:
      # Query succeeded and found a match -> update state to MATCHED
      log.debug(f"updateActiveDict: REID MATCH rv_id={sscape_object.rv_id} "
              f"matched_gid={database_id} similarity={similarity} "
              f"current_persist={sscape_object.chain_data.persist if sscape_object.chain_data else 'NO CHAIN DATA'}")
      sscape_object.reid_state = ReidState.MATCHED
      sscape_object.gid = database_id
      sscape_object.similarity = similarity
      # Store the old gid only when gid transitions; chain tracks historical ids.
      if previous_gid is not None and previous_gid != database_id:
        sscape_object.save_previous_object_id(previous_gid, similarity_score=similarity,
                                       timestamp=query_timestamp)

      historical_persist = self.reid_database.getPersistedAttributes(database_id)
      log.debug(f"updateActiveDict: historical_persist for gid={database_id}: {historical_persist}")
      if historical_persist and sscape_object.chain_data:
        for attr, value in historical_persist.items():
          if sscape_object.chain_data.persist.get(attr) is None:
            sscape_object.chain_data.persist[attr] = value
        log.debug(f"updateActiveDict: merged persist={sscape_object.chain_data.persist}")

      log.debug(
        f"updateActiveDict: Match found for {sscape_object.rv_id}: {database_id}, similarity={similarity}, state={ReidState.MATCHED.value}")
      self.active_ids[sscape_object.rv_id] = [database_id, similarity]

      reid_embedding = self._extractReidEmbedding(sscape_object)
      if (
          reid_embedding is not None
          and not self._queryEmbeddingIsExactHit(
            sscape_object.rv_id, reid_embedding, query_vector_scores, similarity)
      ):
        self._appendEnrollmentEmbedding(sscape_object, reid_embedding)

    # MATCH FOUND - NO / NEW OBJECT
    else:
      if database_id_collision:
        log.warning(
          f"updateActiveDict: Database ID collision for track {sscape_object.rv_id}: "
          f"{database_id} is already assigned to another active track; treating as no-match")
      # Query made but no match -> state is now QUERY_NO_MATCH (distinguishes from PENDING_COLLECTION)
      sscape_object.reid_state = ReidState.QUERY_NO_MATCH
      # Keep a unique gid if one already exists for this object, otherwise generate one.
      if sscape_object.gid is not None and self.isNewID(sscape_object.gid):
        database_id = sscape_object.gid
      else:
        while True:
          with MovingObject.gid_lock:
            database_id = MovingObject.gid_counter
            MovingObject.gid_counter += 1
          if self.isNewID(database_id):
            break
          log.warning(
            f"updateActiveDict generated-gid-collision "
            f"rv_id={sscape_object.rv_id} candidate_gid={database_id} "
            f"active_ids_snapshot={self.active_ids}"
          )
      sscape_object.gid = database_id
      sscape_object.similarity = None
      # Store the old gid only when gid transitions; chain tracks historical ids.
      if previous_gid is not None and previous_gid != database_id:
        sscape_object.save_previous_object_id(previous_gid, similarity_score=None,
                                       timestamp=query_timestamp)

      # Increment counter for unique objects with actual query attempts that found no match
      self._incrementUniqueIdCount()
      log.debug(f"updateActiveDict: No match, assigned new gid={database_id} for track {sscape_object.rv_id}, state={ReidState.QUERY_NO_MATCH.value}")
      self.active_ids[sscape_object.rv_id] = [sscape_object.gid, None]

    self._logLiveGidIntegrity("updateActiveDict", sscape_object.rv_id)

    persist_attrs = (
      sscape_object.chain_data.persist.copy()
      if sscape_object.chain_data and isinstance(sscape_object.chain_data.persist, dict)
      else {}
    )

    if not self.reid_write_healthy:
      return

    # Local and vetted forwarded crops land in enrollment_features at gather time.
    # On no-match with an empty set, promote quality_features so sole enrollment
    # still works — unless upstream claimed will_enroll/enrolled (child owns the write).
    # On rematch, keep locals and any non-exact query vectors so one
    # exact hit in a multi-vector query does not drop near-duplicate enhancements.
    reid_vectors = self.enrollment_features.setdefault(sscape_object.rv_id, [])
    if matched_new_id:
      reid_vectors = self._enrollmentVectorsForMatch(
        sscape_object.rv_id, similarity, query_vector_scores)
      log.debug(
        f"updateActiveDict: Rematch enrollment for track {sscape_object.rv_id}: "
        f"{len(reid_vectors)} vector(s) after per-vector exact skip")
    elif not reid_vectors and not is_upstream_enrollment_claim(
        getattr(sscape_object, 'reid_provenance', None)):
      for promoted in self.quality_features.get(sscape_object.rv_id, []):
        self._appendUniqueEnrollmentEmbedding(reid_vectors, promoted)
      if reid_vectors:
        log.debug(
          f"updateActiveDict: Promoted {len(reid_vectors)} unique query feature(s) "
          f"for enrollment on no-match track {sscape_object.rv_id}")

    entry = {
      'gid': sscape_object.gid,
      'category': sscape_object.category,
      'reid_vectors': reid_vectors,
      'metadata': self._extractSemanticMetadata(sscape_object),
      }

    if persist_attrs:
      entry['persist'] = {**persist_attrs, 'timestamp': sscape_object.when}

    # Store features with semantic metadata for TIER 1 filtering in future queries
    num_features = len(entry['reid_vectors'])
    log.debug(f"updateActiveDict: Storing {num_features} enrollment feature(s) for track "
              f"{sscape_object.rv_id} to features_for_database")
    self.features_for_database[sscape_object.rv_id] = entry
    log.debug(f"updateActiveDict: Storing features for rv_id={sscape_object.rv_id} "
        f"gid={sscape_object.gid} "
        f"persist_in_features_for_database={'persist' in self.features_for_database[sscape_object.rv_id]}")

    self.features_for_database_timestamps[sscape_object.rv_id] = get_epoch_time()
    return

  def getMatchLatencyStats(self):
    """
    Return summary stats over the most recently recorded per-match latencies,
    for downstream metrics consumers (e.g. dashboards, exporters, health checks).

    @return  dict  {'average': float|None, 'min': float|None, 'max': float|None, 'camera_count': int|None}
    """
    return self.match_latency_tracker.getStats()

  def isNewID(self, database_id):
    """
    Checks if the specified database ID already is matched with an existing tracker ID

    @param   database_id  An ID retrieved from the database
    @return  bool         Returns True if the ID is not found; otherwise, returns False
    """
    database_ids = [v[0] for v in self.active_ids.values()]
    return database_id not in database_ids

  def _onQuerySimilarityComplete(self, future):
    """Log unhandled exceptions from querySimilarity so a background failure
    doesn't silently leave a track stuck in PENDING_COLLECTION forever."""
    if future.cancelled():
      return

    try:
      future.result()
    except Exception as err:
      log.error(f"querySimilarity failed with an unhandled exception: {err}", exc_info=True)

  def assignID(self, sscape_object):
    """
    Assigns a unique ID to the Scenescape object

    @param  sscape_object  The current Scenescape object
    """
    is_new = self.isNewTrackerID(sscape_object)
    self._category = sscape_object.category

    reid_embedding = self._extractReidEmbedding(sscape_object)
    if reid_embedding is not None:
      self._category_has_embeddings = True
      CameraRegistry.getInstance().recordEmbeddingObserved(
        self.scene_id, self._extractCameraId(sscape_object))

    # Initialize tracking entry for new tracks
    if is_new:
      has_reid_embedding = reid_embedding is not None

      # Case for incrementing the counter when there is no re-id vector
      # When reid is disabled, or there is no usable embedding vector,
      # this track will not be matched and should contribute to unique_id_count.
      if not self.reid_enabled or not has_reid_embedding:
        self._incrementUniqueIdCount()
      with self.active_ids_lock:
        self.active_ids.setdefault(sscape_object.rv_id, [None, None])
      # Start the per-match latency clock for this track.
      self.match_latency_tracker.markTrackStart(sscape_object.rv_id)

    # If reid is disabled, mark object state immediately (no query will be made)
    if not self.reid_enabled:
      sscape_object.reid_state = ReidState.REID_DISABLED

    # Continue gathering features until we have enough or query is already submitted
    if sscape_object.rv_id not in self.active_query and self.reid_enabled:
      self.gatherQualityVisualFeatures(sscape_object)
      sufficient_features = self.haveSufficientVisualFeatures(sscape_object)
      feature_count = self.quality_observation_counts.get(sscape_object.rv_id, 0)
      log.debug(
        f"assignID: rv_id={sscape_object.rv_id}, sufficient_features={sufficient_features}, "
        f"observation_count={feature_count}, unique_query_vectors="
        f"{len(self.quality_features.get(sscape_object.rv_id, []))}")

      # Submit query once we have enough features
      if sufficient_features:
        log.debug(f"assignID: Submitting similarity query for rv_id={sscape_object.rv_id}")
        self.active_query[sscape_object.rv_id] = True
        future = self.pool.submit(self.querySimilarity, sscape_object)
        future.add_done_callback(self._onQuerySimilarityComplete)
    # Always pick best ID for the current frame
    self.pickBestID(sscape_object)
    return
