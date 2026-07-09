# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from typing import Optional

import numpy as np

import robot_vision as rv
from scene_common import log
from scene_common.camera import Camera
from scene_common.earth_lla import convertLLAToECEF, calculateTRSLocal2LLAFromSurfacePoints
from scene_common.geometry import Point, Region, Size, Tripwire
from scene_common.scene_model import SceneModel
from scene_common.timestamp import get_epoch_time, get_iso_time
from scene_common.transform import CameraPose
from scene_common.mesh_util import getMeshAxisAlignedProjectionToXY, createRegionMesh, createObjectMesh

from controller.analytics.analytics_models import moving_object_to_analytics_object
from controller.analytics.engine import process_frame
from controller.analytics.region import update_region_events
from controller.analytics.sensors import (
  update_attribute_sensor_events,
  update_environmental_sensor_readings,
)
from controller.analytics.tripwire import (
  DEBOUNCE_DELAY,
  MIN_FRAMES_FOR_RELIABLE_TRACK,
  TripwireEvent,
  update_tripwire_events,
)
from controller.controller_mode import ControllerMode
from controller.moving_object import ChainData
from controller.pose_adjustment import (PoseAdjustment,
                                        MIN_POSE_CACHE_TTL,
                                        POSE_CACHE_TTL_MULTIPLIER)
from controller.ilabs_tracking import IntelLabsTracking
from controller.time_chunking import TimeChunkedIntelLabsTracking, DEFAULT_CHUNKING_RATE_FPS
from controller.tracking import (MAX_UNRELIABLE_TIME,
                                 NON_MEASUREMENT_TIME_DYNAMIC,
                                 NON_MEASUREMENT_TIME_STATIC,
                                 EFFECTIVE_OBJECT_UPDATE_RATE,
                                 DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS)

class Scene(SceneModel):
  DEFAULT_TRACKER = "intel_labs"
  available_trackers = {
    'intel_labs': IntelLabsTracking,
    'time_chunked_intel_labs': TimeChunkedIntelLabsTracking,
  }

  def __init__(self, name, map_file, scale=None,
               max_unreliable_time = MAX_UNRELIABLE_TIME,
               non_measurement_time_dynamic = NON_MEASUREMENT_TIME_DYNAMIC,
               non_measurement_time_static = NON_MEASUREMENT_TIME_STATIC,
               effective_object_update_rate = EFFECTIVE_OBJECT_UPDATE_RATE,
               time_chunking_enabled = False,
               time_chunking_rate_fps = DEFAULT_CHUNKING_RATE_FPS,
               suspended_track_timeout_secs = DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS,
               reid_config_data = None,
               pose_adjustment_config_data = None):
    log.info("NEW SCENE", name, map_file, scale, max_unreliable_time,
             non_measurement_time_dynamic, non_measurement_time_static,
             "analytics_only=" + str(ControllerMode.isAnalyticsOnly()))
    super().__init__(name, map_file, scale)
    self.ref_camera_frame_rate = time_chunking_rate_fps if time_chunking_enabled else effective_object_update_rate
    self.max_unreliable_time = max_unreliable_time
    self.non_measurement_time_dynamic = non_measurement_time_dynamic
    self.non_measurement_time_static = non_measurement_time_static
    self.suspended_track_timeout_secs = suspended_track_timeout_secs
    self.reid_config_data = reid_config_data if reid_config_data else {}
    self.pose_adjustment_config_data = (
      pose_adjustment_config_data if pose_adjustment_config_data else {}
    )

    self.tracker = None
    self.trackerType = None
    self.persist_attributes = {}
    self.time_chunking_rate_fps = time_chunking_rate_fps
    self._analytics_objects = {}

    if not ControllerMode.isAnalyticsOnly():
      self._setTracker("time_chunked_intel_labs" if time_chunking_enabled else self.DEFAULT_TRACKER)
    else:
      log.info("Tracker initialization SKIPPED for scene: " + name)

    self._trs_xyz_to_lla = None
    self.use_tracker = not ControllerMode.isAnalyticsOnly()

    # Cache for tracked objects from MQTT (for analytics)
    self.tracked_objects_cache = {}

    # Cache for object history (publishedLocations, etc.) to maintain trails across frames
    self.object_history_cache = {}

    self.pose_adjustment = PoseAdjustment.from_env(
      max_entry_age_seconds=self._get_pose_cache_ttl(),
      default_enabled=True,
      pose_adjustment_config_data=self.pose_adjustment_config_data,
    )

    # FIXME - only for backwards compatibility
    self.scale = scale

    return

  def _setTracker(self, trackerType):
    if trackerType not in self.available_trackers:
      log.error("Chosen tracker is not available")
      return
    self.trackerType = trackerType
    log.info("SETTING TRACKER TYPE", trackerType)

    if self.tracker is not None:
      self.tracker.join()

    args = (self.max_unreliable_time,
            self.non_measurement_time_dynamic,
            self.non_measurement_time_static)
    if trackerType == "intel_labs":
      args += (self.ref_camera_frame_rate, self.suspended_track_timeout_secs, self.reid_config_data)
    elif trackerType == "time_chunked_intel_labs":
      args += (self.time_chunking_rate_fps, self.suspended_track_timeout_secs, self.reid_config_data)
    self.tracker = self.available_trackers[self.trackerType](*args)
    return

  def _hydrateFromSceneData(self, scene_data, reid_runtime_update=True):
    reid_config_changed = False
    if 'reid_config_data' in scene_data:
      new_reid_config_data = scene_data['reid_config_data']
      reid_config_changed = new_reid_config_data != self.reid_config_data
      if reid_config_changed:
        self.reid_config_data = new_reid_config_data

    self.parent = scene_data.get('parent', None)
    self.cameraPose = None
    if 'transform' in scene_data:
      self.cameraPose = CameraPose(scene_data['transform'], None)
    self.use_tracker = scene_data.get('use_tracker', True) and not ControllerMode.isAnalyticsOnly()
    self.output_lla = scene_data.get('output_lla', False)
    self.map_corners_lla = scene_data.get('map_corners_lla', None)
    self.retrack = scene_data.get('retrack', True)
    self.persist_attributes = scene_data.get('persist_attributes', {})
    self._updateChildren(scene_data.get('children', []))
    self.updateCameras(scene_data.get('cameras', []))
    self._updateRegions(self.regions, scene_data.get('regions', []))
    self._updateTripwires(scene_data.get('tripwires', []))
    self._updateRegions(self.sensors, scene_data.get('sensors', []))

    tracker_config = scene_data.get('tracker_config', None)
    if tracker_config:
      self.updateTracker(tracker_config[0], tracker_config[1], tracker_config[2])

    # Apply ReID config changes in-place to preserve active tracks while
    # updating UUID manager thresholds and timers.
    if reid_runtime_update and reid_config_changed and self.trackerType and not ControllerMode.isAnalyticsOnly():
      log.info(f"ReID config changed for scene={self.uid}; updating tracker ReID runtime config")
      self.tracker.updateReidConfig(self.reid_config_data)

    self.name = scene_data['name']
    if 'scale' in scene_data:
      self.scale = scene_data['scale']
    if 'regulated_rate' in scene_data:
      self.regulated_rate = scene_data['regulated_rate']
    if 'external_update_rate' in scene_data:
      self.external_update_rate = scene_data['external_update_rate']
    self._invalidate_trs_xyz_to_lla()
    # Access the property to trigger initialization
    _ = self.trs_xyz_to_lla
    return

  def updateScene(self, scene_data):
    self._hydrateFromSceneData(scene_data, reid_runtime_update=True)
    return

  def updateTracker(self, max_unreliable_time, non_measurement_time_dynamic,
                    non_measurement_time_static):
    # Only update tracker if the values have changed to avoid losing tracking data
    if max_unreliable_time != self.max_unreliable_time or \
       non_measurement_time_dynamic != self.non_measurement_time_dynamic or \
       non_measurement_time_static != self.non_measurement_time_static:
      self.max_unreliable_time = max_unreliable_time
      self.non_measurement_time_dynamic = non_measurement_time_dynamic
      self.non_measurement_time_static = non_measurement_time_static
      self._setTracker(self.trackerType)
    if self.pose_adjustment is not None:
      self.pose_adjustment.set_max_entry_age_seconds(self._get_pose_cache_ttl())
    return

  def _get_pose_cache_ttl(self):
    return max(MIN_POSE_CACHE_TTL, self.max_unreliable_time * POSE_CACHE_TTL_MULTIPLIER)

  def _createMovingObjectsForDetection(self, detectionType, detections, when, camera):
    objects = []
    scene_map_triangle_mesh = self.map_triangle_mesh
    scene_map_translation = self.mesh_translation
    scene_map_rotation = self.mesh_rotation

    for info in detections:
      mobj = self.tracker.createObject(detectionType, info, when, camera, self.persist_attributes.get(detectionType, {}))
      mobj.map_triangle_mesh = scene_map_triangle_mesh
      mobj.map_translation = scene_map_translation
      mobj.map_rotation = scene_map_rotation
      objects.append(mobj)
    return objects

  def processCameraData(self, jdata, when=None, ignoreTimeFlag=False):
    if ControllerMode.isAnalyticsOnly():
      return True

    camera_id = jdata['id']
    camera = None

    if not when:
      if ignoreTimeFlag:
        when = get_epoch_time()
      else:
        when = get_epoch_time(jdata['timestamp'])

    if camera_id in self.cameras:
      camera = self.cameras[camera_id]
    else:
      log.error("Unknown camera", camera_id, self.cameras)
      return False

    if not hasattr(camera, 'pose'):
      log.info("DISCARDING: camera has no pose")
      return True

    for detection_type, detections in jdata['objects'].items():
      self.pose_adjustment.adjust_detections(
        detection_type,
        detections,
        self.name,
        camera,
        when,
      )
      if "intrinsics" not in jdata:
        self._convertPixelBoundingBoxesToMeters(detections, camera.pose.intrinsics.intrinsics, camera.pose.intrinsics.distortion)
      objects = self._createMovingObjectsForDetection(detection_type, detections, when, camera)
      self._finishProcessing(detection_type, when, objects)
    return True

  def _convertPixelBoundingBoxesToMeters(self, objects: list[dict], intrinsics_matrix: np.ndarray, distortion_matrix: np.ndarray) -> None:
    """
    Convert pixel bounding boxes to meters for a batch of objects, including nested sub_detections.

    @param objects           List of object dictionaries containing 'bounding_box_px' to be converted
    @param intrinsics_matrix Camera intrinsics matrix as a numpy array
    @param distortion_matrix Distortion coefficients matrix as a numpy array
    """
    if not objects or len(objects) == 0:
      return

    # Collect all bounding boxes that need conversion
    bboxes_to_convert = []
    bbox_mappings = []  # Track which bbox corresponds to which object/sub_detection

    for obj_idx, obj in enumerate(objects):
      # Check main object bounding box
      if 'bounding_box' not in obj and 'bounding_box_px' in obj:
        bbox_px = obj['bounding_box_px']
        bboxes_to_convert.append((bbox_px['x'], bbox_px['y'], bbox_px['width'], bbox_px['height']))
        bbox_mappings.append(('main', obj_idx, None, None))

      # Check sub_detections bounding boxes
      for key in obj.get('sub_detections', []):
        for sub_idx, sub_obj in enumerate(obj[key]):
          if 'bounding_box' not in sub_obj and 'bounding_box_px' in sub_obj:
            bbox_px = sub_obj['bounding_box_px']
            bboxes_to_convert.append((bbox_px['x'], bbox_px['y'], bbox_px['width'], bbox_px['height']))
            bbox_mappings.append(('sub', obj_idx, key, sub_idx))

    # Convert all bounding boxes in batch if there are any
    if bboxes_to_convert:
      converted_bboxes = rv.tracking.compute_pixels_to_meter_plane_batch(
        bboxes_to_convert, intrinsics_matrix, distortion_matrix
      )

      # Apply converted results back to the objects
      for (bbox_type, obj_idx, key, sub_idx), (agnosticx, agnosticy, agnosticw, agnostich) in zip(bbox_mappings, converted_bboxes):
        converted_bbox = {'x': agnosticx, 'y': agnosticy, 'width': agnosticw, 'height': agnostich}

        if bbox_type == 'main':
          objects[obj_idx]['bounding_box'] = converted_bbox
        elif bbox_type == 'sub':
          objects[obj_idx][key][sub_idx]['bounding_box'] = converted_bbox

    return

  def processSceneData(self, jdata, child, cameraPose,
                       detectionType, when=None):

    if ControllerMode.isAnalyticsOnly():
      log.debug(f"Analytics-only mode enabled, skipping scene data processing for child {child.name if hasattr(child, 'name') else 'unknown'}")
      return True

    new = jdata['objects']

    objects = []
    child_objects = []
    for info in new:
      if 'lat_long_alt' in info:
        if 'translation' in info:
          log.warning("Input data must have only one of 'lat_long_alt' and 'translation'")
          return True
        info['translation'] = convertLLAToECEF(info.pop('lat_long_alt'))
      translation = Point(info['translation'])
      translation = np.hstack([translation.asNumpyCartesian, [1]])
      translation = np.matmul(cameraPose.pose_mat, translation)
      info['translation'] = translation[:3]

      # Remove reid vector from the object info as tracker does not support reid from scene hierarchy
      if 'reid' in info:
        info.pop('reid')

      mobj = self.tracker.createObject(detectionType, info, when, child, self.persist_attributes.get(detectionType, {}))
      log.debug("RX SCENE OBJECT",
              "id=%s" % (mobj.oid), mobj.sceneLoc)
      if child.retrack:
        objects.append(mobj)
      else:
        child_objects.append(mobj)

    self._finishProcessing(detectionType, when, objects, child_objects)
    return True

  def _finishProcessing(self, detectionType, when, objects, already_tracked_objects=[]):
    self._updateVisible(objects)
    if not ControllerMode.isAnalyticsOnly():
      self.tracker.trackObjects(objects, already_tracked_objects, when, [detectionType],
                                self.ref_camera_frame_rate,
                                self.max_unreliable_time,
                                self.non_measurement_time_dynamic,
                                self.non_measurement_time_static,
                                self.use_tracker)
    self._updateEvents(detectionType, when)
    return

  def _isObjectWithinSensor(self, obj, sensor, is_scene_wide):
    """Return True if obj is within the sensor's coverage area."""
    return is_scene_wide or sensor.isPointWithin(obj.sceneLoc)

  def processSensorData(self, jdata, when):
    sensor_id = jdata['id']
    sensor = None

    if sensor_id in self.sensors:
      sensor = self.sensors[sensor_id]
      log.debug("SENSOR DATA RECEIVED", sensor_id, jdata.get('value'), "type:", getattr(sensor, 'singleton_type', 'NONE'))
    else:
      log.error("Unknown sensor", sensor_id, self.sensors)
      return False

    if hasattr(sensor, 'lastWhen') and sensor.lastWhen is not None and when <= sensor.lastWhen:
      log.debug("DISCARDING PAST DATA", sensor_id, when)
      return True

    # Initialize events dict if needed, but don't clear existing events
    if not hasattr(self, 'events') or self.events is None:
      self.events = {}

    old_value = getattr(sensor, 'value', None)
    cur_value = jdata['value']
    # Don't create 'value' event - sensor data is included in object entry/exit events
    sensor.value = cur_value
    sensor.lastValue = old_value
    sensor.lastWhen = when

    timestamp_str = get_iso_time(when)
    timestamp_epoch = when

    # Find all objects currently in the sensor region across ALL detection types
    # Optimization: check if scene-wide to avoid redundant isPointWithin calls
    # TODO: Further optimize for scenes with many objects: spatial indexing (R-tree),
    # bounding box pre-filtering, or tracking only recently-moved objects
    is_scene_wide = sensor.area == Region.REGION_SCENE
    objects_in_sensor = []

    if self.tracker is not None:
      for detectionType in self.tracker.trackers.keys():
        for obj in self.tracker.currentObjects(detectionType):
          if (not self.use_tracker or obj.frameCount > MIN_FRAMES_FOR_RELIABLE_TRACK) and self._isObjectWithinSensor(obj, sensor, is_scene_wide):
            objects_in_sensor.append(obj)
            obj.chain_data.active_sensors.add(sensor_id)
    else:
      for obj in self._analytics_objects.values():
        if self._isObjectWithinSensor(obj, sensor, is_scene_wide):
          objects_in_sensor.append(obj)
          obj.chain_data.active_sensors.add(sensor_id)

    log.debug("SENSOR OBJECTS FOUND", sensor_id, len(objects_in_sensor), "type:", sensor.singleton_type)

    # Update sensor data on objects based on sensor type
    if objects_in_sensor:
      if sensor.singleton_type == "environmental":
        # Environmental sensors: track timestamped readings with value-change detection
        # TODO: Implement bounded cache for readings arrays to prevent memory exhaustion
        # in long-running scenarios. Consider: max size with FIFO eviction, time-based
        # cleanup, or periodic consolidation. Currently, unchanged values update timestamps
        # instead of appending, but frequent value changes can still cause unbounded growth.
        if not self._updateEnvironmentalSensorReadings(objects_in_sensor, sensor_id, cur_value, timestamp_str):
          return False

      elif sensor.singleton_type == "attribute":
        # Event history tracking - append discrete events (or update timestamp if value unchanged)
        # TODO: Implement bounded cache for attr_sensor_events to prevent memory exhaustion
        # in long-running scenarios with frequent attribute changes.
        self._updateAttributeSensorEvents(objects_in_sensor, sensor_id, cur_value, timestamp_str)

    return True

  def _updateEnvironmentalSensorReadings(self, objects_in_sensor, sensor_id, cur_value, timestamp_str):
    return update_environmental_sensor_readings(objects_in_sensor, sensor_id, cur_value, timestamp_str)

  def _updateAttributeSensorEvents(self, objects_in_sensor, sensor_id, cur_value, timestamp_str):
    update_attribute_sensor_events(objects_in_sensor, sensor_id, cur_value, timestamp_str)

  def syncAnalyticsObjects(self, detection_type, tracked_objects):
    """
    Reconcile analytics_objects with a fresh batch of tracked objects
    for the given detection type: evict stale entries, then deserialize
    and index the incoming objects.
    """
    current_ids = {obj['id'] for obj in tracked_objects if 'id' in obj}

    # Only remove stale objects belonging to THIS detection type
    stale = [
      oid for oid, wrapper in self._analytics_objects.items()
      if wrapper.category == detection_type and oid not in current_ids
    ]
    for oid in stale:
      del self._analytics_objects[oid]

    # Create or update wrappers — deserialize as a batch for efficiency,
    # then index results by id so _analytics_objects stays consistent.
    deserialized = self._deserializeTrackedObjects(tracked_objects)
    for wrapper in deserialized:
      self._analytics_objects[wrapper.gid] = wrapper
    return

  def updateTrackedObjects(self, detection_type, tracked_objects):
    """
    Update the cache of tracked objects from MQTT.
    This is used by Analytics to consume tracked objects published by the Tracker service.

    Args:
        detection_type: The type of detection (e.g., 'person', 'vehicle')
        tracked_objects: List of tracked objects for this detection type
    """
    self.tracked_objects_cache[detection_type] = tracked_objects

    if ControllerMode.isAnalyticsOnly():
      self.syncAnalyticsObjects(detection_type, tracked_objects)
    return

  def getTrackedObjects(self, detection_type):
    """
    Get tracked objects from cache (MQTT) or direct tracker call.

    Args:
        detection_type: The type of detection

    Returns:
        List of tracked objects (MovingObject instances or deserialized object-like structures)
    """
    # If analytics-only mode is enabled, only use MQTT cache (from separate Tracker service)
    if ControllerMode.isAnalyticsOnly():
      return [obj for obj in self._analytics_objects.values()
              if obj.category == detection_type]
    if self.tracker is not None:
      return self.tracker.currentObjects(detection_type)
    return []

  def _deserializeTrackedObjects(self, serialized_objects):
    """
    Convert serialized tracked objects to a format usable by Analytics.
    This creates lightweight wrappers that mimic MovingObject interface.
    If objects are already deserialized, returns them as-is.

    Args:
        serialized_objects: List of serialized object dictionaries or already deserialized objects

    Returns:
        List of object-like structures with necessary attributes
    """

    if not serialized_objects or not isinstance(serialized_objects, list):
      return serialized_objects if serialized_objects else []

    if len(serialized_objects) > 0 and not isinstance(serialized_objects[0], dict):
      return serialized_objects

    objects = []
    for obj_data in serialized_objects:
      if not isinstance(obj_data, dict):
        continue

      obj_id = obj_data.get('id')

      # Reuse existing object to preserve chain_data, or create a new one
      if obj_id in self._analytics_objects:
        obj = self._analytics_objects[obj_id]
      else:
        obj = SimpleNamespace()
        obj.chain_data = ChainData(regions={}, publishedLocations=[], persist={})
        self._analytics_objects[obj_id] = obj

      obj.gid = obj_id
      obj.category = obj_data.get('type', obj_data.get('category'))
      obj.sceneLoc = Point(obj_data.get('translation', [0, 0, 0]))
      obj.velocity = Point(obj_data.get('velocity', [0, 0, 0])) if obj_data.get('velocity') else None
      obj.size = obj_data.get('size')
      obj.confidence = obj_data.get('confidence')
      obj.frameCount = obj_data.get('frame_count', 0)
      obj.rotation = obj_data.get('rotation')
      obj.reid = {}
      obj.metadata = {}
      obj.vectors = []
      obj.boundingBox = None
      obj.boundingBoxPixels = None
      obj.intersected = False
      obj.visibility = obj_data.get('visibility', [])
      obj.info = {'category': obj.category, 'confidence': obj.confidence}

      # Restore bbMeters from size if available
      if obj.size and len(obj.size) == 3:
        _, width, height = obj.size
        obj.bbMeters = SimpleNamespace(size=Size(width, height), width=width, height=height)
      else:
        obj.bbMeters = None

      metadata = obj_data.get('metadata', {})
      obj.reid = metadata.get('reid') if metadata else {}
      obj.similarity = obj_data.get('similarity')

      if 'camera_bounds' in obj_data and obj_data['camera_bounds']:
        obj._camera_bounds = obj_data['camera_bounds']
      else:
        obj._camera_bounds = None

      # Timestamps
      if 'first_seen' in obj_data:
        obj.first_seen = get_epoch_time(obj_data['first_seen'])
        obj.when = obj.first_seen
        self.object_history_cache.setdefault(obj_id, {})['first_seen'] = obj.when
      elif obj_id in self.object_history_cache and 'first_seen' in self.object_history_cache[obj_id]:
        obj.first_seen = self.object_history_cache[obj_id]['first_seen']
        obj.when = obj.first_seen
      else:
        current_time = get_epoch_time()
        obj.first_seen = current_time
        obj.when = current_time
        self.object_history_cache.setdefault(obj_id, {})['first_seen'] = current_time
        log.debug(f"First time seeing object id {obj_id} from MQTT; setting first_seen to current time: {current_time}")

      obj.chain_data.regions = obj_data.get('regions', obj.chain_data.regions)
      obj.chain_data.persist = obj_data.get('persistent_data', obj.chain_data.persist)

      # Convert serialized sensors into env_sensor_state and attr_sensor_events
      sensors_data = obj_data.get('sensors', {})
      for sensor_id, sensor_info in sensors_data.items():
        values = sensor_info.get('values', [])
        if not values:
          continue

        is_environmental = self._isEnvironmentalSensor(sensor_id, values)

        if is_environmental:
          obj.chain_data.env_sensor_state[sensor_id] = {'readings': values}
        else:
          obj.chain_data.attr_sensor_events[sensor_id] = values

      if obj_id in self.object_history_cache:
        obj.chain_data.publishedLocations = self.object_history_cache[obj_id].get('publishedLocations', [])
      # Store current object data for next frame
      self.object_history_cache.setdefault(obj_id, {})['publishedLocations'] = obj.chain_data.publishedLocations
      self.object_history_cache.setdefault(obj_id, {})['last_seen'] = obj.sceneLoc

      objects.append(obj)

    return objects

  def _isEnvironmentalSensor(self, sensor_id, values):
    sensor = self.sensors.get(sensor_id)
    if sensor is not None and getattr(sensor, 'singleton_type', None) is not None:
      return sensor.singleton_type == "environmental"

    return True

  def _updateEvents(self, detectionType, now, curObjects=None):
    # Preserve existing events (e.g., sensor 'value' events) instead of clearing
    if not hasattr(self, 'events') or self.events is None:
      self.events = {}
    if curObjects is None:
      if ControllerMode.isAnalyticsOnly():
        curObjects = self.getTrackedObjects(detectionType)
      else:
        curObjects = self.tracker.currentObjects(detectionType) if self.tracker else []
    curObjects = [moving_object_to_analytics_object(o) for o in curObjects]
    process_frame(
      detectionType, now, curObjects,
      self.regions, self.sensors, self.tripwires,
      self.events, self.use_tracker, self.isIntersecting,
    )
    return

  def _updateTripwireEvents(self, detectionType, now, curObjects):
    update_tripwire_events(
      detectionType, self.tripwires, now, curObjects, self.events, self.use_tracker,
    )
    return

  def _updateRegionEvents(self, detectionType, regions, now, now_str, curObjects):
    return update_region_events(
      detectionType, regions, now, now_str, curObjects, self.events,
      self.use_tracker, self.isIntersecting,
    )

  def isIntersecting(self, obj, region):
    if not region.compute_intersection:
      return False

    if region.mesh is None:
      createRegionMesh(region)

    try:
      createObjectMesh(obj)
    except ValueError as e:
      log.info(f"Error creating object mesh for intersection check: {e}")
      return False

    return obj.mesh.is_intersecting(region.mesh)

  def _updateVisible(self, curObjects):
    """! Update the visibility of objects from cameras in the scene."""
    for obj in curObjects:
      vis = []

      for sname in self.cameras:
        camera = self.cameras[sname]
        if hasattr(camera, 'pose') and hasattr(camera.pose, 'regionOfView') \
           and camera.pose.regionOfView.isPointWithin(obj.sceneLoc):
          vis.append(camera.cameraID)

      obj.visibility = vis
    return

  @classmethod
  def deserialize(cls, data):
    tracker_config = data.get('tracker_config', [])
    reid_config_data = data.get('reid_config_data', None)
    pose_adjustment_config_data = data.get('pose_adjustment_config_data', None)
    scale_from_data = data.get('scale', None)
    scene = cls(data['name'], data.get('map', None), scale_from_data,
                *tracker_config,
                reid_config_data=reid_config_data,
                pose_adjustment_config_data=pose_adjustment_config_data)
    scene.uid = data['uid']
    scene.mesh_translation = data.get('mesh_translation', None)
    scene.mesh_rotation = data.get('mesh_rotation', None)
    scene._hydrateFromSceneData(data, reid_runtime_update=False)
    return scene

  def _updateChildren(self, newChildren):
    self.children = [x['name'] for x in newChildren]
    return

  def updateCameras(self, newCameras):
    old = set(self.cameras.keys())
    new = set([x['uid'] for x in newCameras])
    for cameraData in newCameras:
      camID = cameraData['uid']
      self.cameras[camID] = Camera(camID, cameraData, resolution=cameraData['resolution'])
    deleted = old - new
    for camID in deleted:
      self.cameras.pop(camID)
    return

  def _updateRegions(self, existingRegions, newRegions):
    # Sentinel value to distinguish "attribute doesn't exist" from "attribute is None"
    _NOTSET = object()

    old = set(existingRegions.keys())
    new = set([x['uid'] for x in newRegions])
    for regionData in newRegions:
      region_uuid = regionData['uid']
      region_name = regionData['name']
      if region_uuid in existingRegions:
        region = existingRegions[region_uuid]

        # Preserve sensor cache, event state, and region state before geometry updates
        # Use sentinel to distinguish missing attributes from None values
        cached_value = getattr(region, 'value', _NOTSET)
        cached_last_value = getattr(region, 'lastValue', _NOTSET)
        cached_last_when = getattr(region, 'lastWhen', _NOTSET)
        cached_entered = getattr(region, 'entered', _NOTSET)
        cached_exited = getattr(region, 'exited', _NOTSET)
        cached_objects = getattr(region, 'objects', _NOTSET)
        cached_when = getattr(region, 'when', _NOTSET)

        region.updatePoints(regionData)
        region.updateSingletonType(regionData)
        region.updateVolumetricInfo(regionData)
        region.name = region_name

        # Restore sensor cache, event state, and region state after geometry updates
        # Only restore if attribute existed before (even if value was None)
        if cached_value is not _NOTSET:
          region.value = cached_value
        if cached_last_value is not _NOTSET:
          region.lastValue = cached_last_value
        if cached_last_when is not _NOTSET:
          region.lastWhen = cached_last_when
        if cached_entered is not _NOTSET:
          region.entered = cached_entered
        if cached_exited is not _NOTSET:
          region.exited = cached_exited
        if cached_objects is not _NOTSET:
          region.objects = cached_objects
        if cached_when is not _NOTSET:
          region.when = cached_when
      else:
        region = Region(region_uuid, region_name, regionData)
        existingRegions[region_uuid] = region
        # Log sensor configuration for debugging
        if hasattr(region, 'singleton_type') and region.singleton_type:
          log.debug("SENSOR LOADED", region_name, "area:", region.area, "singleton_type:", region.singleton_type)
    deleted = old - new
    for region_uuid in deleted:
      existingRegions.pop(region_uuid)
    return

  def _updateTripwires(self, newTripwires):
    old = set(self.tripwires.keys())
    new = set([x['uid'] for x in newTripwires])
    for tripwireData in newTripwires:
      tripwire_uuid = tripwireData["uid"]
      tripwire_name = tripwireData['name']
      self.tripwires[tripwire_uuid] = Tripwire(tripwire_uuid, tripwire_name, tripwireData)
    deleted = old - new
    for tripwireID in deleted:
      self.tripwires.pop(tripwireID)
    return

  @property
  def trs_xyz_to_lla(self) -> Optional[np.ndarray]:
    """
    Get the transformation matrix from TRS (Translation, Rotation, Scale) coordinates to LLA (Latitude, Longitude, Altitude) coordinates.

    The matrix is calculated lazily on first access and cached for subsequent calls.
    """
    if self._trs_xyz_to_lla is None and self.output_lla and self.map_corners_lla is not None:
      mesh_corners_xyz = getMeshAxisAlignedProjectionToXY(self.map_triangle_mesh)
      self._trs_xyz_to_lla = calculateTRSLocal2LLAFromSurfacePoints(mesh_corners_xyz, self.map_corners_lla)
    return self._trs_xyz_to_lla

  def _invalidate_trs_xyz_to_lla(self):
    """
    Invalidate the cached transformation matrix from TRS to LLA coordinates.
    This method should be called when the scene geospatial mapping parameters change.
    """
    self._trs_xyz_to_lla = None
    return
