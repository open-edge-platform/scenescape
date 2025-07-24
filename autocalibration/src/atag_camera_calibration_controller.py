# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64
import json
import os

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.transform import CameraPose, convertToTransformMatrix, getPoseMatrix
from scene_common.timestamp import get_iso_time

from atag_camera_calibration import CameraCalibrationApriltag, \
  TILE_SIZE, DEFAULT_ROTATION_MATRIX, DEFAULT_MESH_ROTATION, MIN_APRILTAG_COUNT
from auto_camera_calibration_controller import CameraCalibrationController

MAX_WAIT_FRAME_COUNT = 10

class ApriltagCameraCalibrationController(CameraCalibrationController):
  """
  This Class is the CameraCalibration controller, which controls the whole of
  camera calibration processes occuring in the container.
  """

  def processSceneForCalibration(self, sceneobj, map_update=False):
    """! The following tasks are done in this function:
         1) Create CamCalibration Object.
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
          self.cam_calib_objs[sceneobj.id].identifyApriltagsInScene(TILE_SIZE,
                                                                      TILE_SIZE,
                                                                      DEFAULT_ROTATION_MATRIX)
          if self.cam_calib_objs[sceneobj.id].result_data_3d is not None:
            self.saveToDatabase(sceneobj, self.cam_calib_objs[sceneobj.id].result_data_3d)
          log.info("Apriltag center points in 3D identified and saved to database.")
      except FileNotFoundError:
        response_dict['status'] = "Error: Glb file not found"
        return response_dict

    apriltags_from_db = []
    response = self.calibration_data_interface.calibrationMarkersWithSceneID(sceneobj.id)
    if 'results' in response:
      apriltags_from_db = response['results']
    result_data_from_db = {}
    if apriltags_from_db:
      for apriltag in apriltags_from_db:
        result_data_from_db[apriltag['apriltag_id']] = apriltag['dims']
    self.cam_calib_objs[sceneobj.id].result_data_3d = result_data_from_db
    if len(self.cam_calib_objs[sceneobj.id].result_data_3d) < MIN_APRILTAG_COUNT:
      response_dict['status'] = "Cannot auto calibrate. Check scene to ensure there " \
                                f"are at least {MIN_APRILTAG_COUNT} april tags"
    return response_dict

  def resetScene(self, scene):
    self.cam_calib_objs.pop(scene.id, None)
    self.calibration_data_interface.deleteCalibrationMarkersForScene(scene.id)
    return

  def isMapUpdated(self, sceneobj):
    """! function used to check if the map is updated and reset the scene when map is None.
    @param   sceneobj      scene object.

    @return  True/False
    """
    if not sceneobj.map:
      self.resetScene(sceneobj)
      return False
    else:
      return (sceneobj.map_processed is None) or (self.isMapProcessed(sceneobj))

  def saveToDatabase(self, scene, atag_points_3d):
    """! Function stores baseapriltag data into db.
    @param   scene             Scene database object.
    @param   atag_points_3d   Apriltag centers in 3d plane.

    @return  None
    """
    response = self.calibration_data_interface.calibrationMarkersWithSceneID(scene.id)
    if 'results' in response:
      apriltags = response['results']
    if apriltags and len(atag_points_3d) < len(apriltags):
      self.calibration_data_interface.deleteCalibrationMarkersForScene(scene.id)
    else:
      for key, value in atag_points_3d.items():
        post_data = {'marker_id':f"{scene.id}_{str(key)}", 'apriltag_id': key, 'dims': value, 'scene': scene.id}
        self.calibration_data_interface.updateOrCreateCalibrationMarker(scene.id, post_data)
    self.calibration_data_interface.updateMapProcessed(scene.id, get_iso_time())
    return

  def decodeImage(self, img_data):
    """! Decodes image from string format to numpy format.
    @param   img_data  encoded image from MQTT.

    @return  image_new  Image in numpy/cv2 format
    """
    image_array = np.frombuffer(base64.b64decode(img_data), dtype=np.uint8)
    return cv2.imdecode(image_array, flags=1)

  def generateCalibration(self, sceneobj, msg):
    """! Generates the camera pose.
    @param   sceneobj   Scene object
    @param   msg        Payload with camera data from percebro

    @return  dict       Dictionary containing publish topic and data to publish
    """
    rotation = None
    if os.path.splitext(sceneobj.map)[1].lower() == '.glb':
      rotation = DEFAULT_MESH_ROTATION
    self.scene_pose_mat = getPoseMatrix(sceneobj, rotation)
    pub_data = {}
    percebro_cam_data = None
    pub_data['error'] = "True"
    try:
      cur_cam_calib_obj = self.cam_calib_objs[sceneobj.id]
      percebro_cam_data = json.loads(msg)
      log.info(f"Apriltags identified in scene ${sceneobj.name}.")
      if (cur_cam_calib_obj.result_data_3d is None \
          or len(cur_cam_calib_obj.result_data_3d) < MIN_APRILTAG_COUNT):
        raise TypeError((
          f"Fewer than {MIN_APRILTAG_COUNT} tags found in {sceneobj.name}'s map. Make sure "
          f"there are at least {MIN_APRILTAG_COUNT} tags clearly visible in the scene map."))

      image = percebro_cam_data['image']
      src_2d_image = self.decodeImage(image)
      intrinsic_matrix_2d = np.array(percebro_cam_data['intrinsics'])
      cur_cam_calib_obj.intrinsic_matrix_2d = intrinsic_matrix_2d
      cur_cam_calib_obj.findApriltagsInFrame(src_2d_image, True)
      camera_pose = cur_cam_calib_obj.getCameraPoseInScene()
      log.info(f"Camera pose computed for camera {percebro_cam_data['id']}")

      if (camera_pose is not None \
          and len(cur_cam_calib_obj.apriltags_2d_data) >= MIN_APRILTAG_COUNT):
        # Obtain the frustum view points.
        frustum_2d = cur_cam_calib_obj.getCameraFrustum()
        cam_pose = CameraPose(camera_pose,
                              intrinsic_matrix_2d)
        # Get respective 2d and 3d points for representation in UI.
        points_3d, points_2d = cur_cam_calib_obj.calculatePointCorrespondences(
          cam_pose.intrinsics, cam_pose.pose_mat)
        log.info(("Point correspondences calculated for calibration UI for camera"
                  f" {percebro_cam_data['id']}"))

        cam_to_world_y_down = convertToTransformMatrix(self.scene_pose_mat,
                                                       cam_pose.quaternion_rotation.tolist(),
                                                       camera_pose[0:3, 3:].flatten().tolist())
        quat = Rotation.from_matrix(cam_to_world_y_down[0:3, 0:3]).as_quat()
        trans = np.ravel(cam_to_world_y_down[0:3, 3:4].flatten())

        # Apply scene pose to 3d calibration points.
        points_3d = [np.dot(self.scene_pose_mat, np.append(point, 1))[:3].tolist()
                     for point in points_3d]

        pub_data['scene_name'] = sceneobj.name
        pub_data['sensor_id'] = percebro_cam_data['id']
        pub_data['error'] = "False"
        pub_data['camera_frustum'] = frustum_2d
        pub_data['calibration_points_3d'] = points_3d
        pub_data['calibration_points_2d'] = points_2d
        pub_data['quaternion'] = quat.tolist()
        pub_data['translation'] = trans.tolist()
      else:
        if (percebro_cam_data['id'] not in self.frame_count or
            self.frame_count[percebro_cam_data['id']] < MAX_WAIT_FRAME_COUNT):
          if percebro_cam_data['id'] in self.frame_count:
            self.frame_count[percebro_cam_data['id']] += 1
          else:
            self.frame_count[percebro_cam_data['id']] = 1
          publish_topic = PubSub.formatTopic(PubSub.CMD_CAMERA,
                                             camera_id=percebro_cam_data['id'])
          return {'publish_topic': publish_topic, 'publish_data': 'localize'}
        else:
          raise TypeError((
            f"Fewer than {MIN_APRILTAG_COUNT} tags found in {percebro_cam_data['id']}'s"
            f"feed. Make sure there are at least {MIN_APRILTAG_COUNT} tags clearly "
            "visible in camera view."))
    except KeyError as ke:
      pub_data['message'] = str(ke)
    except TypeError as te:
      pub_data['message'] = str(te)
    finally:
      if bool(pub_data):
        publish_topic = PubSub.formatTopic(PubSub.DATA_AUTOCALIB_CAM_POSE,
                                          camera_id=percebro_cam_data['id'])
        return {'publish_topic': publish_topic, 'publish_data': json.dumps(pub_data)}

