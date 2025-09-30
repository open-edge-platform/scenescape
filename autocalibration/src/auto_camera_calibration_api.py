# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import ssl
from typing import Optional, Dict, Any, List
from enum import Enum
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
import uvicorn

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camcalibration-fastapi")

# Enums for status values to match OpenAPI spec
class ServiceStatus(str, Enum):
    RUNNING = "running"
    ERROR = "error"

class RegistrationTriggerStatus(str, Enum):
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
    intrinsics: Optional[Dict[str, Any]] = Field(None, description="Camera intrinsics (optional)")

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
        self._register_exception_handlers()
        self._register_routes()

    def _register_exception_handlers(self):
        """Register custom exception handlers to match OpenAPI spec error format."""

        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(request: Request, exc: HTTPException):
            """Handle HTTPException to return OpenAPI spec compliant error format."""
            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(code=exc.status_code, message=exc.detail).model_dump()
            )

        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            """Handle validation errors to return OpenAPI spec compliant error format."""
            return JSONResponse(
                status_code=400,
                content=ErrorResponse(code=400, message="Invalid request data").model_dump()
            )

    def _register_routes(self):
        """Register all REST API endpoints."""
        app = self.app

        @app.get("/v1/status", response_model=StatusResponse, tags=["Service"])
        async def service_status():
            """Get the current status and version of the calibration service."""
            if not self.calibrationContext:
                return StatusResponse(
                    status=ServiceStatus.ERROR,
                    version=self.API_VERSION
                )

            return StatusResponse(
                status=ServiceStatus.RUNNING,
                version=self.API_VERSION
            )

        @app.post("/v1/scenes/{sceneId}/registration", response_model=SceneRegistrationTriggerResponse, tags=["Scene"])
        async def register_scene(sceneId: str):
            """Register a scene for calibration processing."""
            log.info(f"POST /v1/scenes/{sceneId}/registration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(sceneId)
            if not scene:
                log.warning(f"Scene not found: {sceneId}")
                raise HTTPException(status_code=404, detail="Scene not found")

            if scene.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be registered: {sceneId}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes cannot be registered")

            # Registration logic
            if self.calibrationContext.scene_strategies[scene.camera_calibration].isMapUpdated(scene):
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
                    self.calibrationContext.sceneUpdateThreadWrapperRest(scene, map_update=True)
                    return SceneRegistrationTriggerResponse(
                        status=RegistrationTriggerStatus.REGISTERING,
                        sceneId=sceneId,
                        message="Registration started"
                    )
            else:
                log.info(f"Processing scene for calibration: {sceneId}")
                result = self.calibrationContext.scene_strategies[scene.camera_calibration].processSceneForCalibration(scene)
                result_status = result.get(self.OpenApi.STATUS, self.OpenApi.Status.ERROR) if result else self.OpenApi.Status.ERROR

                if result_status == self.OpenApi.Status.SUCCESS:
                    return SceneRegistrationTriggerResponse(
                        status=RegistrationTriggerStatus.REGISTERING,
                        sceneId=sceneId
                    )
                else:
                    return SceneRegistrationTriggerResponse(
                        status=RegistrationTriggerStatus.ERROR,
                        sceneId=sceneId,
                        message=result.get(self.OpenApi.MESSAGE, result_status) if result else result_status
                    )

        @app.get("/v1/scenes/{sceneId}/registration", response_model=SceneRegistrationStatusResponse, tags=["Scene"])
        async def get_scene_registration_status(sceneId: str):
            """Get the current registration status of a scene."""
            log.info(f"GET /v1/scenes/{sceneId}/registration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            scene = self.calibrationContext.calibration_data_interface.sceneWithID(sceneId)
            if not scene:
                log.warning(f"Scene not found: {sceneId}")
                raise HTTPException(status_code=404, detail="Scene not found")

            if scene.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be queried: {sceneId}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes do not support registration status")

            # Check registration status logic
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

        @app.patch("/v1/scenes/{sceneId}", response_model=SceneUpdateResponse, tags=["Scene"])
        async def update_scene(sceneId: str):
            """Notify the calibration service that a scene has been updated."""
            log.info(f"PATCH /v1/scenes/{sceneId} called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            sceneobj = self.calibrationContext.calibration_data_interface.sceneWithID(sceneId)
            if not sceneobj:
                log.warning(f"Scene not found: {sceneId}")
                raise HTTPException(status_code=404, detail="Scene not found")

            if sceneobj.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be updated: {sceneId}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes cannot be updated")

            strategy = self.calibrationContext.scene_strategies.get(sceneobj.camera_calibration)
            if not strategy:
                log.error(f"Calibration strategy not found for scene {sceneId}")
                raise HTTPException(status_code=500, detail="Calibration strategy not found")

            if strategy.isMapUpdated(sceneobj):
                strategy.resetScene(sceneobj)
                self.calibrationContext.sceneUpdateThreadWrapperRest(sceneobj, map_update=True)
                log.info(f"Scene update triggered for {sceneId}")
                return SceneUpdateResponse(message="Scene update triggered")
            else:
                log.info(f"No update needed for scene {sceneId}")
                return SceneUpdateResponse(message="No update needed")

        @app.post("/v1/cameras/{cameraId}/calibration", response_model=CalibrationTriggerResponse, tags=["Camera"])
        async def calibrate_camera(cameraId: str, request: CalibrationRequest):
            """Trigger calibration for a specific camera."""
            log.info(f"POST /v1/cameras/{cameraId}/calibration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            # Find the scene object
            sceneobj = self.calibrationContext.calibration_data_interface.sceneCameraWithID(cameraId)
            if not sceneobj:
                log.warning(f"Camera or scene not found. Camera provided: {cameraId}")
                raise HTTPException(status_code=404, detail="Camera or scene not found")

            # Validate required image field
            if not request.image:
                log.warning(f"Missing required field 'image' in calibration request for camera {cameraId}")
                raise HTTPException(status_code=400, detail="Missing required field: image")

            image = request.image
            intrinsics = request.intrinsics

            # Get camera intrinsics if not provided
            if intrinsics is None:
                intrinsics = self.calibrationContext.calibration_data_interface.getCameraIntrinsics(cameraId)

            if intrinsics is None:
                log.error(f"Intrinsics not found for camera {cameraId}")
                raise HTTPException(status_code=400, detail=f"Intrinsics not found for camera {cameraId}")

            # Find calibration strategy
            strategy = self.calibrationContext.scene_strategies.get(sceneobj.camera_calibration)
            if not strategy:
                log.error(f"Calibration strategy not found for scene {getattr(sceneobj, 'id', None)}")
                raise HTTPException(status_code=500, detail="Calibration strategy not found")

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
                return CalibrationTriggerResponse(
                    status=CalibrationStatus.CALIBRATING,
                    cameraId=cameraId,
                    message="Calibration started"
                )
            except Exception as e:
                log.error(f"Calibration failed for camera {cameraId}: {e}")
                raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")

        @app.get("/v1/cameras/{cameraId}/calibration", response_model=CalibrationStatusResponse, tags=["Camera"])
        async def get_camera_calibration_status(cameraId: str):
            """Get the current calibration status and result for a camera."""
            log.info(f"GET /v1/cameras/{cameraId}/calibration called")

            if not self.calibrationContext:
                log.error("Calibration context not initialized")
                raise HTTPException(status_code=500, detail="Calibration context not initialized")

            # Find the scene object for this camera
            sceneobj = self.calibrationContext.calibration_data_interface.sceneCameraWithID(cameraId)
            if not sceneobj:
                log.warning(f"Camera or scene not found. Camera provided: {cameraId}")
                raise HTTPException(status_code=404, detail="Camera or scene not found")

            # Manual calibration scenes do not support status
            if sceneobj.camera_calibration == "Manual":
                log.warning(f"Manual calibration scene cannot be queried: {cameraId}")
                raise HTTPException(status_code=400, detail="Manual calibration scenes do not support calibration status")

            # Check if calibration is busy (lock held)
            if self.calibrationContext.calibration_thread_lock.locked():
                return CalibrationStatusResponse(
                    cameraId=cameraId,
                    sceneId=getattr(sceneobj, "id", None),
                    status=CalibrationStatus.BUSY,
                    message="Calibration is currently in progress"
                )

            # Get calibration result from context
            result = self.calibrationContext.calibration_results.get(cameraId)
            if result is None:
                # Calibration has never been started for this camera
                return CalibrationStatusResponse(
                    cameraId=cameraId,
                    sceneId=getattr(sceneobj, "id", None),
                    status=CalibrationStatus.NOT_STARTED,
                    message="Calibration has not been started for this camera"
                )
            elif result.get("status") == self.OpenApi.Status.CALIBRATING:
                return CalibrationStatusResponse(
                    cameraId=cameraId,
                    sceneId=getattr(sceneobj, "id", None),
                    status=CalibrationStatus.CALIBRATING,
                    message="Calibration in progress"
                )

            # If calibration is done, return the result (success or error)
            result_status = result.get("status", self.OpenApi.Status.ERROR)
            if result_status == self.OpenApi.Status.SUCCESS:
                status = CalibrationStatus.SUCCESS
            elif result_status == self.OpenApi.Status.ERROR:
                status = CalibrationStatus.ERROR
            else:
                status = CalibrationStatus.ERROR

            response_data = CalibrationStatusResponse(
                cameraId=cameraId,
                sceneId=getattr(sceneobj, "id", None),
                status=status,
                message=result.get("message", "")
            )

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
        self.start_with_tls(port=port)
