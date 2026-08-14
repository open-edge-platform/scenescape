# API Reference

**Version: v1.0.0**

This API enables automatic camera calibration in Scenescape, supporting both AprilTag and markerless methods.
It also supports sensor-agnostic perceptual sensor calibration, aligning a point cloud from any perceptual
sensor (LiDAR, depth camera, stereo, photogrammetry) to a scene's 3D model.

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

### Perceptual Sensor Localization

- `POST /perceptual-sensors/{sensorId}/localization` — Localize a perceptual sensor by supplying a point cloud (base64-encoded; PCD by default, PLY also accepted) to align against a scene's 3D model and compute the sensor-to-scene transform.
- `GET /perceptual-sensors/{sensorId}/localization` — Get the status and result of perceptual sensor localization, including the 4x4 transform, fitness, and inlier RMSE.

## Schemas

The API uses structured request and response schemas, including:

- `ServiceStatus`
- `SceneRegistrationTriggerResponse`
- `SceneRegistrationStatusResponse`
- `CameraCalibrationRequest`
- `CameraCalibrationTriggerResponse`
- `CameraCalibrationStatusResponse`
- `PerceptualSensorLocalizationRequest`
- `PerceptualSensorLocalizationTriggerResponse`
- `PerceptualSensorLocalizationStatusResponse`
- `Error`

For full schema details and example payloads, see the OpenAPI YAML file below.

---

```{eval-rst}
.. swagger-plugin:: ./_assets/autocalibration-api.yaml
```
