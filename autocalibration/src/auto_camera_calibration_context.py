# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading

from atag_camera_calibration_controller import ApriltagCameraCalibrationController
from auto_camera_calibration_model import CameraCalibrationModel
from markerless_camera_calibration_controller import MarkerlessCameraCalibrationController
from point_cloud_registration_controller import PointCloudRegistrationController

from scene_common import log
from scene_common.options import POINTCLOUD


class CameraCalibrationContext:
  scene_strategies = {}

  def __init__(self, cert, root_cert, rest_url, rest_auth):
    self.calibration_data_interface = CameraCalibrationModel(root_cert, rest_url, rest_auth)

    self.scene_strategies["AprilTag"] = ApriltagCameraCalibrationController(calibration_data_interface=self.calibration_data_interface)
    self.scene_strategies["Markerless"] = MarkerlessCameraCalibrationController(calibration_data_interface=self.calibration_data_interface)
    self.scene_strategies[POINTCLOUD] = PointCloudRegistrationController(calibration_data_interface=self.calibration_data_interface)
    # Point cloud registration is dispatched directly (independent of the
    # scene's camera_calibration mode), so keep a direct reference.
    self.point_cloud_strategy = self.scene_strategies[POINTCLOUD]

    self.calibration_results = {}
    self.socket_clients = {}
    self.socket_scene_clients = {}
    self.socketio = None

    self.register_thread_lock = threading.Lock()
    self.calibration_thread_lock = threading.Lock()
    self.current_processing_scene = None

    return

  def preprocess_scenes(self):
    """! For all scenes in database, preprocess the scene map and store/update results

    @return  None
    """
    all_scene_objects = self.calibration_data_interface.all_scenes()
    for scene_object in all_scene_objects:
      if scene_object.camera_calibration != "Manual":
        self.scene_update_thread_wrapper(scene_object, map_update=False)
        log.info(f"Validating Scene = {scene_object.name} on start.")
    return

  def scene_update_thread_wrapper(self, sceneobj, map_update=False):
    """! function checks if lock is not acquired and processes the
    scene with updated metadata.
    status.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    if not self.register_thread_lock.locked():
      thread = threading.Thread(target=self.process_scene, args=(sceneobj, map_update))
      thread.start()
    return

  def process_scene(self, sceneobj, map_update):
    """! function processes the uploaded scene(image/glb) and publish back the
    status.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    with self.register_thread_lock:
      try:
        response_dict = self.scene_strategies[sceneobj.camera_calibration].process_scene_for_calibration(sceneobj, map_update)
      except (FileNotFoundError, KeyError) as e:
        log.error(f"Error in register dataset : {e}")
    self.current_processing_scene = {}
    return

  def calibrate_camera_thread_wrapper(self, sceneobj, cameraId, intrinsics, cam_frame_data):
    """
    Starts a background thread to process camera calibration for REST API.
    """
    if not self.calibration_thread_lock.locked():
      self.socketio.start_background_task(
          self.process_camera_calibration,
          sceneobj, cameraId, intrinsics, cam_frame_data
      )
      self.calibration_results[cameraId] = {
          "status": "calibrating",
          "message": "Calibration started"
      }
    else:
      self.calibration_results[cameraId] = {
          "status": "busy",
          "message": "Another calibration is already in progress"
      }

  def process_camera_calibration(self, sceneobj, cameraId, intrinsics, cam_frame_data):
    """
    Processes camera calibration in a background thread for REST API.
    Stores or updates calibration status/result in a suitable place.
    """
    log.info(f"[processCameraCalibration] Thread started for camera {cameraId}")
    with self.calibration_thread_lock:
      try:
        log.info(f"[processCameraCalibration] About to get strategy for {sceneobj.camera_calibration}")
        strategy = self.scene_strategies.get(sceneobj.camera_calibration)
        if not strategy:
          result = {
              "status": "error",
              "message": "Calibration strategy not found"
          }
        else:
          result = strategy.generate_calibration(sceneobj, intrinsics, cam_frame_data)
      except Exception as e:
        result = {
            "status": "error",
            "message": f"Calibration failed: {str(e)}"
        }
      # Store result for later retrieval
      self.calibration_results[cameraId] = result
      socket_id = self.socket_clients.get(cameraId)
      if socket_id:
        self.socketio.emit("calibration_result", {"camera_id": cameraId, "result": result}, to=socket_id)
        log.info(f"Sent WebSocket result to {socket_id} for {cameraId}")
      else:
        log.info(f"No socket_id found for {cameraId}, can't send result via WebSocket")

  def register_point_cloud_thread_wrapper(self, sceneobj, sensorId, sensor_frame_data):
    """
    Starts a background thread to register a sensor point cloud against a scene.
    """
    if not self.calibration_thread_lock.locked():
      self.socketio.start_background_task(
          self.process_point_cloud_registration,
          sceneobj, sensorId, sensor_frame_data
      )
      self.calibration_results[sensorId] = {
          "status": "calibrating",
          "message": "Registration started"
      }
    else:
      self.calibration_results[sensorId] = {
          "status": "busy",
          "message": "Another registration is already in progress"
      }

  def process_point_cloud_registration(self, sceneobj, sensorId, sensor_frame_data):
    """
    Registers a sensor point cloud against a scene in a background thread.
    Stores the resulting transform and emits it over Socket.IO.
    """
    log.info(f"[processPointCloudRegistration] Thread started for sensor {sensorId}")
    with self.calibration_thread_lock:
      try:
        result = self.point_cloud_strategy.generate_calibration(
            sceneobj, None, sensor_frame_data)
      except Exception as e:
        result = {
            "status": "error",
            "message": f"Registration failed: {str(e)}"
        }
      self.calibration_results[sensorId] = result
      socket_id = self.socket_clients.get(sensorId)
      if socket_id:
        self.socketio.emit("point_cloud_registration_result",
                           {"sensor_id": sensorId, "result": result}, to=socket_id)
        log.info(f"Sent WebSocket result to {socket_id} for {sensorId}")
      else:
        log.info(f"No socket_id found for {sensorId}, can't send result via WebSocket")
