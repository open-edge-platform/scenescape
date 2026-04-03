# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np

from controller.scene import TripwireEvent
from scene_common.earth_lla import convertXYZToLLA, calculateHeading
from scene_common.geometry import DEFAULTZ, Point, Size
from scene_common.timestamp import get_iso_time


def buildDetectionsDict(objects, scene, include_sensors=False):
  result_dict = {}
  for obj in objects:
    obj_dict = prepareObjDict(scene, obj, False, include_sensors)
    result_dict[obj_dict['id']] = obj_dict
  return result_dict

def buildDetectionsList(objects, scene, update_visibility=False, include_sensors=False):
  result_list = []
  for obj in objects:
    obj_dict = prepareObjDict(scene, obj, update_visibility, include_sensors)
    result_list.append(obj_dict)
  return result_list

def prepareObjDict(scene, obj, update_visibility, include_sensors=False):
  aobj = obj
  if isinstance(obj, TripwireEvent):
    aobj = obj.object
  otype = aobj.category

  scene_loc_vector = aobj.sceneLoc.asCartesianVector

  velocity = aobj.velocity
  if velocity is None:
    velocity = Point(0, 0, 0)
  if not velocity.is3D:
    velocity = Point(velocity.x, velocity.y, DEFAULTZ)

  # Build a fresh top-level dict per serialization so optional fields like
  # sensors do not leak between scene, regulated, and external outputs.
  obj_dict = dict(aobj.info)
  obj_dict.update({
    'id': aobj.gid, # gid is the global ID - computed by SceneScape server.
    'type': otype,
    'translation': scene_loc_vector,
    'size': aobj.size,
    'velocity': velocity.asCartesianVector
  })

  rotation = aobj.rotation
  if rotation is not None:
    obj_dict['rotation'] = rotation

  if scene and scene.output_lla:
    lat_long_alt = convertXYZToLLA(scene.trs_xyz_to_lla, scene_loc_vector)
    obj_dict['lat_long_alt'] = lat_long_alt.tolist()
    heading = calculateHeading(scene.trs_xyz_to_lla, aobj.sceneLoc.asCartesianVector, velocity.asCartesianVector)
    obj_dict['heading'] = heading.tolist()

  # Restore semantic metadata (age, gender, clothing, etc.) stripped from info during construction
  if hasattr(aobj, 'metadata') and aobj.metadata:
    if 'metadata' not in obj_dict:
      obj_dict['metadata'] = {}
    for key, value in aobj.metadata.items():
      if key != 'reid':
        obj_dict['metadata'][key] = value

  # Output reid in metadata structure
  if aobj.reid and 'embedding_vector' in aobj.reid:
    reid_embedding = aobj.reid['embedding_vector']
    if reid_embedding is not None:
      if 'metadata' not in obj_dict:
        obj_dict['metadata'] = {}
      if isinstance(reid_embedding, np.ndarray):
        obj_dict['metadata']['reid'] = {'embedding_vector': reid_embedding.tolist()}
      else:
        obj_dict['metadata']['reid'] = {'embedding_vector': reid_embedding}
      # Add model_name if available
      if 'model_name' in aobj.reid:
        obj_dict['metadata']['reid']['model_name'] = aobj.reid['model_name']

  if hasattr(aobj, 'visibility'):
    obj_dict['visibility'] = aobj.visibility
    if update_visibility:
      computeCameraBounds(scene, aobj, obj_dict)

  if hasattr(aobj, 'chain_data'):
    chain_data = aobj.chain_data
    if len(chain_data.regions):
      obj_dict['regions'] = chain_data.regions

    if include_sensors:
      sensors_output = {}

      # Copy sensor data while holding lock, then release
      with chain_data._lock:
        env_state_copy = dict(chain_data.env_sensor_state)
        attr_events_copy = dict(chain_data.attr_sensor_events)

      # Environmental sensors: timestamped readings
      for sensor_id, state in env_state_copy.items():
        values = state['readings'] if 'readings' in state and state['readings'] else []

        sensors_output[sensor_id] = {
          'values': values
        }

      # Attribute sensors: events as structured object
      for sensor_id, events in attr_events_copy.items():
        if events:
          sensors_output[sensor_id] = {
            'values': events
          }

      if sensors_output:
        obj_dict['sensors'] = sensors_output

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
    if aobj and len(aobj.vectors) > 0 and hasattr(aobj.vectors[0].camera, 'cameraID') \
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
