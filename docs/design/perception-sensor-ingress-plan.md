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

The migration is staged: existing camera publishers continue working through compatibility adapters.

---

## 2. Goals

- Replace camera-as-catch-all ingress with one stable topic:
  `scenescape/data/perceptual_sensor/{sensor_id}`.
- Route by JSON metadata (`modality`) through strategy plugins.
- Keep external interfaces stable as new modalities are introduced.
- Eliminate hierarchical namespace collisions while keeping user-friendly sensor identifiers.
- Make calibration requirements modality-appropriate.
- Preserve backward compatibility for existing camera deployments.

---

## 3. Non-Goals

- Rewriting tracker fusion or Kalman filter math.
- Migrating discrete event sensors (`SingletonSensor`) from `scenescape/data/sensor/+`.
- Removing camera compatibility ingress in this change cycle.

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

Compatibility fields:

- `id` is retained short-term as legacy alias and mapped to `source_key`

Canonical processing always converts ingress identity to `source_uid` at the boundary.

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

### 5.2 Shared detection envelope

A top-level `modality` field is required for perceptual ingress.

```json
{
  "id": "legacy-alias",
  "source_uid": "e7cdcbf4-9e2d-4b10-8d8d-f8f4be8a9dbe",
  "source_key": "dock-north-lidar",
  "timestamp": "2026-06-10T12:00:00.000Z",
  "modality": "camera",
  "objects": {
    "person": [
      {
        "category": "person",
        "bounding_box_px": { "x": 1, "y": 2, "width": 3, "height": 4 },
        "translation": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.7],
        "rotation": [0, 0, 0, 1],
        "confidence": 0.9
      }
    ]
  }
}
```

Resolution rules:

1. If `source_uid` is present and valid, use it directly.
2. Else if `source_key` (or legacy `id`) is present, resolve via identity registry.
3. If unresolved and auto-reserve is enabled, create `reserved` mapping and emit warning event.
4. If ambiguous, reject with explicit diagnostics.

Each detection satisfies exactly one of:

- `bounding_box_px`
- `translation + size`
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

Add a resolver service/module used by ingress and UI:

- `resolve(source_key, scope) -> source_uid`
- `reserve(source_key, scope, modality) -> source_uid`
- `bind(source_uid, scene_sensor_ref) -> active mapping`

State machine:

- `reserved` -> `bound` -> `active`

Suggested scope key:

- `(tenant, site, scene_path, source_key)` unique

This allows reused friendly names in different hierarchy branches without collision.

### 5.5 C++ tracker changes

- `message_handler.cpp` subscribes to `scenescape/data/perceptual_sensor/+`.
- Payload parser reads `modality` and dispatches to `IProjectionStrategy` implementation.
- `CoordinateTransformer` is wrapped by `CameraProjectionStrategy`.
- Add `LidarProjectionStrategy` and `RadarProjectionStrategy` implementations.

### 5.6 Manager model changes

- Add `modality` field to `Cam` (default `"camera"`).
- Add `source_uid` (UUID, immutable) and `source_key` (string alias).
- Gate `DEFAULT_INTRINSICS` auto-fill behind `modality == "camera"`.
- Serializer validation delegates calibration fields to `calibration_schema()` for modality.
- Enforce scoped uniqueness for `source_key` and shared validation rules with topic segment constraints.

### 5.7 UI changes

- Keep existing sensor editor but add modality selector.
- Show camera/thermal intrinsics controls only for those modalities.
- Show pose-centric controls for lidar/radar.
- Existing camera objects retain current UX by default.
- Add "reserve alias" and "bind existing alias" workflows so pipeline setup can happen before
  full scene configuration.
- Display identity status badge: `Reserved`, `Bound`, `Active`.

---

## 6. Implementation Phases

### Phase 1 — Foundation

- [ ] Add required `modality` field to perceptual envelope schema.
- [ ] Add `source_uid` and `source_key` fields to envelope schema (with compatibility `id`).
- [ ] Add `sensor_strategy.py` and `sensor_registry.py`.
- [ ] Add identity resolver module with reserve/resolve/bind APIs.
- [ ] Implement and register `CameraStrategy`.
- [ ] Add unified perceptual topic constant in `mqtt.py`.
- [ ] Add unit tests for modality registry and unknown modality behavior.
- [ ] Add unit tests for identity resolution, ambiguity rejection, and reserved state.

### Phase 2 — Compatibility adapter + lidar

- [ ] Add compatibility bridge from `data/camera/+` to unified envelope.
- [ ] Add `modality` field to `Cam` and DB migration.
- [ ] Add `source_uid`/`source_key` fields and migration for existing sensors.
- [ ] Gate intrinsics autofill for camera only.
- [ ] Implement `LidarStrategy` and register it.
- [ ] Extend tracker parser/dispatcher for modality routing.
- [ ] Add lidar unit tests and camera compatibility tests.
- [ ] Add compatibility path resolving legacy `id` to `source_key` then `source_uid`.

### Phase 3 — Radar strategy

- [ ] Implement `RadarStrategy` and register it.
- [ ] Add radar projection strategy tests.

### Phase 4 — UI and API cleanup

- [ ] Modality selector and conditional calibration UI.
- [ ] API docs updated to show `modality` field and unified ingress contract.

### Phase 5 — Deprecation follow-up

- [ ] Mark `data/camera/+` compatibility path deprecated.
- [ ] Set timeline for removing compatibility bridge after migration window.

---

## 7. Validation Approach

1. Unit tests for registry dispatch and modality validation.
2. Backward compatibility tests for existing camera payloads.
3. Lidar and radar modality tests on unified topic.
4. Full run: `make run_unit_tests && make run_functional_tests`.

---

## 8. Open Questions

1. Should `modality` be required immediately, or optional with default `camera` for one release?
2. Should raw lidar/radar streams remain MQTT or move to another channel for high bandwidth?
3. Should discrete event sensors eventually use a parallel strategy interface for consistency?
4. Should unresolved alias messages be buffered briefly or fail-fast with diagnostics only?
