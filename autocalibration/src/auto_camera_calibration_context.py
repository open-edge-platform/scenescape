# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading

from atag_camera_calibration_controller import ApriltagCameraCalibrationController
from auto_camera_calibration_model import CameraCalibrationModel
from markerless_camera_calibration_controller import MarkerlessCameraCalibrationController
from point_cloud_calibration_controller import PointCloudCalibrationController

from scene_common import log
from scene_common.options import POINTCLOUD


class CameraCalibrationContext:
  scene_strategies = {}

  # Modality keys (and aliases) that route to the point-cloud calibration
  # strategy. Point-cloud calibration is sensor-agnostic, so any point-cloud
  # producing modality maps to it.
  DEFAULT_SENSOR_MODALITY = POINTCLOUD
  SENSOR_MODALITY_ALIASES = {
      "pointcloud": POINTCLOUD,
      "point_cloud": POINTCLOUD,
      "point-cloud": POINTCLOUD,
      "lidar": POINTCLOUD,
      "depth": POINTCLOUD,
      "depth_camera": POINTCLOUD,
      "stereo": POINTCLOUD,
      "photogrammetry": POINTCLOUD,
  }

  def __init__(self, cert, root_cert, rest_url, rest_auth):
    self.calibration_data_interface = CameraCalibrationModel(root_cert, rest_url, rest_auth)

    self.scene_strategies["AprilTag"] = ApriltagCameraCalibrationController(calibration_data_interface=self.calibration_data_interface)
    self.scene_strategies["Markerless"] = MarkerlessCameraCalibrationController(calibration_data_interface=self.calibration_data_interface)

    # Perceptual-sensor calibration strategies are routed by modality,
    # independently of a scene's camera_calibration mode. Each modality owns its
    # strategy and its own lock so a long job for one modality never reports
    # another modality busy.
    self.sensor_calibration_strategies = {
        POINTCLOUD: PointCloudCalibrationController(calibration_data_interface=self.calibration_data_interface),
    }
    self.sensor_calibration_locks = {
        modality: threading.Lock() for modality in self.sensor_calibration_strategies
    }

    self.calibration_results = {}
    self.socket_clients = {}
    self.socket_scene_clients = {}
    self.socketio = None

    self.register_thread_lock = threading.Lock()
    self.calibration_thread_lock = threading.Lock()
    # Map updates requested while a registration runs, keyed by scene id.
    self.pending_map_updates = {}
    self.pending_map_updates_lock = threading.Lock()

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
    """! function starts processing the scene unless a registration is running.
    A map update received while a registration is running is queued and
    re-run once that registration finishes, so it is not lost.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    with self.pending_map_updates_lock:
      # The lock is taken here, not in the worker thread, so a run is busy from
      # the moment it is accepted until its queued work is done.
      if not self.register_thread_lock.acquire(blocking=False):
        if map_update:
          self.pending_map_updates[sceneobj.id] = sceneobj
          log.info(f"Map update for scene {sceneobj.name} queued until the current registration finishes")
        return
      try:
        threading.Thread(target=self.process_scene, args=(sceneobj, map_update)).start()
      except Exception:
        self.register_thread_lock.release()
        raise
    return

  def process_scene(self, sceneobj, map_update):
    """! function runs the registration for the scene, then re-runs any map
    update queued while it was running. Called with register_thread_lock held;
    the lock is released when no queued work remains.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    while sceneobj is not None:
      self._run_registration(sceneobj, map_update)
      sceneobj, map_update = self._next_queued_update_or_release()
    return

  def _run_registration(self, sceneobj, map_update):
    """! runs one registration. A map update starts from a clean scene (reset),
    inside the locked run so it never races a registration in progress.
    Any failure is logged so the queue always advances and the lock is released.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    try:
      strategy = self.scene_strategies[sceneobj.camera_calibration]
      if map_update:
        strategy.reset_scene(sceneobj)
      strategy.process_scene_for_calibration(sceneobj, map_update)
    except Exception as e:
      log.error(f"Error in register dataset for scene {sceneobj.name} : {e}")

  def _next_queued_update_or_release(self):
    """! takes the next queued map update for this run, or releases the lock.
    The queue check and the lock release happen under one lock, so an update
    accepted at any point is either picked up here or starts a new run.
    @return  tuple of (scene object, True) for the next run, or (None, False) when idle.
    """
    with self.pending_map_updates_lock:
      if self.pending_map_updates:
        _, sceneobj = self.pending_map_updates.popitem()
        return sceneobj, True
      self.register_thread_lock.release()
      return None, False

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

  def calibrate_perceptual_sensor_thread_wrapper(self, sceneobj, sensorId, sensor_frame_data):
    """
    Starts a background thread to localize a perceptual sensor against a scene.
    Routes by modality to the per-modality strategy and lock, and atomically
    claims that lock so concurrent requests get a deterministic "busy" response.
    The lock is released by process_perceptual_sensor_calibration once done.
    """
    modality = self._resolve_sensor_modality(sensor_frame_data.get("modality"))
    if modality is None:
      self.calibration_results[sensorId] = {
          "status": "error",
          "message": f"Unsupported sensor modality: {sensor_frame_data.get('modality')}"
      }
      return

    lock = self.sensor_calibration_locks[modality]
    if lock.acquire(blocking=False):
      try:
        self.socketio.start_background_task(
            self.process_perceptual_sensor_calibration,
            sceneobj, sensorId, sensor_frame_data, modality
        )
      except Exception:
        lock.release()
        raise
      self.calibration_results[sensorId] = {
          "status": "calibrating",
          "message": "Localization started"
      }
    else:
      self.calibration_results[sensorId] = {
          "status": "busy",
          "message": "Another localization is already in progress"
      }

  def _resolve_sensor_modality(self, modality):
    """Resolve a request modality to a registered calibration strategy key.

    @param   modality   Modality string from the request, or None.

    @return  A strategy key registered in sensor_calibration_strategies, or
             None when the modality is not supported.
    """
    if modality is None:
      return self.DEFAULT_SENSOR_MODALITY
    key = self.SENSOR_MODALITY_ALIASES.get(str(modality).strip().lower())
    if key in self.sensor_calibration_strategies:
      return key
    return None

  def process_perceptual_sensor_calibration(self, sceneobj, sensorId, sensor_frame_data, modality):
    """
    Calibrates a perceptual sensor against a scene in a background thread.
    Stores the resulting transform and emits it over Socket.IO.
    The modality lock is acquired by the caller
    (calibrate_perceptual_sensor_thread_wrapper) and released here when done.
    """
    log.info(f"[processPerceptualSensorCalibration] Thread started for sensor {sensorId}")
    lock = self.sensor_calibration_locks[modality]
    try:
      try:
        strategy = self.sensor_calibration_strategies[modality]
        result = strategy.generate_calibration(sceneobj, None, sensor_frame_data)
      except Exception as e:
        result = {
            "status": "error",
            "message": f"Localization failed: {str(e)}"
        }
      self.calibration_results[sensorId] = result
      socket_id = self.socket_clients.get(sensorId)
      if socket_id:
        self.socketio.emit("perceptual_sensor_calibration_result",
                           {"sensor_id": sensorId, "result": result}, to=socket_id)
        log.info(f"Sent WebSocket result to {socket_id} for {sensorId}")
      else:
        log.info(f"No socket_id found for {sensorId}, can't send result via WebSocket")
    finally:
      lock.release()
