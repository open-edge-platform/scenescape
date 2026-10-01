# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import json
import uuid
from datetime import datetime

import numpy as np
import robot_vision as rv

from controller.moving_object import (DEFAULT_EDGE_LENGTH,
                                      DEFAULT_TRACKING_RADIUS)
from controller.tracking import (MAX_UNRELIABLE_TIME,
                                 NON_MEASUREMENT_TIME_DYNAMIC,
                                 NON_MEASUREMENT_TIME_STATIC,
                                 DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS,
                                 Tracking)
from scene_common import log
from scene_common.geometry import Point
from scene_common.timestamp import get_epoch_time


PENDING_HANDOFF_GRACE_SECS = 2.0
PENDING_HANDOFF_MAX_DISTANCE_M = 1.5
DEFAULT_SUSPENDED_REID_OBJECT_GRACE_SECS = 60.0


def _quaternion_to_yaw(rotation):
  """Return Z-axis yaw in radians from an ``[x, y, z, w]`` quaternion.

  Implemented manually instead of
  ``scipy.spatial.transform.Rotation.from_quat(...).as_euler(...)`` for
  performance: benchmarking showed this atan2-only path is ~2.2x faster
  per call (~3.5us vs ~8.0us) since it avoids scipy's Cython overhead which
  is amortized only with batch processing.
  """
  try:
    quaternion = np.asarray(rotation, dtype=float)
  except (TypeError, ValueError):
    return 0.0
  if quaternion.shape != (4,) or not np.all(np.isfinite(quaternion)):
    return 0.0

  norm = np.linalg.norm(quaternion)
  if norm == 0.0:
    return 0.0

  x, y, z, w = quaternion / norm
  sin_yaw_cos_pitch = 2.0 * (w * z + x * y)
  cos_yaw_cos_pitch = 1.0 - 2.0 * (y * y + z * z)
  return math.atan2(sin_yaw_cos_pitch, cos_yaw_cos_pitch)


def _yaw_to_quaternion(yaw):
  """Return an ``[x, y, z, w]`` quaternion for a Z-axis-only ``yaw`` in radians."""
  return [0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)]


class IntelLabsTracking(Tracking):

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static, effective_object_update_rate, suspended_track_timeout_secs=DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS, reid_config_data=None, name=None):
    """Initialize the tracker with tracker configuration parameters"""
    super().__init__(reid_config_data=reid_config_data)
    self.name = name if name is not None else "IntelLabsTracking"
    # ref_camera_frame_rate is used to determine the frame-based param values
    self.ref_camera_frame_rate = effective_object_update_rate
    tracker_config = rv.tracking.TrackManagerConfig()

    tracker_config.default_process_noise = 1e-4
    tracker_config.default_measurement_noise = 2e-1
    tracker_config.init_state_covariance = 1

    tracker_config.motion_models = [rv.tracking.MotionModel.CV, rv.tracking.MotionModel.CA,
                                    rv.tracking.MotionModel.CTRV]

    if self.check_valid_time_parameters(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
      tracker_config.max_unreliable_time = max_unreliable_time
      tracker_config.non_measurement_time_dynamic = non_measurement_time_dynamic
      tracker_config.non_measurement_time_static = non_measurement_time_static
    else:
      log.error("The time-based parameters need to be positive and less than 10 seconds. \
                 Initiating the tracker with the default values of the time-based parameters.")
      tracker_config.max_unreliable_time = MAX_UNRELIABLE_TIME
      tracker_config.non_measurement_time_dynamic = NON_MEASUREMENT_TIME_DYNAMIC
      tracker_config.non_measurement_time_static = NON_MEASUREMENT_TIME_STATIC

    tracker_config.suspended_track_timeout_secs = suspended_track_timeout_secs

    self.tracker = rv.tracking.MultipleObjectTracker(tracker_config)
    # Recently disappeared unresolved tracks. These are candidates for a
    # bounded handoff when Robot Vision creates a replacement tracker ID.
    self.pending_reid_handoffs = {}
    self.last_reliable_objects = {}
    self.suspended_reid_objects = {}
    self.suspended_reid_object_grace_secs = float(
      (reid_config_data or {}).get(
        'inactive_track_grace_secs',
        DEFAULT_SUSPENDED_REID_OBJECT_GRACE_SECS,
      )
    )
    log.info(f"Multiple Object Tracker {self.__str__()} initialized")
    log.info("Tracker config: {}".format(tracker_config))
    self.tracker.update_tracker_params(self.ref_camera_frame_rate)
    return

  def check_valid_time_parameters(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    param_list = [max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static]
    result = all(value is not None for value in param_list)
    if result:
      if all((value > 0) and (value < 10) for value in param_list):
        return True
    return False

  def rv_classification(self, confidence=None):
    confidence = 1.0 if confidence is None else confidence
    return np.array([confidence, 1.0 - confidence])

  @staticmethod
  def metadata_to_attributes(metadata):
    """Encode metadata fields for RobotVision's per-field fusion."""
    attributes = {}
    for field, value in metadata.items():
      try:
        attributes[f'metadata.{field}'] = json.dumps(value, separators=(',', ':'))
      except (TypeError, ValueError) as error:
        log.warning(f"Unable to serialize metadata field '{field}': {error}")
        continue

      confidence = value.get('confidence') if isinstance(value, dict) else None
      if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        attributes[f'metadata_confidence.{field}'] = str(value['confidence'])
    return attributes

  @staticmethod
  def metadata_from_attributes(attributes):
    """Decode metadata fields selected by RobotVision."""
    metadata = {}
    for key in sorted(attributes):
      if not key.startswith('metadata.'):
        continue
      value = attributes[key]
      field = key.removeprefix('metadata.')
      try:
        metadata[field] = json.loads(value)
      except (TypeError, json.JSONDecodeError) as error:
        log.warning(f"Unable to deserialize fused metadata field '{field}': {error}")
    return metadata

  def to_rv_object(self, sscape_object):
    """Convert sscape detected object to robot vision tracking input object format"""
    sscape_object.uuid = str(uuid.uuid4())
    rv_object = rv.tracking.TrackedObject()
    pt = sscape_object.sceneLoc
    rv_object.x = pt.x
    rv_object.y = pt.y
    rv_object.z = pt.z
    # length is mapped to x, width is mapped to y and height is to z if intel labs tracker
    size = sscape_object.size if sscape_object.size else [DEFAULT_EDGE_LENGTH] * 3
    rv_object.length = size[0]
    rv_object.width = size[1]
    rv_object.height = size[2]
    rv_object.yaw = _quaternion_to_yaw(sscape_object.rotation)
    rv_object.classification = self.rv_classification(sscape_object.confidence)
    info = sscape_object.info.copy()
    info['framecount'] = sscape_object.frameCount
    attributes = {'info': sscape_object.uuid}
    attributes.update(self.metadata_to_attributes(sscape_object.metadata))
    rv_object.attributes = attributes
    return rv_object

  def update_tracks(self, objects, timestamp):
    rv_objects = [self.to_rv_object(sscape_object) for sscape_object in objects]
    tracking_radius = DEFAULT_TRACKING_RADIUS
    if len(objects):
      tracking_radius = sum([x.tracking_radius for x in objects]) / len(objects)

    self.tracker.track(rv_objects, timestamp, distance_type=rv.tracking.DistanceType.Euclidean,
                       distance_threshold=tracking_radius)
    return

  def from_tracked_object(self, tracked_object, objects):
    """Get associated sscape object from reliable tracked object"""
    object_uuid = tracked_object.attributes['info']
    sscape_object = None
    for obj in objects:
      if object_uuid == obj.uuid:
        sscape_object = obj
        break
    if not sscape_object:
      for obj in self.all_tracker_objects:
        if object_uuid == obj.uuid:
          return obj

    sscape_object.metadata = self.metadata_from_attributes(tracked_object.attributes)

    sscape_object.location[0].point = Point(tracked_object.x, tracked_object.y,
                                            tracked_object.z)
    sscape_object.velocity = Point((tracked_object.vx, tracked_object.vy, 0.0))

    # Only overwrite rotation with the tracker's Kalman-filtered yaw when the
    # object has a real detector-provided rotation measurement. For
    # velocity-inferred rotation, self.velocity already comes from this same
    # Kalman filter, so re-filtering it here would just be smoothing an
    # already-smoothed signal with no new information gained.
    if sscape_object.has_detection_rotation:
      sscape_object.rotation = _yaw_to_quaternion(tracked_object.yaw)

    sscape_object.rv_id = tracked_object.id
    found = False
    for obj in self.all_tracker_objects:
      if hasattr(obj, 'rv_id') and sscape_object.rv_id == obj.rv_id:
        found = True
        sscape_object.setPrevious(obj)
        sscape_object.inferRotationFromVelocity()
        break
    if not found:
      sscape_object.setGID(object_uuid)

      suspended = self._takeSuspendedReidObject(sscape_object.rv_id)
      if suspended is not None:
        # UUIDManager already retained this rv_id and its feature buffers.
        # Restore the MovingObject chain as well so the provisional UUID that
        # was previously published is recorded when the eventual match changes
        # the gid.
        self._continueReidObjectChain(
          sscape_object, suspended, object_uuid)
        log.info(
          f"Restored suspended ReID object chain for "
          f"rv_id={sscape_object.rv_id}")
      else:
        handoff = self._takePendingReidHandoff(sscape_object)
        if handoff is not None:
          old_track_id, old_object = handoff
          if self.uuid_manager.transferPendingTrack(
              old_track_id, sscape_object.rv_id):
            self.pending_reid_handoffs.pop(old_track_id, None)
            self.suspended_reid_objects.pop(old_track_id, None)
            # Carry the provisional gid, history and chain data forward. When
            # ReID later matches, updateActiveDict records this provisional gid
            # in previous_ids_chain before switching to the established gid.
            self._continueReidObjectChain(
              sscape_object, old_object, object_uuid)
            log.info(
              f"ReID tracker-fragment handoff rv_id={old_track_id} "
              f"-> {sscape_object.rv_id}")

    self.uuid_manager.assignID(sscape_object)

    return sscape_object

  @staticmethod
  def _continueReidObjectChain(new_object, old_object, new_provisional_gid):
    """Carry object history forward without extending the old provisional gid.

    The old provisional UUID must be linked through previous_ids_chain, but it
    must not remain the current gid across a long suspension. Otherwise the
    test (and consumers) correctly interpret it as another lasting identity.
    """
    old_provisional_gid = old_object.gid
    new_object.setPrevious(old_object)
    new_object.gid = new_provisional_gid

    if (old_provisional_gid is not None
        and old_provisional_gid != new_provisional_gid):
      new_object.save_previous_object_id(
        old_provisional_gid,
        similarity_score=None,
        timestamp=new_object.when,
      )

  @staticmethod
  def _sourceId(sscape_object):
    source = getattr(sscape_object, 'camera', None)
    return (
      getattr(source, 'cameraID', None)
      or getattr(source, 'uid', None)
    )

  @staticmethod
  def _distanceBetween(first, second):
    first_point = first.sceneLoc
    second_point = second.sceneLoc
    return math.sqrt(
      (first_point.x - second_point.x) ** 2
      + (first_point.y - second_point.y) ** 2
      + (first_point.z - second_point.z) ** 2
    )

  def _expirePendingReidHandoffs(self, now):
    for track_id, candidate in list(self.pending_reid_handoffs.items()):
      if now - candidate['disappeared_at'] > PENDING_HANDOFF_GRACE_SECS:
        self.pending_reid_handoffs.pop(track_id, None)

  def _expireSuspendedReidObjects(self, now):
    for track_id, candidate in list(self.suspended_reid_objects.items()):
      if (now - candidate['disappeared_at']
          > self.suspended_reid_object_grace_secs):
        self.suspended_reid_objects.pop(track_id, None)

  def _takeSuspendedReidObject(self, track_id):
    now = get_epoch_time()
    self._expireSuspendedReidObjects(now)
    candidate = self.suspended_reid_objects.pop(track_id, None)
    if candidate is None:
      return None
    self.pending_reid_handoffs.pop(track_id, None)
    return candidate['object']

  def _cacheDisappearedPendingTracks(self, current_track_ids, now):
    """Cache unresolved tracks that disappeared since the previous update."""
    self._expirePendingReidHandoffs(now)
    self._expireSuspendedReidObjects(now)
    for track_id, old_object in self.last_reliable_objects.items():
      if track_id in current_track_ids:
        continue
      if not self.uuid_manager.hasPendingTrack(track_id):
        continue
      self.pending_reid_handoffs.setdefault(track_id, {
        'object': old_object,
        'disappeared_at': now,
      })
      self.suspended_reid_objects.setdefault(track_id, {
        'object': old_object,
        'disappeared_at': now,
      })

  def _takePendingReidHandoff(self, new_object):
    """Return one unambiguous same-camera, nearby pending-track candidate."""
    now = get_epoch_time()
    self._expirePendingReidHandoffs(now)
    source_id = self._sourceId(new_object)
    candidates = []

    for track_id, candidate in self.pending_reid_handoffs.items():
      old_object = candidate['object']
      if self._sourceId(old_object) != source_id:
        continue
      distance = self._distanceBetween(old_object, new_object)
      if distance <= PENDING_HANDOFF_MAX_DISTANCE_M:
        candidates.append((distance, track_id, old_object))

    # Reject ambiguous association rather than transferring one person's ReID
    # evidence into another person's tracker ID.
    if len(candidates) != 1:
      if len(candidates) > 1:
        log.warning(
          f"Ambiguous ReID tracker-fragment handoff for "
          f"rv_id={new_object.rv_id}: candidates="
          f"{[(track_id, round(distance, 3)) for distance, track_id, _ in candidates]}")
      return None

    _, track_id, old_object = candidates[0]
    return track_id, old_object

  def _convertReliableTracks(self, tracked_objects, objects):
    """Cache disappearances, convert tracks, then prune unclaimed ReID state."""
    now = get_epoch_time()
    current_track_ids = {tracked_object.id for tracked_object in tracked_objects}
    self._cacheDisappearedPendingTracks(current_track_ids, now)

    converted = [
      self.from_tracked_object(tracked_object, objects)
      for tracked_object in tracked_objects
    ]
    self.last_reliable_objects = {
      obj.rv_id: obj for obj in converted if hasattr(obj, 'rv_id')
    }
    self.uuid_manager.pruneInactiveTracks(tracked_objects)
    return converted

  def mergeAlreadyTrackedObjects(self, tracks):
    """Merge already tracked objects with current objects"""
    now = get_epoch_time()
    result = []
    existing_tracks = {}
    new_tracks = {}
    non_existing_tracks = {}

    for new_obj in tracks:
      found = False
      for existing_obj in self.already_tracked_objects:
        if new_obj.oid == existing_obj.oid:
          found = True
          existing_tracks[new_obj.oid] = (new_obj, existing_obj)
          break
      if not found:
        new_tracks[new_obj.oid] = new_obj
    for existing_obj in self.already_tracked_objects:
      if existing_obj.oid not in existing_tracks:
        non_existing_tracks[existing_obj.oid] = existing_obj

    for new, old in existing_tracks.values():
      new.setPrevious(old)
      new.inferRotationFromVelocity()
      new.last_seen = now
      result.append(new)

    for obj in new_tracks.values():
      obj.setGID(obj.oid)
      obj.last_seen = now
      result.append(obj)

    for obj in non_existing_tracks.values():
      if now - obj.last_seen < MAX_UNRELIABLE_TIME:
        result.append(obj)
    return result

  def trackCategory(self, objects, when, already_tracked_objects):
    """Create reliable tracks for objects detected and tracks detected"""
    when = datetime.fromtimestamp(when)
    self.update_tracks(objects, when)
    tracked_objects = self.tracker.get_reliable_tracks()
    tracks_from_detections = self._convertReliableTracks(
      tracked_objects, objects)

    # Already tracked objects include moving objects from tracks consumed directly
    self.already_tracked_objects = self.mergeAlreadyTrackedObjects(already_tracked_objects)
    self.all_tracker_objects = tracks_from_detections + self.already_tracked_objects
    return

  def trackCategoryBatched(self, objects_per_camera, when, already_tracked_objects):
    """Create reliable tracks for objects from multiple cameras using batched tracking"""
    when = datetime.fromtimestamp(when)
    self.update_tracks_batched(objects_per_camera, when)
    tracked_objects = self.tracker.get_reliable_tracks()

    # Flatten all objects for from_tracked_object lookup
    all_objects = [obj for camera_objects in objects_per_camera for obj in camera_objects]

    tracks_from_detections = self._convertReliableTracks(
      tracked_objects, all_objects)

    # Already tracked objects include moving objects from tracks consumed directly
    self.already_tracked_objects = self.mergeAlreadyTrackedObjects(already_tracked_objects)
    self.all_tracker_objects = tracks_from_detections + self.already_tracked_objects
    return

  def update_tracks_batched(self, objects_per_camera, timestamp):
    """Update tracks using batched per-camera object data"""
    rv_objects_per_camera = []
    tracking_radius = DEFAULT_TRACKING_RADIUS

    # Calculate average tracking radius across all objects from all cameras
    total_tracking_radius = 0
    total_object_count = 0

    for camera_objects in objects_per_camera:
      rv_camera_objects = [self.to_rv_object(sscape_object) for sscape_object in camera_objects]
      rv_objects_per_camera.append(rv_camera_objects)

      # Accumulate tracking radius sum and object count
      if len(camera_objects):
        total_tracking_radius += sum([x.tracking_radius for x in camera_objects])
        total_object_count += len(camera_objects)

    # Calculate overall average tracking radius
    if total_object_count > 0:
      tracking_radius = total_tracking_radius / total_object_count

    self.tracker.track(rv_objects_per_camera, timestamp,
                       distance_type=rv.tracking.DistanceType.Euclidean, distance_threshold=tracking_radius)
    return
