# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import ssl
from typing import Optional, Dict, Any, List
from enum import Enum
import logging
import re
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camcalibration-fastapi")

# Enums for status values to match OpenAPI spec
class ServiceStatus(str, Enum):
    RUNNING = "running"
    ERROR = "error"

class RegistrationTriggerStatus(str, Enum):
    SUCCESS = "success"
    REGISTERING = "registering"
    BUSY = "busy"
    ERROR = "error"

class RegistrationStatus(str, Enum):
    SUCCESS = "success"
    REGISTERING = "registering"
    BUSY = "busy"
    ERROR = "error"

class CalibrationStatus(str, Enum):
    SUCCESS = "success"
    CALIBRATING = "calibrating"
    ERROR = "error"
    NOT_STARTED = "not_started"
    BUSY = "busy"

# Pydantic models for request/response validation
class ErrorResponse(BaseModel):
    code: int
    message: str

class StatusResponse(BaseModel):
    status: ServiceStatus
    version: str

class SceneRegistrationTriggerResponse(BaseModel):
    status: RegistrationTriggerStatus
    sceneId: str
    message: Optional[str] = None

class SceneRegistrationStatusResponse(BaseModel):
    status: RegistrationStatus
    sceneId: str
    message: Optional[str] = None

class SceneUpdateResponse(BaseModel):
    message: str

class CalibrationRequest(BaseModel):
    image: str = Field(..., description="Base64 encoded calibration image")
    intrinsics: Optional[List[List[float]]] = Field(None, description="Camera intrinsics matrix (3x3)")

class CalibrationTriggerResponse(BaseModel):
    status: CalibrationStatus
    cameraId: str
    message: Optional[str] = None

class CalibrationStatusResponse(BaseModel):
    cameraId: str
    sceneId: Optional[str] = None
    status: CalibrationStatus
    message: str
    pose: Optional[Dict[str, Any]] = None
    quaternion: Optional[List[float]] = None
    translation: Optional[List[float]] = None
    camera_frustum: Optional[Dict[str, Any]] = None
    calibration_points_3d: Optional[List[List[float]]] = None
    calibration_points_2d: Optional[List[List[float]]] = None

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
        self._registerErrorHandlers()
        self._registerRoutes()

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

    def _registerErrorHandlers(self):
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

        @self.app.errorhandler(413)
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

    def _validateCalibrationContext(self):
        """Validate that calibration context is initialized."""
        if not self.calibrationContext:
            raise CalibrationContextError()

    def _getScene(self, scene_id):
        """Get scene by ID with validation."""
        self._validateCalibrationContext()
        self._validate_id(scene_id, "Scene ID")
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
        self._validate_id(camera_id, "Camera ID")
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

    def _registerRoutes(self):
        """Register all REST API endpoints for camera calibration."""
        app = self.app

        API_PREFIX = "/v1"

        @app.route(f'{API_PREFIX}/status', methods=['GET'])
        def serviceStatus():
            """
            Get the current status and version of the calibration service.

            Returns:
                JSON response with service status and version.
            """
            if not self.calibrationContext:
                return StatusResponse(
                    status=ServiceStatus.ERROR,
                    version=self.API_VERSION
                )

            return StatusResponse(
                status=ServiceStatus.RUNNING,
                version=self.API_VERSION
            )

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration', methods=['POST'])
        def registerScene(sceneId):
            """
            Register a scene for calibration processing.

            Args:
                sceneId: Unique identifier of the scene.

            Returns:
                JSON response indicating registration status or error.
            """
            log.info(f"POST {API_PREFIX}/scenes/{sceneId}/registration called")
            # Error: Internal server error
            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                return jsonify({
                    self.OpenApi.CODE: 500,
                    self.OpenApi.MESSAGE: "Calibration context not initialized"
                }), 500

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(
                sceneId)
            # Error: Scene not found
            if not scene:
                log.warning(f"Scene not found: {sceneId}")
                return jsonify({
                    self.OpenApi.CODE: 404,
                    self.OpenApi.MESSAGE: "Scene not found"
                }), 404

            # Error: Invalid scene ID (manual calibration)
            if scene.camera_calibration == "Manual":
                log.warning(
                    f"Manual calibration scene cannot be registered: {sceneId}")
                return jsonify({
                    self.OpenApi.CODE: 400,
                    self.OpenApi.MESSAGE: "Manual calibration scenes cannot be registered"
                }), 400

            if strategy.isMapUpdated(scene):
                log.info(f"Scene map updated for {sceneId}")
                if self.calibrationContext.register_thread_lock.locked():
                    log.info(f"Registration busy for {sceneId}")
                    return SceneRegistrationTriggerResponse(
                        status=RegistrationTriggerStatus.BUSY,
                        sceneId=sceneId,
                        message="Registration is currently busy"
                    )
                else:
                    log.info(f"Registration triggered for {sceneId}")
                    register_response = {
                        self.OpenApi.STATUS: self.OpenApi.Status.REGISTERING,
                        self.OpenApi.SCENE_ID: sceneId,
                        self.OpenApi.MESSAGE: "Registration started"
                    }
                    self.calibrationContext.sceneUpdateThreadWrapperRest(
                        scene, map_update=True)
            else:
                log.info(f"Processing scene for calibration: {sceneId}")
                result = self.calibrationContext.scene_strategies[scene.camera_calibration].processSceneForCalibration(
                    scene)
                status = result.get(
                    self.OpenApi.STATUS,
                    self.OpenApi.Status.ERROR) if result else self.OpenApi.Status.ERROR
                if status == self.OpenApi.Status.SUCCESS:
                    register_response = {
                        self.OpenApi.STATUS: self.OpenApi.Status.SUCCESS,
                        self.OpenApi.SCENE_ID: sceneId,
                    }
                else:
                    register_response = {
                        self.OpenApi.STATUS: self.OpenApi.Status.ERROR,
                        self.OpenApi.SCENE_ID: sceneId,
                        self.OpenApi.MESSAGE: result.get(
                            self.OpenApi.MESSAGE,
                            status) if result else status,
                    }

            log.info(f"Returning response for {sceneId}: {register_response}")
            return jsonify(register_response), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration', methods=['GET'])
        def getSceneRegistrationStatus(sceneId):
            """
            Get the current registration status of a scene.

            Args:
                sceneId: Unique identifier of the scene.

            if strategy.isMapUpdated(scene):
                if self.calibrationContext.register_thread_lock.locked():
                    status_val = RegistrationStatus.BUSY
                    message = "Registration is currently busy"
                else:
                    status_val = RegistrationStatus.REGISTERING
                    message = "Registration is in progress"
            else:
                status_val = RegistrationStatus.SUCCESS
                message = "Registration is complete"

            return SceneRegistrationStatusResponse(
                status=status_val,
                sceneId=sceneId,
                message=message
            )

            log.info(f"Returning registration status for {sceneId}: {response}")
            return jsonify(response), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>', methods=['PATCH'])
        def updateScene(sceneId):
            """
            Notify the calibration service that a scene has been updated.

            Args:
                sceneId: Unique identifier of the scene.

            Returns:
                JSON response acknowledging the update notification.
            """
            log.info(f"POST {API_PREFIX}/scenes/{sceneId} called")
            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration context not initialized"}), 500

            sceneobj = self.calibrationContext.calibration_data_interface.sceneWithID(sceneId)
            if not sceneobj:
                log.warning(f"Scene not found: {sceneId}")
                return jsonify(
                    {self.OpenApi.CODE: 404, self.OpenApi.MESSAGE: "Scene not found"}), 404

            if sceneobj.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be updated: {sceneId}")
                return jsonify(
                    {self.OpenApi.CODE: 400, self.OpenApi.MESSAGE: "Manual calibration scenes cannot be updated"}), 400

            strategy = self.calibrationContext.scene_strategies.get(sceneobj.camera_calibration)
            if not strategy:
                log.error(f"Calibration strategy not found for scene {sceneId}")
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration strategy not found"}), 500

            if strategy.isMapUpdated(sceneobj):
                strategy.resetScene(sceneobj)
                self.calibrationContext.sceneUpdateThreadWrapperRest(sceneobj, map_update=True)
                log.info(f"Scene update triggered for {sceneId}")
                return jsonify(
                    {self.OpenApi.MESSAGE: "Scene update triggered"}), 202
            else:
                log.info(f"No update needed for scene {sceneId}")
                return jsonify(
                    {self.OpenApi.MESSAGE: "No update needed"}), 200

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration', methods=['POST'])
        def calibrateCamera(cameraId):
            """
            Trigger calibration for a specific camera.

            Args:
                cameraId: Unique identifier of the camera.

            Returns:
                JSON response indicating calibration status or error.
            """
            log.info(f"POST {API_PREFIX}/cameras/{cameraId}/calibration  called")
            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                return jsonify({
                    self.OpenApi.CODE: 500,
                    self.OpenApi.MESSAGE: "Calibration context not initialized"
                }), 500

            # Find the scene object
            sceneobj = self.calibrationContext.calibration_data_interface.sceneCameraWithID(cameraId)
            if not sceneobj:
                log.warning(f"Camera or scene not found. Camera provided: {cameraId}")
                return jsonify({
                    self.OpenApi.CODE: 404,
                    self.OpenApi.MESSAGE: "Camera or scene not found"
                }), 404

            try:
                data = request.get_json(force=True)
            except Exception as e:
                log.warning(f"Failed to parse JSON for camera {cameraId}: {e}")
                raise ValidationError("Invalid JSON in request body")

            if not data or self.OpenApi.IMAGE not in data:
                log.warning(f"Missing required field 'image' in calibration request for camera {cameraId}")
                return jsonify({
                    self.OpenApi.CODE: 400,
                    self.OpenApi.MESSAGE: "Missing required field: image"
                }), 400

            image = data[self.OpenApi.IMAGE]
            self._validate_image_data(image)
            intrinsics = data.get(self.OpenApi.INTRINSICS)

            if intrinsics is None:
                intrinsics = self.calibrationContext.calibration_data_interface.getCameraIntrinsics(cameraId)

            if intrinsics is None:
                log.error(f"Intrinsics not found for camera {cameraId}")
                return jsonify({
                    self.OpenApi.CODE: 400,
                    self.OpenApi.MESSAGE: f"Intrinsics not found for camera {cameraId}"
                }), 400

            # Find calibration strategy
            strategy = self.calibrationContext.scene_strategies.get(sceneobj.camera_calibration)
            if not strategy:
                log.error(f"Calibration strategy not found for scene {getattr(sceneobj, 'id', None)}")
                return jsonify({
                    self.OpenApi.CODE: 500,
                    self.OpenApi.MESSAGE: "Calibration strategy not found"
                }), 500

            cam_frame_data = {
                "image": image,
                "id": cameraId
            }

            try:
                self.calibrationContext.calibrateCameraThreadWrapperRest(
                    scene, cameraId, intrinsics, cam_frame_data
                )
                return CalibrationTriggerResponse(
                    status=CalibrationStatus.CALIBRATING,
                    cameraId=cameraId,
                    message="Calibration started"
                )
            except Exception as e:
                log.error(f"Calibration failed for camera {cameraId}: {e}")
                return jsonify({
                    self.OpenApi.CODE: 500,
                    self.OpenApi.MESSAGE: f"Calibration failed: {str(e)}"
                }), 500

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration', methods=['GET'])
        def getCameraCalibrationStatus(cameraId):
            """
            Get the current calibration status and result for a camera.

            Args:
                cameraId: Unique identifier of the camera.

            Returns:
                JSON response with calibration status, pose, or error.
            """
            log.info(f"GET {API_PREFIX}/cameras/{cameraId}/calibration called")
            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration context not initialized"}), 500

            # Find the scene object for this camera
            sceneobj = self.calibrationContext.calibration_data_interface.sceneCameraWithID(cameraId)
            if not sceneobj:
                log.warning(f"Camera or scene not found. Camera provided: {cameraId}")
                return jsonify({
                    self.OpenApi.CODE: 404,
                    self.OpenApi.MESSAGE: "Camera or scene not found"
                }), 404

            # Manual calibration scenes do not support status
            if sceneobj.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be queried: {cameraId}")
                return jsonify({
                    self.OpenApi.CODE: 400,
                    self.OpenApi.MESSAGE: "Manual calibration scenes do not support calibration status"
                }), 400

            if self.calibrationContext.calibration_thread_lock.locked():
                response = {
                    self.OpenApi.CAMERA_ID: cameraId,
                    self.OpenApi.SCENE_ID: getattr(sceneobj, "id", None),
                    self.OpenApi.STATUS: self.OpenApi.Status.BUSY,
                    self.OpenApi.MESSAGE: "Calibration is currently in progress"
                }
                return jsonify(response), 200

            result = self.calibrationContext.calibration_results.get(cameraId)
            if result is None:
                response = {
                    self.OpenApi.CAMERA_ID: cameraId,
                    self.OpenApi.SCENE_ID: getattr(sceneobj, "id", None),
                    self.OpenApi.STATUS: self.OpenApi.Status.NOT_STARTED,
                    self.OpenApi.MESSAGE: "Calibration has not been started for this camera"
                }
                return jsonify(response), 200
            elif result.get("status") == self.OpenApi.Status.CALIBRATING:
                response = {
                    self.OpenApi.CAMERA_ID: cameraId,
                    self.OpenApi.SCENE_ID: getattr(sceneobj, "id", None),
                    self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
                    self.OpenApi.MESSAGE: "Calibration in progress"
                }
                return jsonify(response), 200

            response = {
                self.OpenApi.CAMERA_ID: cameraId,
                self.OpenApi.SCENE_ID: getattr(sceneobj, "id", None),
                self.OpenApi.STATUS: result.get("status", self.OpenApi.Status.ERROR),
                self.OpenApi.MESSAGE: result.get("message", ""),
            }
            if result.get("status") == self.OpenApi.Status.SUCCESS:
                response["pose"] = result.get("pose")
                for key in ("quaternion", "translation", "camera_frustum", "calibration_points_3d", "calibration_points_2d"):
                    if key in result:
                        response[key] = result[key]
            return jsonify(response), 200

    def start(self, port=8000):
        """
        Start the FastAPI server.

        Args:
            port: Port number to listen on (default: 8000)
        """
        log.info(f"Starting REST API server on port {port}")
        threading.Thread(
            target=lambda: self.app.run(
                host='0.0.0.0',
                port=port,
                threaded=True),
            daemon=True).start()
        log.info("REST API server started")
