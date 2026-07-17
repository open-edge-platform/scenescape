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

    if not ControllerMode.isAnalyticsOnly():
      self._setTracker("time_chunked_intel_labs" if time_chunking_enabled else self.DEFAULT_TRACKER)
    else:
      log.info("Tracker initialization SKIPPED for scene: " + name)

    self._trs_xyz_to_lla = None
    self.use_tracker = not ControllerMode.isAnalyticsOnly()

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
    return

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

        # Preserve sensor cache before geometry updates
        cached_value = getattr(region, 'value', _NOTSET)
        cached_last_value = getattr(region, 'lastValue', _NOTSET)
        cached_last_when = getattr(region, 'lastWhen', _NOTSET)

        region.updatePoints(regionData)
        region.updateSingletonType(regionData)
        region.updateVolumetricInfo(regionData)
        region.name = region_name

        # Restore sensor cache after geometry updates
        if cached_value is not _NOTSET:
          region.value = cached_value
        if cached_last_value is not _NOTSET:
          region.lastValue = cached_last_value
        if cached_last_when is not _NOTSET:
          region.lastWhen = cached_last_when
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
