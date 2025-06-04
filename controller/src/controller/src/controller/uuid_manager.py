# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import collections
import concurrent.futures
import threading

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

available_databases = {
  "VDMS": VDMSDatabase,
}

class UUIDManager:
  def __init__(self, database=DEFAULT_DATABASE):
    self.active_ids = {}
    self.active_ids_lock = threading.Lock()
    self.active_query = {}
    self.features_for_database = {}
    self.quality_features = {}
    self.unique_id_count = 0
    self.reid_database = available_databases[database]()
    self.pool = concurrent.futures.ThreadPoolExecutor()
    self.similarity_query_times = collections.deque(
      maxlen=DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED)
    self.similarity_query_times_lock = threading.Lock()
    self.reid_enabled = True
    return

  def connectDatabase(self):
    self.pool.submit(self.reid_database.connect)

  def pruneInactiveTracks(self, tracked_objects):
    """
    Removes inactive tracks from the active_ids dict and adds pending features to the database

    @param  tracked_objects  The objects currently tracked by the tracker
    """
    active_tracks = [tracked_object.id for tracked_object in tracked_objects]
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
      # Increment the unique id counter for tracks where no match was found (similiarity=None)
      if data[1] is None:
        self.unique_id_count += 1
      self._addNewFeaturesToDatabase(track_id)
    return

  def _addNewFeaturesToDatabase(self, track_id, slice_size=DEFAULT_FEATURE_SLICE_SIZE):
    """
    Add the features when the track is no longer active to reduce the total number of
    queries sent to the database. Also only take a subset of the captured features to
    add to the database otherwise too many features will impede performance of the
    similiarity search.
    Note: Slice size should be relative to frame rate, but this will only be implemented
    when the tracker is refactored to take into account frame rate.

    @param  track_id    The ID of the track with features to add to the database
    @param  slice_size  The size of the slice to use to reduce the size of the feature list
    """
    features = self.features_for_database.pop(track_id, None)
    if features:
      features['reid_vectors'] = features['reid_vectors'][::slice_size]
      log.debug(
        f"Adding {len(features['reid_vectors'])} features for track {track_id} to database")
      self.pool.submit(self.reid_database.addEntry, features['gid'], track_id,
                       features['category'], features['reid_vectors'])

  def isNewTrackerID(self, sscape_object):
    """
    Checks if the Tracker ID has been seen before and if it has an ID in the database

    @param  sscape_object  The current Scenescape object
    """
    result = self.active_ids.get(sscape_object.rv_id, None)
    # Case for incrementing the counter when there is no re-id vector
    if sscape_object.reidVector is None and result is None:
      self.unique_id_count += 1
    return result is None or result[0] is None

  def gatherQualityVisualFeatures(self, sscape_object,
                                  minimum_bbox_area=DEFAULT_MINIMUM_BBOX_AREA):
    """
    This function gathers quality visual features for identifying newly detected objects.
    It currently only uses re-id vectors but can be expanded to include more features.

    @param  sscape_object        The Scenescape object to gather features from
    @param  minimum_bbox_area    The minimum size of the bbox for the detected object (px)
    """
    if sscape_object.reidVector is not None and self.reid_enabled:
      if sscape_object.boundingBoxPixels.area > minimum_bbox_area:
        if sscape_object.rv_id in self.quality_features:
          self.quality_features[sscape_object.rv_id].append(sscape_object.reidVector)
        else:
          self.quality_features[sscape_object.rv_id] = [sscape_object.reidVector]
    return

  def pickBestID(self, sscape_object):
    """
    Checks if there is a value for the database ID corresponding to the active track for a
    Scenescape object in the active tracks dictionary. If one does exist, we set the gid and
    similarity of the object to the values in the dictionary. Otherwise, we keep the gid from
    the tracker.

    @param  sscape_object  The current Scenescape object
    """
    # LOOKUP ID IN DICT
    result = self.active_ids.get(sscape_object.rv_id, None)
    # DATABASE ID IS NOT NULL
    if result and result[0] is not None:
      sscape_object.gid = result[0]
      sscape_object.similarity = result[1]
      if sscape_object.reidVector is not None:
        if sscape_object.rv_id in self.features_for_database:
          self.features_for_database[sscape_object.rv_id]['reid_vectors'].append(
            sscape_object.reidVector)
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
        log.warn(
          f"Track {sscape_object.rv_id} left scene before ID query finished")
    return

  def sendSimilarityQuery(self, sscape_object, max_query_time=DEFAULT_MAX_QUERY_TIME):
    """
    Sends a query to find similarity scores for a given sscape_object and stores the time it
    takes for query completion. If the time is over a threshold, disables re-id queries.

    @param   sscape_object  The sscape_object for which similarity scores are to be found
    @return  scores         The similarity scores for the given sscape_object
    """
    reid_vectors = self.quality_features.get(sscape_object.rv_id)
    log.debug(f"Finding similarity scores for track {sscape_object.rv_id}")
    start_time = get_epoch_time()
    scores = self.reid_database.findSimilarityScores(sscape_object.category, reid_vectors)
    query_time = get_epoch_time() - start_time
    log.debug(
      f"Similarity scores for track {sscape_object.rv_id} found in {query_time} seconds")

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
    IDs. Also adds creates an entry in the features_for_database dictionary to be added to the
    database when the track leaves the scene.

    @param  sscape_object  The current Scenescape object
    @param  database_id    The ID from the database
    @param  similarity     The similarity score from the database
    """
    # MATCH FOUND - YES + DB ID ALREADY IN DICT - NO
    if database_id and self.isNewID(database_id):
      self.active_ids[sscape_object.rv_id] = [database_id, similarity]
      log.debug(
        f"Match found for {sscape_object.rv_id}: {database_id},{similarity}")
    # MATCH FOUND - NO / DB ID ALREADY IN DICT - YES
    else:
      self.active_ids[sscape_object.rv_id] = [sscape_object.gid, None]
      database_id = sscape_object.gid

    self.features_for_database[sscape_object.rv_id] = {
      'gid': database_id,
      'category': sscape_object.category,
      'reid_vectors': self.quality_features[sscape_object.rv_id]
    }
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
    if self.isNewTrackerID(sscape_object):
      with self.active_ids_lock:
        self.active_ids.setdefault(sscape_object.rv_id, [None, None])
      self.gatherQualityVisualFeatures(sscape_object)
      self.pickBestID(sscape_object)
      if self.haveSufficientVisualFeatures(sscape_object) and self.reid_enabled:
        # Only do the query for similarity if it hasn't been run before
        if sscape_object.rv_id not in self.active_query:
          self.active_query[sscape_object.rv_id] = True
          self.pool.submit(self.querySimilarity, sscape_object)
    else:
      self.pickBestID(sscape_object)
    return
