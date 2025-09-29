# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
import uvicorn
import ssl

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camcalibration-fastapi")

# Pydantic models for request/response validation
class StatusResponse(BaseModel):
    status: str
    version: str

class SceneRegistrationResponse(BaseModel):
    status: str
    sceneId: str
    message: Optional[str] = None

class CalibrationResponse(BaseModel):
    cameraId: str
    sceneId: Optional[str] = None
    status: str
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
            SUCCESS = "success"

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
        self._register_routes()

    def _register_routes(self):
        """Register all REST API endpoints."""
        app = self.app

        @app.get("/v1/status", response_model=StatusResponse, tags=["Service"])
        async def service_status():
            """Get the current status and version of the calibration service."""
            if not self.calibrationContext:
                return StatusResponse(
                    status=self.OpenApi.Status.ERROR,
                    version=self.API_VERSION
                )

            return StatusResponse(
                status=self.OpenApi.Status.RUNNING,
                version=self.API_VERSION
            )

        @app.post("/v1/scenes/{scene_id}/registration", response_model=SceneRegistrationResponse, tags=["Scene"])
        async def register_scene(scene_id: str):
            """Register a scene for calibration processing."""
            log.info(f"POST /v1/scenes/{scene_id}/registration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(scene_id)
            if not scene:
                log.warning(f"Scene not found: {scene_id}")
                raise HTTPException(status_code=404, detail="Scene not found")

            if scene.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be registered: {scene_id}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes cannot be registered")

            # Registration logic
            if self.calibrationContext.scene_strategies[scene.camera_calibration].isMapUpdated(scene):
                log.info(f"Scene map updated for {scene_id}")
                if self.calibrationContext.register_thread_lock.locked():
                    log.info(f"Registration busy for {scene_id}")
                    return SceneRegistrationResponse(
                        status=self.OpenApi.Status.BUSY,
                        sceneId=scene_id,
                        message="Registration is currently busy"
                    )
                else:
                    log.info(f"Registration triggered for {scene_id}")
                    self.calibrationContext.sceneUpdateThreadWrapperRest(scene, map_update=True)
                    return SceneRegistrationResponse(
                        status=self.OpenApi.Status.REGISTERING,
                        sceneId=scene_id,
                        message="Registration started"
                    )
            else:
                log.info(f"Processing scene for calibration: {scene_id}")
                result = self.calibrationContext.scene_strategies[scene.camera_calibration].processSceneForCalibration(scene)
                result_status = result.get(self.OpenApi.STATUS, self.OpenApi.Status.ERROR) if result else self.OpenApi.Status.ERROR

                if result_status == self.OpenApi.Status.SUCCESS:
                    return SceneRegistrationResponse(
                        status=self.OpenApi.Status.SUCCESS,
                        sceneId=scene_id
                    )
                else:
                    return SceneRegistrationResponse(
                        status=self.OpenApi.Status.ERROR,
                        sceneId=scene_id,
                        message=result.get(self.OpenApi.MESSAGE, result_status) if result else result_status
                    )

        @app.get("/v1/scenes/{scene_id}/registration", response_model=SceneRegistrationResponse, tags=["Scene"])
        async def get_scene_registration_status(scene_id: str):
            """Get the current registration status of a scene."""
            log.info(f"GET /v1/scenes/{scene_id}/registration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(scene_id)
            if not scene:
                log.warning(f"Scene not found: {scene_id}")
                raise HTTPException(status_code=404, detail="Scene not found")

            if scene.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be queried: {scene_id}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes do not support registration status")

            # Check registration status logic
            strategy = self.calibrationContext.scene_strategies[scene.camera_calibration]
            if strategy.isMapUpdated(scene):
                if self.calibrationContext.register_thread_lock.locked():
                    status_val = self.OpenApi.Status.BUSY
                    message = "Registration is currently busy"
                else:
                    status_val = self.OpenApi.Status.REGISTERING
                    message = "Registration is in progress"
            else:
                status_val = self.OpenApi.Status.SUCCESS
                message = "Registration is complete"

            return SceneRegistrationResponse(
                status=status_val,
                sceneId=scene_id,
                message=message
            )

        @app.patch("/v1/scenes/{scene_id}", tags=["Scene"])
        async def update_scene(scene_id: str):
            """Notify the calibration service that a scene has been updated."""
            log.info(f"PATCH /v1/scenes/{scene_id} called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            sceneobj = self.calibrationContext.calibration_data_interface.sceneWithID(scene_id)
            if not sceneobj:
                log.warning(f"Scene not found: {scene_id}")
                raise HTTPException(status_code=404, detail="Scene not found")

            if sceneobj.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be updated: {scene_id}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes cannot be updated")

            strategy = self.calibrationContext.scene_strategies.get(sceneobj.camera_calibration)
            if not strategy:
                log.error(f"Calibration strategy not found for scene {scene_id}")
                raise HTTPException(status_code=500, detail="Calibration strategy not found")

            if strategy.isMapUpdated(sceneobj):
                strategy.resetScene(sceneobj)
                self.calibrationContext.sceneUpdateThreadWrapperRest(sceneobj, map_update=True)
                log.info(f"Scene update triggered for {scene_id}")
                return JSONResponse(status_code=202, content={"message": "Scene update triggered"})
            else:
                log.info(f"No update needed for scene {scene_id}")
                return JSONResponse(status_code=200, content={"message": "No update needed"})

        @app.post("/v1/cameras/{camera_id}/calibration", response_model=CalibrationResponse, tags=["Camera"])
        async def calibrate_camera(camera_id: str):
            """Trigger calibration for a specific camera."""
            log.info(f"POST /v1/cameras/{camera_id}/calibration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            # Find the scene object
            sceneobj = self.calibrationContext.calibration_data_interface.sceneCameraWithID(camera_id)
            if not sceneobj:
                log.warning(f"Camera not found: {camera_id}")
                raise HTTPException(status_code=404, detail="Camera not found")

            if sceneobj.camera_calibration == "Manual":
                log.warning(f"Manual calibration camera cannot be calibrated: {camera_id}")
                raise HTTPException(status_code=400, detail="Manual calibration cameras cannot be auto-calibrated")

            # Check if calibration is already in progress
            if self.calibrationContext.calibration_thread_lock.locked():
                log.info(f"Calibration busy for camera {camera_id}")
                return CalibrationResponse(
                    cameraId=camera_id,
                    sceneId=getattr(sceneobj, "id", None),
                    status=self.OpenApi.Status.BUSY,
                    message="Calibration is currently in progress"
                )

            # Start calibration
            self.calibrationContext.calibrateThreadWrapperRest(camera_id, sceneobj)
            log.info(f"Calibration started for camera {camera_id}")

            return CalibrationResponse(
                cameraId=camera_id,
                sceneId=getattr(sceneobj, "id", None),
                status=self.OpenApi.Status.CALIBRATING,
                message="Calibration started"
            )

        @app.get("/v1/cameras/{camera_id}/calibration", response_model=CalibrationResponse, tags=["Camera"])
        async def get_camera_calibration_status(camera_id: str):
            """Get the current calibration status of a camera."""
            log.info(f"GET /v1/cameras/{camera_id}/calibration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            sceneobj = self.calibrationContext.calibration_data_interface.sceneCameraWithID(camera_id)
            if not sceneobj:
                log.warning(f"Camera not found: {camera_id}")
                raise HTTPException(status_code=404, detail="Camera not found")

            # Check if calibration is currently in progress
            if self.calibrationContext.calibration_thread_lock.locked():
                return CalibrationResponse(
                    cameraId=camera_id,
                    sceneId=getattr(sceneobj, "id", None),
                    status=self.OpenApi.Status.BUSY,
                    message="Calibration is currently in progress"
                )

            # Get calibration result from context
            result = self.calibrationContext.calibration_results.get(camera_id)
            if result is None:
                return CalibrationResponse(
                    cameraId=camera_id,
                    sceneId=getattr(sceneobj, "id", None),
                    status=self.OpenApi.Status.NOT_STARTED,
                    message="Calibration has not been started for this camera"
                )
            elif result.get("status") == self.OpenApi.Status.CALIBRATING:
                return CalibrationResponse(
                    cameraId=camera_id,
                    sceneId=getattr(sceneobj, "id", None),
                    status=self.OpenApi.Status.CALIBRATING,
                    message="Calibration in progress"
                )

            # If calibration is done, return the result (success or error)
            response_data = CalibrationResponse(
                cameraId=camera_id,
                sceneId=getattr(sceneobj, "id", None),
                status=result.get("status", self.OpenApi.Status.ERROR),
                message=result.get("message", "")
            )

            # If calibration was successful, include pose and details
            if result.get("status") == self.OpenApi.Status.SUCCESS:
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
        self.start_with_tls(port=port)
