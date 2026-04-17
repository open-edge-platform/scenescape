# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import collections
import concurrent.futures
import threading
import time

import numpy as np

from controller.vdms_adapter import VDMSDatabase
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
    # ReID embedding dimensions are inferred from the first observed embedding.
    if reid_config_data is None:
      reid_config_data = {}
    self._inferred_dimensions = None
    self._dimensions_lock = threading.Lock()
    self.reid_database = available_databases[database](dimensions=None)
    self.pool = concurrent.futures.ThreadPoolExecutor()
    self.similarity_query_times = collections.deque(
      maxlen=DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED)
    self.similarity_query_times_lock = threading.Lock()
    self.reid_enabled = True
    # Extract stale feature timeout from reid config, use default if not provided
    self.stale_feature_timeout_secs = reid_config_data.get('stale_feature_timeout_secs', DEFAULT_STALE_FEATURE_TIMEOUT_SECS)
    self.stale_feature_check_interval_secs = reid_config_data.get('stale_feature_check_interval_secs', DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS)
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
      # Increment the unique id counter for tracks where no match was found (similarity=None)
      if data[1] is None:
        self.unique_id_count += 1
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
      if not self._ensureReIDDimensions(reid_embedding):
        return
      bbox_area = sscape_object.boundingBoxPixels.area if hasattr(sscape_object, 'boundingBoxPixels') else 0
      if bbox_area > minimum_bbox_area:
        if sscape_object.rv_id in self.quality_features:
          self.quality_features[sscape_object.rv_id].append(reid_embedding)
        else:
          self.quality_features[sscape_object.rv_id] = [reid_embedding]
      else:
        log.debug(f"gatherQualityVisualFeatures: Bbox too small for rv_id={sscape_object.rv_id} (area={bbox_area} <= {minimum_bbox_area})")
    return

  def pickBestID(self, sscape_object):
    """
    Checks if there is a value for the database ID corresponding to the active track for a
    Scenescape object in the active tracks dictionary. If one does exist, we set the gid and
    similarity of the object to the values in the dictionary. Otherwise, we keep the gid from
    the tracker.

    Also stores semantic metadata for future database storage.

    @param  sscape_object  The current Scenescape object
    """
    # LOOKUP ID IN DICT
    result = self.active_ids.get(sscape_object.rv_id, None)
    # DATABASE ID IS NOT NULL
    if result and result[0] is not None:
      sscape_object.gid = result[0]
      sscape_object.similarity = result[1]
      reid_embedding = self._extractReidEmbedding(sscape_object)

      if reid_embedding is not None and self._ensureReIDDimensions(reid_embedding):
        if sscape_object.rv_id in self.features_for_database:
          self.features_for_database[sscape_object.rv_id]['reid_vectors'].append(
            reid_embedding)
    # DATABASE ID IS NULL
    else:
      sscape_object.similarity = None
    return

  def haveSufficientVisualFeatures(self, sscape_object,
                                   minimum_feature_count=DEFAULT_MINIMUM_FEATURE_COUNT):
    """
    Checks if there are enough visual features to send a query to the database

    @param   sscape_object          The current Scenescape object
    @param   minimum_feature_count  The number of features to collect
    @return  bool                   Returns True if the total number of collected features
                                    for a tracker ID is greater than the minimum value;
                                    otherwise, returns False
    """
    count = len(self.quality_features.get(sscape_object.rv_id, []))
    return count >= minimum_feature_count

  def querySimilarity(self, sscape_object):
    """
    Query the database for a match and update the active_ids dictionary. This function is
    mainly used as a wrapper to run the query in its own thread.

    @param  sscape_object  The current Scenescape object
    """
    similarity_scores = self.sendSimilarityQuery(sscape_object)
    database_id, similarity = self.parseQueryResults(similarity_scores)
    with self.active_ids_lock:
      # Make sure object is still in active_ids before updating since there is a chance
      # that the similiarity search does not complete until after the object leaves
      if sscape_object.rv_id in self.active_ids:
        self.updateActiveDict(sscape_object, database_id, similarity)
      else:
        log.warning(
          f"Track {sscape_object.rv_id} left scene before ID query finished")
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

  def parseQueryResults(self, similarity_scores, threshold=DEFAULT_SIMILARITY_THRESHOLD):
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

  def updateActiveDict(self, sscape_object, database_id, similarity):
    """
    Updates the dictionary tracking the active tracker IDs and their corresponding database
    IDs. Also creates an entry in the features_for_database dictionary with semantic metadata
    to be added to the database when the track leaves the scene.

    @param  sscape_object  The current Scenescape object
    @param  database_id    The ID from the database
    @param  similarity     The similarity score from the database
    """
    # MATCH FOUND - YES + DB ID ALREADY IN DICT - NO
    if database_id and self.isNewID(database_id):
      self.active_ids[sscape_object.rv_id] = [database_id, similarity]
      log.debug(
        f"updateActiveDict: Match found for {sscape_object.rv_id}: {database_id},{similarity}")
    # MATCH FOUND - NO / DB ID ALREADY IN DICT - YES
    else:
      self.active_ids[sscape_object.rv_id] = [sscape_object.gid, None]
      database_id = sscape_object.gid
      log.debug(f"updateActiveDict: No match, using gid={database_id} for track {sscape_object.rv_id}")

    # Store features with semantic metadata for TIER 1 filtering in future queries
    num_features = len(self.quality_features.get(sscape_object.rv_id, []))
    log.debug(f"updateActiveDict: Storing {num_features} features for track {sscape_object.rv_id} to features_for_database")
    self.features_for_database[sscape_object.rv_id] = {
      'gid': database_id,
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
      # Case for incrementing the counter when there is no re-id vector
      if sscape_object.reid is None:
        self.unique_id_count += 1
      with self.active_ids_lock:
        self.active_ids.setdefault(sscape_object.rv_id, [None, None])

    # Continue gathering features until we have enough or query is already submitted
    if sscape_object.rv_id not in self.active_query and self.reid_enabled:
      self.gatherQualityVisualFeatures(sscape_object)
      sufficient_features = self.haveSufficientVisualFeatures(sscape_object)
      log.debug(f"assignID: rv_id={sscape_object.rv_id}, sufficient_features={sufficient_features}")

      # Submit query once we have enough features
      if sufficient_features:
        log.debug(f"assignID: Submitting similarity query for rv_id={sscape_object.rv_id}")
        self.active_query[sscape_object.rv_id] = True
        self.pool.submit(self.querySimilarity, sscape_object)

    # Always pick best ID for the current frame
    self.pickBestID(sscape_object)
    return
