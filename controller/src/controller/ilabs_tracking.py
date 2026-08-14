# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

import time
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


class IntelLabsTracking(Tracking):

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static,
               baseline_frame_rate=30, suspended_track_timeout_secs=DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS,
               name=None):
    """Initialize the tracker with tracker configuration parameters"""
    super().__init__()
    self.name = name if name is not None else "IntelLabsTracking"
    self.ref_camera_frame_rate = baseline_frame_rate
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

    if suspended_track_timeout_secs is not None and 0 < suspended_track_timeout_secs <= 3600:
      tracker_config.suspended_track_timeout_secs = suspended_track_timeout_secs
    else:
      log.error("The suspended_track_timeout_secs parameter needs to be positive and at most 3600 seconds. "
                "Initiating the tracker with the default value.")
      tracker_config.suspended_track_timeout_secs = DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS

    self.tracker = rv.tracking.MultipleObjectTracker(tracker_config)
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
    rv_object.yaw = sscape_object.rotation[1] if sscape_object.rotation else 0.
    rv_object.classification = self.rv_classification(sscape_object.confidence)
    info = sscape_object.info.copy()
    info['framecount'] = sscape_object.frameCount
    rv_object.attributes = {
      'info': sscape_object.uuid,
    }
    return rv_object

  def update_tracks(self, objects, timestamp):
    t_conv_start = time.time_ns()
    rv_objects = [self.to_rv_object(sscape_object) for sscape_object in objects]
    t_conv = (time.time_ns() - t_conv_start) / 1e6

    tracking_radius = DEFAULT_TRACKING_RADIUS
    if len(objects):
      tracking_radius = sum([x.tracking_radius for x in objects]) / len(objects)

    t_track_start = time.time_ns()
    self.tracker.track(rv_objects, timestamp, distance_type=rv.tracking.DistanceType.Euclidean, distance_threshold=tracking_radius)
    t_track = (time.time_ns() - t_track_start) / 1e6

    log.debug(f"[PROFILE_UPDATE] objs={len(objects)}, conv_ms={t_conv:.3f}, track_ms={t_track:.3f}")
    return

  def _build_tracking_lookups(self, objects):
    """Build O(1) lookup maps for current-frame and previously tracked objects."""
    current_objects_by_uuid = {obj.uuid: obj for obj in objects if hasattr(obj, 'uuid')}
    tracked_objects_by_uuid = {obj.uuid: obj for obj in self.all_tracker_objects if hasattr(obj, 'uuid')}
    tracked_objects_by_rv_id = {obj.rv_id: obj for obj in self.all_tracker_objects if hasattr(obj, 'rv_id')}
    return current_objects_by_uuid, tracked_objects_by_uuid, tracked_objects_by_rv_id

  def _from_tracked_objects(self, tracked_objects, objects):
    """Convert reliable tracker output using shared prebuilt lookup maps."""
    current_objects_by_uuid, tracked_objects_by_uuid, tracked_objects_by_rv_id = self._build_tracking_lookups(objects)
    return [t for t in (
        self._from_tracked_object_indexed(
            tracked_object,
            current_objects_by_uuid,
            tracked_objects_by_uuid,
            tracked_objects_by_rv_id
        )
        for tracked_object in tracked_objects
    ) if t is not None]

  def _from_tracked_object_indexed(self, tracked_object, current_objects_by_uuid, tracked_objects_by_uuid,
                                   tracked_objects_by_rv_id):
    """Get associated sscape object using pre-built O(1) lookup maps.

    Args:
        tracked_object: The tracked object from robot_vision tracker
        current_objects_by_uuid: Dict mapping uuid -> sscape_object for current frame objects
        tracked_objects_by_uuid: Dict mapping uuid -> sscape_object for tracked objects
        tracked_objects_by_rv_id: Dict mapping rv_id -> sscape_object for tracked objects

    Returns:
        The associated sscape object with updated tracking info
    """
    uuid = tracked_object.attributes['info']

    sscape_object = current_objects_by_uuid.get(uuid)
    if sscape_object is None:
      sscape_object = tracked_objects_by_uuid.get(uuid)
      if sscape_object is not None:
        return sscape_object
      # Neither current objects nor tracker objects matched this UUID
      log.warning(f"No sscape_object found for tracked UUID {uuid}, track_id={tracked_object.id}")
      return None

    # Update location and velocity
    sscape_object.location[0].point = Point(tracked_object.x, tracked_object.y,
                                            tracked_object.z)
    sscape_object.velocity = Point((tracked_object.vx, tracked_object.vy, 0.0))
    sscape_object.rv_id = tracked_object.id

    prev_obj = tracked_objects_by_rv_id.get(tracked_object.id)
    if prev_obj is not None:
      sscape_object.setPrevious(prev_obj)
      sscape_object.inferRotationFromVelocity()
    else:
      # Preserve existing UUID mapping if one exists for this rv_id.
      # Without this check, a new GID is assigned every time a track transitions
      # between reliable/unreliable/suspended states, breaking identity continuity.
      existing_gid = self.uuid_manager.getActiveGID(sscape_object.rv_id)
      if existing_gid is None:
        sscape_object.setGID(uuid)
      else:
        sscape_object.setGID(existing_gid)

    self.uuid_manager.assignID(sscape_object)
    return sscape_object

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
    """Create reliable tracks for objects detected and tracks detected.
    OWNERSHIP: Called only from this tracker's daemon thread via run() loop."""
    self._assert_owner_thread()
    log.debug(f"[PROFILE_ENTRY] trackCategory called with {len(objects)} objects")
    t_start = time.time_ns()

    when_dt = datetime.fromtimestamp(when)

    t_update_start = time.time_ns()
    self.update_tracks(objects, when_dt)
    t_update = (time.time_ns() - t_update_start) / 1e6

    t_get_tracks_start = time.time_ns()
    tracked_objects = self.tracker.get_reliable_tracks()
    # Include all active C++ tracks to preserve UUID mappings across track states.
    # Unreliable and suspended tracks must be included so pruneInactiveTracks does not
    # remove UUID mappings for objects that are temporarily occluded or lost.
    all_active_tracks = (tracked_objects +
                         self.tracker.get_unreliable_tracks() +
                         self.tracker.get_suspended_tracks())
    t_get_tracks = (time.time_ns() - t_get_tracks_start) / 1e6

    t_prune_start = time.time_ns()
    self.uuid_manager.pruneInactiveTracks(all_active_tracks)
    t_prune = (time.time_ns() - t_prune_start) / 1e6

    t_from_start = time.time_ns()
    tracks_from_detections = self._from_tracked_objects(tracked_objects, objects)
    t_from = (time.time_ns() - t_from_start) / 1e6

    t_merge_start = time.time_ns()
    # Already tracked objects include moving objects from tracks consumed directly
    self.already_tracked_objects = self.mergeAlreadyTrackedObjects(already_tracked_objects)
    t_merge = (time.time_ns() - t_merge_start) / 1e6

    self.all_tracker_objects = tracks_from_detections + self.already_tracked_objects

    t_total = (time.time_ns() - t_start) / 1e6

    log.debug(f"[PROFILE_TRACK] objs={len(objects)}, tracks={len(tracked_objects)}, "
              f"update_ms={t_update:.3f}, get_ms={t_get_tracks:.3f}, "
              f"prune_ms={t_prune:.3f}, from_ms={t_from:.3f}, "
              f"merge_ms={t_merge:.3f}, total_ms={t_total:.3f}")

    return

  def trackCategoryBatched(self, objects_per_camera, when, already_tracked_objects):
    """Create reliable tracks for objects from multiple cameras using batched tracking.
    OWNERSHIP: Called only from this tracker's daemon thread via run() loop."""
    self._assert_owner_thread()
    total_objects = sum(len(objs) for objs in objects_per_camera)
    log.debug(f"[PROFILE_ENTRY] trackCategoryBatched called with {len(objects_per_camera)} cameras, {total_objects} objects")
    t_start = time.time_ns()

    when_dt = datetime.fromtimestamp(when)

    t_update_start = time.time_ns()
    self.update_tracks_batched(objects_per_camera, when_dt)
    t_update = (time.time_ns() - t_update_start) / 1e6

    t_get_tracks_start = time.time_ns()
    tracked_objects = self.tracker.get_reliable_tracks()
    # Include all active C++ tracks to preserve UUID mappings across track states.
    # Unreliable and suspended tracks must be included so pruneInactiveTracks does not
    # remove UUID mappings for objects that are temporarily occluded or lost.
    all_active_tracks = (tracked_objects +
                         self.tracker.get_unreliable_tracks() +
                         self.tracker.get_suspended_tracks())
    t_get_tracks = (time.time_ns() - t_get_tracks_start) / 1e6

    t_prune_start = time.time_ns()
    self.uuid_manager.pruneInactiveTracks(all_active_tracks)
    t_prune = (time.time_ns() - t_prune_start) / 1e6

    # Flatten all objects for shared tracked-object lookup
    all_objects = [obj for camera_objects in objects_per_camera for obj in camera_objects]

    t_from_start = time.time_ns()
    tracks_from_detections = self._from_tracked_objects(tracked_objects, all_objects)
    t_from = (time.time_ns() - t_from_start) / 1e6

    t_merge_start = time.time_ns()
    # Already tracked objects include moving objects from tracks consumed directly
    self.already_tracked_objects = self.mergeAlreadyTrackedObjects(already_tracked_objects)
    t_merge = (time.time_ns() - t_merge_start) / 1e6

    self.all_tracker_objects = tracks_from_detections + self.already_tracked_objects

    t_total = (time.time_ns() - t_start) / 1e6

    log.debug(f"[PROFILE_TRACK_BATCHED] cameras={len(objects_per_camera)}, objs={total_objects}, tracks={len(tracked_objects)}, "
              f"update_ms={t_update:.3f}, get_ms={t_get_tracks:.3f}, "
              f"prune_ms={t_prune:.3f}, from_ms={t_from:.3f}, "
              f"merge_ms={t_merge:.3f}, total_ms={t_total:.3f}")
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

    self.tracker.track(rv_objects_per_camera, timestamp, distance_type=rv.tracking.DistanceType.Euclidean, distance_threshold=tracking_radius)
    return
