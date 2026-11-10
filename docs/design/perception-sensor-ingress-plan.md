<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Design Document: Perception Sensor Ingress — Unified Topic and Strategy Registry

- **Author(s)**: [spoluri](https://github.com/spoluri)
- **Date**: 2026-06-10
- **Status**: `Proposed`
- **Related ADRs**: [ADR-12](../adr/0012-perception-sensor-ingress.md)

---

## 1. Overview

SceneScape currently models all spatial perception sensors as cameras. This document describes a
migration to one stable perceptual ingress topic and a plugin/strategy-based modality registry that
is open for extension without modifying core message handlers.

Publishers port to the unified topic. The legacy `scenescape/data/camera/+` path is removed when
this change is confirmed; there is no compatibility adapter.

---

## 2. Goals

- Replace camera-as-catch-all ingress with one stable topic:
  `scenescape/data/perceptual_sensor/{sensor_id}`.
- Route by JSON metadata (`modality`) through strategy plugins.
- Keep external interfaces stable as new modalities are introduced.
- Eliminate hierarchical namespace collisions while keeping user-friendly sensor identifiers.
- Make calibration requirements modality-appropriate.
- Cut over camera publishers to the unified topic; remove the legacy camera ingress path on
  confirmation.

---

## 3. Non-Goals

- Rewriting tracker fusion or Kalman filter math.
- Migrating discrete event sensors (`SingletonSensor`) from `scenescape/data/sensor/+`, or unifying
  them with perceptual sensors under a single model/UI.
- Shipping a long-lived camera-topic compatibility bridge.

---

## 4. Background / Context

See [ADR-12](../adr/0012-perception-sensor-ingress.md). The current camera assumptions are spread
across manager, controller, scene_common, and tracker.

---

## 5. Proposed Design

### 5.0 Identity model

Perceptual sensors use dual identity:

- `source_uid` (UUID): canonical internal identity for routing, storage, joins, and fusion
- `source_key` (string alias): user-facing/pipeline-facing identifier

There is no legacy `id` field. Canonical processing always converts ingress identity to
`source_uid` at the boundary.

### 5.1 Topic namespace

```
scenescape/
  data/
    perceptual_sensor/{sensor_id}  <- unified perceptual ingress
    sensor/{sensor_id}             <- existing discrete events, unchanged
  image/
    camera/{sensor_id}             <- existing preview path
    thermal/{sensor_id}            <- optional preview path
  raw/
    lidar/{sensor_id}              <- optional raw stream
    radar/{sensor_id}              <- optional raw stream
```

Notes:

- `data/perceptual_sensor/{sensor_id}` is the only perceptual detection ingress.
- Raw and preview topics can stay modality-specific because they are non-fusion side channels.
- `data/camera/{sensor_id}` is removed at cutover; publishers must use the unified topic.

### 5.2 Shared detection envelope

A top-level `modality` field is required for perceptual ingress.

Pixel detection example (`bounding_box_px`):

```json
{
  "source_uid": "e7cdcbf4-9e2d-4b10-8d8d-f8f4be8a9dbe",
  "source_key": "dock-north-cam",
  "timestamp": "2026-06-10T12:00:00.000Z",
  "modality": "camera",
  "objects": {
    "person": [
      {
        "category": "person",
        "bounding_box_px": { "x": 1, "y": 2, "width": 3, "height": 4 },
        "confidence": 0.9
      }
    ]
  }
}
```

3D bounding-box example (`bounding_box_3D`), e.g. lidar:

```json
{
  "source_uid": "a1b2c3d4-1111-2222-3333-444455556666",
  "source_key": "dock-north-lidar",
  "timestamp": "2026-06-10T12:00:00.000Z",
  "modality": "lidar",
  "objects": {
    "vehicle": [
      {
        "category": "vehicle",
        "bounding_box_3D": {
          "x": 1.0,
          "y": 0.0,
          "z": 0.5,
          "width": 4.0,
          "height": 1.5,
          "depth": 2.0
        },
        "rotation": [0.0, 0.0, 0.0, 1.0],
        "confidence": 0.95
      }
    ]
  }
}
```

Metric pass-through example (`translation + rotation + size`) is also valid when the
publisher has already projected into scene coordinates.

Resolution rules:

1. If `source_uid` is present and valid, use it directly.
2. Else if `source_key` is present, resolve via identity registry.
3. If unresolved and auto-reserve is enabled, create `reserved` mapping and emit warning event.
4. If ambiguous, reject with explicit diagnostics.

Each detection satisfies exactly one of:

- `bounding_box_px`
- `translation + rotation + size`
- `bounding_box_3D`

### 5.3 PerceptualSensorStrategy interface

Location: `scene_common/src/scene_common/sensor_strategy.py`

```python
from abc import ABC, abstractmethod

class PerceptualSensorStrategy(ABC):
  @property
  @abstractmethod
  def modality(self) -> str:
    pass

  @abstractmethod
  def parse(self, payload: dict) -> dict:
    pass

  @abstractmethod
  def project(self, detections: list, sensor_config: dict) -> list:
    pass

  @abstractmethod
  def calibration_schema(self) -> dict:
    pass
```

### 5.4 Strategy registry

Location: `scene_common/src/scene_common/sensor_registry.py`

```python
_registry = {}

def register(strategy):
  _registry[strategy.modality] = strategy

def get(modality):
  strategy = _registry.get(modality)
  if strategy is None:
    raise KeyError(f"No strategy registered for modality '{modality}'")
  return strategy
```

Routing flow:

1. Subscriber receives payload on `data/perceptual_sensor/{sensor_id}`.
2. Resolve ingress identity to canonical `source_uid`.
3. Parse top-level `modality`.
4. Resolve strategy from registry.
5. Delegate parse + project to that strategy.

### 5.4.1 Identity resolver service

Add a resolver service/module used by ingress and UI (`scope` is the owning
`scene_uid`):

- `resolve(source_key, scene_uid) -> source_uid`
- `reserve(source_key, scene_uid, modality) -> source_uid`
- `bind(source_uid, scene_sensor_ref) -> active mapping`

State machine:

- `reserved` -> `bound` -> `active`

Suggested scope key:

- `(scene_uid, source_key)` unique

`scene_uid` is the owning Scene UUID (already used for hierarchy parent/child links,
regulated MQTT topics, and controller bindings). SceneScape does not currently model
`tenant`, `site`, or `scene_path` as configuration concepts; uniqueness is scoped to the
owning scene so the same friendly `source_key` can exist in different scenes in a
parent/child hierarchy.

### 5.5 C++ tracker changes

- `message_handler.cpp` subscribes to `scenescape/data/perceptual_sensor/+`.
- Payload parser reads `modality` and dispatches to `IProjectionStrategy` implementation.
- `CoordinateTransformer` is wrapped by `CameraProjectionStrategy`.
- Add `LidarProjectionStrategy` and `RadarProjectionStrategy` implementations.
- Unsubscribe and remove handlers for `scenescape/data/camera/+` at cutover.

### 5.6 Manager model changes

- Introduce a common perceptual sensor base with modality-specific derived models (preferred over
  tagging `Cam` with a `modality` flag).
- Shared base fields: `source_uid` (UUID, immutable) and `source_key` (string alias).
- Modality-specific subclasses own calibration fields and validation.
- Gate `DEFAULT_INTRINSICS` auto-fill to camera-derived models only.
- Serializer validation delegates calibration fields to `calibration_schema()` for modality.
- Enforce scoped uniqueness for `source_key` and shared validation rules with topic segment
  constraints.
- DB migration maps existing `Cam` rows onto the camera-derived model and drops any transitional
  legacy `id` alias afterward.

### 5.7 UI changes

Singleton (discrete event) sensors and perceptual sensors remain separate entities: different
models, topics (`data/sensor/+` vs `data/perceptual_sensor/+`), and editors. This design does not
merge them into one sensor type.

- Keep the existing _perceptual_ sensor editor and add a modality selector there only
  (camera / lidar / radar / thermal). Singleton sensor UI is unchanged.
- Show camera/thermal intrinsics controls only for those perceptual modalities.
- Show pose-centric controls for lidar/radar.
- Existing camera objects retain current UX by default.
- Add "reserve alias" and "bind existing alias" workflows so pipeline setup can happen before
  full scene configuration.
- Display identity status badge: `Reserved`, `Bound`, `Active`.

---

## 6. Implementation Phases

### Phase 1 — Foundation

- [ ] Add required `modality` field to perceptual envelope schema.
- [ ] Add `source_uid` and `source_key` fields to envelope schema (no legacy `id`).
- [ ] Add `sensor_strategy.py` and `sensor_registry.py`.
- [ ] Add identity resolver module with reserve/resolve/bind APIs.
- [ ] Implement and register `CameraStrategy`.
- [ ] Add unified perceptual topic constant in `mqtt.py`.
- [ ] Add unit tests for modality registry and unknown modality behavior.
- [ ] Add unit tests for identity resolution, ambiguity rejection, and reserved state.

### Phase 2 — Model cutover + lidar

- [ ] Introduce common perceptual sensor base and camera-derived model; migrate existing `Cam`
      rows.
- [ ] Add `source_uid`/`source_key` fields; eliminate legacy `id` after migration.
- [ ] Gate intrinsics autofill for camera only.
- [ ] Implement `LidarStrategy` and register it.
- [ ] Extend tracker parser/dispatcher for modality routing on the unified topic.
- [ ] Port camera publishers to `data/perceptual_sensor/+`.
- [ ] Remove `data/camera/+` ingress handlers and schemas on confirmation.
- [ ] Add lidar unit tests and camera-on-unified-topic tests.

### Phase 3 — Radar strategy

- [ ] Implement `RadarStrategy` and register it.
- [ ] Add radar projection strategy tests.

### Phase 4 — UI and API cleanup

- [ ] Modality selector and conditional calibration UI.
- [ ] API docs updated to show `modality` field and unified ingress contract.
- [ ] Docs and samples reference only the unified topic.

---

## 7. Validation Approach

1. Unit tests for registry dispatch and modality validation.
2. Camera payloads published on the unified topic (post-port).
3. Lidar and radar modality tests on unified topic.
4. Regression check that `data/camera/+` is no longer accepted after cutover.
5. Full run: `make run_unit_tests && make run_functional_tests`.

---

## 8. Open Questions

1. Should `modality` be required immediately, or optional with default `camera` for one release?
2. Should raw lidar/radar streams remain MQTT or move to another channel for high bandwidth?
3. Should discrete event sensors eventually use a parallel strategy interface for consistency?
4. Should unresolved alias messages be buffered briefly or fail-fast with diagnostics only?
5. Confirm Django inheritance vs composition for the common perceptual sensor base model.
