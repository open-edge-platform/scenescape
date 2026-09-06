# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import json
import uuid
from datetime import datetime

import numpy as np
import robot_vision as rv

from controller.moving_object import (DEFAULT_EDGE_LENGTH,
                                      DEFAULT_TRACKING_RADIUS,
                                      SPEED_THRESHOLD_ON)
from controller.tracking import (MAX_UNRELIABLE_TIME,
                                 NON_MEASUREMENT_TIME_DYNAMIC,
                                 NON_MEASUREMENT_TIME_STATIC,
                                 DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS,
                                 Tracking)
from scene_common import log
from scene_common.geometry import Point
from scene_common.timestamp import get_epoch_time


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


# When sticky Kalman yaw lags a smooth camera-driven turn (common under
# intermittent LiDAR), prefer velocity heading for publish. Below this
# absolute yaw error, keep the filtered orienting-sensor yaw.
YAW_VELOCITY_DISAGREE_RAD = 0.6


def _wrap_angle(angle):
  """Wrap an angle in radians to ``(-pi, pi]``."""
  return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _kalman_yaw_disagrees_with_velocity(tracked_object,
                                       min_speed=SPEED_THRESHOLD_ON,
                                       max_agree_rad=YAW_VELOCITY_DISAGREE_RAD):
  """True when motion heading and Kalman yaw diverge while the object is moving."""
  speed = math.hypot(tracked_object.vx, tracked_object.vy)
  if speed < min_speed:
    return False
  velocity_heading = math.atan2(tracked_object.vy, tracked_object.vx)
  return abs(_wrap_angle(velocity_heading - tracked_object.yaw)) > max_agree_rad


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
    # Only pass detector yaw when the sensor provided an orientation. Camera
    # detections leave yaw unset so Kalman correct can neutralize that axis.
    attributes = {'info': sscape_object.uuid}
    if sscape_object.has_detection_rotation:
      rv_object.yaw = _quaternion_to_yaw(sscape_object.rotation)
      attributes['has_orientation'] = 'true'
    else:
      rv_object.yaw = 0.0
    rv_object.classification = self.rv_classification(sscape_object.confidence)
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

    # Prefer Kalman yaw whenever the track has received an orienting sensor
    # update (sticky orientation_observed), even if this frame's linked
    # detection is a camera without rotation. Velocity heading is a published
    # fallback only — never fed back as a Kalman yaw measurement. Apply after
    # setPrevious so rotation_from_velocity chain copy cannot overwrite it.
    #
    # Exception: during cam/lidar oscillation on a smooth curve, sticky yaw
    # can freeze while XY follows the turn. If this frame is non-orienting and
    # velocity heading disagrees with Kalman yaw, publish velocity heading.
    attrs = tracked_object.attributes or {}
    use_kalman_yaw = (
      attrs.get('orientation_observed') == 'true'
      or attrs.get('has_orientation') == 'true'
      or sscape_object.has_detection_rotation
    )

    sscape_object.rv_id = tracked_object.id
    found = False
    for obj in self.all_tracker_objects:
      if hasattr(obj, 'rv_id') and sscape_object.rv_id == obj.rv_id:
        found = True
        sscape_object.setPrevious(obj)
        break
    if not found:
      sscape_object.setGID(object_uuid)

    if use_kalman_yaw:
      # Camera-linked frames: fall back at ~0.6 rad. Orienting frames still
      # prefer LiDAR unless the conflict is extreme (≈90°+), which usually
      # means a PointPillars flip or bad association during a curve.
      disagree_limit = (
        math.pi / 2.0 if sscape_object.has_detection_rotation
        else YAW_VELOCITY_DISAGREE_RAD
      )
      if _kalman_yaw_disagrees_with_velocity(tracked_object,
                                             max_agree_rad=disagree_limit):
        heading = math.atan2(tracked_object.vy, tracked_object.vx)
        sscape_object.rotation = _yaw_to_quaternion(heading)
      else:
        sscape_object.rotation = _yaw_to_quaternion(tracked_object.yaw)
    else:
      sscape_object.inferRotationFromVelocity()

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
    self.all_tracker_objects = tracks_from_detections + self.already_tracked_objects
    return

  def trackCategoryBatched(self, objects_per_camera, when, already_tracked_objects):
    """Create reliable tracks for objects from multiple cameras using batched tracking"""
    when = datetime.fromtimestamp(when)
    self.update_tracks_batched(objects_per_camera, when)
    tracked_objects = self.tracker.get_reliable_tracks()
    self.uuid_manager.pruneInactiveTracks(tracked_objects)

    # Flatten all objects for from_tracked_object lookup
    all_objects = [obj for camera_objects in objects_per_camera for obj in camera_objects]

    tracks_from_detections = [self.from_tracked_object(tracked_object, all_objects)
                              for tracked_object in tracked_objects]

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
