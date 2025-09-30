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
    FastAPI-based REST API service for automatic camera calibration in Intel SceneScape.
    """

    API_VERSION = "1.0.0"

    MAX_ID_LENGTH = 255
    MIN_ID_LENGTH = 1
    VALID_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_\.]+$')  # Allow alphanumeric, hyphens, underscores, dots
    MAX_IMAGE_SIZE = 20 * 1024 * 1024
    MAX_REQUEST_SIZE = 25 * 1024 * 1024

    class OpenApi:
        """Constants for OpenAPI field names and enumerations."""
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

    def __init__(self, calibrationContext=None):
        """Initialize the FastAPI application with calibration context."""
        self.app = FastAPI(
            title="Camera Calibration API",
            description="REST API service for automatic camera calibration in Intel SceneScape",
            version=self.API_VERSION,
            docs_url="/v1/docs",
            redoc_url="/v1/redoc",
            openapi_url="/v1/openapi.json"
        )
        self.calibrationContext = calibrationContext
        self._registerErrorHandlers()
        self._registerRoutes()

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

            # Registration logic
            if self.calibrationContext.scene_strategies[scene.camera_calibration].isMapUpdated(
                    scene):
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

            Returns:
                JSON response with registration status or error.
            """
            log.info(f"GET {API_PREFIX}/scenes/{sceneId}/registration-status called")
            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                return jsonify({
                    self.OpenApi.CODE: 500,
                    self.OpenApi.MESSAGE: "Calibration context not initialized"
                }), 500

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(sceneId)
            if not scene:
                log.warning(f"Scene not found: {sceneId}")
                return jsonify({
                    self.OpenApi.CODE: 404,
                    self.OpenApi.MESSAGE: "Scene not found"
                }), 404

            if scene.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be queried: {sceneId}")
                return jsonify({
                    self.OpenApi.CODE: 400,
                    self.OpenApi.MESSAGE: "Manual calibration scenes do not support registration status"
                }), 400

            # Check registration status logic (re-used from registerScene, but no processing)
            strategy = self.calibrationContext.scene_strategies[scene.camera_calibration]
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

            # Parse request body
            data = request.get_json(silent=True)
            if not data or self.OpenApi.IMAGE not in data:
                log.warning(f"Missing required field 'image' in calibration request for camera {cameraId}")
                return jsonify({
                    self.OpenApi.CODE: 400,
                    self.OpenApi.MESSAGE: "Missing required field: image"
                }), 400

            image = data[self.OpenApi.IMAGE]
            intrinsics = data.get(self.OpenApi.INTRINSICS)  # Optional

            # Get camera intrinsics if not provided
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

            # Prepare cam_frame_data
            cam_frame_data = {
                "image": image,
                "id": cameraId
            }

            # Start calibration in background
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

            # Check if calibration is busy (lock held)
            if self.calibrationContext.calibration_thread_lock.locked():
                response = {
                    self.OpenApi.CAMERA_ID: cameraId,
                    self.OpenApi.SCENE_ID: getattr(sceneobj, "id", None),
                    self.OpenApi.STATUS: self.OpenApi.Status.BUSY,
                    self.OpenApi.MESSAGE: "Calibration is currently in progress"
                }
                return jsonify(response), 200

            # Get calibration result from context
            result = self.calibrationContext.calibration_results.get(cameraId)
            if result is None:
                # Calibration has never been started for this camera
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

            # If calibration is done, return the result (success or error)
            response = {
                self.OpenApi.CAMERA_ID: cameraId,
                self.OpenApi.SCENE_ID: getattr(sceneobj, "id", None),
                self.OpenApi.STATUS: result.get("status", self.OpenApi.Status.ERROR),
                self.OpenApi.MESSAGE: result.get("message", ""),
            }
            # If calibration was successful, include pose and details
            if status == CalibrationStatus.SUCCESS:
                response_data.pose = result.get("pose")
                response_data.quaternion = result.get("quaternion")
                response_data.translation = result.get("translation")
                response_data.camera_frustum = result.get("camera_frustum")
                response_data.calibration_points_3d = result.get("calibration_points_3d")
                response_data.calibration_points_2d = result.get("calibration_points_2d")

            return response_data

    def start_with_tls(self, port=8000, certfile=None, keyfile=None, ca_certs=None):
        """
        Start the FastAPI server with native TLS support.

        Args:
            port: Port number to listen on (default: 8000)
            certfile: Path to SSL certificate file
            keyfile: Path to SSL private key file
            ca_certs: Path to CA certificate file (optional)
        """
        if certfile and keyfile:
            log.info(f"Starting FastAPI server with TLS on port {port}")
            uvicorn.run(
                self.app,
                host="0.0.0.0",
                port=port,
                ssl_keyfile=keyfile,
                ssl_certfile=certfile,
                ssl_ca_certs=ca_certs,
                ssl_version=ssl.PROTOCOL_TLS_SERVER,
                log_level="info"
            )
        else:
            log.info(f"Starting FastAPI server without TLS on port {port}")
            uvicorn.run(
                self.app,
                host="0.0.0.0",
                port=port,
                log_level="info"
            )

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
