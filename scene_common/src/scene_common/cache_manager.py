# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# The controller package (and robot_vision, imported by controller.scene at
# module level) isn't installed in the analytics image, so keep all
# controller.* imports lazy to allow CacheManager (and therefore
# AnalyticsService) to be imported there.
import threading

# Scene (and robot_vision, imported by controller.scene at module level)
# isn't installed in the analytics image, so keep that one import lazy to
# allow CacheManager (and therefore AnalyticsService) to be imported there.
# CameraRegistry/TrackedObjectRegistry now live in scene_common alongside
# everything else here, so they're safe to import eagerly.
from scene_common.data_source import RestSceneDataSource, FileSceneDataSource
from scene_common.camera_registry import CameraRegistry
from scene_common.tracking_object_registry import TrackedObjectRegistry

from scene_common import log
from scene_common.timestamp import get_epoch_time

REFRESH_TIME = 60

class CacheManager:
  def __init__(self, data_source=None, rest_url=None, rest_auth=None,
               root_cert=None, tracker_config_data={}, reid_config_data={},
               pose_adjustment_config_data=None, scene_cls=None):
    self._lock = threading.RLock()
    self._refresh_done = threading.Condition(self._lock)
    # Per-instance refresh coordination (not class state — multiple managers
    # in one process must not block or supersede each other).
    self._cache_epoch = 0
    self._refresh_in_progress = False
    self.cached_child_transforms_by_uid = {}
    self.camera_parameters = {}
    self.tracker_config_data = tracker_config_data
    self.reid_config_data = reid_config_data
    self.pose_adjustment_config_data = (
      pose_adjustment_config_data if pose_adjustment_config_data else {}
    )
    self._scene_cls = scene_cls
    if self._scene_cls is None:
      from controller.scene import Scene
      self._scene_cls = Scene
    self.cached_scenes_by_uid = {}
    self._cached_scenes_by_cameraID = {}
    self._cached_scenes_by_sensorID = {}

    if rest_url and rest_auth:
      self.data_source = RestSceneDataSource(rest_url, rest_auth, root_cert)
    elif data_source:
      self.data_source = FileSceneDataSource(data_source)
    else:
      raise ValueError("Invalid configuration: must provide rest_url/rest_auth or .json file(s)")
    self.refreshScenes()
    return

  def _refreshLock(self):
    """Lock and condition used for single-flight refresh, created on first use."""
    if not hasattr(self, '_lock'):
      self._lock = threading.RLock()
    if not hasattr(self, '_refresh_done'):
      self._refresh_done = threading.Condition(self._lock)
    if not hasattr(self, '_cache_epoch'):
      self._cache_epoch = 0
    if not hasattr(self, '_refresh_in_progress'):
      self._refresh_in_progress = False
    return self._lock

  def _cacheNeedsRefresh(self):
    return (
      not hasattr(self, 'cached_scenes_by_uid')
      or self.cached_scenes_by_uid is None
      or not hasattr(self, '_cache_refreshed')
    )

  def refreshScenes(self, force=False):
    # Single-flight: concurrent callers share one in-flight refresh instead of
    # racing parallel REST fetches. A waiter accepts the shared result only if
    # the cache ends up usable; otherwise (the fetch was superseded by
    # invalidate(), or failed) it fetches itself. force=True always fetches
    # after waiting, so a refresh requested after a write never adopts a result
    # fetched before it.
    self._refreshLock()
    while True:
      with self._lock:
        if self._refresh_in_progress:
          while self._refresh_in_progress:
            self._refresh_done.wait()
          if not force and not self._cacheNeedsRefresh():
            return
          continue

        self._refresh_in_progress = True
        epoch = self._cache_epoch

      try:
        # REST fetch happens OUTSIDE the lock so it doesn't block other threads
        # doing lookups while we wait on the network.
        result = self.data_source.getScenes()
        if 'results' not in result:
          log.error("Failed to get results, error code: ", result.statusCode)
          return
        found = result.get("results", [])

        # _refreshCameras also does REST calls; keep those outside the lock too.
        for scene_data in found:
          self._refreshCameras(scene_data)

        with self._lock:
          if epoch != self._cache_epoch:
            # invalidate() superseded this fetch, so its results are stale.
            return
          self._applySceneResults(found)
        return
      finally:
        with self._lock:
          self._refresh_in_progress = False
          self._refresh_done.notify_all()

  def _applySceneResults(self, found):
    """Apply fetched scene results. Caller must hold self._lock."""
    if not hasattr(self, 'cached_scenes_by_uid') or self.cached_scenes_by_uid is None:
      self.cached_scenes_by_uid = {}
    self._cached_scenes_by_cameraID = {}
    self._cached_scenes_by_sensorID = {}

    old = set(self.cached_scenes_by_uid.keys())
    new = set(x['uid'] for x in found)
    deleted = old - new
    for uid in deleted:
      self._teardownScene(self.cached_scenes_by_uid.pop(uid, None))

    for scene_data in found:
      if self.tracker_config_data:
        scene_data["tracker_config"] = [self.tracker_config_data["max_unreliable_time"],
                                      self.tracker_config_data["non_measurement_time_dynamic"],
                                      self.tracker_config_data["non_measurement_time_static"],
                                      self.tracker_config_data["effective_object_update_rate"],
                                      self.tracker_config_data["time_chunking_enabled"],
                                      self.tracker_config_data["time_chunking_rate_fps"],
                                      self.tracker_config_data["suspended_track_timeout_secs"]]
        scene_data["persist_attributes"] = self.tracker_config_data.get("persist_attributes", {})
      if self.reid_config_data:
        scene_data["reid_config_data"] = self.reid_config_data
      if getattr(self, 'pose_adjustment_config_data', {}):
        scene_data["pose_adjustment_config_data"] = self.pose_adjustment_config_data

      uid = scene_data['uid']
      if uid not in self.cached_scenes_by_uid:
        old_scene = self._sensorNeedsRestoring(uid)
        if old_scene is not None:
          # Reuse the existing scene to preserve tracked objects, sensor state,
          # analytics_state and dwell times across DB-triggered refreshes.
          scene = old_scene
          scene.updateScene(scene_data)
        else:
          scene_cls = getattr(self, '_scene_cls', None)
          if scene_cls is None:
            from controller.scene import Scene
            scene_cls = Scene
          scene = scene_cls.deserialize(scene_data)
      else:
        scene = self.cached_scenes_by_uid[uid]
        scene.updateScene(scene_data)

      for cameraID in scene.cameras.keys():
        self._cached_scenes_by_cameraID[cameraID] = scene
      for sensorID in scene.sensors.keys():
        self._cached_scenes_by_sensorID[sensorID] = scene
      self.cached_scenes_by_uid[scene.uid] = scene

    # Clear old scene cache after processing all scenes
    if hasattr(self, '_old_scene_cache'):
      self._old_scene_cache = None

    self._cache_refreshed = get_epoch_time()

  def _teardownScene(self, scene):
    """
    Fully tear down a Scene that has been deleted (no longer present in the
    data source). Stops its tracker thread(s) -- which in turn shuts down
    each category's UUIDManager (thread pool, stale-feature timer) -- and
    clears its process-wide registry state, so a deleted scene doesn't leak
    threads or linger in CameraRegistry/TrackedObjectRegistry indefinitely.
    Must run in this order: join the tracker before clearing the registries,
    since an in-flight detection could otherwise repopulate registry state
    for a scene_id that's about to disappear.

    @param  scene  The Scene instance being removed, or None (safe no-op --
                   pop(uid, None) returns None if uid was somehow already gone)
    """
    if scene is None:
      return
    if getattr(scene, "tracker", None) is not None:
      scene.tracker.join()
    CameraRegistry.getInstance().removeScene(scene.name)
    TrackedObjectRegistry.getInstance().removeScene(scene.name)
    return

  def _sensorNeedsRestoring(self, uid):
    # Check if any old scene has sensors with cache values that can be restored
    if hasattr(self, '_old_scene_cache') and self._old_scene_cache:
      return self._old_scene_cache.get(uid)
    return None

  def _restoreSensorCache(self, uid, old_scene, scene):
    """Restore sensor cache values from old_scene to new scene"""
    restored_count = 0
    for sensor_id, old_sensor in old_scene.sensors.items():
      if hasattr(scene, 'sensors') and sensor_id in scene.sensors:
        new_sensor = scene.sensors[sensor_id]
        restored = False
        if hasattr(old_sensor, 'value'):
          new_sensor.value = old_sensor.value
          restored = True
        if hasattr(old_sensor, 'lastValue'):
          new_sensor.lastValue = old_sensor.lastValue
          restored = True
        if hasattr(old_sensor, 'lastWhen'):
          new_sensor.lastWhen = old_sensor.lastWhen
          restored = True
        if restored:
          restored_count += 1
    if restored_count > 0:
      log.debug(f"Restored sensor cache for {restored_count} sensor(s) in scene {uid}")

  def _refreshCameras(self, scene_data):
    for camera in scene_data.get('cameras', []):
      update_data = {}
      supported_distortion_values = ('k1','k2','p1','p2','k3')

      if camera['uid'] in self.camera_parameters:
        intrinsics = self.camera_parameters[camera['uid']].get('intrinsics')
        if intrinsics and camera.get('intrinsics') != intrinsics:
          update_data['intrinsics'] = intrinsics

        # FIXME: Only use supported distortion values until more are supported by database
        distortion_values = {
          dist_coeff: self.camera_parameters[camera['uid']].get('distortion')[dist_coeff]
          for dist_coeff in supported_distortion_values
        }
        if camera.get('distortion') != distortion_values:
          update_data['distortion'] = self.camera_parameters[camera['uid']]['distortion']

      if update_data:
        res = self.data_source.updateCamera(camera['uid'], update_data)
        if not res:
          log.warning(f"Failed to update camera {camera['uid']}")

        # Make a get request to pull the updated camera information
        # from db and store it to existing camera dictionary
        camera = self.data_source.getCamera(camera['uid'])
    return

  def refreshScenesForCamParams(self, jdata):
    intrinsics_changed = self.cameraParametersChanged(jdata, 'intrinsics')
    distortion_changed = self.cameraParametersChanged(jdata, 'distortion')

    if not (intrinsics_changed or distortion_changed):
      return

    self.checkRefresh()
    cameras_to_update = []
    with self._lock:
      if self.cached_scenes_by_uid is None:
        log.warning("refreshScenesForCamParams: cache still None after refresh attempt, skipping")
        return
      for scene in self.cached_scenes_by_uid.values():
        for camera in scene.cameras:
          if jdata['id'] == camera:
            intrinsics = jdata.get('intrinsics', {})
            cx = intrinsics.get('cx')
            cy = intrinsics.get('cy')

            if cx is not None and cy is not None:
              width = cx * 2
              height = cy * 2
              current_resolution = scene.cameras[camera].pose.resolution if hasattr(scene.cameras[camera].pose, 'resolution') else None
              if current_resolution != [width, height]:
                self.camera_parameters[camera]['resolution'] = [width, height]
                cameras_to_update.append(scene.cameras[camera])

    # updateCamera does REST; keep it outside the lock so lookups aren't blocked.
    for cam in cameras_to_update:
      self.updateCamera(cam)

    self.refreshScenes(force=True)
    return

  def updateCamera(self, cam):
    if cam.cameraID not in self.camera_parameters:
      return
    params = self.camera_parameters[cam.cameraID]
    intrinsics = params.get('intrinsics')
    distortion = params.get('distortion')
    resolution = params.get('resolution')

    payload = {
      'intrinsics': intrinsics,
      'distortion': distortion
    }
    if resolution is not None:
      payload['resolution'] = {
        'width': resolution[0],
        'height': resolution[1]
      }

    res = self.data_source.updateCamera(cam.cameraID, payload)
    if not res:
      log.warning(f"Failed to update camera {cam.cameraID}")
    return

  def cameraParametersChanged(self, message, parameter_type):
    message_parameters = message.get(parameter_type)
    stored_parameters = self.camera_parameters.get(message['id'], {}).get(parameter_type)
    if message_parameters and message_parameters != stored_parameters:
      self.camera_parameters.setdefault(message['id'], {})[parameter_type] = message[parameter_type]
      return True
    return False

  def checkRefresh(self):
    self._refreshLock()
    with self._lock:
      needs_refresh = self._cacheNeedsRefresh()
    if not needs_refresh:
      return

    self.refreshScenes()

    # A refresh discarded by a concurrent invalidate() leaves the cache empty;
    # retry once so lookups do not treat it as permanently missing.
    with self._lock:
      still_needs_refresh = self._cacheNeedsRefresh()
    if still_needs_refresh:
      self.refreshScenes()
    return

  def allScenes(self):
    self.checkRefresh()
    with self._lock:
      return list(self.cached_scenes_by_uid.values()) if self.cached_scenes_by_uid else []

  def sceneWithID(self, sceneID):
    self.checkRefresh()
    with self._lock:
      if self.cached_scenes_by_uid is None:
        return None
      return self.cached_scenes_by_uid.get(sceneID, None)

  def sceneWithCameraID(self, cameraID):
    self.checkRefresh()
    with self._lock:
      return self._cached_scenes_by_cameraID.get(cameraID, None)

  def sceneWithSensorID(self, sensorID):
    self.checkRefresh()
    with self._lock:
      return self._cached_scenes_by_sensorID.get(sensorID, None)

  def sceneWithRemoteChildID(self, childID):
    self.checkRefresh()
    with self._lock:
      return self.cached_child_transforms_by_uid.get(childID, None)

  def invalidate(self):
    # Preserve old scene cache for sensor value restoration
    self._refreshLock()
    with self._lock:
      if self.cached_scenes_by_uid is not None:
        self._old_scene_cache = self.cached_scenes_by_uid
      elif not hasattr(self, '_old_scene_cache'):
        self._old_scene_cache = {}
      self.cached_scenes_by_uid = None
      self._cached_scenes_by_cameraID = {}
      self._cached_scenes_by_sensorID = {}
      # Supersede any in-flight refresh so its results are discarded.
      self._cache_epoch += 1
      if not hasattr(self, 'cached_child_transforms_by_uid') or self.cached_child_transforms_by_uid is None:
        self.cached_child_transforms_by_uid = {}
    return
