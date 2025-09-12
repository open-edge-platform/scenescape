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

        @app.route('/status', methods=['GET'])
        def serviceStatus():
            if not self.calibrationContext:
                return jsonify({"status": "error", "version": self.API_VERSION}), 200
            return jsonify({"status": "running", "version": self.API_VERSION}), 200

        @app.route('/scenes/<sceneId>/register', methods=['POST'])
        def registerScene(sceneId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement registration logic
            return jsonify({"status": "registering", "sceneId": sceneId, "message": "Registration triggered"}), 200

        @app.route('/scenes/<sceneId>/registration-status', methods=['GET'])
        def getSceneRegistrationStatus(sceneId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement status lookup logic
            return jsonify({"status": "registering", "sceneId": sceneId, "sceneName": "Example Scene", "message": "Registration in progress"}), 200

        @app.route('/scenes/<sceneId>/update', methods=['POST'])
        def updateScene(sceneId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement update logic
            return jsonify({"message": "Update notification received"}), 202

        @app.route('/cameras/<cameraId>/calibrate', methods=['POST'])
        def calibrateCamera(cameraId):
            if not self.calibrationContext:
                return jsonify({"code": 500, "message": "Calibration context not initialized"}), 500
            # TODO: Implement calibration logic
            return jsonify({"status": "calibrating", "cameraId": cameraId, "message": "Calibration triggered"}), 200

        @app.route('/cameras/<cameraId>/calibration-status', methods=['GET'])
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
