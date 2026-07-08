<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Research Report: Analytics Extraction from Controller

- Date: 2026-07-07
- Branch: adr/0013-controller-breakdown
- Scope: Controller analytics implementation and extraction constraints
- Context ADR: [docs/adr/0013-controller-breakdown-microservices.md](docs/adr/0013-controller-breakdown-microservices.md)

## Executive Summary

Analytics is a strong extraction candidate and appears to be the easiest major component to separate after Tracker.  
Current code already supports an analytics-only runtime path that consumes tracked objects from MQTT, which significantly reduces extraction risk.

The main extraction challenges are not core analytics algorithms, but:
1. Preserving stateful event behavior (region enter/exit, dwell, tripwire debounce, sensor histories).
2. Stabilizing tracker-to-analytics contracts.
3. Keeping topic and payload compatibility for downstream consumers.
4. Clarifying hierarchy event propagation ownership.

## 1. Where Analytics Is Implemented (Units)

### 1.1 Core Analytics Computation (Scene-level)

Primary unit: [controller/src/controller/scene.py](controller/src/controller/scene.py)

- Event orchestration: [_updateEvents](controller/src/controller/scene.py#L629)
- Region logic (enter/exit/count, dwell, singleton sensor behavior): [_updateRegionEvents](controller/src/controller/scene.py#L682)
- Tripwire crossing logic: [_updateTripwireEvents](controller/src/controller/scene.py#L648)
- Sensor analytics enrichment (environmental + attribute): [processSensorData](controller/src/controller/scene.py#L341)
- Analytics call after frame processing: [_finishProcessing](controller/src/controller/scene.py#L325)

### 1.2 Analytics-Only Ingestion Path (Already Present)

- Store tracked objects from MQTT: [updateTrackedObjects](controller/src/controller/scene.py#L480)
- Retrieve tracked objects in analytics-only mode: [getTrackedObjects](controller/src/controller/scene.py#L495)
- Convert serialized tracked payloads to analytics wrappers: [_deserializeTrackedObjects](controller/src/controller/scene.py#L513)
- Scene-data MQTT handler for analytics-only processing: [handleSceneDataMessage](controller/src/controller/scene_controller.py#L554)
- Mode switch: [controller/src/controller/controller_mode.py](controller/src/controller/controller_mode.py)
- CLI flag: [controller/src/controller-cmd](controller/src/controller-cmd#L93)

### 1.3 Output / Publication Layer (Controller orchestration)

Primary unit: [controller/src/controller/scene_controller.py](controller/src/controller/scene_controller.py)

- Publish pipeline entry: [publishDetections](controller/src/controller/scene_controller.py#L191)
- Regulated output stream: [publishRegulatedDetections](controller/src/controller/scene_controller.py#L247)
- Region-specific stream output: [publishRegionDetections](controller/src/controller/scene_controller.py#L308)
- Event publishing: [publishEvents](controller/src/controller/scene_controller.py#L329)

### 1.4 Serialization and Analytics Payload Shaping

Primary unit: [controller/src/controller/detections_builder.py](controller/src/controller/detections_builder.py)

- Object serialization entrypoint: [prepareObjDict](controller/src/controller/detections_builder.py#L61)
- Region dwell serialization support: [_buildRegionOutput](controller/src/controller/detections_builder.py#L36)
- Sensor inclusion behavior: [prepareObjDict sensor branch](controller/src/controller/detections_builder.py#L135)

### 1.5 Hierarchy-related Analytics Event Flow

- Child event republish to parent context: [republishEvents](controller/src/controller/scene_controller.py#L693)
- Object coordinate transformation in republished events: [transformObjectsinEvent](controller/src/controller/scene_controller.py#L730)
- Remote child wiring: [controller/src/controller/child_scene_controller.py](controller/src/controller/child_scene_controller.py)

## 2. Is Analytics Blended with Other Functionalities?

## 2.1 Re-ID Coupling Assessment

### Direct coupling: Low
Analytics does not execute Re-ID matching/association itself.

Evidence:
- In analytics-only mode, controller skips loading tracker/reid/pose-adjustment configs:
  - [scene_controller.py](controller/src/controller/scene_controller.py#L54)
  - [scene_controller.py](controller/src/controller/scene_controller.py#L59)
  - [scene_controller.py](controller/src/controller/scene_controller.py#L64)
- Analytics-only path consumes tracked scene output from MQTT:
  - [handleSceneDataMessage](controller/src/controller/scene_controller.py#L554)

### Data-model coupling: Medium
Analytics still depends on identity semantics in payloads.

Evidence:
- Re-ID metadata can be serialized in output: [detections_builder.py](controller/src/controller/detections_builder.py#L107)
- Re-ID state is emitted: [detections_builder.py](controller/src/controller/detections_builder.py#L169)
- Previous ID lineage can be emitted: [detections_builder.py](controller/src/controller/detections_builder.py#L173)
- Analytics wrapper restoration keeps metadata/reid from incoming objects in deserialization path:
  - [scene.py](controller/src/controller/scene.py#L513)

Conclusion: Analytics is not logically responsible for Re-ID decisions, but it is contract-coupled to identity-related fields.

## 2.2 Tracking Coupling Assessment

Analytics is currently implemented on top of MovingObject-like mutable state.

Evidence:
- ChainData is central for analytics state (regions, published locations, sensor state): [controller/src/controller/moving_object.py](controller/src/controller/moving_object.py#L131)
- Analytics-only wrappers reconstruct MovingObject-like structures and ChainData:
  - [scene.py](controller/src/controller/scene.py#L513)

Conclusion: Analytics algorithms are separable, but runtime representation is still tied to controller internal object model.

## 2.3 Hierarchy Coupling Assessment

Analytics event propagation across child/parent scenes remains inside Controller orchestration.

Evidence:
- Event republish + transform in controller:
  - [scene_controller.py](controller/src/controller/scene_controller.py#L693)
  - [scene_controller.py](controller/src/controller/scene_controller.py#L730)

Conclusion: Extraction must explicitly assign hierarchy/event propagation ownership to avoid split-brain behavior.

## 3. Constraints for Extracting Analytics from Controller

1. Stable tracker-to-analytics input contract is required.
- Analytics-only validates scene-data payload schema:
  - [scene_controller.py](controller/src/controller/scene_controller.py#L73)
  - [tracker/schema/scene-data.schema.json](tracker/schema/scene-data.schema.json)
- Current code relies on optional fields beyond minimal required schema in practical analytics behavior.

2. Stateful behavior must be preserved exactly.
- Region transitions and dwell timing:
  - [scene.py](controller/src/controller/scene.py#L682)
- Tripwire debounce and crossing semantics:
  - [scene.py](controller/src/controller/scene.py#L648)
- Object location history used for tripwire:
  - [scene.py](controller/src/controller/scene.py#L629)

3. Sensor lifecycle and per-object sensor histories must move with analytics.
- Environmental sensor readings handling:
  - [scene.py](controller/src/controller/scene.py#L401)
- Attribute sensor event handling:
  - [scene.py](controller/src/controller/scene.py#L432)
- Sensor-driven event shaping in published payloads:
  - [scene_controller.py](controller/src/controller/scene_controller.py#L329)
  - [detections_builder.py](controller/src/controller/detections_builder.py#L135)

4. Scene config and geometry dependencies must be available in analytics service.
- Regions/tripwires/sensors/cameras loaded via cache manager:
  - [controller/src/controller/cache_manager.py](controller/src/controller/cache_manager.py)
- Region intersection can involve mesh-based checks:
  - [scene.py](controller/src/controller/scene.py#L805)

5. Topic and payload compatibility must be maintained.
- Existing publication surfaces:
  - Scene/regulated/region/event flows in [scene_controller.py](controller/src/controller/scene_controller.py)
- Downstream consumers depend on existing topic/payload semantics.

6. Hierarchy event republish contract must be formalized.
- Parent-child event forwarding and transformation currently coupled to controller runtime:
  - [scene_controller.py](controller/src/controller/scene_controller.py#L693)

7. Identity fields are pass-through but behaviorally important.
- Even if Re-ID service is separate, analytics output currently may expose:
  - metadata.reid
  - reid_state
  - previous_ids_chain
- See [detections_builder.py](controller/src/controller/detections_builder.py#L107), [detections_builder.py](controller/src/controller/detections_builder.py#L169), [detections_builder.py](controller/src/controller/detections_builder.py#L173)

## 4. Practical Extraction Readiness

Readiness signals already present:
- Analytics-only mode exists and is production-oriented in flow design:
  - [controller_mode.py](controller/src/controller/controller_mode.py)
  - [handleSceneDataMessage](controller/src/controller/scene_controller.py#L554)
- Controller can already consume external tracked streams and compute analytics independently of local tracker process.

Most likely migration sequence (aligned with findings):
1. Freeze and version the tracker-to-analytics contract.
2. Move Scene analytics logic into dedicated analytics package/module.
3. Keep same MQTT topics and payload format while process-separating.
4. Extract hierarchy republish behavior either into analytics service or a dedicated hierarchy adapter.

## 5. Final Assessment

The research supports the feedback conclusion: analytics is the next logical extraction candidate before Re-ID.

- Why feasible:
  - Mainly consumes scene state and produces events.
  - Existing analytics-only path demonstrates architectural viability.
- Why still non-trivial:
  - Stateful event semantics, sensor histories, and hierarchy propagation need strict compatibility guarantees.
  - Contract discipline is the primary extraction risk, not algorithmic complexity.