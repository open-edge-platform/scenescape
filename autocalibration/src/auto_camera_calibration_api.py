# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import re
import os
import base64

from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError, RequestEntityTooLarge

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("autocalibration-rest")


class CameraCalibrationError(Exception):
  """Base exception for camera calibration errors."""

  def __init__(self, message, status_code=500, error_code=None):
    super().__init__(message)
    self.message = message
    self.status_code = status_code
    self.error_code = error_code or status_code


class ValidationError(CameraCalibrationError):
  """Raised when input validation fails."""

  def __init__(self, message):
    super().__init__(message, 400, 400)


class SceneNotFoundError(CameraCalibrationError):
  """Raised when a scene is not found."""

  def __init__(self, scene_id):
    super().__init__(f"Scene not found: {scene_id}", 404, 404)
    self.scene_id = scene_id


class CameraNotFoundError(CameraCalibrationError):
  """Raised when a camera is not found."""

  def __init__(self, camera_id):
    super().__init__(f"Camera or scene not found for camera: {camera_id}", 404, 404)
    self.camera_id = camera_id


class ManualCalibrationError(CameraCalibrationError):
  """Raised when trying to perform operations on manual calibration scenes."""

  def __init__(self, operation):
    super().__init__(f"Manual calibration scenes cannot be {operation}", 400, 400)


class CalibrationContextError(CameraCalibrationError):
  """Raised when calibration context is not initialized."""

  def __init__(self):
    super().__init__("Calibration context not initialized", 500, 500)


class MissingFieldError(CameraCalibrationError):
  """Raised when required fields are missing from request."""

  def __init__(self, field_name):
    super().__init__(f"Missing required field: {field_name}", 400, 400)


class IntrinsicsNotFoundError(CameraCalibrationError):
  """Raised when camera intrinsics are not found."""

  def __init__(self, camera_id):
    super().__init__(f"Intrinsics not found for camera {camera_id}", 400, 400)


class StrategyNotFoundError(CameraCalibrationError):
  """Raised when calibration strategy is not found."""

  def __init__(self):
    super().__init__("Calibration strategy not found", 500, 500)


class InvalidPointCloudError(CameraCalibrationError):
  """Raised when point cloud input validation fails."""

  def __init__(self, message):
    super().__init__(message, 400, 400)


class CameraCalibrationApi:
  """
  REST API service for automatic camera calibration in Scenescape.
  """

  API_VERSION = "1.0.0"

  MAX_ID_LENGTH = 255
  MIN_ID_LENGTH = 1
  VALID_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_\.]+$')  # Allow alphanumeric, hyphens, underscores, dots
  MAX_IMAGE_SIZE = 20 * 1024 * 1024
  MAX_REQUEST_SIZE = 25 * 1024 * 1024
  # Point clouds can be large (KPI targets >1M points); allow a bigger payload.
  MAX_POINTCLOUD_SIZE = 100 * 1024 * 1024

  class OpenApi:
    """
    Constants for OpenAPI field names and enumerations.
    """
    CODE = "code"
    MESSAGE = "message"
    STATUS = "status"
    VERSION = "version"
    SCENE_ID = "sceneId"
    CAMERA_ID = "cameraId"
    IMAGE = "image"
    INTRINSICS = "intrinsics"
    SENSOR_ID = "sensorId"
    POINTCLOUD = "pointcloud"
    FORMAT = "format"
    INITIAL_TRANSFORM = "initialTransform"

    class Status:
      BUSY = "busy"
      CALIBRATING = "calibrating"
      ERROR = "error"
      NOT_STARTED = "not_started"
      REGISTERING = "registering"
      RUNNING = "running"
      SUCCESS = "success"

  def __init__(self, calibrationContext=None):
    """
    Initialize the CameraCalibrationApi REST service.

    Args:
        calibrationContext: The calibration context object providing access
                           to scene and camera calibration logic.
    """
    self.app = Flask(__name__)
    # Set maximum content length to prevent huge payloads
    self.app.config['MAX_CONTENT_LENGTH'] = max(self.MAX_REQUEST_SIZE,
                                                self.MAX_POINTCLOUD_SIZE + 5 * 1024 * 1024)
    self.calibrationContext = calibrationContext

    self.socketio = SocketIO(self.app, path="/v1/socket.io/", cors_allowed_origins=["*"])
    if self.calibrationContext is not None:
      self.calibrationContext.socketio = self.socketio
    self.socket_client = {}

    self._register_error_handlers()
    self._register_routes()
    self._register_socket_events()

  def _validate_id(self, id_value, id_type="ID"):
    """
    Validate scene ID or camera ID format and length.

    Args:
        id_value: The ID string to validate
        id_type: Type of ID for error messages ("Scene ID" or "Camera ID")

    Raises:
        ValidationError: If the ID is invalid
    """
    if not id_value:
      raise ValidationError(f"{id_type} cannot be empty")
    if not isinstance(id_value, str):
      raise ValidationError(f"{id_type} must be a string")
    if len(id_value) < self.MIN_ID_LENGTH:
      raise ValidationError(f"{id_type} is too short (minimum {self.MIN_ID_LENGTH} characters)")
    if len(id_value) > self.MAX_ID_LENGTH:
      log.warning(f"Rejecting oversized {id_type}: {len(id_value)} characters")
      raise ValidationError(f"{id_type} is too long (maximum {self.MAX_ID_LENGTH} characters)")
    if not self.VALID_ID_PATTERN.match(id_value):
      raise ValidationError(f"{id_type} contains invalid characters (only alphanumeric, hyphens, underscores, and dots allowed)")

  def _validate_image_data(self, image_data):
    """
    Validate image data from request.

    Args:
        image_data: The image data to validate

    Raises:
        ValidationError: If the image data is invalid
    """
    if not isinstance(image_data, str):
      raise ValidationError("Image must be a string (base64 encoded)")
    if len(image_data) == 0:
      raise ValidationError("Image data cannot be empty")
    if len(image_data) > self.MAX_IMAGE_SIZE:
      log.warning(f"Rejecting oversized image data: {len(image_data)} bytes")
      raise ValidationError("Image data is too large")

    try:
      decoded = base64.b64decode(image_data, validate=True)
    except Exception:
      raise ValidationError("Image must be valid base64-encoded data")

    IMAGE_SIGNATURES = [
      b'\xff\xd8\xff',       # JPEG
      b'\x89PNG\r\n\x1a\n',  # PNG
      b'GIF87a', b'GIF89a',  # GIF
      b'BM',                 # BMP
      b'RIFF',               # WebP (starts with RIFF)
    ]
    if not any(decoded.startswith(sig) for sig in IMAGE_SIGNATURES):
      raise ValidationError("Image data does not appear to be a valid image format")

  def _validate_intrinsics(self, intrinsics):
    """Validate camera intrinsics matrix format."""
    if not isinstance(intrinsics, list) or len(intrinsics) != 3:
      raise ValidationError("Intrinsics must be a 3x3 matrix")
    for row in intrinsics:
      if not isinstance(row, list) or len(row) != 3:
        raise ValidationError("Each intrinsics row must contain exactly 3 values")
      for value in row:
        if not isinstance(value, (int, float)):
          raise ValidationError("Intrinsics values must be numbers")

  def _validate_pointcloud(self, pc_data, fmt=None):
    """Validate a base64-encoded point cloud payload (PLY or PCD)."""
    if not isinstance(pc_data, str):
      raise InvalidPointCloudError("Point cloud must be a string (base64 encoded)")
    if len(pc_data) == 0:
      raise InvalidPointCloudError("Point cloud data cannot be empty")
    if len(pc_data) > self.MAX_POINTCLOUD_SIZE:
      log.warning(f"Rejecting oversized point cloud data: {len(pc_data)} bytes")
      raise InvalidPointCloudError("Point cloud data is too large")

    if fmt is not None and (not isinstance(fmt, str) or fmt.lower() not in ("ply", "pcd")):
      raise InvalidPointCloudError("Point cloud format must be 'ply' or 'pcd'")

    try:
      decoded = base64.b64decode(pc_data, validate=True)
    except Exception:
      raise InvalidPointCloudError("Point cloud must be valid base64-encoded data")

    head = decoded[:64].upper()
    is_ply = decoded[:3] == b'ply'
    is_pcd = b'.PCD' in head or head.startswith(b'VERSION') or decoded[:1] == b'#'
    if not (is_ply or is_pcd):
      raise InvalidPointCloudError("Point cloud data must be a valid PLY or PCD file")

  def _validate_transform(self, transform):
    """Validate an optional 4x4 initial transform matrix."""
    if not isinstance(transform, list) or len(transform) != 4:
      raise ValidationError("Initial transform must be a 4x4 matrix")
    for row in transform:
      if not isinstance(row, list) or len(row) != 4:
        raise ValidationError("Each initial transform row must contain exactly 4 values")
      for value in row:
        if not isinstance(value, (int, float)):
          raise ValidationError("Initial transform values must be numbers")

  def _validate_pose_data(self, data):
    """Validate pose-related data in responses."""
    if "quaternion" in data:
      quat = data["quaternion"]
      if not isinstance(quat, list) or len(quat) != 4:
        raise ValidationError("Quaternion must contain exactly 4 values")
      for value in quat:
        if not isinstance(value, (int, float)):
          raise ValidationError("Quaternion values must be numbers")

    if "translation" in data:
      trans = data["translation"]
      if not isinstance(trans, list) or len(trans) != 3:
        raise ValidationError("Translation must contain exactly 3 values")
      for value in trans:
        if not isinstance(value, (int, float)):
          raise ValidationError("Translation values must be numbers")

  def _register_error_handlers(self):
    """Register global error handlers for consistent error responses."""

    @self.app.errorhandler(CameraCalibrationError)
    def handle_calibration_error(error):
      """Handle custom calibration errors."""
      log.error(f"Calibration error: {error.message}")
      response = {
          self.OpenApi.CODE: error.error_code,
          self.OpenApi.MESSAGE: error.message
      }
      return jsonify(response), error.status_code

    @self.app.errorhandler(BadRequest)
    def handle_bad_request(error):
      """Handle 400 Bad Request errors."""
      log.warning(f"Bad request: {error.description}")
      response = {
          self.OpenApi.CODE: 400,
          self.OpenApi.MESSAGE: error.description or "Bad request"
      }
      return jsonify(response), 400

    @self.app.errorhandler(NotFound)
    def handle_not_found(error):
      """Handle 404 Not Found errors."""
      log.warning(f"Not found: {error.description}")
      response = {
          self.OpenApi.CODE: 404,
          self.OpenApi.MESSAGE: error.description or "Resource not found"
      }
      return jsonify(response), 404

    @self.app.errorhandler(InternalServerError)
    def handle_internal_error(error):
      """Handle 500 Internal Server Error."""
      log.error(f"Internal server error: {error.description}")
      response = {
          self.OpenApi.CODE: 500,
          self.OpenApi.MESSAGE: "Internal server error"
      }
      return jsonify(response), 500

    @self.app.errorhandler(RequestEntityTooLarge)
    def handle_request_entity_too_large(error):
      """Handle 413 Request Entity Too Large errors."""
      log.warning("Request entity too large")
      response = {
          self.OpenApi.CODE: 413,
          self.OpenApi.MESSAGE: "Request payload too large"
      }
      return jsonify(response), 413

    @self.app.errorhandler(Exception)
    def handle_unexpected_error(error):
      """Handle unexpected errors."""
      log.error(f"Unexpected error: {str(error)}", exc_info=True)
      response = {
          self.OpenApi.CODE: 500,
          self.OpenApi.MESSAGE: "An unexpected error occurred"
      }
      return jsonify(response), 500

  def _validate_calibration_context(self):
    """Validate that calibration context is initialized."""
    if not self.calibrationContext:
      raise CalibrationContextError()

  def _get_scene(self, scene_id):
    """Get scene by ID with validation."""
    self._validate_calibration_context()
    self._validate_id(scene_id, "Scene ID")
    scene = self.calibrationContext.calibration_data_interface.scene_with_id(scene_id)
    if not scene:
      raise SceneNotFoundError(scene_id)
    return scene

  def _validate_scene_for_operation(self, scene, operation):
    """Validate scene can be used for the specified operation."""
    if scene.camera_calibration == "Manual":
      raise ManualCalibrationError(operation)

  def _get_camera(self, camera_id):
    """Get camera scene by camera ID with validation."""
    self._validate_calibration_context()
    self._validate_id(camera_id, "Camera ID")
    scene = self.calibrationContext.calibration_data_interface.scene_camera_with_id(camera_id)
    if not scene:
      raise CameraNotFoundError(camera_id)
    return scene

  def _get_calibration_strategy(self, scene):
    """Get calibration strategy for scene."""
    strategy = self.calibrationContext.scene_strategies.get(scene.camera_calibration)
    if not strategy:
      raise StrategyNotFoundError()
    return strategy

  def _register_socket_events(self):
    @self.socketio.on("connect")
    def handle_connect():
      log.info(f"WebSocket connected: {request.sid}")
      self.socketio.emit(
            "service_ready",
            {"status": self.OpenApi.Status.RUNNING, "version": self.API_VERSION},
            to=request.sid,
        )
      return

    @self.socketio.on("disconnect")
    def handle_disconnect():
      sid = request.sid
      log.info(f"WebSocket disconnected: {sid}")

      camera_to_remove = None
      for camera_id, stored_sid in self.calibrationContext.socket_clients.items():
        if stored_sid == sid:
          camera_to_remove = camera_id
          break

      if camera_to_remove:
        del self.calibrationContext.socket_clients[camera_to_remove]
        log.info(f"Removed camera '{camera_to_remove}' from socket_clients")
      else:
        log.info("No registered camera found for disconnected sid")
      return

    @self.socketio.on("register_camera")
    def handle_register_camera(data):
      log.info(f"handle_register_camera received: {data}")

      camera_id = data.get("camera_id") if isinstance(data, dict) else None
      if not camera_id:
        log.warning("Missing 'camera_id' in payload")
        return

      sid = request.sid
      self.calibrationContext.socket_clients[camera_id] = sid
      log.info(f"Registered camera '{camera_id}' with socket id {sid}")
      return

    @self.socketio.on("register_scene")
    def handle_register_scene(data):
      log.info(f"handle_register_scene received: {data}")

      scene_id = data.get("scene_id") if isinstance(data, dict) else None
      if not scene_id:
        log.warning("Missing 'scene_id' in payload")
        return

      sid = request.sid
      self.calibrationContext.socket_scene_clients[scene_id] = sid
      log.info(f"Registered scene '{scene_id}' with socket id {sid}")
      return

    @self.socketio.on("register_point_cloud_sensor")
    def handle_register_point_cloud_sensor(data):
      log.info(f"handle_register_point_cloud_sensor received: {data}")

      sensor_id = data.get("sensor_id") if isinstance(data, dict) else None
      if not sensor_id:
        log.warning("Missing 'sensor_id' in payload")
        return

      sid = request.sid
      self.calibrationContext.socket_clients[sensor_id] = sid
      log.info(f"Registered sensor '{sensor_id}' with socket id {sid}")
      return

  def _register_routes(self):
    """Register all REST API endpoints for camera calibration."""
    app = self.app
    API_PREFIX = "/v1"

    @app.route(f'{API_PREFIX}/status', methods=['GET'])
    def service_status():
      """Get the current status and version of the calibration service."""
      if not self.calibrationContext:
        return jsonify({
            self.OpenApi.STATUS: self.OpenApi.Status.ERROR,
            self.OpenApi.VERSION: self.API_VERSION
        }), 200

      return jsonify({
          self.OpenApi.STATUS: self.OpenApi.Status.RUNNING,
          self.OpenApi.VERSION: self.API_VERSION
      }), 200

    @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration', methods=['POST'])
    def register_scene(sceneId):
      """Register a scene for calibration processing."""
      log.info(f"POST {API_PREFIX}/scenes/{sceneId}/registration called")

      scene = self._get_scene(sceneId)
      self._validate_scene_for_operation(scene, "registered")
      strategy = self._get_calibration_strategy(scene)
      strategy.socketio = self.socketio
      strategy.socket_scene_clients = self.calibrationContext.socket_scene_clients

      if strategy.is_map_updated(scene):
        log.info(f"Scene map updated for {sceneId}")
        if self.calibrationContext.register_thread_lock.locked():
          log.info(f"Registration busy for {sceneId}")
          register_response = {
              self.OpenApi.STATUS: self.OpenApi.Status.BUSY,
              self.OpenApi.SCENE_ID: sceneId,
              self.OpenApi.MESSAGE: "Registration is currently busy"
          }
        else:
          log.info(f"Registration triggered for {sceneId}")
          register_response = {
              self.OpenApi.STATUS: self.OpenApi.Status.REGISTERING,
              self.OpenApi.SCENE_ID: sceneId,
              self.OpenApi.MESSAGE: "Registration started"
          }
          self.calibrationContext.scene_update_thread_wrapper(scene, map_update=True)
      else:
        log.info(f"Processing scene for calibration: {sceneId}")
        result = strategy.process_scene_for_calibration(scene)
        status = result.get(self.OpenApi.STATUS, self.OpenApi.Status.ERROR) if result else self.OpenApi.Status.ERROR

        if status == self.OpenApi.Status.SUCCESS:
          register_response = {
              self.OpenApi.STATUS: self.OpenApi.Status.SUCCESS,
              self.OpenApi.SCENE_ID: sceneId,
          }
        else:
          register_response = {
              self.OpenApi.STATUS: self.OpenApi.Status.ERROR,
              self.OpenApi.SCENE_ID: sceneId,
              self.OpenApi.MESSAGE: result.get(self.OpenApi.MESSAGE, status) if result else status,
          }

      log.info(f"Returning response for {sceneId}: {register_response}")
      return jsonify(register_response), 202 if register_response.get(self.OpenApi.STATUS) == self.OpenApi.Status.REGISTERING else 200

    @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration', methods=['GET'])
    def get_scene_registration_status(sceneId):
      """Get the current registration status of a scene."""
      log.info(f"GET {API_PREFIX}/scenes/{sceneId}/registration called")

      scene = self._get_scene(sceneId)
      self._validate_scene_for_operation(scene, "queried")
      strategy = self._get_calibration_strategy(scene)

      if strategy.is_map_updated(scene):
        if self.calibrationContext.register_thread_lock.locked():
          status = self.OpenApi.Status.BUSY
          message = "Registration is currently busy"
        else:
          status = self.OpenApi.Status.REGISTERING
          message = "Registration is in progress"
      else:
        status = self.OpenApi.Status.SUCCESS
        message = "Registration is complete"

      response = {
          self.OpenApi.STATUS: status,
          self.OpenApi.SCENE_ID: sceneId,
          self.OpenApi.MESSAGE: message
      }

      log.info(f"Returning registration status for {sceneId}: {response}")
      return jsonify(response), 200

    @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration', methods=['PATCH'])
    def update_scene(sceneId):
      """Notify the calibration service that a scene has been updated."""
      log.info(f"PATCH {API_PREFIX}/scenes/{sceneId}/registration called")

      scene = self._get_scene(sceneId)
      self._validate_scene_for_operation(scene, "updated")
      strategy = self._get_calibration_strategy(scene)

      if strategy.is_map_updated(scene):
        strategy.reset_scene(scene)
        self.calibrationContext.scene_update_thread_wrapper(scene, map_update=True)
        log.info(f"Scene update triggered for {sceneId}")
        return jsonify({self.OpenApi.MESSAGE: "Scene update triggered"}), 202
      else:
        log.info(f"No update needed for scene {sceneId}")
        return jsonify({self.OpenApi.MESSAGE: "No update needed"}), 200

    @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration', methods=['POST'])
    def calibrate_camera(cameraId):
      """Trigger calibration for a specific camera."""
      log.info(f"POST {API_PREFIX}/cameras/{cameraId}/calibration called")

      scene = self._get_camera(cameraId)
      strategy = self._get_calibration_strategy(scene)

      try:
        data = request.get_json(force=True)
      except Exception as e:
        log.warning(f"Failed to parse JSON for camera {cameraId}: {e}")
        raise ValidationError("Invalid JSON in request body")

      if not data or self.OpenApi.IMAGE not in data:
        raise MissingFieldError('image')

      image = data[self.OpenApi.IMAGE]
      self._validate_image_data(image)
      intrinsics = data.get(self.OpenApi.INTRINSICS)

      if intrinsics is not None:
        self._validate_intrinsics(intrinsics)

      if intrinsics is None:
        intrinsics = self.calibrationContext.calibration_data_interface.get_camera_intrinsics(cameraId)

      if intrinsics is None:
        raise IntrinsicsNotFoundError(cameraId)

      cam_frame_data = {
          "image": image,
          "id": cameraId
      }

      try:
        self.calibrationContext.calibrate_camera_thread_wrapper(
            scene, cameraId, intrinsics, cam_frame_data
        )
        return jsonify({
            self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
            self.OpenApi.CAMERA_ID: cameraId,
            self.OpenApi.MESSAGE: "Calibration started"
        }), 202
      except Exception as e:
        log.error(f"Calibration failed for camera {cameraId}: {e}")
        raise CameraCalibrationError(f"Calibration failed: {str(e)}")

    @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration', methods=['GET'])
    def get_camera_calibration_status(cameraId):
      """Get the current calibration status and result for a camera."""
      log.info(f"GET {API_PREFIX}/cameras/{cameraId}/calibration called")

      scene = self._get_camera(cameraId)
      self._validate_scene_for_operation(scene, "queried")

      if self.calibrationContext.calibration_thread_lock.locked():
        response = {
            self.OpenApi.CAMERA_ID: cameraId,
            self.OpenApi.SCENE_ID: getattr(scene, "id", None),
            self.OpenApi.STATUS: self.OpenApi.Status.BUSY,
            self.OpenApi.MESSAGE: "Calibration is currently in progress"
        }
        return jsonify(response), 200

      result = self.calibrationContext.calibration_results.get(cameraId)
      if result is None:
        response = {
            self.OpenApi.CAMERA_ID: cameraId,
            self.OpenApi.SCENE_ID: getattr(scene, "id", None),
            self.OpenApi.STATUS: self.OpenApi.Status.NOT_STARTED,
            self.OpenApi.MESSAGE: "Calibration has not been started for this camera"
        }
        return jsonify(response), 200
      elif result.get("status") == self.OpenApi.Status.CALIBRATING:
        response = {
            self.OpenApi.CAMERA_ID: cameraId,
            self.OpenApi.SCENE_ID: getattr(scene, "id", None),
            self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
            self.OpenApi.MESSAGE: "Calibration in progress"
        }
        return jsonify(response), 200

      response = {
          self.OpenApi.CAMERA_ID: cameraId,
          self.OpenApi.SCENE_ID: getattr(scene, "id", None),
          self.OpenApi.STATUS: result.get("status", self.OpenApi.Status.ERROR),
          self.OpenApi.MESSAGE: result.get("message", ""),
      }
      if result.get("status") == self.OpenApi.Status.SUCCESS:
        self._validate_pose_data(result)
        response["pose"] = result.get("pose")
        for key in ("quaternion", "translation", "calibration_points_3d", "calibration_points_2d"):
          if key in result:
            response[key] = result[key]
      return jsonify(response), 200

    @app.route(f'{API_PREFIX}/point-cloud-sensors/<sensorId>/registration', methods=['POST'])
    def register_point_cloud_sensor_calibration(sensorId):
      """Register a sensor point cloud against a scene point cloud."""
      log.info(f"POST {API_PREFIX}/point-cloud-sensors/{sensorId}/registration called")

      self._validate_calibration_context()
      self._validate_id(sensorId, "Sensor ID")

      try:
        data = request.get_json(force=True)
      except Exception as e:
        log.warning(f"Failed to parse JSON for sensor {sensorId}: {e}")
        raise ValidationError("Invalid JSON in request body")

      if not data:
        raise ValidationError("Request body cannot be empty")

      scene_id = data.get(self.OpenApi.SCENE_ID)
      if not scene_id:
        raise MissingFieldError(self.OpenApi.SCENE_ID)
      scene = self._get_scene(scene_id)

      pointcloud = data.get(self.OpenApi.POINTCLOUD)
      if not pointcloud:
        raise MissingFieldError(self.OpenApi.POINTCLOUD)
      fmt = data.get(self.OpenApi.FORMAT)
      self._validate_pointcloud(pointcloud, fmt)

      initial_transform = data.get(self.OpenApi.INITIAL_TRANSFORM)
      if initial_transform is not None:
        self._validate_transform(initial_transform)

      sensor_frame_data = {
          "pointcloud": pointcloud,
          "format": fmt,
          "initial_transform": initial_transform,
          "id": sensorId
      }

      try:
        self.calibrationContext.register_point_cloud_thread_wrapper(
            scene, sensorId, sensor_frame_data
        )
        return jsonify({
            self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
            self.OpenApi.SENSOR_ID: sensorId,
            self.OpenApi.SCENE_ID: scene_id,
            self.OpenApi.MESSAGE: "Registration started"
        }), 202
      except Exception as e:
        log.error(f"Registration failed for sensor {sensorId}: {e}")
        raise CameraCalibrationError(f"Registration failed: {str(e)}")

    @app.route(f'{API_PREFIX}/point-cloud-sensors/<sensorId>/registration', methods=['GET'])
    def get_point_cloud_registration_status(sensorId):
      """Get the current registration status and result for a sensor."""
      log.info(f"GET {API_PREFIX}/point-cloud-sensors/{sensorId}/registration called")

      self._validate_calibration_context()
      self._validate_id(sensorId, "Sensor ID")

      if self.calibrationContext.point_cloud_thread_lock.locked():
        return jsonify({
            self.OpenApi.SENSOR_ID: sensorId,
            self.OpenApi.STATUS: self.OpenApi.Status.BUSY,
            self.OpenApi.MESSAGE: "Registration is currently in progress"
        }), 200

      result = self.calibrationContext.calibration_results.get(sensorId)
      if result is None:
        return jsonify({
            self.OpenApi.SENSOR_ID: sensorId,
            self.OpenApi.STATUS: self.OpenApi.Status.NOT_STARTED,
            self.OpenApi.MESSAGE: "Registration has not been started for this sensor"
        }), 200
      elif result.get("status") == self.OpenApi.Status.CALIBRATING:
        return jsonify({
            self.OpenApi.SENSOR_ID: sensorId,
            self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
            self.OpenApi.MESSAGE: "Registration in progress"
        }), 200

      response = {
          self.OpenApi.SENSOR_ID: sensorId,
          self.OpenApi.STATUS: result.get("status", self.OpenApi.Status.ERROR),
          self.OpenApi.MESSAGE: result.get("message", ""),
      }
      if result.get("status") == self.OpenApi.Status.SUCCESS:
        for key in ("transform", "fitness", "inlier_rmse", "scene_name"):
          if key in result:
            response[key] = result[key]
      return jsonify(response), 200

  def start(self, port=8443, ssl_cert=None, ssl_key=None):
    """
    Start the REST API server with mandatory TLS support.

    Args:
        port: HTTPS port number to listen on (default: 8443).
        ssl_cert: Path to SSL certificate file (required)
        ssl_key: Path to SSL private key file (required)
    """
    log.info(f"Starting HTTPS REST API server on port {port}")

    # TLS is mandatory - validate certificates are provided
    if not ssl_cert or not ssl_key:
      raise ValueError("SSL certificate and key file paths must be provided.")

    # Validate certificate files exist
    if not os.path.exists(ssl_cert):
      raise FileNotFoundError(f"SSL certificate not found: {ssl_cert}")
    if not os.path.exists(ssl_key):
      raise FileNotFoundError(f"SSL private key not found: {ssl_key}")

    log.info(f"TLS enabled with certificate: {ssl_cert}")

    self.socketio.run(
            self.app,
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False,
            certfile=ssl_cert,
            keyfile=ssl_key)

    log.info(f"HTTPS server started on port {port}")
