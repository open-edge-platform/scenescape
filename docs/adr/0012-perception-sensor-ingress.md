<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 12: Perception Sensor Ingress — Modality-Specific Topics and Strategy-Based Handlers

- **Author(s)**: [spoluri](https://github.com/spoluri)
- **Date**: 2026-06-10
- **Status**: `Proposed`

## TLDR

Replace the current practice of modeling all perception sensors (lidar, radar, thermal, etc.) as
cameras with explicit modality-specific MQTT topics and a plugin/strategy-based handler registry.
Each modality publishes on its own topic namespace (e.g. `scenescape/data/lidar/+`) using a shared
detection envelope schema. New modalities are added by registering a strategy, not by branching
existing code.

## Context

SceneScape currently ingests all spatial detection data through a single camera-shaped path:

- MQTT topic: `scenescape/data/camera/{camera_id}`
- Manager model: `Cam` with `intrinsics_fx/fy/cx/cy` and `distortion_k*` fields
- Tracker ingress schema: `camera-data.schema.json` with `bounding_box_px` required per detection
- Projection math: `CoordinateTransformer` (C++) and `CameraIntrinsics` + `CameraPose` (Python)
  both assume a pinhole camera model
- UI: `SceneCamera` renders a `THREE.PerspectiveCamera` frustum, exposes FOV/intrinsics controls,
  and links to the autocalibration image flow for all sensors

Adding a lidar by masquerading it as a camera creates several concrete problems:

1. **Wrong calibration contract.** `Cam.save()` auto-fills `DEFAULT_INTRINSICS`
   (`fx=570, fy=570, cx=320, cy=240`) when fields are absent, silently making a lidar's
   geometry appear valid to downstream consumers that never read its detections correctly.
2. **Projection math mismatch.** `CoordinateTransformer` requires a pinhole `K` matrix and calls
   `cv::undistortPoints` before ray-plane intersection. Lidar detections that arrive pre-projected
   in metric 3D bypass this, but the code path always runs the camera model unless
   `"intrinsics" in jdata` is detected—a fragile special-case guard in
   `controller/src/controller/scene.py`.
3. **Misleading topic semantics.** A lidar publishing on `scenescape/data/camera/lidar-front`
   confuses operators, access-control policies, and any subscriber that treats the topic as an
   authoritative signal about what kind of sensor produced the data.
4. **Camera-centric UX everywhere.** The UI shows a camera frustum for every sensor, the
   calibration flow asks for image point correspondences, and the control panel exposes FOV/
   intrinsics fields that are meaningless for lidar or radar.
5. **No OCP extension point.** Adding radar or thermal requires editing the core message handler,
   the scene loader, the controller's `processCameraData`, and the Manager model, instead of
   registering a new strategy.
6. **Discrete event sensors conflated with perceptual sensors.** Temperature readers, badge
   scanners, and weight scales are already handled separately via `SingletonSensor`, but
   the split is not formalized into a documented boundary.

## Decision

### 1. Explicit modality-specific MQTT topic namespaces

| Modality         | Ingress topic                         | Raw/preview topic                      |
| ---------------- | ------------------------------------- | -------------------------------------- |
| Camera (optical) | `scenescape/data/camera/{sensor_id}`  | `scenescape/image/camera/{sensor_id}`  |
| Lidar            | `scenescape/data/lidar/{sensor_id}`   | `scenescape/raw/lidar/{sensor_id}`     |
| Radar            | `scenescape/data/radar/{sensor_id}`   | `scenescape/raw/radar/{sensor_id}`     |
| Thermal          | `scenescape/data/thermal/{sensor_id}` | `scenescape/image/thermal/{sensor_id}` |
| Discrete event   | `scenescape/data/sensor/{sensor_id}`  | _(unchanged, already exists)_          |

Existing camera topics are preserved unchanged for backward compatibility. No message is silently
re-routed; publishers choose their own topic at pipeline configuration time.

### 2. Shared detection envelope schema

All perceptual sensor topics share a common JSON envelope:

```json
{
  "id": "<sensor_id>",
  "timestamp": "<ISO8601>",
  "modality": "camera | lidar | radar | thermal",
  "objects": {
    "<category>": [
      {
        "category": "<string>",
        "bounding_box_px": { "x": 0, "y": 0, "width": 0, "height": 0 },
        "translation": [x, y, z],
        "size": [l, w, h],
        "rotation": [x, y, z, w],
        "confidence": 0.0
      }
    ]
  }
}
```

Each detection satisfies **one** of: `bounding_box_px` (camera/thermal pixel detections),
`translation + size` (pre-projected metric 3D detections from lidar/radar), or
`bounding_box_3D` (sensor-native 3D box, to be projected by the handler). The schema uses
`oneOf` to enforce this, matching the existing controller schema contract.

### 3. Plugin/strategy registry (Open/Closed Principle)

A `PerceptualSensorStrategy` interface carries three responsibilities:

- **parse(payload) → DetectionBatch** — validate and decode the raw MQTT payload
- **project(batch, sensor_config) → WorldDetections** — convert sensor-space detections to scene
  world coordinates using the appropriate projection model
- **calibration_schema() → JSONSchema** — return the schema for this modality's calibration
  parameters, used by the Manager API and UI

Built-in strategies shipped with this change:

| Strategy         | Topic           | Projection model                                                                                      |
| ---------------- | --------------- | ----------------------------------------------------------------------------------------------------- |
| `CameraStrategy` | `data/camera/+` | Pinhole `K` matrix + `cv::undistortPoints` + ray-plane intersection (current `CoordinateTransformer`) |
| `LidarStrategy`  | `data/lidar/+`  | Identity pass-through for metric 3D; optional range-image projection for 2D bboxes                    |
| `RadarStrategy`  | `data/radar/+`  | Polar-to-Cartesian conversion from heatmap or range-doppler detections                                |

The registry maps topic prefix → strategy instance. Adding a new modality means creating a new
strategy class and registering it—no changes to the message handler, controller, or tracker core.

### 4. Calibration inputs by modality

| Modality | Required calibration                                      | Optional                                            |
| -------- | --------------------------------------------------------- | --------------------------------------------------- |
| Camera   | `intrinsics` (fx, fy, cx, cy), `distortion`, `extrinsics` | —                                                   |
| Lidar    | `extrinsics` (translation, rotation, scale)               | Beam model for 2D bbox projection                   |
| Radar    | `extrinsics`                                              | Azimuth/elevation resolution for heatmap projection |
| Thermal  | Same as camera                                            | —                                                   |

The Manager `Cam` model's `DEFAULT_INTRINSICS` auto-fill behavior is gated behind a
`modality == "camera"` check. Non-camera sensors that omit intrinsics do not receive defaults.

### 5. Migration compatibility

- Existing `scenescape/data/camera/+` subscriptions and publishers continue to work unchanged.
- The `Cam` database model is extended with a `modality` field (default `"camera"`) rather than
  replaced; all existing rows remain valid.
- The UI adds a modality selector on new sensor creation; existing sensors render with
  `modality = "camera"` and see no UX change.
- The camera compatibility path is explicitly marked deprecated in docs, to be removed after one
  major release once all known publishers have migrated.

## Alternatives Considered

- **Single generic topic `scenescape/data/perceptual_sensor/+`** — Rejected. Hides modality
  identity in payload; forces every subscriber to inspect the body before knowing what it received.
  Preserves the camera-first mental model in a different location.
- **Keep everything as camera** — Rejected. Leaks camera assumptions (intrinsics defaults, pixel
  bbox, pinhole projection, FOV UI) into semantically wrong places. Blocks OCP-compliant extension.
- **One topic per sensor instance with modality in payload** — Rejected. Operators cannot write
  broker ACLs or MQTT subscriptions scoped to a modality; modality becomes an unenforceable
  convention rather than a structural boundary.

## Consequences

### Positive

- Transport boundary is semantically honest: `data/lidar/+` means lidar.
- New modalities require no changes to core controller, tracker, or manager code.
- Calibration requirements are modality-appropriate; no spurious intrinsics defaults.
- UI, docs, and ACLs can be modality-aware without payload inspection.
- Existing camera deployments continue working with no migration work.

### Negative

- More distinct topic namespaces (4 instead of 1) adds surface area in broker ACL configs.
- The strategy registry and shared envelope schema are new infrastructure that must be built,
  tested, and documented.
- The UI and docs require a deliberate, staged migration from camera-only language.

## References

- [Implementation plan](../design/perception-sensor-ingress-plan.md)
- [Current coordinate transformer](../../tracker/src/coordinate_transformer.cpp)
- [Current camera-data schema](../../tracker/schema/camera-data.schema.json)
- [Current scene schema](../../tracker/schema/scene.schema.json)
- [Controller scene ingress](../../controller/src/controller/scene.py)
- [Manager Cam model](../../manager/src/manager/models.py)
- [ADR-7: Tracker Service](0007-tracker-service.md)
- [ADR-3: Scaling Controller Performance](0003-scaling-controller-performance.md)
