# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64

from scene_common import log
from scene_common.timestamp import get_iso_time

from perceptual_sensor_calibration_controller import PerceptualSensorCalibrationController
from point_cloud_registration import PointCloudRegistration, PointCloudRegistrationError


class PointCloudCalibrationController(PerceptualSensorCalibrationController):
  """Strategy that localizes a sensor point cloud against a scene.

  The scene 3D mesh is converted to a point cloud (lazily, on first use) and
  cached per scene. Incoming sensor point clouds are registered against the
  cached scene cloud. The strategy is sensor-agnostic: any perceptual sensor
  producing a PCD/PLY point cloud is supported.
  """

  def __init__(self, calibration_data_interface):
    super().__init__(calibration_data_interface)
    # Per-scene caches, kept on the instance to avoid colliding with other
    # calibration strategies.
    self.scene_clouds = {}
    self.scene_registrations = {}
    return

  def _ensure_scene_cloud(self, sceneobj, map_update=False):
    """Lazily build and cache the scene point cloud from the scene mesh.

    @param   sceneobj     Scene object.
    @param   map_update   Force a rebuild when the scene map changed.

    @return  o3d.geometry.PointCloud for the scene.
    """
    if sceneobj.id not in self.scene_clouds or map_update:
      registration = PointCloudRegistration()
      scene_cloud = registration.scene_mesh_to_point_cloud(sceneobj.map)
      self.scene_registrations[sceneobj.id] = registration
      self.scene_clouds[sceneobj.id] = scene_cloud
      log.info(f"Cached scene point cloud for scene {sceneobj.id}")
    return self.scene_clouds[sceneobj.id]

  def process_scene_for_calibration(self, sceneobj, map_update=False):
    """Build and cache the scene point cloud used for registration.

    @param   sceneobj     Scene object.
    @param   map_update   Flag set when the scene map was updated.

    @return  dict with a "status" key.
    """
    response_dict = {'status': "success"}
    log.info(f"Processing point cloud scene for registration: {sceneobj.name}")

    if sceneobj is None or not sceneobj.map:
      response_dict['status'] = "Error: Scene has no map"
      return response_dict

    try:
      self._ensure_scene_cloud(sceneobj, map_update)
      self.calibration_data_interface.update_map_processed(sceneobj.id, get_iso_time())
    except (FileNotFoundError, ValueError, PointCloudRegistrationError) as e:
      response_dict['status'] = f"Error: {e}"
      return response_dict

    self.notify_scene_registration(sceneobj.id, response_dict)
    return response_dict

  def reset_scene(self, scene):
    """Invalidate the cached scene point cloud."""
    self.scene_clouds.pop(scene.id, None)
    self.scene_registrations.pop(scene.id, None)
    return

  def is_map_updated(self, sceneobj):
    """Report whether the scene map needs (re)processing."""
    if not sceneobj.map:
      self.reset_scene(sceneobj)
      return False
    return sceneobj.map_processed is None

  def generate_calibration(self, sceneobj, sensor_config, msg):
    """Register a sensor point cloud against the scene point cloud.

    @param   sceneobj        Scene object.
    @param   sensor_config   Unused for point cloud calibration.
    @param   msg             Payload with keys "id", "pointcloud" (base64),
                             optional "format" and "initial_transform".

    @return  dict with the calibration transform or error info.
    """
    sensor_id = msg.get('id')
    try:
      scene_cloud = self._ensure_scene_cloud(sceneobj)
      registration = self.scene_registrations[sceneobj.id]

      raw_bytes = base64.b64decode(msg['pointcloud'], validate=True)
      sensor_cloud = registration.decode_point_cloud(raw_bytes, msg.get('format'))

      result = registration.register(sensor_cloud, scene_cloud,
                                     msg.get('initial_transform'))
    except (KeyError, TypeError, ValueError, PointCloudRegistrationError, FileNotFoundError) as e:
      log.error(f"Point cloud registration failed for sensor {sensor_id}: {e}")
      return {"status": "error", "message": f"Registration failed: {e}"}

    return {
        "status": "success",
        "sensor_id": sensor_id,
        "scene_name": sceneobj.name,
        "transform": result["transform"],
        "fitness": result["fitness"],
        "inlier_rmse": result["inlier_rmse"],
    }
