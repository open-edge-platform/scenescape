# Auto Camera Calibration API Reference

**Version: v1.0.0**

This API enables automatic camera calibration in Intel® SceneScape, supporting both AprilTag and markerless methods.

**Base URL:** `https://localhost:8443/v1`

## Endpoints

### Service Status

- `GET /status` — Check if the calibration service is running.

### Scene Registration

- `POST /scenes/{sceneId}/registration` — Register a scene for calibration processing.
- `GET /scenes/{sceneId}/registration` — Get the status of scene registration.
- `PATCH /scenes/{sceneId}/registration` — Notify the service that a scene has been updated and needs re-processing.

### Camera Calibration

- `POST /cameras/{cameraId}/calibration` — Start camera calibration by uploading an image and (optionally) camera intrinsics.
- `GET /cameras/{cameraId}/calibration` — Get the status and result of camera calibration, including pose and calibration data.

## Schemas

The API uses structured request and response schemas, including:

- `ServiceStatus`
- `SceneRegistrationTriggerResponse`
- `SceneRegistrationStatusResponse`
- `CameraCalibrationRequest`
- `CameraCalibrationTriggerResponse`
- `CameraCalibrationStatusResponse`
- `Error`

For full schema details and example payloads, see the OpenAPI YAML file below.

---

```{eval-rst}
.. swagger-plugin:: api-docs/autocalibration-api.yaml
```
