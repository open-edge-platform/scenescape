# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import itertools
from types import SimpleNamespace
from typing import Optional
import numpy as np
import robot_vision as rv
from controller.controller_mode import ControllerMode
from scene_common import log
from scene_common.camera import Camera
from scene_common.earth_lla import convertLLAToECEF, calculateTRSLocal2LLAFromSurfacePoints
from scene_common.geometry import Line, Point, Region, Tripwire
from scene_common.scene_model import SceneModel
from scene_common.timestamp import get_epoch_time, get_iso_time
from scene_common.transform import CameraPose
from scene_common.mesh_util import getMeshAxisAlignedProjectionToXY, createRegionMesh, createObjectMesh

from controller.ilabs_tracking import IntelLabsTracking
from controller.time_chunking import TimeChunkedIntelLabsTracking, DEFAULT_CHUNKING_RATE_FPS
from controller.tracking import (MAX_UNRELIABLE_TIME,
                                 NON_MEASUREMENT_TIME_DYNAMIC,
                                 NON_MEASUREMENT_TIME_STATIC,
                                 EFFECTIVE_OBJECT_UPDATE_RATE,
                                 DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS)

DEBOUNCE_DELAY = 0.5

class TripwireEvent:
  def __init__(self, object, direction):
    self.object = object
    self.direction = direction
    return

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
               suspended_track_timeout_secs = DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS):
    log.info("NEW SCENE", name, map_file, scale, max_unreliable_time,
             non_measurement_time_dynamic, non_measurement_time_static,
             "analytics_only=" + str(ControllerMode.isAnalyticsOnly()))
    super().__init__(name, map_file, scale)
    self.ref_camera_frame_rate = time_chunking_rate_fps if time_chunking_enabled else effective_object_update_rate
    self.max_unreliable_time = max_unreliable_time
    self.non_measurement_time_dynamic = non_measurement_time_dynamic
    self.non_measurement_time_static = non_measurement_time_static
    self.suspended_track_timeout_secs = suspended_track_timeout_secs
    self.tracker = None
    self.trackerType = None
    self.persist_attributes = {}
    self.time_chunking_rate_fps = time_chunking_rate_fps

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

    # FIXME - only for backwards compatibility
    self.scale = scale

    return

  def _setTracker(self, trackerType):
    if trackerType not in self.available_trackers:
      log.error("Chosen tracker is not available")
      return
    self.trackerType = trackerType
    log.info("SETTING TRACKER TYPE", trackerType)

    args = (self.max_unreliable_time,
            self.non_measurement_time_dynamic,
            self.non_measurement_time_static)
    if trackerType == "intel_labs":
      args += (self.ref_camera_frame_rate, self.suspended_track_timeout_secs)
    elif trackerType == "time_chunked_intel_labs":
      args += (self.time_chunking_rate_fps, self.suspended_track_timeout_secs)
    self.tracker = self.available_trackers[self.trackerType](*args)
    return

  def updateScene(self, scene_data):
    self.parent = scene_data.get('parent', None)
    self.cameraPose = None
    if 'transform' in scene_data:
      self.cameraPose = CameraPose(scene_data['transform'], None)
    self.use_tracker = scene_data.get('use_tracker', True)
    self.output_lla = scene_data.get('output_lla', False)
    self.map_corners_lla = scene_data.get('map_corners_lla', None)
    self._updateChildren(scene_data.get('children', []))
    self.updateCameras(scene_data.get('cameras', []))
    self._updateRegions(self.regions, scene_data.get('regions', []))
    self._updateTripwires(scene_data.get('tripwires', []))
    self._updateRegions(self.sensors, scene_data.get('sensors', []))
    tracker_config = scene_data.get('tracker_config', None)
    if tracker_config:
      self.updateTracker(tracker_config[0], tracker_config[1], tracker_config[2])
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
    return

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

  def _updateSensorObjects(self, name, sensor, objects=None):
    if not hasattr(sensor, 'value'):
      return

    if objects is None:
      objects = itertools.chain.from_iterable(sensor.objects.values())

    for obj in objects:
      if name not in obj.chain_data.sensors:
        obj.chain_data.sensors[name] = []
      ts_str = get_iso_time(sensor.lastWhen)
      existing = [x[0] for x in obj.chain_data.sensors[name]]
      if ts_str not in existing:
        obj.chain_data.sensors[name].append((ts_str, sensor.value))
    return

  def processSensorData(self, jdata, when):
    sensor_id = jdata['id']
    sensor = None

    if sensor_id in self.sensors:
      sensor = self.sensors[sensor_id]
    else:
      log.error("Unknown sensor", sensor_id, self.sensors)
      return False

    if hasattr(sensor, 'lastWhen') and sensor.lastWhen is not None and when <= sensor.lastWhen:
      log.info("DISCARDING PAST DATA", sensor_id, when)
      return True

    self.events = {}
    old_value = getattr(sensor, 'value', None)
    cur_value = jdata['value']
    self.events['value'] = [(sensor_id, sensor)]
    sensor.value = cur_value
    sensor.lastValue = old_value
    sensor.lastWhen = when
    self._updateSensorObjects(sensor_id, sensor)

    return True

  def updateTrackedObjects(self, detection_type, objects):
    """
    Update the cache of tracked objects from MQTT.
    This is used by Analytics to consume tracked objects published by the Tracker service.

    Args:
        detection_type: The type of detection (e.g., 'person', 'vehicle')
        objects: List of tracked objects for this detection type
    """
    self.tracked_objects_cache[detection_type] = objects
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
      if detection_type in self.tracked_objects_cache:
        cached_objects = self.tracked_objects_cache[detection_type]
        return self._deserializeTrackedObjects(cached_objects)
      return []

    # If tracker is enabled, use direct tracker call (traditional mode)
    if self.tracker is not None:
      log.debug(f"Using direct tracker call for detection type: {detection_type}")
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
      obj = SimpleNamespace()
      obj.gid = obj_data.get('id')
      obj.category = obj_data.get('type', obj_data.get('category'))
      obj.sceneLoc = Point(obj_data.get('translation', [0, 0, 0]))
      obj.velocity = Point(obj_data.get('velocity', [0, 0, 0])) if obj_data.get('velocity') else None
      obj.size = obj_data.get('size')
      obj.confidence = obj_data.get('confidence')
      obj.frameCount = obj_data.get('frame_count', 0)
      obj.rotation = obj_data.get('rotation')
      obj.reidVector = obj_data.get('reid')
      obj.similarity = obj_data.get('similarity')
      obj.vectors = []  # Empty list - tracked objects from MQTT don't have detection vectors
      obj.boundingBoxPixels = None  # Will use camera_bounds from obj_data if available

      if 'first_seen' in obj_data:
        obj.when = get_epoch_time(obj_data.get('first_seen'))
        obj.first_seen = obj.when
      else:
        obj.when = None
        obj.first_seen = None
        log.warning(f"Missing 'first_seen' for object id {obj_data.get('id')}; setting obj.when to None.")
      obj.visibility = obj_data.get('visibility', [])

      obj.info = {
        'category': obj.category,
        'confidence': obj.confidence,
      }

      if 'center_of_mass' in obj_data:
        obj.info['center_of_mass'] = obj_data['center_of_mass']

      if 'camera_bounds' in obj_data and obj_data['camera_bounds']:
        obj._camera_bounds = obj_data['camera_bounds']
      else:
        obj._camera_bounds = None

      obj.chain_data = SimpleNamespace()
      obj.chain_data.regions = obj_data.get('regions', {})
      obj.chain_data.sensors = obj_data.get('sensors', {})
      obj.chain_data.persist = obj_data.get('persistent_data', {})

      obj_id = obj.gid
      if obj_id in self.object_history_cache:
        obj.chain_data.publishedLocations = self.object_history_cache[obj_id].get('publishedLocations', [])
      else:
        obj.chain_data.publishedLocations = []
        self.object_history_cache[obj_id] = {}

      # Store current object data for next frame
      self.object_history_cache[obj_id]['publishedLocations'] = obj.chain_data.publishedLocations
      self.object_history_cache[obj_id]['last_seen'] = obj.sceneLoc

      objects.append(obj)

    return objects

  def _updateEvents(self, detectionType, now, curObjects=None):
    self.events = {}
    now_str = get_iso_time(now)
    if curObjects is None:
      if ControllerMode.isAnalyticsOnly():
        curObjects = self.getTrackedObjects(detectionType)
      else:
        curObjects = self.tracker.currentObjects(detectionType) if self.tracker else []
    for obj in curObjects:
      obj.chain_data.publishedLocations.insert(0, obj.sceneLoc)

    self._updateRegionEvents(detectionType, self.regions, now, now_str, curObjects)
    self._updateRegionEvents(detectionType, self.sensors, now, now_str, curObjects)

    self._updateTripwireEvents(detectionType, now, curObjects)
    return

  def _updateTripwireEvents(self, detectionType, now, curObjects):
    for key in self.tripwires:
      tripwire = self.tripwires[key]
      tripwireObjects = tripwire.objects.get(detectionType, [])
      objects = []
      for obj in curObjects:
        age = now - obj.when
        if obj.frameCount > 3 \
           and len(obj.chain_data.publishedLocations) > 1:
          d = tripwire.lineCrosses(Line(obj.chain_data.publishedLocations[0].as2Dxy,
                                        obj.chain_data.publishedLocations[1].as2Dxy))
          if d != 0:
            event = TripwireEvent(obj, -d)
            objects.append(event)

      if len(tripwireObjects) != len(objects) \
         and now - tripwire.when > DEBOUNCE_DELAY:
        log.debug("TRIPWIRE EVENT", tripwireObjects, len(objects))
        tripwire.objects[detectionType] = objects
        tripwire.when = now
        if 'objects' not in self.events:
          self.events['objects'] = []
        self.events['objects'].append((key, tripwire))
    return

  def _updateRegionEvents(self, detectionType, regions, now, now_str, curObjects):
    updated = set()
    for key in regions:
      region = regions[key]
      regionObjects = region.objects.get(detectionType, [])
      objects = []
      for obj in curObjects:
        # When tracker is disabled, skip the frameCount check and consider all objects;
        # otherwise, only consider objects with frameCount > 3 as reliable.
        if (obj.frameCount > 3 or not self.use_tracker) \
           and (region.isPointWithin(obj.sceneLoc) or self.isIntersecting(obj, region)):
          objects.append(obj)

      cur = set(x.gid for x in objects)
      prev = set(x.gid for x in regionObjects)
      new = cur - prev
      old = prev - cur
      newObjects = [x for x in objects if x.gid in new]
      for obj in newObjects:
        if key not in obj.chain_data.regions:
          obj.chain_data.regions[key] = {'entered': now_str}
          updated.add(key)

      # For sensors add the current sensor value to any new objects
      if hasattr(region, 'value') and region.singleton_type=="environmental":
        for obj in newObjects:
          obj.chain_data.sensors[key] = []
        self._updateSensorObjects(key, region, newObjects)

      if (len(new) or len(old)) and now - region.when > DEBOUNCE_DELAY:
        log.debug("REGION EVENT", key, now_str, regionObjects, len(objects))
        entered = []
        for obj in objects:
          if obj.gid in new and key in obj.chain_data.regions:
            entered.append(obj)
        if not hasattr(region, 'entered'):
          region.entered = {}
        region.entered[detectionType] = entered

        exited = []
        for obj in regionObjects:
          if obj.gid in old:
            if key in obj.chain_data.regions:
              entered = get_epoch_time(obj.chain_data.regions[key]['entered'])
              dwell = now - entered
              exited.append((obj, dwell))
            obj.chain_data.regions.pop(key, None)
        if not hasattr(region, 'exited'):
          region.exited = {}
        region.exited[detectionType] = exited

        region.objects[detectionType] = objects
        updated.add(key)
        region.when = now
        if 'objects' not in self.events:
          self.events['objects'] = []
        self.events['objects'].append((key, region))
        if len(cur) != len(prev):
          if 'count' not in self.events:
            self.events['count'] = []
          self.events['count'].append((key, region))

    return updated

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
    scale_from_data = data.get('scale', None)
    scene = cls(data['name'], data.get('map', None), scale_from_data,
                *tracker_config)
    scene.uid = data['uid']
    scene.mesh_translation = data.get('mesh_translation', None)
    scene.mesh_rotation = data.get('mesh_rotation', None)
    scene.use_tracker = data.get('use_tracker', True) and not ControllerMode.isAnalyticsOnly()
    scene.output_lla = data.get('output_lla', None)
    scene.map_corners_lla = data.get('map_corners_lla', None)
    scene.retrack = data.get('retrack', True)
    scene.regulated_rate = data.get('regulated_rate', None)
    scene.external_update_rate = data.get('external_update_rate', None)
    scene.persist_attributes = data.get('persist_attributes', {})
    if 'cameras' in data:
      scene.updateCameras(data['cameras'])
    if 'regions' in data:
      scene._updateRegions(scene.regions, data['regions'])
    if 'tripwires' in data:
      scene._updateTripwires(data['tripwires'])
    if 'sensors' in data:
      scene._updateRegions(scene.sensors, data['sensors'])
    if 'children' in data:
      scene.children = [x['name'] for x in data['children']]
    if 'parent' in data:
      scene.parent = data['parent']
    if 'transform' in data:
      scene.cameraPose = CameraPose(data['transform'], None)
    if 'tracker_config' in data:
      tracker_config = data['tracker_config']
      scene.updateTracker(tracker_config[0], tracker_config[1], tracker_config[2])
    # Access the property to trigger initialization
    _ = scene.trs_xyz_to_lla
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
    old = set(existingRegions.keys())
    new = set([x['uid'] for x in newRegions])
    for regionData in newRegions:
      region_uuid = regionData['uid']
      region_name = regionData['name']
      if region_uuid in existingRegions:
        existingRegions[region_uuid].updatePoints(regionData)
        existingRegions[region_uuid].updateSingletonType(regionData)
        existingRegions[region_uuid].updateVolumetricInfo(regionData)
        existingRegions[region_uuid].name = region_name
      else:
        existingRegions[region_uuid] = Region(region_uuid, region_name, regionData)
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
