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

Publishers port to the unified topic. The legacy `scenescape/data/camera/+` ingress path is removed
when this change is confirmed; there is no long-lived compatibility adapter or `id` alias.

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
  "source_uid": "<uuid>",
  "source_key": "<alias>",
  "timestamp": "<ISO8601>",
  "modality": "camera | lidar | radar | thermal",
  "objects": {
    "<category>": [
      {
        "category": "<string>",
        "bounding_box_px": { "x": 0, "y": 0, "width": 0, "height": 0 },
        "translation": [0.0, 0.0, 0.0],
        "size": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0, 1.0],
        "confidence": 0.0
      }
    ]
  }
}
```

Identity rules:

- `source_uid` is canonical and immutable once bound.
- `source_key` is user-facing and scoped-unique (not globally unique).
- There is no legacy `id` field. Ingress identity is `source_uid` and/or `source_key` only.

Each detection satisfies **one** of:

- `bounding_box_px` (camera/thermal pixel detections),
- `translation + rotation + size` (pre-projected metric 3D detections), or
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

### 5. Data model and cutover

Prefer a common perceptual sensor base model with modality-specific derived models (for example
`PerceptualSensor` with `Camera` / `Lidar` / `Radar` / `Thermal` subtypes) over extending `Cam`
with a `modality` flag. Derived models keep calibration fields and validation rules local to each
modality while sharing identity (`source_uid`, `source_key`) and scene association.

Cutover rules:

- Publishers and pipelines port to `scenescape/data/perceptual_sensor/+`. There is no
  compatibility adapter from `scenescape/data/camera/+`.
- On confirmation of this change, remove the legacy camera ingress path. Do not keep a deprecated
  dual-path for a later release.
- Ingress accepts `source_uid` and/or `source_key`. A resolver maps `source_key` -> `source_uid`
  using scene scope.
- Support alias pre-registration so DLStreamer can be configured before scene sensor binding.
- When binding is completed, reserved aliases transition to active mappings without pipeline
  reconfiguration.

## Alternatives Considered

- **Modality-specific topics (`scenescape/data/lidar/+`, `.../radar/+`)** — Not chosen as the
  default. Clear per modality, but each new modality would add an external topic unless topic
  registration is config-driven. A config-extensible modality topic map remains a viable escape
  hatch if unified-topic routing proves insufficient.
- **Keep everything as camera** — Rejected. Keeps wrong semantics and camera-specific assumptions.
- **Extend `Cam` with `modality`** — Considered. Simpler short-term migration of existing rows, but
  leaves camera-shaped fields and validation on non-camera sensors. Prefer a common base with
  derived modality models.

## Consequences

### Positive

- External ingestion interface remains stable as modalities expand.
- New modalities require no core handler edits.
- Calibration requirements are modality-appropriate.
- Hierarchical namespace collisions are prevented by canonical UUID routing.
- Users can configure pipelines early with aliases and bind later via resolver.
- No long-lived dual ingress or legacy `id` field to maintain.

### Negative

- Consumers must inspect payload metadata to determine modality.
- Strategy registry and envelope schema infrastructure must be built and maintained.
- Existing camera publishers must be ported to the unified topic at cutover.
- UI/docs require migration from camera-only language.
- Resolver and alias reservation lifecycle add state-management complexity.

## Implementation Notes

Recommended identifier lifecycle:

1. `reserved`: `source_key` created, provisional `source_uid` allocated
2. `bound`: alias is attached to concrete scene sensor
3. `active`: ingestion and fusion use canonical `source_uid`

Recommended uniqueness constraint:

- Unique on `(scene_uid, source_key)`

`scene_uid` is the owning Scene's UUID — the same identifier already used in hierarchy links
(`ChildScene`), MQTT regulated topics, and controller bindings. There is no separate
`tenant` / `site` / `scene_path` namespace in SceneScape configuration today; multi-tenancy is
out of scope for this ADR. Scoping by owning scene lets the same friendly `source_key` appear
in different scenes in a parent/child hierarchy while canonical routing stays on `source_uid`.

## References

- [Implementation plan](../design/perception-sensor-ingress-plan.md)
- [Current coordinate transformer](../../tracker/src/coordinate_transformer.cpp)
- [Current camera-data schema](../../tracker/schema/camera-data.schema.json)
- [Current scene schema](../../tracker/schema/scene.schema.json)
- [Controller scene ingress](../../controller/src/controller/scene.py)
- [Manager Cam model](../../manager/src/manager/models.py)
- [ADR-7: Tracker Service](0007-tracker-service.md)
- [ADR-3: Scaling Controller Performance](0003-scaling-controller-performance.md)
