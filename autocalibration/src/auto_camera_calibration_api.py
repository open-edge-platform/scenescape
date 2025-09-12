# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from flask import Flask, jsonify, request
import threading
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camcalibration-rest")

class CameraCalibrationApi:
    API_VERSION = "1.0.0"

    def __init__(self, calibrationContext=None):
        self.app = Flask(__name__)
        self.calibrationContext = calibrationContext
        self._registerRoutes()

    def _registerRoutes(self):
        app = self.app

        API_PREFIX = "/v1"

        @app.route(f'{API_PREFIX}/status', methods=['GET'])
        def serviceStatus():
            if not self.calibrationContext:
                return jsonify({"status": "error", "version": self.API_VERSION}), 200
            return jsonify({"status": "running", "version": self.API_VERSION}), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/register', methods=['POST'])
        def registerScene(sceneId):
            log.info(f"POST {API_PREFIX}/scenes/{sceneId}/register called")
            # Error: Internal server error
            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                return jsonify({
                    "code": 500,
                    "message": "Calibration context not initialized"
                }), 500

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(sceneId)
            # Error: Scene not found
            if not scene:
                log.warning(f"Scene not found: {sceneId}")
                return jsonify({
                    "code": 404,
                    "message": "Scene not found"
                }), 404

            # Error: Invalid scene ID (manual calibration)
            if scene.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be registered: {sceneId}")
                return jsonify({
                    "code": 400,
                    "message": "Manual calibration scenes cannot be registered"
                }), 400

            # Registration logic
            if self.calibrationContext.scene_strategies[scene.camera_calibration].isMapUpdated(scene):
                log.info(f"Scene map updated for {sceneId}")
                if self.calibrationContext.register_thread_lock.locked():
                    log.info(f"Registration busy for {sceneId}")
                    register_response = {
                        "status": "busy",
                        "sceneId": sceneId,
                        "message": "Registration is currently busy"
                    }
                else:
                    log.info(f"Registration triggered for {sceneId}")
                    register_response = {
                        "status": "registering",
                        "sceneId": sceneId,
                        "message": "Registration started"
                    }
                    self.calibrationContext.sceneUpdateThreadWrapperRest(scene, map_update=True)
            else:
                log.info(f"Processing scene for calibration: {sceneId}")
                result = self.calibrationContext.scene_strategies[scene.camera_calibration].processSceneForCalibration(scene)
                register_response = {
                    "status": result.get("status", "error") if result else "error",
                    "sceneId": sceneId,
                    "message": result.get("message", "Unknown error") if result else "Unknown error"
                }

            log.info(f"Returning response for {sceneId}: {register_response}")
            return jsonify(register_response), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/registration-status', methods=['GET'])
        def getSceneRegistrationStatus(sceneId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement status lookup logic
            return jsonify({"status": "registering", "sceneId": sceneId, "sceneName": "Example Scene", "message": "Registration in progress"}), 200

        @app.route(f'{API_PREFIX}/scenes/<sceneId>/update', methods=['POST'])
        def updateScene(sceneId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement update logic
            return jsonify({"message": "Update notification received"}), 202

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibrate', methods=['POST'])
        def calibrateCamera(cameraId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement calibration logic
            return jsonify({"status": "calibrating", "cameraId": cameraId, "message": "Calibration triggered"}), 200

        @app.route(f'{API_PREFIX}/cameras/<cameraId>/calibration-status', methods=['GET'])
        def getCameraCalibrationStatus(cameraId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement status/result lookup logic
            return jsonify({"cameraId": cameraId, "sceneId": "exampleScene", "status": "calibrating", "message": "Calibration in progress"}), 200

    def start(self, port=8000):
        log.info(f"Starting REST API server on port {port}")
        threading.Thread(
            target=lambda: self.app.run(host='0.0.0.0', port=port, threaded=True),
            daemon=True
        ).start()
        log.info("REST API server started")
