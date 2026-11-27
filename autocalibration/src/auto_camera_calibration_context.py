# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import traceback
from collections import OrderedDict

from eventlet import tpool

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
    self.registration_results = {}
    # Bumped on worker start and finish so a stale synchronous result is dropped.
    self.registration_generations = {}
    # Requests received while a registration runs, keyed by scene id, oldest first.
    self.pending_registrations = OrderedDict()
    self.socket_clients = {}
    self.socketio = None

    self.register_thread_lock = threading.Lock()
    # Guards worker start/finish and pending_registrations so they change together.
    self.registration_state_lock = threading.RLock()
    self.calibration_thread_lock = threading.Lock()
    self.current_processing_scene = None

    return

  @staticmethod
  def scene_room(scene_id):
    return f"scene:{scene_id}"

  def preprocess_scenes(self):
    """! For all scenes in database, preprocess the scene map and store/update results

    @return  None
    """
    all_scene_objects = self.calibration_data_interface.all_scenes()
    for scene_object in all_scene_objects:
      if scene_object.camera_calibration != "Manual":
        self.scene_update_thread_wrapper(scene_object, map_update=self._is_map_stale(scene_object),
                                         queue_if_busy=True)
        log.info(f"Validating Scene = {scene_object.name} on start.")
    return

  def _is_map_stale(self, sceneobj):
    """! checks whether the scene map changed since it was last processed.
    A scene that cannot be checked is treated as not stale, so one bad scene
    cannot stop the others from being processed.
    @param   sceneobj      scene object.

    @return  True/False
    """
    strategy = self.scene_strategies.get(sceneobj.camera_calibration)
    if strategy is None:
      return False
    try:
      return bool(strategy.is_map_stale(sceneobj))
    except Exception as e:
      log.error(f"Could not check whether the map of scene {sceneobj.name} changed : {e}")
      return False

  def request_scene_registration(self, sceneobj, reset=False):
    """! Start registering a scene, or queue it while a registration runs.
    @param   sceneobj      scene object.
    @param   reset         boolean for resetting the scene before the run.

    @return  "active", "started", or "busy".
    """
    with self.registration_state_lock:
      active = self.current_processing_scene == sceneobj.id
      if self.scene_update_thread_wrapper(sceneobj, map_update=True, reset=reset,
                                          queue_if_busy=True):
        return "started"
      return "active" if active else "busy"

  def scene_update_thread_wrapper(self, sceneobj, map_update=False, reset=False,
                                  queue_if_busy=False):
    """! function starts processing the scene unless a registration is running.
    When busy, the request is queued if queue_if_busy is set, and run once the
    current registration finishes; otherwise it is dropped.
    @param   sceneobj        scene object.
    @param   map_update      boolean for re-registering the scene.
    @param   reset           boolean for resetting the scene before the run.
    @param   queue_if_busy   boolean for queueing the request when a registration is running.

    @return  True if this call started the run, False otherwise.
    """
    with self.registration_state_lock:
      # The lock is taken here, not in the worker, so a run is busy from the
      # moment it is accepted until its queued work is done.
      if not self.register_thread_lock.acquire(blocking=False):
        if queue_if_busy:
          self._queue_update(sceneobj, map_update, reset)
        return False
      self._mark_running(sceneobj)
      try:
        # Emits from a plain OS thread are never flushed by the eventlet Socket.IO server.
        self.socketio.start_background_task(self.process_scene, sceneobj, map_update, reset)
      except Exception:
        self.current_processing_scene = None
        self.register_thread_lock.release()
        raise
      return True

  def _mark_running(self, sceneobj):
    """! records that the scene owns the worker slot. Called with registration_state_lock held. """
    self.current_processing_scene = sceneobj.id
    self.pending_registrations.pop(sceneobj.id, None)
    self.registration_results.pop(sceneobj.id, None)
    self._bump_registration_generation(sceneobj.id)

  def _queue_update(self, sceneobj, map_update, reset):
    """! queues a request for a scene, merging it with one already queued.
    Called with registration_state_lock held.
    """
    queued = self.pending_registrations.get(sceneobj.id)
    if queued:
      _, queued_map_update, queued_reset = queued
      map_update = map_update or queued_map_update
      reset = reset or queued_reset
    # Re-assigning an existing key keeps its place in the queue.
    self.pending_registrations[sceneobj.id] = (sceneobj, map_update, reset)
    log.info(f"Scene {sceneobj.name} queued until the current registration finishes")

  def process_scene(self, sceneobj, map_update, reset=False):
    """! function runs the registration for the scene, then runs any request
    queued while it was running. Called with register_thread_lock held;
    the lock is released when no queued work remains, or on any exit.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.
    @param   reset         boolean for resetting the scene before the run.

    @return  None
    """
    request = (sceneobj, map_update, reset)
    lock_held = True
    try:
      while request is not None:
        sceneobj, map_update, reset = request
        # Pages already open for the scene must show the spinner while it re-registers.
        self.notify_scene_registration(sceneobj, {"status": "registering"})
        result = self._run_registration(sceneobj, map_update, reset)
        request = self.finish_registration(sceneobj.id, result)
        lock_held = request is not None
        self.notify_scene_registration(sceneobj, result)
    finally:
      if lock_held:
        self._abort_registration()
    return

  def _run_registration(self, sceneobj, map_update, reset):
    """! runs one registration. A reset starts from a clean scene, inside the
    locked run so it never races a registration in progress.
    Any failure becomes an error result so the queue always advances.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.
    @param   reset         boolean for resetting the scene before the run.

    @return  registration result dict.
    """
    try:
      strategy = self.scene_strategies[sceneobj.camera_calibration]
      # CPU-heavy work runs in a native thread so the Socket.IO hub keeps serving.
      if reset:
        tpool.execute(strategy.reset_scene, sceneobj)
      return tpool.execute(strategy.process_scene_for_calibration, sceneobj, map_update)
    except (FileNotFoundError, KeyError) as e:
      log.error(f"Error in register dataset : {e}")
      return {"status": "error", "message": str(e)}
    except Exception:
      log.error(f"Unexpected error registering scene {sceneobj.id}:\n{traceback.format_exc()}")
      return {"status": "error", "message": "Scene registration failed"}

  def finish_registration(self, scene_id, result):
    """! Record the worker result, then hand the worker slot to the next queued
    request, or free it when none remains.

    @return  tuple of (scene object, map_update, reset) for the next run, or None when idle.
    """
    with self.registration_state_lock:
      try:
        self.record_registration_result(scene_id, result)
      finally:
        self._bump_registration_generation(scene_id)
        self.current_processing_scene = None
      if not self.pending_registrations:
        self.register_thread_lock.release()
        return None
    return self._take_next_queued_request()

  def _take_next_queued_request(self):
    """! takes the oldest queued request that still needs to run, or releases the lock.
    The queue check and the lock release happen under one lock, so a request
    accepted at any point is either picked up here or starts a new run.
    @return  tuple of (scene object, map_update, reset) for the next run, or None when idle.
    """
    while True:
      with self.registration_state_lock:
        if not self.pending_registrations:
          self.register_thread_lock.release()
          return None
        _, request = self.pending_registrations.popitem(last=False)
      # Refreshing calls the manager, so it runs outside registration_state_lock.
      request = self._refresh_queued_request(request)
      if request is not None:
        with self.registration_state_lock:
          self._mark_running(request[0])
        return request

  def _abort_registration(self):
    """! frees the worker slot when a run ends without a clean hand-off. """
    with self.registration_state_lock:
      scene_id = self.current_processing_scene
      if scene_id is not None:
        self.record_registration_result(scene_id, None)
        self._bump_registration_generation(scene_id)
        self.current_processing_scene = None
      self.register_thread_lock.release()

  def _refresh_queued_request(self, request):
    """! reloads the scene of a queued request, so the run sees current data, and
    drops a map update the previous run already processed.
    @param   request       tuple of (scene object, map_update, reset).

    @return  the request to run, or None when it is no longer needed.
    """
    sceneobj, map_update, reset = request
    try:
      current = self.calibration_data_interface.scene_with_id(sceneobj.id)
    except Exception as e:
      log.warning(f"Could not reload queued scene {sceneobj.name}, using the queued copy : {e}")
      current = None
    if current is None:
      return request
    if map_update and not self._is_map_stale(current):
      log.info(f"Skipping queued update for scene {sceneobj.name}: its map is already processed")
      return None
    return current, map_update, reset

  def notify_scene_registration(self, sceneobj, response):
    # Every page open for the scene joins its room, so no page misses the result.
    room = self.scene_room(sceneobj.id)
    # The calibration type may have changed since the page loaded.
    self.socketio.emit("register_result", {
        "scene_id": sceneobj.id,
        "camera_calibration": sceneobj.camera_calibration,
        "data": response,
    }, to=room)
    log.info(f"Sent WebSocket result to room {room}")
    return

  def _bump_registration_generation(self, scene_id):
    self.registration_generations[scene_id] = self.registration_generations.get(scene_id, 0) + 1

  def begin_sync_registration(self, scene_id):
    """! Snapshot the scene's generation before an in-request registration."""
    with self.registration_state_lock:
      return self.registration_generations.get(scene_id, 0)

  def finish_sync_registration(self, scene_id, generation, result):
    """! Record an in-request result unless a worker started or finished meanwhile.

    @return  True if the result was recorded.
    """
    with self.registration_state_lock:
      if self.registration_generations.get(scene_id, 0) != generation:
        return False
      self.record_registration_result(scene_id, result)
      return True

  def record_registration_result(self, scene_id, result):
    """! Store a scene's terminal registration result as success or error."""
    status = result.get("status") if isinstance(result, dict) else None
    if status == "success":
      self.registration_results[scene_id] = {"status": "success"}
    else:
      message = result.get("message", status) if isinstance(result, dict) else None
      self.registration_results[scene_id] = {
          "status": "error",
          "message": message or "Scene registration failed",
      }

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
