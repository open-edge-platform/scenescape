# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from scene_common.camera import Camera
from scene_common.geometry import Point, Region, Tripwire
from scene_common.mesh_util import createObjectMesh, createRegionMesh
from scene_common.scene_model import SceneModel
from scene_common.timestamp import get_iso_time
from scene_common.transform import CameraPose

from controller.analytics.adapters.ingestion import SceneDataIngestion
from controller.analytics.analytics_models import moving_object_to_analytics_object
from controller.analytics.engine import process_frame
from controller.analytics.event_publisher import publish_events
from controller.analytics.sensors import (
  update_attribute_sensor_events,
  update_environmental_sensor_readings,
)
from controller.analytics.state import AnalyticsStateStore


class AnalyticsScene(SceneModel):
  """Scene model for the standalone analytics service.

  Equivalent to Scene but without the tracker, robot_vision, pose-adjustment,
  or Re-ID dependencies.  Allows CacheManager (and therefore the analytics
  image) to be imported without building the robot_vision C++ extension.
  """

  def __init__(self, name, map_file, scale=None):
    super().__init__(name, map_file, scale)
    log.info("NEW ANALYTICS SCENE", name, map_file, scale)

    self._ingestion = SceneDataIngestion()
    self._analytics_objects = self._ingestion._objects
    self.object_history_cache = self._ingestion._history

    self.use_tracker = False
    self.persist_attributes = {}
    self.analytics_state = AnalyticsStateStore()
    self.regulated_rate = 30
    self.external_update_rate = 30
    return

  def _hydrateFromSceneData(self, scene_data):
    self.parent = scene_data.get('parent', None)
    self.cameraPose = None
    if 'transform' in scene_data:
      self.cameraPose = CameraPose(scene_data['transform'], None)
    self.use_tracker = False
    self.output_lla = scene_data.get('output_lla', False)
    self.map_corners_lla = scene_data.get('map_corners_lla', None)
    self.retrack = scene_data.get('retrack', True)
    self.persist_attributes = scene_data.get('persist_attributes', {})
    self._updateChildren(scene_data.get('children', []))
    self.updateCameras(scene_data.get('cameras', []))
    self._updateRegions(self.regions, scene_data.get('regions', []))
    self._updateTripwires(scene_data.get('tripwires', []))
    self._updateRegions(self.sensors, scene_data.get('sensors', []))
    self.name = scene_data['name']
    if 'scale' in scene_data:
      self.scale = scene_data['scale']
    if 'regulated_rate' in scene_data:
      self.regulated_rate = scene_data['regulated_rate']
    if 'external_update_rate' in scene_data:
      self.external_update_rate = scene_data['external_update_rate']
    return

  def updateScene(self, scene_data):
    self._hydrateFromSceneData(scene_data)
    return

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
    _NOTSET = object()
    old = set(existingRegions.keys())
    new = set([x['uid'] for x in newRegions])
    for regionData in newRegions:
      region_uuid = regionData['uid']
      region_name = regionData['name']
      if region_uuid in existingRegions:
        region = existingRegions[region_uuid]
        cached_value = getattr(region, 'value', _NOTSET)
        cached_last_value = getattr(region, 'lastValue', _NOTSET)
        cached_last_when = getattr(region, 'lastWhen', _NOTSET)
        region.updatePoints(regionData)
        region.updateSingletonType(regionData)
        region.updateVolumetricInfo(regionData)
        region.name = region_name
        if cached_value is not _NOTSET:
          region.value = cached_value
        if cached_last_value is not _NOTSET:
          region.lastValue = cached_last_value
        if cached_last_when is not _NOTSET:
          region.lastWhen = cached_last_when
      else:
        region = Region(region_uuid, region_name, regionData)
        existingRegions[region_uuid] = region
    deleted = old - new
    for region_uuid in deleted:
      existingRegions.pop(region_uuid)
      self.analytics_state.remove_region(region_uuid)
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
      self.analytics_state.remove_tripwire(tripwireID)
    return

  def syncAnalyticsObjects(self, detection_type, tracked_objects):
    self._ingestion.ingest(detection_type, tracked_objects, self.sensors)
    return

  def updateTrackedObjects(self, detection_type, tracked_objects):
    self.syncAnalyticsObjects(detection_type, tracked_objects)
    return

  def getTrackedObjects(self, detection_type):
    return self._ingestion.get_objects(detection_type)

  def _deserializeTrackedObjects(self, serialized_objects):
    return self._ingestion.deserialize(serialized_objects, self.sensors)

  def _isEnvironmentalSensor(self, sensor_id, values):
    return SceneDataIngestion._is_environmental_sensor(sensor_id, self.sensors)

  def _isObjectWithinSensor(self, obj, sensor, is_scene_wide):
    return is_scene_wide or sensor.isPointWithin(obj.sceneLoc)

  def processSensorData(self, jdata, when):
    sensor_id = jdata['id']
    if sensor_id in self.sensors:
      sensor = self.sensors[sensor_id]
      log.debug("SENSOR DATA RECEIVED", sensor_id, jdata.get('value'), "type:", getattr(sensor, 'singleton_type', 'NONE'))
    else:
      log.error("Unknown sensor", sensor_id, self.sensors)
      return False

    if hasattr(sensor, 'lastWhen') and sensor.lastWhen is not None and when <= sensor.lastWhen:
      log.debug("DISCARDING PAST DATA", sensor_id, when)
      return True

    if not hasattr(self, 'events') or self.events is None:
      self.events = {}

    old_value = getattr(sensor, 'value', None)
    cur_value = jdata['value']
    sensor.value = cur_value
    sensor.lastValue = old_value
    sensor.lastWhen = when

    timestamp_str = get_iso_time(when)

    is_scene_wide = sensor.area == Region.REGION_SCENE
    objects_in_sensor = []
    for obj in self._analytics_objects.values():
      if self._isObjectWithinSensor(obj, sensor, is_scene_wide):
        objects_in_sensor.append(obj)
        obj.chain_data.active_sensors.add(sensor_id)

    if objects_in_sensor:
      if sensor.singleton_type == "environmental":
        if not update_environmental_sensor_readings(objects_in_sensor, sensor_id, cur_value, timestamp_str):
          return False
      elif sensor.singleton_type == "attribute":
        update_attribute_sensor_events(objects_in_sensor, sensor_id, cur_value, timestamp_str)

    return True

  def _updateEvents(self, detectionType, now, curObjects=None, publish_fn=None):
    if not hasattr(self, 'events') or self.events is None:
      self.events = {}
    if curObjects is None:
      curObjects = self.getTrackedObjects(detectionType)
    curObjects = [moving_object_to_analytics_object(o) for o in curObjects]
    process_frame(
      detectionType, now, curObjects,
      self.regions, self.sensors, self.tripwires,
      self.events, self.analytics_state, self.isIntersecting,
    )
    if publish_fn is not None:
      publish_events(self, get_iso_time(now), publish_fn)
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
    scene = cls(data['name'], data.get('map', None), data.get('scale', None))
    scene.uid = data['uid']
    scene.mesh_translation = data.get('mesh_translation', None)
    scene.mesh_rotation = data.get('mesh_rotation', None)
    scene._hydrateFromSceneData(data)
    return scene
