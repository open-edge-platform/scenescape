# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from flask import Flask, jsonify, request
import threading
import logging
import re
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError

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

    This class provides endpoints for scene registration, camera calibration,
    and status queries, replacing the previous MQTT-based workflow with a
    standards-compliant RESTful interface as defined in the OpenAPI schema.
    """

    API_VERSION = "1.0.0"

    class OpenApi:
        """
        Constants for OpenAPI field names and enumerations.

        These values are derived directly from the OpenAPI schema to ensure
        consistency and reduce errors from hardcoded strings.
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


    def __init__(self, calibrationContext=None):
        """
        Initialize the CameraCalibrationApi REST service.

        Args:
            calibrationContext: The calibration context object providing access
                               to scene and camera calibration logic.
        """
        self.app = Flask(__name__)
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

            # Registration logic
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
                    self.calibrationContext.sceneUpdateThreadWrapperRest(scene, map_update=True)
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
            return jsonify(register_response), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration', methods=['GET'])
        def getSceneRegistrationStatus(sceneId):
            """Get the current registration status of a scene."""
            log.info(f"GET {API_PREFIX}/scenes/{sceneId}/registration called")

            scene = self._getScene(sceneId)
            self._validateSceneForOperation(scene, "queried")
            strategy = self._getCalibrationStrategy(scene)

            # Check registration status logic
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

        @app.route(f'{API_PREFIX}/scenes/<sceneId>', methods=['PATCH'])
        def updateScene(sceneId):
            """Notify the calibration service that a scene has been updated."""
            log.info(f"PATCH {API_PREFIX}/scenes/{sceneId} called")

            scene = self._getScene(sceneId)
            self._validateSceneForOperation(scene, "updated")
            strategy = self._getCalibrationStrategy(scene)

            if strategy.isMapUpdated(scene):
                strategy.resetScene(scene)
                self.calibrationContext.sceneUpdateThreadWrapperRest(scene, map_update=True)
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

            # Parse request body
            data = request.get_json(silent=True)
            if not data or self.OpenApi.IMAGE not in data:
                raise MissingFieldError('image')

            image = data[self.OpenApi.IMAGE]
            intrinsics = data.get(self.OpenApi.INTRINSICS)

            # Get camera intrinsics if not provided
            if intrinsics is None:
                intrinsics = self.calibrationContext.calibration_data_interface.getCameraIntrinsics(cameraId)

            if intrinsics is None:
                raise IntrinsicsNotFoundError(cameraId)

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

            # Check if calibration is busy (lock held)
            if self.calibrationContext.calibration_thread_lock.locked():
                response = {
                    self.OpenApi.CAMERA_ID: cameraId,
                    self.OpenApi.SCENE_ID: getattr(scene, "id", None),
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

            # If calibration is done, return the result (success or error)
            response = {
                self.OpenApi.CAMERA_ID: cameraId,
                self.OpenApi.SCENE_ID: getattr(scene, "id", None),
                self.OpenApi.STATUS: result.get("status", self.OpenApi.Status.ERROR),
                self.OpenApi.MESSAGE: result.get("message", ""),
            }
            # If calibration was successful, include pose and details
            if result.get("status") == self.OpenApi.Status.SUCCESS:
                # Add pose and any other calibration data
                response["pose"] = result.get("pose")
                for key in ("quaternion", "translation", "camera_frustum", "calibration_points_3d", "calibration_points_2d"):
                    if key in result:
                        response[key] = result[key]
            return jsonify(response), 200

    def start(self, port=8000):
        """
        Start the REST API server in a background thread.

        Args:
            port: Port number to listen on (default: 8000).
        """
        log.info(f"Starting REST API server on port {port}")
        threading.Thread(
            target=lambda: self.app.run(
                host='0.0.0.0',
                port=port,
                threaded=True),
            daemon=True).start()
        log.info("REST API server started")