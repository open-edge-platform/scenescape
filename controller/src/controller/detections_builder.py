# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import numpy as np

from controller.scene import TripwireEvent
from scene_common.earth_lla import convertXYZToLLA
from scene_common.geometry import DEFAULTZ, Point, Size
from scene_common.timestamp import get_iso_time


def buildDetectionsDict(objects, scene):
  result_dict = {}
  for obj in objects:
    obj_dict = prepareObjDict(scene, obj, False)
    result_dict[obj_dict['id']] = obj_dict
  return result_dict

def buildDetectionsList(objects, scene, update_visibility=False):
  result_list = []
  for obj in objects:
    obj_dict = prepareObjDict(scene, obj, update_visibility)
    result_list.append(obj_dict)
  return result_list

def prepareObjDict(scene, obj, update_visibility):
  aobj = obj
  if isinstance(obj, TripwireEvent):
    aobj = obj.object
  otype = aobj.category

  velocity = aobj.velocity
  if velocity is None:
    velocity = Point(0, 0, 0)
  if not velocity.is3D:
    velocity = Point(velocity.x, velocity.y, DEFAULTZ)

  obj_dict = aobj.info
  obj_dict.update({
    'id': aobj.gid, # gid is the global ID - computed by SceneScape server.
    'type': otype,
    'translation': aobj.sceneLoc.asCartesianVector,
    'size': aobj.size,
    'velocity': velocity.asCartesianVector
  })

  if aobj.rotation is not None:
    obj_dict['rotation'] = aobj.rotation

  if scene and scene.output_lla:
    lat_long_alt = convertXYZToLLA(scene.trs_xyz_to_lla, aobj.sceneLoc.asCartesianVector)
    obj_dict['lat_long_alt'] = lat_long_alt.tolist()

  reid = aobj.reidVector
  if reid is not None:
    if isinstance(aobj.reidVector, np.ndarray):
      obj_dict['reid'] = aobj.reidVector.tolist()
    else:
      obj_dict['reid'] = aobj.reidVector

  if hasattr(aobj, 'visibility'):
    obj_dict['visibility'] = aobj.visibility
    if update_visibility:
      computeCameraBounds(scene, aobj, obj_dict)

  if len(aobj.chain_data.regions):
    obj_dict['regions'] = aobj.chain_data.regions
  if len(aobj.chain_data.sensors):
    obj_dict['sensors'] = aobj.chain_data.sensors
  if hasattr(aobj, 'confidence'):
    obj_dict['confidence'] = aobj.confidence
  if hasattr(aobj, 'similarity'):
    obj_dict['similarity'] = aobj.similarity
  if hasattr(aobj, 'first_seen'):
    obj_dict['first_seen'] = get_iso_time(aobj.first_seen)
  if isinstance(obj, TripwireEvent):
    obj_dict['direction'] = obj.direction
  if hasattr(aobj, 'asset_scale'):
    obj_dict['asset_scale'] = aobj.asset_scale
  if len(aobj.chain_data.persist):
    obj_dict['persistent_data'] = aobj.chain_data.persist
  return obj_dict

def computeCameraBounds(scene, aobj, obj_dict):
  camera_bounds = {}
  for cameraID in obj_dict['visibility']:
    bounds = None
    if aobj and hasattr(aobj.vectors[0].camera, 'cameraID') \
          and cameraID == aobj.vectors[0].camera.cameraID:
      bounds = getattr(aobj, 'boundingBoxPixels', None)
    elif scene:
      camera = scene.cameraWithID(cameraID)
      if camera is not None and 'bb_meters' in obj_dict:
        obj_translation = None
        obj_size = None
        if aobj:
          obj_translation = aobj.sceneLoc
          obj_size = aobj.bbMeters.size
        else:
          obj_translation = Point(obj_dict['translation'])
          obj_size = Size(obj_dict['bb_meters']['width'], obj_dict['bb_meters']['height'])
        bounds = camera.pose.projectEstimatedBoundsToCameraPixels(obj_translation,
                                                                  obj_size)
    if bounds:
      camera_bounds[cameraID] = bounds.asDict
  obj_dict['camera_bounds'] = camera_bounds
  return
