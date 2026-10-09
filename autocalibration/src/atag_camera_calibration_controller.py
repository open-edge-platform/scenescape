# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import os

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from scene_common import log
from scene_common.transform import (
  CameraPose, convertToTransformMatrix, getPoseMatrix, CameraIntrinsics,
)
from scene_common.timestamp import get_iso_time

from atag_camera_calibration import CameraCalibrationApriltag, \
    TILE_SIZE, DEFAULT_ROTATION_MATRIX, DEFAULT_MESH_ROTATION, MIN_APRILTAG_COUNT
from auto_camera_calibration_controller import CameraCalibrationController
from calibration_geometry import validate_camera_pose, PLANAR_MAP_EXTENSIONS

MAX_WAIT_FRAME_COUNT = 10


class ApriltagCameraCalibrationController(CameraCalibrationController):
  """
  This Class is the CameraCalibration controller, which controls the whole of
  camera calibration processes occuring in the container.
  """

  def process_scene_for_calibration(self, sceneobj, map_update=False):
    """! The following tasks are done in this function:
         1) Create AutoCalibration Object.
         2) If Scene is not updated, use data stored in database.
            If Scene is updated, identify all the apriltags in the scene
            and store data to database.
         3) Publish ready message to UI, allowing it to enable the calibration button.
    @param   sceneobj     Scene object
    @param   map_update   Flag is set when there is a map update in scene object.

    @return  mqtt_response
    """
    response_dict = {'status': "success"}
    log.info("processing apriltags scene for calibration for ", sceneobj.name)

    if sceneobj is None:
      log.error("Topic Structure mismatch")
      response_dict['status'] = "Error: Topic Structure mismatch"
      return response_dict

    if sceneobj.id not in self.cam_calib_objs or map_update:
      try:
        self.cam_calib_objs[sceneobj.id] = CameraCalibrationApriltag(sceneobj.map,
                                                                     sceneobj.scale,
                                                                     sceneobj.name, tag_size=sceneobj.apriltag_size)
      except ValueError as ve:
        response_dict['status'] = str(ve)
        return response_dict

    if sceneobj.map_processed is None or map_update:
      try:
        with self.cam_calib_objs[sceneobj.id].cam_calib_lock:
          self.cam_calib_objs[sceneobj.id].identify_apriltags_in_scene(TILE_SIZE,
                                                                    TILE_SIZE,
                                                                    DEFAULT_ROTATION_MATRIX)
          if self.cam_calib_objs[sceneobj.id].result_data_3d is not None:
            self.save_to_database(sceneobj, self.cam_calib_objs[sceneobj.id].result_data_3d)
          log.info("Apriltag center points in 3D identified and saved to database.")
      except FileNotFoundError:
        response_dict['status'] = "Error: Glb file not found"
        return response_dict

    apriltags_from_db = []
    response = self.calibration_data_interface.calibration_markers_with_scene_id(sceneobj.id)
    if 'results' in response:
      apriltags_from_db = response['results']
    result_data_from_db = {}
    if apriltags_from_db:
      for apriltag in apriltags_from_db:
        result_data_from_db[apriltag['apriltag_id']] = apriltag['dims']
    self.cam_calib_objs[sceneobj.id].result_data_3d = result_data_from_db
    if len(self.cam_calib_objs[sceneobj.id].result_data_3d) < MIN_APRILTAG_COUNT:
      response_dict['status'] = f"Cannot auto calibrate. Check scene to ensure there are at least {MIN_APRILTAG_COUNT} april tags"
    self.notify_scene_registration(sceneobj.id, response_dict)
    return response_dict

  def reset_scene(self, scene):
    self.cam_calib_objs.pop(scene.id, None)
    self.calibration_data_interface.delete_calibration_markers_for_scene(scene.id)
    return

  def is_map_updated(self, sceneobj):
    """! function used to check if the map is updated and reset the scene when map is None.
    @param   sceneobj      scene object.

    @return  True/False
    """
    if not sceneobj.map:
      self.reset_scene(sceneobj)
      return False
    else:
      return (sceneobj.map_processed is None)

  def save_to_database(self, scene, atag_points_3d):
    """! Function stores baseapriltag data into db.
    @param   scene             Scene database object.
    @param   atag_points_3d   Apriltag centers in 3d plane.

    @return  None
    """
    response = self.calibration_data_interface.calibration_markers_with_scene_id(scene.id)
    if 'results' in response:
      apriltags = response['results']
    if apriltags and len(atag_points_3d) < len(apriltags):
      self.calibration_data_interface.delete_calibration_markers_for_scene(scene.id)
    else:
      for key, value in atag_points_3d.items():
        post_data = {'marker_id': f"{scene.id}_{str(key)}", 'apriltag_id': key, 'dims': value, 'scene': scene.id}
        self.calibration_data_interface.update_or_create_calibration_marker(scene.id, post_data)
    self.calibration_data_interface.update_map_processed(scene.id, get_iso_time())
    return

  def decode_image(self, img_data):
    """! Decodes image from string format to numpy format.
    @param   img_data  encoded image from MQTT.

    @return  image_new  Image in numpy/cv2 format
    """
    image_array = np.frombuffer(base64.b64decode(img_data), dtype=np.uint8)
    return cv2.imdecode(image_array, flags=1)

  def generate_calibration(self, sceneobj, camera_intrinsics, cam_frame_data):
    """! Generates the camera pose.
    @param   sceneobj           Scene object
    @param   camera_intrinsics  Camera Intrinsics
    @param   cam_frame_data     Payload with camera frame data

    @return  dict       Dictionary containing calibration result or error info
    """
    rotation = None
    if os.path.splitext(sceneobj.map)[1].lower() == '.glb':
      rotation = DEFAULT_MESH_ROTATION
    self.scene_pose_mat = getPoseMatrix(sceneobj, rotation)
    try:
      cur_cam_calib_obj = self.cam_calib_objs[sceneobj.id]
      log.info(f"Apriltags identified in scene ${sceneobj.name}.")
      if (cur_cam_calib_obj.result_data_3d is None
              or len(cur_cam_calib_obj.result_data_3d) < MIN_APRILTAG_COUNT):
        raise TypeError((
            f"Fewer than {MIN_APRILTAG_COUNT} tags found in {sceneobj.name}'s map. Make sure "
            f"there are at least {MIN_APRILTAG_COUNT} tags clearly visible in the scene map."))
      if camera_intrinsics is None:
        raise TypeError(f"Intrinsics not found for camera {cam_frame_data['id']}!")
      image = cam_frame_data['image']
      log.info(f"Decoding image for camera {cam_frame_data['id']}")
      src_2d_image = self.decode_image(image)
      log.info(f"Image decoded for camera {cam_frame_data['id']}, shape: {src_2d_image.shape if src_2d_image is not None else 'None'}")
      intrinsic_matrix_2d = np.array(camera_intrinsics)
      cur_cam_calib_obj.intrinsic_matrix_2d = intrinsic_matrix_2d
      cur_cam_calib_obj.find_apriltags_in_frame(src_2d_image, True)
      camera_pose = cur_cam_calib_obj.get_camera_pose_in_scene()
      log.info(f"Camera pose computed for camera {cam_frame_data['id']}")

      if (camera_pose is not None
              and len(cur_cam_calib_obj.apriltags_2d_data) >= MIN_APRILTAG_COUNT):
        # Obtain the frustum view points.
        frustum_2d = cur_cam_calib_obj.get_camera_frustum()
        cam_pose = CameraPose(camera_pose,
                              CameraIntrinsics(intrinsic_matrix_2d))
        # Get respective 2d and 3d points for representation in UI.
        points_3d, points_2d = cur_cam_calib_obj.get_point_correspondences()
        map_points_3d = np.asarray(points_3d, dtype=float)
        log.info(f"Point correspondences calculated for calibration UI for camera {cam_frame_data['id']}")

        cam_to_world_y_down = convertToTransformMatrix(self.scene_pose_mat,
                                                       cam_pose.quaternion_rotation.tolist(),
                                                       camera_pose[0:3, 3:].flatten().tolist())
        quat = Rotation.from_matrix(cam_to_world_y_down[0:3, 0:3]).as_quat()
        trans = np.ravel(cam_to_world_y_down[0:3, 3:4].flatten())

        # Apply scene pose to 3d calibration points.
        points_3d = [np.dot(self.scene_pose_mat, np.append(point, 1))[:3].tolist()
                     for point in points_3d]

        validation = validate_camera_pose(
            map_points_3d, points_3d, points_2d, camera_pose, trans, intrinsic_matrix_2d,
            cur_cam_calib_obj.tag_size,
            os.path.splitext(sceneobj.map)[1].lower() in PLANAR_MAP_EXTENSIONS)
        if not validation.accepted:
          log.error(f"Rejecting calibration for camera {cam_frame_data['id']}: {validation.message}")
          return self._rejection_response(validation, trans, points_3d, points_2d)

        return self._success_response(sceneobj, cam_frame_data['id'], validation, frustum_2d,
                                      quat, trans, points_3d, points_2d)
      return self._pending_response(cam_frame_data['id'])
    except KeyError as ke:
      return {
          "status": "error",
          "message": str(ke)
      }
    except TypeError as te:
      return {
          "status": "error",
          "message": str(te)
      }
    except Exception as e:
      return {
          "status": "error",
          "message": f"Unexpected error: {str(e)}"
      }

  @staticmethod
  def _rejection_response(validation, trans, points_3d, points_2d):
    return {"status": "error", "message": validation.message,
            "spread_ratio": validation.spread_ratio, "translation": trans.tolist(),
            "calibration_points_3d": points_3d, "calibration_points_2d": points_2d}

  @staticmethod
  def _success_response(sceneobj, camera_id, validation, frustum_2d, quat, trans,
                        points_3d, points_2d):
    details = {
        'error': "False",
        'scene_name': sceneobj.name,
        'sensor_id': camera_id,
        'camera_frustum': frustum_2d,
        'calibration_points_3d': points_3d,
        'calibration_points_2d': points_2d,
        'quaternion': quat.tolist(),
        'translation': trans.tolist(),
    }
    return {
        "status": "success",
        "camera_id": camera_id,
        "scene_name": sceneobj.name,
        "calibration_points_3d": points_3d,
        "calibration_points_2d": points_2d,
        "quaternion": quat.tolist(),
        "translation": trans.tolist(),
        "spread_ratio": validation.spread_ratio,
        "details": details,
    }

  def _pending_response(self, camera_id):
    """Wait up to MAX_WAIT_FRAME_COUNT frames for enough tags, then fail."""
    count = self.frame_count.get(camera_id, 0)
    if count >= MAX_WAIT_FRAME_COUNT:
      raise TypeError(
          f"Fewer than {MIN_APRILTAG_COUNT} tags found in {camera_id}'s feed. Make sure there "
          f"are at least {MIN_APRILTAG_COUNT} tags clearly visible in camera view.")
    self.frame_count[camera_id] = count + 1
    return {
        "status": "pending",
        "message": "Waiting for more frames or tags to be detected"
    }
