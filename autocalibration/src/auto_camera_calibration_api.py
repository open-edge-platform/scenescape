# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import re
import os

from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError, RequestEntityTooLarge

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camcalibration-rest")


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


class CameraCalibrationApi:
  """
  REST API service for automatic camera calibration in Intel SceneScape.
  """

  API_VERSION = "1.0.0"

  MAX_ID_LENGTH = 255
  MIN_ID_LENGTH = 1
  VALID_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_\.]+$')  # Allow alphanumeric, hyphens, underscores, dots
  MAX_IMAGE_SIZE = 20 * 1024 * 1024
  MAX_REQUEST_SIZE = 25 * 1024 * 1024

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
    self.app.config['MAX_CONTENT_LENGTH'] = self.MAX_REQUEST_SIZE
    self.calibrationContext = calibrationContext

    self.socketio = SocketIO(self.app, cors_allowed_origins=["*"])
    if self.calibrationContext is not None:
      self.calibrationContext.socketio = self.socketio
    self.socket_client = {}

    self._registerErrorHandlers()
    self._registerRoutes()
    self._registerSocketEvents()

  def _validateId(self, id_value, id_type="ID"):
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

  def _validateImageData(self, image_data):
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

  def _validateIntrinsics(self, intrinsics):
    """Validate camera intrinsics matrix format."""
    if not isinstance(intrinsics, list) or len(intrinsics) != 3:
      raise ValidationError("Intrinsics must be a 3x3 matrix")
    for row in intrinsics:
      if not isinstance(row, list) or len(row) != 3:
        raise ValidationError("Each intrinsics row must contain exactly 3 values")
      for value in row:
        if not isinstance(value, (int, float)):
          raise ValidationError("Intrinsics values must be numbers")

  def _validatePoseData(self, data):
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

  def _registerErrorHandlers(self):
    """Register global error handlers for consistent error responses."""

    @self.app.errorhandler(CameraCalibrationError)
    def handleCalibrationError(error):
      """Handle custom calibration errors."""
      log.error(f"Calibration error: {error.message}")
      response = {
          self.OpenApi.CODE: error.error_code,
          self.OpenApi.MESSAGE: error.message
      }
      return jsonify(response), error.status_code

    @self.app.errorhandler(BadRequest)
    def handleBadRequest(error):
      """Handle 400 Bad Request errors."""
      log.warning(f"Bad request: {error.description}")
      response = {
          self.OpenApi.CODE: 400,
          self.OpenApi.MESSAGE: error.description or "Bad request"
      }
      return jsonify(response), 400

    @self.app.errorhandler(NotFound)
    def handleNotFound(error):
      """Handle 404 Not Found errors."""
      log.warning(f"Not found: {error.description}")
      response = {
          self.OpenApi.CODE: 404,
          self.OpenApi.MESSAGE: error.description or "Resource not found"
      }
      return jsonify(response), 404

    @self.app.errorhandler(InternalServerError)
    def handleInternalError(error):
      """Handle 500 Internal Server Error."""
      log.error(f"Internal server error: {error.description}")
      response = {
          self.OpenApi.CODE: 500,
          self.OpenApi.MESSAGE: "Internal server error"
      }
      return jsonify(response), 500

    @self.app.errorhandler(RequestEntityTooLarge)
    def handleRequestEntityTooLarge(error):
      """Handle 413 Request Entity Too Large errors."""
      log.warning("Request entity too large")
      response = {
          self.OpenApi.CODE: 413,
          self.OpenApi.MESSAGE: "Request payload too large"
      }
      return jsonify(response), 413

    @self.app.errorhandler(Exception)
    def handleUnexpectedError(error):
      """Handle unexpected errors."""
      log.error(f"Unexpected error: {str(error)}", exc_info=True)
      response = {
          self.OpenApi.CODE: 500,
          self.OpenApi.MESSAGE: "An unexpected error occurred"
      }
      return jsonify(response), 500

  def _validateCalibrationContext(self):
    """Validate that calibration context is initialized."""
    if not self.calibrationContext:
      raise CalibrationContextError()

  def _getScene(self, scene_id):
    """Get scene by ID with validation."""
    self._validateCalibrationContext()
    self._validateId(scene_id, "Scene ID")
    scene = self.calibrationContext.calibration_data_interface.sceneWithID(scene_id)
    if not scene:
      raise SceneNotFoundError(scene_id)
    return scene

  def _validateSceneForOperation(self, scene, operation):
    """Validate scene can be used for the specified operation."""
    if scene.camera_calibration == "Manual":
      raise ManualCalibrationError(operation)

  def _getCamera(self, camera_id):
    """Get camera scene by camera ID with validation."""
    self._validateCalibrationContext()
    self._validateId(camera_id, "Camera ID")
    scene = self.calibrationContext.calibration_data_interface.sceneCameraWithID(camera_id)
    if not scene:
      raise CameraNotFoundError(camera_id)
    return scene

  def _getCalibrationStrategy(self, scene):
    """Get calibration strategy for scene."""
    strategy = self.calibrationContext.scene_strategies.get(scene.camera_calibration)
    if not strategy:
      raise StrategyNotFoundError()
    return strategy

  def _registerSocketEvents(self):
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

  def _registerRoutes(self):
    """Register all REST API endpoints for camera calibration."""
    app = self.app
    API_PREFIX = "/v1"

    @app.route(f'{API_PREFIX}/status', methods=['GET'])
    def serviceStatus():
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
    def registerScene(sceneId):
      """Register a scene for calibration processing."""
      log.info(f"POST {API_PREFIX}/scenes/{sceneId}/registration called")

      scene = self._getScene(sceneId)
      self._validateSceneForOperation(scene, "registered")
      strategy = self._getCalibrationStrategy(scene)
      strategy.socketio = self.socketio
      strategy.socket_scene_clients = self.calibrationContext.socket_scene_clients

      if strategy.isMapUpdated(scene):
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
          self.calibrationContext.sceneUpdateThreadWrapper(scene, map_update=True)
      else:
        log.info(f"Processing scene for calibration: {sceneId}")
        result = strategy.processSceneForCalibration(scene)
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
    def getSceneRegistrationStatus(sceneId):
      """Get the current registration status of a scene."""
      log.info(f"GET {API_PREFIX}/scenes/{sceneId}/registration called")

      scene = self._getScene(sceneId)
      self._validateSceneForOperation(scene, "queried")
      strategy = self._getCalibrationStrategy(scene)

      if strategy.isMapUpdated(scene):
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
    def updateScene(sceneId):
      """Notify the calibration service that a scene has been updated."""
      log.info(f"PATCH {API_PREFIX}/scenes/{sceneId}/registration called")

      scene = self._getScene(sceneId)
      self._validateSceneForOperation(scene, "updated")
      strategy = self._getCalibrationStrategy(scene)

      if strategy.isMapUpdated(scene):
        strategy.resetScene(scene)
        self.calibrationContext.sceneUpdateThreadWrapper(scene, map_update=True)
        log.info(f"Scene update triggered for {sceneId}")
        return jsonify({self.OpenApi.MESSAGE: "Scene update triggered"}), 202
      else:
        log.info(f"No update needed for scene {sceneId}")
        return jsonify({self.OpenApi.MESSAGE: "No update needed"}), 200

    @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration', methods=['POST'])
    def calibrateCamera(cameraId):
      """Trigger calibration for a specific camera."""
      log.info(f"POST {API_PREFIX}/cameras/{cameraId}/calibration called")

      scene = self._getCamera(cameraId)
      strategy = self._getCalibrationStrategy(scene)

      try:
        data = request.get_json(force=True)
      except Exception as e:
        log.warning(f"Failed to parse JSON for camera {cameraId}: {e}")
        raise ValidationError("Invalid JSON in request body")

      if not data or self.OpenApi.IMAGE not in data:
        raise MissingFieldError('image')

      image = data[self.OpenApi.IMAGE]
      self._validateImageData(image)
      intrinsics = data.get(self.OpenApi.INTRINSICS)

      if intrinsics is not None:
        self._validateIntrinsics(intrinsics)

      if intrinsics is None:
        intrinsics = self.calibrationContext.calibration_data_interface.getCameraIntrinsics(cameraId)

      if intrinsics is None:
        raise IntrinsicsNotFoundError(cameraId)

      cam_frame_data = {
          "image": image,
          "id": cameraId
      }

      try:
        self.calibrationContext.calibrateCameraThreadWrapper(
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
    def getCameraCalibrationStatus(cameraId):
      """Get the current calibration status and result for a camera."""
      log.info(f"GET {API_PREFIX}/cameras/{cameraId}/calibration called")

      scene = self._getCamera(cameraId)
      self._validateSceneForOperation(scene, "queried")

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
        self._validatePoseData(result)
        response["pose"] = result.get("pose")
        for key in ("quaternion", "translation", "calibration_points_3d", "calibration_points_2d"):
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
