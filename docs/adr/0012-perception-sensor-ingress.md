<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 12: Perception Sensor Ingress — Unified Topic and Strategy-Based Modality Routing

- **Author(s)**: [spoluri](https://github.com/spoluri)
- **Date**: 2026-06-10
- **Status**: `Proposed`

## TLDR

Replace the current practice of modeling all perception sensors (lidar, radar, thermal, etc.) as
cameras with one stable perceptual MQTT ingress topic and a plugin/strategy-based modality
registry. Modality is declared in JSON metadata and used for routing to the proper parser and
projection strategy. New modalities are added by registering a strategy, not by branching existing
code or changing external topic interfaces.

Also adopt a dual-identity contract to avoid hierarchical namespace collisions while preserving
operator-friendly configuration:

- `source_uid` (UUID): canonical internal identity used for storage, joins, routing, and fusion
- `source_key` (string alias): human/external identifier used by pipelines and UI

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
   `"intrinsics" in jdata` is detected.
3. **Misleading topic semantics.** Non-camera pipelines must publish on a camera topic just to be
   ingested, which obscures intent and pollutes interfaces.
4. **Camera-centric UX everywhere.** The UI shows a camera frustum for every sensor, and exposes
   FOV/intrinsics controls that are meaningless for lidar or radar.
5. **No OCP extension point.** Adding radar or thermal requires editing core handlers instead of
   registering a new strategy.
6. **Identifier collision in scene hierarchy.** User-provided sensor IDs can collide across parent/
   child scenes. UUIDs solve collisions, but UUID-only external configuration creates poor UX when
   pipelines must be configured before scene objects exist.

## Decision

### 1. Unified perceptual ingress topic with metadata-based routing

- Perceptual ingress topic: `scenescape/data/perceptual_sensor/{sensor_id}`
- Discrete event topic remains: `scenescape/data/sensor/{sensor_id}`

Routing to camera/lidar/radar/thermal handlers is based on the top-level `modality` field in the
JSON envelope. This keeps the external interface stable as the modality list grows.

### 2. Shared detection envelope schema

All perceptual sensor messages on the unified topic share a common envelope:

```json
{
  "id": "<legacy alias>",
  "source_uid": "<uuid>",
  "source_key": "<alias>",
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

Identity rules:

- `source_uid` is canonical and immutable once bound.
- `source_key` is user-facing and scoped-unique (not globally unique).
- `id` remains as compatibility alias during migration and maps to `source_key`.

Each detection satisfies **one** of:

- `bounding_box_px` (camera/thermal pixel detections),
- `translation + size` (pre-projected metric 3D detections), or
- `bounding_box_3D` (sensor-native 3D box to be projected by strategy).

### 3. Plugin/strategy registry (Open/Closed Principle)

A `PerceptualSensorStrategy` interface carries three responsibilities:

- **parse(payload) -> DetectionBatch**
- **project(batch, sensor_config) -> WorldDetections**
- **calibration_schema() -> JSONSchema**

Built-in strategies:

| Strategy         | Modality key | Projection model                                        |
| ---------------- | ------------ | ------------------------------------------------------- |
| `CameraStrategy` | `camera`     | Pinhole `K` matrix + undistort + ray-plane intersection |
| `LidarStrategy`  | `lidar`      | Metric 3D pass-through; optional range-image projection |
| `RadarStrategy`  | `radar`      | Polar-to-Cartesian conversion for heatmap/range-doppler |

Registry maps `modality` -> strategy instance. Adding a new modality means implementing and
registering a strategy, with no core handler changes.

### 4. Calibration inputs by modality

| Modality | Required calibration                       | Optional                     |
| -------- | ------------------------------------------ | ---------------------------- |
| Camera   | `intrinsics` + `distortion` + `extrinsics` | —                            |
| Lidar    | `extrinsics`                               | Beam model for 2D projection |
| Radar    | `extrinsics`                               | Resolution metadata          |
| Thermal  | Same as camera                             | —                            |

`DEFAULT_INTRINSICS` auto-fill is applied only when `modality == "camera"`.

### 5. Migration compatibility

- Existing `scenescape/data/camera/+` publishers continue through a compatibility adapter that
  transforms into the unified perceptual envelope.
- `Cam` model is extended with `modality` (default `"camera"`), preserving current rows.
- UI adds modality selector for new sensors; existing sensors default to `camera` behavior.
- Camera ingress compatibility is marked deprecated for later removal.

Identity compatibility and ordering:

- Ingress accepts either `source_uid` or `source_key` during transition.
- A resolver maps `source_key` -> `source_uid` using scene scope.
- Support alias pre-registration so DLStreamer can be configured before scene sensor binding.
- When binding is completed, reserved aliases transition to active mappings without pipeline
  reconfiguration.

## Alternatives Considered

- **Modality-specific topics (`scenescape/data/lidar/+`, `.../radar/+`)** — Rejected. Clear, but
  forces external interface additions for every new modality.
- **Keep everything as camera** — Rejected. Keeps wrong semantics and camera-specific assumptions.

## Consequences

### Positive

- External ingestion interface remains stable as modalities expand.
- New modalities require no core handler edits.
- Calibration requirements are modality-appropriate.
- Existing camera deployments continue working.
- Hierarchical namespace collisions are prevented by canonical UUID routing.
- Users can configure pipelines early with aliases and bind later via resolver.

### Negative

- Consumers must inspect payload metadata to determine modality.
- Strategy registry and envelope schema infrastructure must be built and maintained.
- UI/docs still require migration from camera-only language.
- Resolver and alias reservation lifecycle add state-management complexity.

## Implementation Notes

Recommended identifier lifecycle:

1. `reserved`: `source_key` created, provisional `source_uid` allocated
2. `bound`: alias is attached to concrete scene sensor
3. `active`: ingestion and fusion use canonical `source_uid`

Recommended uniqueness constraint:

- Unique on `(tenant, site, scene_path, source_key)`

This permits reuse of friendly aliases in different branches of a hierarchy while keeping
collision-free canonical routing.

## References

- [Implementation plan](../design/perception-sensor-ingress-plan.md)
- [Current coordinate transformer](../../tracker/src/coordinate_transformer.cpp)
- [Current camera-data schema](../../tracker/schema/camera-data.schema.json)
- [Current scene schema](../../tracker/schema/scene.schema.json)
- [Controller scene ingress](../../controller/src/controller/scene.py)
- [Manager Cam model](../../manager/src/manager/models.py)
- [ADR-7: Tracker Service](0007-tracker-service.md)
- [ADR-3: Scaling Controller Performance](0003-scaling-controller-performance.md)
