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
        ACTION = "action"

        class Status:
            RUNNING = "running"
            ERROR = "error"
            REGISTERING = "registering"
            BUSY = "busy"
            SUCCESS = "success"
            CALIBRATING = "calibrating"
            RE_REGISTER = "re-register"

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

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration-status',
                   methods=['GET'])
        def getSceneRegistrationStatus(sceneId):
            """
            Get the current registration status of a scene.

            Args:
                sceneId: Unique identifier of the scene.

            Returns:
                JSON response with registration status or error.
            """
            if not self.calibrationContext:
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration context not initialized"}), 500
            # TODO: Implement status lookup logic
            # Probably will not be needed
            return jsonify({
                self.OpenApi.STATUS: self.OpenApi.Status.REGISTERING,
                self.OpenApi.SCENE_ID: sceneId,
                self.OpenApi.SCENE_NAME: "Example Scene",
                self.OpenApi.MESSAGE: "Registration in progress"
            }), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/update', methods=['POST'])
        def updateScene(sceneId):
            """
            Notify the calibration service that a scene has been updated.

            Args:
                sceneId: Unique identifier of the scene.

            Returns:
                JSON response acknowledging the update notification.
            """
            if not self.calibrationContext:
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration context not initialized"}), 500
            # TODO: Implement update logic
            return jsonify(
                {self.OpenApi.MESSAGE: "Update notification received"}), 202

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibrate',
                   methods=['POST'])
        def calibrateCamera(cameraId):
            """
            Trigger calibration for a specific camera.

            Args:
                cameraId: Unique identifier of the camera.

            Returns:
                JSON response indicating calibration status or error.
            """
            if not self.calibrationContext:
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration context not initialized"}), 500
            # TODO: Implement calibration logic
            return jsonify({
                self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
                self.OpenApi.CAMERA_ID: cameraId,
                self.OpenApi.MESSAGE: "Calibration triggered"
            }), 200

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration-status',
                   methods=['GET'])
        def getCameraCalibrationStatus(cameraId):
            """
            Get the current calibration status and result for a camera.

            Args:
                cameraId: Unique identifier of the camera.

            Returns:
                JSON response with calibration status or error.
            """
            if not self.calibrationContext:
                return jsonify(
                    {self.OpenApi.CODE: 500, self.OpenApi.MESSAGE: "Calibration context not initialized"}), 500
            # TODO: Implement status/result lookup logic
            return jsonify({
                self.OpenApi.CAMERA_ID: cameraId,
                self.OpenApi.SCENE_ID: "exampleScene",
                self.OpenApi.STATUS: self.OpenApi.Status.CALIBRATING,
                self.OpenApi.MESSAGE: "Calibration in progress"
            }), 200

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
