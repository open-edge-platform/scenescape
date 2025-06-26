# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common import log
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_datetime_from_string


class CalibrationScene:
  #FIXME: should be defined in common location accessible to both models and camcalibration
  DEFAULTS = {
    'rotation_x': 0.0,
    'rotation_y': 0.0,
    'rotation_z': 0.0,
    'translation_x': 0.0,
    'translation_y': 0.0,
    'translation_z': 0.0,
    'scale_x': 1.0,
    'scale_y': 1.0,
    'scale_z': 1.0,
    'map': None,
    'scale': 1.0,
    'apriltag_size': 0.162,
    'map_processed': None,
    'camera_calibration': 'Manual',
    'polycam_data': None,
    'number_of_localizations': 50,
    'global_feature': 'netvlad',
    'local_feature': {"sift": dict()},
    'matcher': {"NN-ratio": dict()},
    'minimum_number_of_matches': 20,
    'inlier_threshold': 0.5,
    'output': ''
  }

  def __init__(self, uid, name):
    self.id = uid
    self.name = name
    self.mesh_rotation = [self.DEFAULTS['rotation_x'], self.DEFAULTS['rotation_y'],
                          self.DEFAULTS['rotation_z']]
    self.mesh_translation = [self.DEFAULTS['translation_x'], self.DEFAULTS['translation_y'],
                             self.DEFAULTS['translation_z']]
    self.mesh_scale = [self.DEFAULTS['scale_x'], self.DEFAULTS['scale_y'],
                       self.DEFAULTS['scale_z']]
    return

  @classmethod
  def deserialize(cls, data):
    scene = cls(data['uid'], data['name'])
    scene.map = "/workspace/media/" + data['map'].split('/')[-1] if 'map' in data else scene.DEFAULTS['map']
    scene.scale = data.get('scale', scene.DEFAULTS['scale'])
    scene.mesh_rotation = data.get('mesh_rotation', scene.mesh_rotation)
    scene.mesh_translation = data.get('mesh_translation', scene.mesh_translation)
    scene.mesh_scale = data.get('mesh_scale', scene.mesh_scale)
    scene.apriltag_size = data.get('apriltag_size', scene.DEFAULTS['apriltag_size'])
    scene.map_processed = get_datetime_from_string(data['map_processed']) if 'map_processed' in data else scene.DEFAULTS['map_processed']
    scene.camera_calibration = data.get('camera_calibration', scene.DEFAULTS['camera_calibration'])
    scene.polycam_data = "/workspace/media/" + data['polycam_data'].split('/')[-1] if 'polycam_data' in data else scene.DEFAULTS['polycam_data']
    scene.number_of_localizations = data.get('number_of_localizations', scene.DEFAULTS['number_of_localizations'])
    scene.global_feature = data.get('global_feature', scene.DEFAULTS['global_feature'])
    scene.local_feature = data.get('local_feature', scene.DEFAULTS['local_feature'])
    scene.matcher = data.get('matcher', scene.DEFAULTS['matcher'])
    scene.minimum_number_of_matches = data.get('minimum_number_of_matches', scene.DEFAULTS['minimum_number_of_matches'])
    scene.inlier_threshold = data.get('inlier_threshold', scene.DEFAULTS['inlier_threshold'])
    scene.output = scene.DEFAULTS['output']
    return scene

class CameraCalibrationModel():
  def __init__(self, root_cert, rest_url, rest_auth):
    self.rest = RESTClient(rest_url, rootcert=root_cert, auth=rest_auth)
    return

  def sceneWithID(self, scene_id):
    response = self.rest.getScene(scene_id)
    if not response:
      log.error(f"Failed to get responses for scene {scene_id}, error code: ", response.statusCode)
      return
    return CalibrationScene.deserialize(response)

  def sceneCameraWithID(self, camera_id):
    response = self.rest.getCamera(camera_id)
    if not response:
      log.error(f"Failed to get responses for camera {camera_id}, error code: ", response.statusCode)
      return
    else:
      scene = response['scene']
      return self.sceneWithID(scene)

  def allScenes(self):
    response = self.rest.getScenes(None)
    if 'results' not in response:
      log.error(f"Failed to get responses for all scenes, error code: ", response.statusCode)
      return
    found = response['results']
    return [CalibrationScene.deserialize(scene) for scene in found]

  def updateMapProcessed(self, scene_id, map_processed):
    response = self.rest.updateScene(scene_id, {'map_processed': map_processed})
    if not response:
      log.error(f"Failed to update map processed for scene {scene_id}, error code: ", response.statusCode)
      return
    return response

  def calibrationMarkersWithSceneID(self, scene_id):
    response = self.rest.getCalibrationMarkers({'scene':scene_id})
    if not response:
      log.error(f"Failed to get responses for calibration markers with scene {scene_id}, error code: ", response.statusCode)
      return
    return response

  def deleteCalibrationMarkersForScene(self, scene_id):
    response = self.rest.getCalibrationMarkers({'scene':scene_id})
    if not response:
      log.error(f"Failed to delete calibration markers for scene {scene_id}, error code: ", response.statusCode)
      return
    found = []
    if 'results' in response:
      found = response['results']
    for marker in found:
      self.rest.deleteCalibrationMarker(marker['marker_id'])
    return

  def updateOrCreateCalibrationMarker(self, scene_id, data):
    response = self.rest.getCalibrationMarkers({'scene':scene_id})
    if not response:
      log.error(f"Failed to get responses for calibration markers with scene {scene_id}, error code: ", response.statusCode)
      return
    found = []
    if 'results' in response:
      found = response['results']
    marker_id = data['marker_id']
    for marker in found:
      if marker['marker_id'] == marker_id:
        return self.rest.updateCalibrationMarker(marker_id, data)
    return self.rest.createCalibrationMarker(data)
