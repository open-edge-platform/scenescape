# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import collections
import concurrent.futures
import threading
import time

from controller.vdms_adapter import VDMSDatabase
from controller.moving_object import ReidState, MovingObject
from scene_common import log
from scene_common.timestamp import get_epoch_time

DEFAULT_DATABASE = "VDMS"
DEFAULT_SIMILARITY_THRESHOLD = 60
DEFAULT_MINIMUM_BBOX_AREA = 5000
DEFAULT_MINIMUM_FEATURE_COUNT = 12
DEFAULT_FEATURE_SLICE_SIZE = 10
DEFAULT_MAX_QUERY_TIME = 4
DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED = 10
DEFAULT_STALE_FEATURE_TIMEOUT_SECS = 5.0
DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS = 1.0
available_databases = {
  "VDMS": VDMSDatabase,
}

class UUIDManager:
  def __init__(self, database=DEFAULT_DATABASE, reid_config_data=None):
    self.active_ids = {}
    self.active_ids_lock = threading.Lock()
    self.active_query = {}
    self.features_for_database = {}
    self.features_for_database_timestamps = {}  # Track when features were added
    self.quality_features = {}
    self.unique_id_count = 0
    self.reid_database = available_databases[database]()
    self.pool = concurrent.futures.ThreadPoolExecutor()
    self.similarity_query_times = collections.deque(
      maxlen=DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED)
    self.similarity_query_times_lock = threading.Lock()
    self.reid_enabled = True
    # Extract stale feature timeout from reid config, use default if not provided
    if reid_config_data is None:
      reid_config_data = {}
    self.stale_feature_timeout_secs = reid_config_data.get('stale_feature_timeout_secs', DEFAULT_STALE_FEATURE_TIMEOUT_SECS)
    self.stale_feature_check_interval_secs = reid_config_data.get('stale_feature_check_interval_secs', DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS)
    self.minimum_feature_count = reid_config_data.get('feature_accumulation_threshold', DEFAULT_MINIMUM_FEATURE_COUNT)
    self.similarity_threshold = reid_config_data.get('similarity_threshold', DEFAULT_SIMILARITY_THRESHOLD)
    self.stale_feature_timer = None
    self._start_stale_feature_timer()
    return

  def __del__(self):
    """Clean up resources when the UUIDManager is destroyed"""
    self.shutdown()

  def shutdown(self):
    """Explicitly stop the stale feature timer and clean up resources"""
    if self.stale_feature_timer is not None:
      self.stale_feature_timer.cancel()
      self.stale_feature_timer = None
    if hasattr(self, 'pool') and self.pool is not None:
      self.pool.shutdown(wait=False)

  def _start_stale_feature_timer(self):
    """Start a background timer to periodically check for and flush stale features"""
    def check_stale_features():
      """Timer callback: check for features older than timeout and flush them"""
      self._flush_stale_features()
      # Reschedule the timer
      self._schedule_timer(check_stale_features)

    self._schedule_timer(check_stale_features)

  def _schedule_timer(self, callback):
    """Create and start a daemon timer with the configured check interval"""
    self.stale_feature_timer = threading.Timer(self.stale_feature_check_interval_secs, callback)
    self.stale_feature_timer.daemon = True
    self.stale_feature_timer.start()

  def _flush_stale_features(self):
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

  def _extractReidEmbedding(self, sscape_object):
    """
    Extract embedding vector from sscape_object's reid field.
    Returns the decoded embedding vector (numpy array or list), not the base64 string.
    Handles both formats:
    1. New format: dict with 'embedding_vector' and 'model_name' keys
    2. Legacy format: direct vector (list or numpy array)

    @param   sscape_object  The Scenescape object with detection data
    @return  embedding      The decoded embedding vector (numpy array or list), or None if not available
    """
    try:
      reid = sscape_object.reid
    except AttributeError:
      return None

    if reid is None:
      return None

    # New format: dict with 'embedding_vector' key
    if isinstance(reid, dict):
      embedding = reid.get('embedding_vector', None)
      # Only return if it's already decoded (numpy array or list, not a string)
      if embedding is not None and not isinstance(embedding, str):
        return embedding
      return None

    # Legacy format: direct vector (list or numpy array)
    # Return if it's not a dict and not a string
    if not isinstance(reid, str) and not isinstance(reid, dict):
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

  def pruneInactiveTracks(self, tracked_objects):
    """
    Removes inactive tracks from the active_ids dict.
    Note: Stale feature flushing is now handled by a background timer in _flush_stale_features()
    that runs every 1 second and flushes features older than 5 seconds.

    @param  tracked_objects  The objects currently tracked by the tracker
    """
    active_tracks = [tracked_object.id for tracked_object in tracked_objects]
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
      self.features_for_database_timestamps.pop(track_id, None)
      self._addNewFeaturesToDatabase(track_id)
    return

  def _addNewFeaturesToDatabase(self, track_id, slice_size=DEFAULT_FEATURE_SLICE_SIZE):
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
    features = self.features_for_database.pop(track_id, None)
    if features:
      features['reid_vectors'] = features['reid_vectors'][::slice_size]
      log.debug(
        f"_addNewFeaturesToDatabase: Adding {len(features['reid_vectors'])} features for track {track_id} to database (gid={features['gid']}, category={features['category']})")

      # Extract semantic metadata from stored feature data
      metadata = features.get('metadata', {})

      self.pool.submit(self.reid_database.addEntry, features['gid'], track_id,
                       features['category'], features['reid_vectors'], **metadata)

  def isNewTrackerID(self, sscape_object):
    """
    Checks if the Tracker ID has been seen before and if it has an ID in the database

    @param  sscape_object  The current Scenescape object
    """
    result = self.active_ids.get(sscape_object.rv_id, None)
    # Track is new only if not yet in active_ids dictionary
    return result is None

  def gatherQualityVisualFeatures(self, sscape_object,
                                  minimum_bbox_area=DEFAULT_MINIMUM_BBOX_AREA):
    """
    This function gathers quality visual features for identifying newly detected objects.
    It currently only uses re-id vectors but can be expanded to include more features.

    @param  sscape_object        The Scenescape object to gather features from
    @param  minimum_bbox_area    The minimum size of the bbox for the detected object (px)
    """
    reid_embedding = self._extractReidEmbedding(sscape_object)

    if reid_embedding is not None and self.reid_enabled:
      bbox_area = sscape_object.boundingBoxPixels.area if hasattr(sscape_object, 'boundingBoxPixels') else 0
      if bbox_area > minimum_bbox_area:
        if sscape_object.rv_id in self.quality_features:
          self.quality_features[sscape_object.rv_id].append(reid_embedding)
        else:
          self.quality_features[sscape_object.rv_id] = [reid_embedding]
        log.debug(f"gatherQualityVisualFeatures: Accepted embedding for rv_id={sscape_object.rv_id} (area={bbox_area:.2f})")
      else:
        log.debug(f"gatherQualityVisualFeatures: Bbox too small for rv_id={sscape_object.rv_id} (area={bbox_area} <= {minimum_bbox_area})")
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

      if reid_embedding is not None:
        if sscape_object.rv_id in self.features_for_database:
          self.features_for_database[sscape_object.rv_id]['reid_vectors'].append(
            reid_embedding)
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
    count = len(self.quality_features.get(sscape_object.rv_id, []))
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
    database_id, similarity = self.parseQueryResults(similarity_scores)
    with self.active_ids_lock:
      # Make sure object is still in active_ids before updating since there is a chance
      # that the similiarity search does not complete until after the object leaves
      if sscape_object.rv_id in self.active_ids:
        self.updateActiveDict(sscape_object, database_id, similarity, query_timestamp=start_time)
      else:
        active_snapshot, _ = self._active_ids_snapshot_locked()
        log.warning(
          f"Track {sscape_object.rv_id} left scene before ID query finished "
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
        sscape_object.category, reid_vectors, **metadata_constraints)
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
      self.reid_enabled = False
      log.error("Disabling reid due to average query time exceeding the maximum threshold")

    return scores

  def parseQueryResults(self, similarity_scores, threshold=None):
    """
    Check database for any similar objects and return an ID and similarity score.
    The threshold value is used as the deciding criteria for close matches.

    @param   similarity_scores  The similarity scores obtained from the database query
    @param   threshold          The maximum difference between the Re-ID vectors which would
                                still be considered a valid match
    @return  database_id        Returns the ID of the matched entry from the database if one
                                is found; otherwise, returns None
    @return  similarity         Distance between the Re-ID vectors for the object and the
                                matched entry if it is found; otherwise, return None
    """
    if threshold is None:
      threshold = self.similarity_threshold

    if similarity_scores:
      minimum_distances = [self._findMinimumDistance(entities)
                           for entities in similarity_scores]
      distances_below_threshold = [(uuid, distance) for (uuid, distance) in
                                   minimum_distances if
                                   distance is not None and distance < threshold]
      if distances_below_threshold:
        counter = collections.Counter(item[0] for item in distances_below_threshold)
        most_common_uuid, count = counter.most_common(1)[0]
        if count >= (len(minimum_distances) / 2):
          similarity = min(item[1] for item in distances_below_threshold
                           if item[0] == most_common_uuid)
          return most_common_uuid, similarity
    return None, None

  def _findMinimumDistance(self, entities):
    """
    Find the uuid with the minimum distance and the corresponding distance value

    Sctructure of entities:
    [{'uuid': <UUID>, 'rvid': <TRACKER_ID>, '_distance': <SIMILARITY_SCORE>}, ...]
    """
    if entities:
      minimum_distance_entity = min(entities, key=lambda x: x['_distance'])
      return (minimum_distance_entity['uuid'], minimum_distance_entity['_distance'])
    return (None, None)

  def _active_gid_index_locked(self):
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

  def _log_live_gid_integrity_locked(self, source, rv_id):
    """
    Log whether any live active tracks currently share the same gid.
    Must be called while holding self.active_ids_lock.
    """
    gid_index = self._active_gid_index_locked()
    duplicate_gids = {gid: rv_ids for gid, rv_ids in gid_index.items() if len(rv_ids) > 1}
    if duplicate_gids:
      log.error(
        f"live-gid-collision "
        f"source={source} rv_id={rv_id} duplicate_gids={duplicate_gids} "
        f"active_ids_snapshot={self.active_ids}"
      )
    else:
      pass

  def _active_ids_snapshot_locked(self):
    """
    Return a compact snapshot of active rv_id->gid and duplicate gid holders.
    Must be called while holding self.active_ids_lock.
    """
    snapshot = {rv_id: values[0] for rv_id, values in self.active_ids.items()}
    gid_index = self._active_gid_index_locked()
    duplicate_gids = {gid: rv_ids for gid, rv_ids in gid_index.items() if len(rv_ids) > 1}
    return snapshot, duplicate_gids

  def updateActiveDict(self, sscape_object, database_id, similarity, query_timestamp=None):
    """
    Updates the dictionary tracking the active tracker IDs and their corresponding database
    IDs. Also creates an entry in the features_for_database dictionary with semantic metadata
    to be added to the database when the track leaves the scene.

    Updates object's reid_state and records ID changes in previous_ids_chain for post-mortem
    stitching analysis.

    @param  sscape_object    The current Scenescape object
    @param  database_id      The ID from the database (or newly generated if no match)
    @param  similarity       The similarity score from the database (None if no match)
    @param  query_timestamp  When the query was initiated (for chain recording)
    """
    if query_timestamp is None:
      query_timestamp = get_epoch_time()

    gid_index = self._active_gid_index_locked()
    current_holders = gid_index.get(database_id, []) if database_id is not None else []
    matched_new_id = database_id is not None and self.isNewID(database_id)
    database_id_collision = database_id is not None and not matched_new_id

    if database_id is not None and current_holders:
      log.warning(
        f"updateActiveDict candidate-gid-already-live "
        f"rv_id={sscape_object.rv_id} candidate_gid={database_id} "
        f"current_holders={current_holders} similarity={similarity}"
      )

    # MATCH FOUND - YES + DB ID ALREADY IN DICT - NO
    if matched_new_id:
      # Query succeeded and found a match -> update state to MATCHED
      sscape_object.reid_state = ReidState.MATCHED
      sscape_object.gid = database_id
      sscape_object.similarity = similarity
      # Record the matched ID in chain with similarity score
      sscape_object.record_id_change(database_id, similarity_score=similarity, timestamp=query_timestamp)

      log.debug(
        f"updateActiveDict: Match found for {sscape_object.rv_id}: {database_id}, similarity={similarity}, state={ReidState.MATCHED.value}")
      self.active_ids[sscape_object.rv_id] = [database_id, similarity]

      reid_embedding = self._extractReidEmbedding(sscape_object)
      if reid_embedding is not None:
        if sscape_object.rv_id in self.features_for_database:
          self.features_for_database[sscape_object.rv_id]['reid_vectors'].append(
            reid_embedding)

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
      # Record the new ID in chain with no match (None similarity indicates no match)
      sscape_object.record_id_change(database_id, similarity_score=None, timestamp=query_timestamp)

      # Increment counter for unique objects with actual query attempts that found no match
      self.unique_id_count += 1
      log.debug(f"updateActiveDict: No match, assigned new gid={database_id} for track {sscape_object.rv_id}, state={ReidState.QUERY_NO_MATCH.value}")
      self.active_ids[sscape_object.rv_id] = [sscape_object.gid, None]

    self._log_live_gid_integrity_locked("updateActiveDict", sscape_object.rv_id)

    # Store features with semantic metadata for TIER 1 filtering in future queries
    num_features = len(self.quality_features.get(sscape_object.rv_id, []))
    log.debug(f"updateActiveDict: Storing {num_features} features for track {sscape_object.rv_id} to features_for_database")
    self.features_for_database[sscape_object.rv_id] = {
      'gid': sscape_object.gid,
      'category': sscape_object.category,
      'reid_vectors': self.quality_features[sscape_object.rv_id],
      'metadata': self._extractSemanticMetadata(sscape_object)
    }
    self.features_for_database_timestamps[sscape_object.rv_id] = time.time()  # Record when added
    return

  def isNewID(self, database_id):
    """
    Checks if the specified database ID already is matched with an existing tracker ID

    @param   database_id  An ID retrieved from the database
    @return  bool         Returns True if the ID is not found; otherwise, returns False
    """
    database_ids = [v[0] for v in self.active_ids.values()]
    return database_id not in database_ids

  def assignID(self, sscape_object):
    """
    Assigns a unique ID to the Scenescape object

    @param  sscape_object  The current Scenescape object
    """
    is_new = self.isNewTrackerID(sscape_object)

    # Initialize tracking entry for new tracks
    if is_new:
      has_reid_embedding = self._extractReidEmbedding(sscape_object) is not None

      # Case for incrementing the counter when there is no re-id vector
      # When reid is disabled, or there is no usable embedding vector,
      # this track will not be matched and should contribute to unique_id_count.
      if not self.reid_enabled or not has_reid_embedding:
        self.unique_id_count += 1
      with self.active_ids_lock:
        self.active_ids.setdefault(sscape_object.rv_id, [None, None])

    # If reid is disabled, mark object state immediately (no query will be made)
    if not self.reid_enabled:
      sscape_object.reid_state = ReidState.REID_DISABLED

    # Continue gathering features until we have enough or query is already submitted
    if sscape_object.rv_id not in self.active_query and self.reid_enabled:
      self.gatherQualityVisualFeatures(sscape_object)
      sufficient_features = self.haveSufficientVisualFeatures(sscape_object)
      feature_count = len(self.quality_features.get(sscape_object.rv_id, []))
      log.debug(f"assignID: rv_id={sscape_object.rv_id}, sufficient_features={sufficient_features}")

      # Submit query once we have enough features
      if sufficient_features:
        log.debug(f"assignID: Submitting similarity query for rv_id={sscape_object.rv_id}")
        self.active_query[sscape_object.rv_id] = True
        self.pool.submit(self.querySimilarity, sscape_object)

    # Always pick best ID for the current frame
    self.pickBestID(sscape_object)
    return
