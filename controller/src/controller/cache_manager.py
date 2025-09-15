# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from controller.scene import Scene
from controller.data_source import RestSceneDataSource, FileSceneDataSource

from scene_common import log
from scene_common.timestamp import get_epoch_time

REFRESH_TIME = 60

class CacheManager:
  def __init__(self, data_source=None, rest_url=None, rest_auth=None,
               root_cert=None, tracker_config_data={}):
    self.cached_child_transforms_by_uid = {}
    self.camera_parameters = {}
    self.tracker_config_data = tracker_config_data
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

  def refreshScenes(self):
    if not hasattr(self, 'cached_scenes_by_uid') or self.cached_scenes_by_uid is None:
      self.cached_scenes_by_uid = {}
    self._cached_scenes_by_cameraID = {}
    self._cached_scenes_by_sensorID = {}

    result = self.data_source.getScenes()
    if 'results' not in result:
      log.error("Failed to get results, error code: ", result.statusCode)
      return

    found = result.get("results", [])
    old = set(self.cached_scenes_by_uid.keys())
    new = set(x['uid'] for x in found)
    deleted = old - new
    for uid in deleted:
      self.cached_scenes_by_uid.pop(uid, None)

    for scene_data in found:
      self._refreshCameras(scene_data)
      if self.tracker_config_data:
        scene_data["tracker_config"] = [self.tracker_config_data["max_unreliable_time"],
                                      self.tracker_config_data["non_measurement_time_dynamic"],
                                      self.tracker_config_data["non_measurement_time_static"]]
        scene_data["persist_attributes"] = self.tracker_config_data.get("persist_attributes", {})

      uid = scene_data['uid']
      if uid not in self.cached_scenes_by_uid:
        scene = Scene.deserialize(scene_data)
      else:
        scene = self.cached_scenes_by_uid[uid]
        scene.updateScene(scene_data)

      for cameraID in scene.cameras.keys():
        self._cached_scenes_by_cameraID[cameraID] = scene
      for sensorID in scene.sensors.keys():
        self._cached_scenes_by_sensorID[sensorID] = scene
      self.cached_scenes_by_uid[scene.uid] = scene
    self._cache_refreshed = get_epoch_time()
    return

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
          log.warn(f"Failed to update camera {camera['uid']}")

        # Make a get request to pull the updated camera information
        # from db and store it to existing camera dictionary
        camera = self.data_source.getCamera(camera['uid'])
    return

  def refreshScenesForCamParams(self, jdata):
    intrinsics_changed = self.cameraParametersChanged(jdata, 'intrinsics')
    distortion_changed = self.cameraParametersChanged(jdata, 'distortion')

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
              self.updateCamera(scene.cameras[camera])

    if intrinsics_changed or distortion_changed:
      self.refreshScenes()
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
      log.warn(f"Failed to update camera {cam.cameraID}")
    return

  def cameraParametersChanged(self, message, parameter_type):
    message_parameters = message.get(parameter_type)
    stored_parameters = self.camera_parameters.get(message['id'], {}).get(parameter_type)
    if message_parameters and message_parameters != stored_parameters:
      self.camera_parameters.setdefault(message['id'], {})[parameter_type] = message[parameter_type]
      return True
    return False

  def checkRefresh(self):
    now = get_epoch_time()
    if not hasattr(self, 'cached_scenes_by_uid') \
       or self.cached_scenes_by_uid is None \
       or not hasattr(self, '_cache_refreshed'):
       #or now - self._cache_refreshed > REFRESH_TIME:
      self.refreshScenes()
    return

  def allScenes(self):
    self.checkRefresh()
    return self.cached_scenes_by_uid.values()

  def sceneWithID(self, sceneID):
    self.checkRefresh()
    return self.cached_scenes_by_uid.get(sceneID, None)

  def sceneWithCameraID(self, cameraID):
    self.checkRefresh()
    return self._cached_scenes_by_cameraID.get(cameraID, None)

  def sceneWithSensorID(self, sensorID):
    self.checkRefresh()
    return self._cached_scenes_by_sensorID.get(sensorID, None)

  def sceneWithRemoteChildID(self, childID):
    self.checkRefresh()
    return self.cached_child_transforms_by_uid.get(childID, None)

  def invalidate(self):
    self.cached_scenes_by_uid = None
    if not hasattr(self, 'cached_child_transforms_by_uid') or self.cached_child_transforms_by_uid is None:
      self.cached_child_transforms_by_uid = {}
    return
