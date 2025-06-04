# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.


import uuid
from datetime import datetime

import numpy as np
import robot_vision as rv

from controller.moving_object import (DEFAULT_EDGE_LENGTH,
                                      DEFAULT_TRACKING_RADIUS)
from controller.tracking import (MAX_UNRELIABLE_TIME,
                                 NON_MEASUREMENT_TIME_DYNAMIC,
                                 NON_MEASUREMENT_TIME_STATIC, Tracking)
from scene_common import log
from scene_common.geometry import Point
from scene_common.timestamp import get_epoch_time


class IntelLabsTracking(Tracking):

  def __init__(self, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    """Initialize the tracker with tracker configuration parameters"""
    super().__init__()
    #ref_camera_frame_rate is used to determine the frame-based param values
    self.ref_camera_frame_rate = 30
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

    self.tracker = rv.tracking.MultipleObjectTracker(tracker_config)
    log.info("Multiple Object Tracker initialized")
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
    rv_objects = [self.to_rv_object(sscape_object) for sscape_object in objects]
    tracking_radius = DEFAULT_TRACKING_RADIUS
    if len(objects):
      tracking_radius = sum([x.tracking_radius for x in objects]) / len(objects)

    self.tracker.track(rv_objects, timestamp, distance_type=rv.tracking.DistanceType.Euclidean, distance_threshold=tracking_radius)
    return

  def from_tracked_object(self, tracked_object, objects):
    """Get associated sscape object from reliable tracked object"""
    uuid = tracked_object.attributes['info']
    sscape_object = None
    for obj in objects:
      if uuid == obj.uuid:
        sscape_object = obj
        break
    if not sscape_object:
      for obj in self._objects:
        if uuid == obj.uuid:
          return obj

    sscape_object.location[0].point = Point(tracked_object.x, tracked_object.y,
                                            tracked_object.z)
    sscape_object.velocity = Point((tracked_object.vx, tracked_object.vy, 0.0))

    sscape_object.rv_id = tracked_object.id
    found = False
    for obj in self._objects:
      if hasattr(obj, 'rv_id') and sscape_object.rv_id == obj.rv_id:
        found = True
        sscape_object.setPrevious(obj)
        sscape_object.inferRotationFromVelocity()
        break
    if not found:
      sscape_object.setGID(uuid)

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
    """Create reliable tracks for objects detected and tracks detected"""
    when = datetime.fromtimestamp(when)
    self.update_tracks(objects, when)
    tracked_objects = self.tracker.get_reliable_tracks()
    self.uuid_manager.pruneInactiveTracks(tracked_objects)
    tracks_from_detections = [self.from_tracked_object(tracked_object, objects)
                     for tracked_object in tracked_objects]

    # Already tracked objects include moving objects from tracks consumed directly
    self.already_tracked_objects = self.mergeAlreadyTrackedObjects(already_tracked_objects)
    self._objects = tracks_from_detections + self.already_tracked_objects
    return
