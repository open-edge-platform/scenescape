# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from flask import Flask, jsonify, request
import threading
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camcalibration-rest")

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
        SCENE_NAME = "sceneName"
        IMAGE = "image"
        INTRINSICS = "intrinsics"
        ACTION = "action"

        class Status:
            BUSY = "busy"
            CALIBRATING = "calibrating"
            ERROR = "error"
            NOT_STARTED = "not_started"
            REGISTERING = "registering"
            RE_REGISTER = "re-register"
            RUNNING = "running"
            SUCCESS = "success"

        class Action:
            UPDATED = "updated"
            DELETED = "deleted"
            CREATED = "created"

    def __init__(self, calibrationContext=None):
        """
        Initialize the CameraCalibrationApi REST service.

        Args:
            calibrationContext: The calibration context object providing access
                               to scene and camera calibration logic.
        """
        self.app = Flask(__name__)
        self.calibrationContext = calibrationContext
        self._registerRoutes()

    def _registerRoutes(self):
        """
        Register all REST API endpoints for camera calibration.

        Endpoints:
            - /v1/status: Service health and version.
            - /v1/scenes/<sceneId>/register: Register a scene for calibration.
            - /v1/scenes/<sceneId>/registration-status: Query scene registration status.
            - /v1/scenes/<sceneId>/update: Notify service of scene updates.
            - /v1/cameras/<cameraId>/calibrate: Trigger camera calibration.
            - /v1/cameras/<cameraId>/calibration-status: Query camera calibration status.
        """
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
                return jsonify({
                    self.OpenApi.STATUS: self.OpenApi.Status.ERROR,
                    self.OpenApi.VERSION: self.API_VERSION
                }), 200

            return jsonify({
                self.OpenApi.STATUS: self.OpenApi.Status.RUNNING,
                self.OpenApi.VERSION: self.API_VERSION
            }), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/register', methods=['POST'])
        def registerScene(sceneId):
            """
            Register a scene for calibration processing.

            Args:
                sceneId: Unique identifier of the scene.

            Returns:
                JSON response indicating registration status or error.
            """
            log.info(f"POST {API_PREFIX}/scenes/{sceneId}/register called")
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

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration-status', methods=['GET'])
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

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/update', methods=['POST'])
        def updateScene(sceneId):
            """
            Notify the calibration service that a scene has been updated.

            Args:
                sceneId: Unique identifier of the scene.

            Returns:
                JSON response acknowledging the update notification.
            """
            log.info(f"POST {API_PREFIX}/scenes/{sceneId}/update called")
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

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibrate', methods=['POST'])
        def calibrateCamera(cameraId):
            """
            Trigger calibration for a specific camera.

            Args:
                cameraId: Unique identifier of the camera.

            Returns:
                JSON response indicating calibration status or error.
            """
            log.info(f"POST {API_PREFIX}/cameras/{cameraId}/calibrate called")
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
                    sceneobj, cameraId, intrinsics, cam_frame_data
                )
                return jsonify({
                    self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
                    self.OpenApi.CAMERA_ID: cameraId,
                    self.OpenApi.MESSAGE: "Calibration started"
                }), 202
            except Exception as e:
                log.error(f"Calibration failed for camera {cameraId}: {e}")
                return jsonify({
                    self.OpenApi.CODE: 500,
                    self.OpenApi.MESSAGE: f"Calibration failed: {str(e)}"
                }), 500

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration-status', methods=['GET'])
        def getCameraCalibrationStatus(cameraId):
            """
            Get the current calibration status and result for a camera.

            Args:
                cameraId: Unique identifier of the camera.

            Returns:
                JSON response with calibration status, pose, or error.
            """
            log.info(f"GET {API_PREFIX}/cameras/{cameraId}/calibration-status called")
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
