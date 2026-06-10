<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Design Document: Perception Sensor Ingress — Modality-Specific Topics and Strategy Registry

- **Author(s)**: [spoluri](https://github.com/spoluri)
- **Date**: 2026-06-10
- **Status**: `Proposed`
- **Related ADRs**: [ADR-12](../adr/0012-perception-sensor-ingress.md)

---

## 1. Overview

SceneScape currently models all spatial perception sensors as cameras. This document describes the
implementation plan to replace that approach with explicit modality-specific ingress topics and a
plugin/strategy-based handler registry that is open for extension without modifying the core
message handler, controller, or tracker code.

The migration is staged: existing camera publishers continue working throughout. Non-camera
modalities gain first-class topics and handlers incrementally.

---

## 2. Goals

- Replace camera-as-catch-all ingress with explicit `scenescape/data/{modality}/{sensor_id}` topics.
- Introduce a `PerceptualSensorStrategy` interface so new modalities are registered, not branched.
- Make calibration requirements modality-appropriate (intrinsics only where the model needs them).
- Preserve full backward compatibility for existing camera deployments.
- Eliminate camera-specific language from shared code paths in the controller, tracker, and UI.

---

## 3. Non-Goals

- Rewriting tracker fusion or Kalman filter math (those stay stable during this migration).
- Migrating discrete event sensors (`SingletonSensor`); they remain on `scenescape/data/sensor/+`.
- Removing camera topic support within this change cycle.

---

## 4. Background / Context

See [ADR-12](../adr/0012-perception-sensor-ingress.md) for the full problem statement. Key files
carrying camera-specific assumptions today:

| File                                                 | Camera assumption                                          |
| ---------------------------------------------------- | ---------------------------------------------------------- |
| `manager/src/manager/models.py`                      | `Cam.DEFAULT_INTRINSICS` auto-filled for all sensors       |
| `manager/src/manager/serializers.py`                 | Intrinsics/distortion treated as canonical shape           |
| `manager/src/manager/static/js/thing/scenecamera.js` | `THREE.PerspectiveCamera` frustum for all sensors          |
| `controller/src/controller/scene.py`                 | `processCameraData` + `_convertPixelBoundingBoxesToMeters` |
| `controller/src/schema/metadata.schema.json`         | `bounding_box_px` as primary detection format              |
| `scene_common/src/scene_common/camera.py`            | `Camera` = sensor, `CameraIntrinsics` required             |
| `scene_common/src/scene_common/transform.py`         | Projection math tied to pinhole model                      |
| `tracker/schema/camera-data.schema.json`             | `bounding_box_px` required                                 |
| `tracker/schema/scene.schema.json`                   | `cameras` array only                                       |
| `tracker/src/message_handler.cpp`                    | Subscribes only `scenescape/data/camera/+`                 |
| `tracker/src/coordinate_transformer.cpp`             | Pinhole ray-plane intersection hardcoded                   |
| `scene_common/src/scene_common/mqtt.py`              | `DATA_CAMERA` topic template                               |

---

## 5. Proposed Design

### 5.1 Topic namespace

```
scenescape/
  data/
    camera/{sensor_id}      ← existing, unchanged
    lidar/{sensor_id}       ← new
    radar/{sensor_id}       ← new
    thermal/{sensor_id}     ← new
    sensor/{sensor_id}      ← existing (discrete event), unchanged
  image/
    camera/{sensor_id}      ← existing, unchanged
    thermal/{sensor_id}     ← new
  raw/
    lidar/{sensor_id}       ← new (optional point cloud stream)
    radar/{sensor_id}       ← new (optional raw heatmap stream)
```

### 5.2 Shared detection envelope

The common message shape is an extension of the existing detector schema in
`controller/src/schema/metadata.schema.json`. A new top-level `modality` field is added.
The `detection` object satisfies exactly one of:

- `bounding_box_px` — pixel-space detection (camera, thermal)
- `translation + size` — metric 3D detection already in sensor frame (lidar, radar)
- `bounding_box_3D` — sensor-native 3D box for strategy-driven projection

```json
{
  "id": "lidar-front",
  "timestamp": "2026-06-10T12:00:00.000Z",
  "modality": "lidar",
  "objects": {
    "vehicle": [
      {
        "category": "vehicle",
        "translation": [4.2, 1.1, 0.5],
        "size": [4.5, 2.0, 1.6],
        "rotation": [0, 0, 0, 1],
        "confidence": 0.92
      }
    ]
  }
}
```

### 5.3 PerceptualSensorStrategy interface (Python)

Location: `scene_common/src/scene_common/sensor_strategy.py`

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod

class PerceptualSensorStrategy(ABC):
  """Modality plugin: parse, project, and declare calibration schema."""

  @property
  @abstractmethod
  def modality(self) -> str:
    """Return the modality identifier, e.g. 'camera', 'lidar', 'radar'."""

  @abstractmethod
  def parse(self, payload: dict) -> dict:
    """Validate and normalise a raw MQTT payload into the shared envelope."""

  @abstractmethod
  def project(self, detections: list, sensor_config: dict) -> list:
    """Convert sensor-space detections to scene world coordinates."""

  @abstractmethod
  def calibration_schema(self) -> dict:
    """Return JSON Schema for this modality's calibration parameters."""
```

### 5.4 Strategy registry

Location: `scene_common/src/scene_common/sensor_registry.py`

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

_registry: dict[str, PerceptualSensorStrategy] = {}

def register(strategy: PerceptualSensorStrategy) -> None:
  _registry[strategy.modality] = strategy

def get(modality: str) -> PerceptualSensorStrategy:
  strategy = _registry.get(modality)
  if strategy is None:
    raise KeyError(f"No strategy registered for modality '{modality}'")
  return strategy
```

Built-in strategies registered at package import time:

- `CameraStrategy` — wraps the existing `CameraIntrinsics` + `CameraPose` + `CoordinateTransformer` path
- `LidarStrategy` — identity pass-through for metric 3D; optional range-image projection
- `RadarStrategy` — polar-to-Cartesian for heatmap or range-doppler detections

### 5.5 C++ tracker changes

The tracker's `MessageHandler` currently subscribes only to `scenescape/data/camera/+`. The
`main.cpp` startup registers each sensor topic from the scene config. Three changes are needed:

1. **`scene.schema.json`** — replace `cameras` array with `sensors` array; each entry carries a
   `modality` field alongside `uid`, `name`, `intrinsics` (optional), and `extrinsics`.
2. **`message_handler.cpp`** — subscribe to `scenescape/data/{modality}/{sensor_id}` for each
   sensor; the handler dispatches to the matching `IProjectionStrategy` (C++ equivalent of the
   Python interface).
3. **`coordinate_transformer.cpp`** — refactor into a `CameraProjectionStrategy` that implements
   `IProjectionStrategy`; `LidarProjectionStrategy` passes metric 3D detections through without
   the pinhole undistortion step.

The `CoordinateTransformer` class remains intact as the implementation behind
`CameraProjectionStrategy`; no tracking math changes.

### 5.6 Manager model changes

`Cam` gains a `modality` field (CharField, default `"camera"`). The `DEFAULT_INTRINSICS` auto-fill
in `save()` is guarded by `self.modality == "camera"`. The serializer gains a
`calibration_schema_for_modality()` method that delegates to the registered strategy.

### 5.7 UI changes

`scenecamera.js` is renamed to `scenesensor.js`. The sensor creation panel gains a modality
selector. When `modality == "camera"` or `"thermal"`, the existing intrinsics/FOV/frustum controls
are shown. For `"lidar"` or `"radar"`, a pose-only calibration panel is shown instead. The
Three.js rendering adds modality-appropriate visualizations (point cloud origin cone for lidar,
radar sweep arc for radar).

### 5.8 MQTT topic constants

`scene_common/src/scene_common/mqtt.py` gains new `_Topic` enum values and templates:

```python
DATA_LIDAR   = auto()  # scenescape/data/lidar/${sensor_id}
DATA_RADAR   = auto()  # scenescape/data/radar/${sensor_id}
DATA_THERMAL = auto()  # scenescape/data/thermal/${sensor_id}
RAW_LIDAR    = auto()  # scenescape/raw/lidar/${sensor_id}
RAW_RADAR    = auto()  # scenescape/raw/radar/${sensor_id}
IMAGE_THERMAL = auto() # scenescape/image/thermal/${sensor_id}
```

---

## 6. Implementation Phases

### Phase 1 — Foundation (prerequisite for all others)

Files: `scene_common`, `controller/src/schema/metadata.schema.json`

- [ ] Add `modality` field to the shared detection schema (`metadata.schema.json`), remaining optional and defaulting to `"camera"` for backward compatibility.
- [ ] Create `sensor_strategy.py` and `sensor_registry.py` in `scene_common`.
- [ ] Implement and register `CameraStrategy` as a thin wrapper around existing logic.
- [ ] Add `DATA_LIDAR`, `DATA_RADAR`, `DATA_THERMAL`, `RAW_LIDAR`, `RAW_RADAR`, `IMAGE_THERMAL` topic constants to `mqtt.py`.
- [ ] Unit tests for registry lookup, camera strategy parse/project, unknown modality error.

### Phase 2 — Lidar first-class support

Files: `manager/models.py`, `manager/serializers.py`, `controller/src/controller/scene.py`, `tracker/schema/scene.schema.json`, `tracker/src/message_handler.cpp`, `tracker/src/coordinate_transformer.cpp`

- [ ] Add `modality` field (default `"camera"`) to `Cam` model; create and run DB migration.
- [ ] Gate `DEFAULT_INTRINSICS` auto-fill on `self.modality == "camera"`.
- [ ] Implement `LidarStrategy` in `scene_common`; register it.
- [ ] Extend `tracker/schema/scene.schema.json` to accept `sensors` array alongside `cameras`.
- [ ] Extend `tracker/src/message_handler.cpp` to subscribe `scenescape/data/lidar/+` and dispatch to `LidarProjectionStrategy`.
- [ ] Implement `LidarProjectionStrategy` in C++ (metric 3D pass-through; no undistortion).
- [ ] Controller `processCameraData` renamed `processSensorData`; dispatches to strategy via registry.
- [ ] Unit tests for lidar parse, project, no-intrinsics-required validation.
- [ ] Compatibility test: existing camera MQTT payloads unchanged.

### Phase 3 — Radar support

Files: same patterns as Phase 2 for radar.

- [ ] Implement `RadarStrategy` (polar-to-Cartesian or metric 3D depending on pipeline output).
- [ ] Add radar to `message_handler.cpp` subscription and strategy dispatch.
- [ ] Unit tests for radar parse, project.

### Phase 4 — UI and Manager UX

Files: `manager/src/manager/static/js/thing/scenecamera.js` → `scenesensor.js`, templates

- [ ] Rename `scenecamera.js` to `scenesensor.js`; update all imports.
- [ ] Add modality selector on new sensor creation form.
- [ ] Show/hide calibration controls by modality (intrinsics+FOV for camera/thermal; pose-only for lidar/radar).
- [ ] Add modality-appropriate 3D visualizations.
- [ ] UI tests covering modality selector and form validation.

### Phase 5 — Documentation and deprecation

- [ ] Rewrite `convert-object-detections-to-normalized-image-space.md` to cover all modalities.
- [ ] Add a migration guide for publishers currently using `scenescape/data/camera/` for non-camera sensors.
- [ ] Mark legacy camera-only API fields as deprecated in the API reference.
- [ ] Update `tracker/Agents.md` to describe sensor strategy interface and calibration requirements per modality.

---

## 7. Validation Approach

1. **Phase 1 gate**: `make run_unit_tests` passes with new strategy registry tests.
2. **Phase 2 gate**: Existing camera integration test suite passes unchanged (compatibility). New lidar unit tests pass.
3. **Phases 3–4 gate**: Functional tests for radar and UI modality selector.
4. **Final gate**: Full `make run_unit_tests && make run_functional_tests` suite green.

---

## 8. Open Questions

1. Should the public REST API rename `cameras` to `sensors` immediately (Phase 2), or in a later release?
2. Should raw lidar point cloud and radar heatmap streams be binary-encoded MQTT or a separate protocol (e.g. gRPC)?
3. Should `SingletonSensor` (discrete events) share the `PerceptualSensorStrategy` interface for uniformity, or remain a separate hierarchy?
