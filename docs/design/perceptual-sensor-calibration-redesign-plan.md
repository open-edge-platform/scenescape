<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Perceptual sensor calibration — API redesign plan

Redesign plan for the AutoCalibration service following review of PR #1658
("ITEP-93047 Add point-cloud registration to `autocalibration` service").

- **Reference (working design):** [point-cloud-autocalibration-plan.md](./point-cloud-autocalibration-plan.md)
- **Architectural direction:** [ADR-12: Perception Sensor Ingress](../adr/0012-perception-sensor-ingress.md)

This document is built up in stages, each gated by approval:

1. Unification feasibility assessment — **approved** (phased approach; align API
   endpoint *and* code structures/methods with the modality-agnostic approach).
2. Phase 1 redesign + endpoint renaming and terminology alignment —
   **approved**.
3. Remediation of unresolved review comments (this section) — **awaiting final
   approval to implement**.

---

## Stage 1 — Unification feasibility assessment

**Question:** Can the legacy camera-calibration endpoint API be unified into the
new (point-cloud) endpoint API so that a single, modality-agnostic calibration
API serves multiple modalities in future (cameras **and** 3D point-cloud
sensors)?

**Short answer:** Yes — unification is feasible and is the direction ADR-12
prescribes (one ingress surface + strategy-based modality routing). However, a
*full* merge now (folding cameras into the new endpoint) is high-risk because of
Manager/UI coupling, identity-model differences, and backward compatibility. The
low-risk, ADR-aligned path is **phased**: introduce the generic modality-routed
calibration endpoint now (point-cloud only), keep the legacy camera endpoint
unchanged, and add the camera modality + deprecate the legacy endpoint later.

### Current state

| Concern | Legacy camera calibration | New point-cloud registration |
| --- | --- | --- |
| Endpoint | `POST/GET /v1/cameras/{cameraId}/calibration` | `POST/GET /v1/point-cloud-sensors/{sensorId}/registration` |
| Scene identity | Implicit — camera looked up in Manager DB via `scene_camera_with_id(cameraId)`; scene derived from camera | Explicit — `sceneId` supplied in request body |
| Manager coupling | Coupled — camera must exist and be bound to a scene | Decoupled — arbitrary `sensorId`, no DB entity |
| Strategy dispatch | Selected from `scene.camera_calibration` (AprilTag / Markerless / Manual) | Dispatched directly via `point_cloud_strategy`, independent of scene mode |
| Input payload | `image` (base64) + optional `intrinsics` | `pointcloud` (base64) + `format` + optional `initialTransform` |
| Async model | Background task + poll `GET` + Socket.IO `calibration_result` | Background task + poll `GET` + Socket.IO `point_cloud_registration_result` |
| Result | pose / quaternion / translation / calibration points | 4×4 transform / fitness / inlier RMSE |

Both flows already share the `CameraCalibrationController` base class, the
`scene_strategies` registry, the `calibration_results` store, and the
async-plus-poll-plus-socket pattern. The underlying mechanism is *already*
strategy-based modality routing — exactly what ADR-12 endorses.

### What makes unification feasible

1. **Strategy registry already exists.** `scene_strategies` maps a key to a
   controller implementing a common interface (`process_scene_for_calibration`,
   `generate_calibration`, `is_map_updated`, `reset_scene`). Adding a modality is
   registering a strategy — ADR-12 §3 verbatim.
2. **Shared async lifecycle.** Both endpoints trigger a background task, poll a
   `GET`, and emit a Socket.IO result. A single lifecycle can serve all
   modalities.
3. **Converging result contract.** Both ultimately return a sensor-to-scene
   pose/transform plus quality metrics; a common response envelope is natural.
4. **Common validation/error surface.** ID validation, error classes, size
   guards, and status polling are near-duplicate implementations ready to be
   consolidated behind one route.
5. **Explicit `sceneId` is the more general contract.** The point-cloud flow's
   "`sceneId` in body" model is a superset of the camera flow's implicit lookup
   and maps cleanly onto ADR-12's dual-identity plan.

### Conflicts and risks

| # | Conflict / risk | Severity | Notes / mitigation |
| --- | --- | --- | --- |
| R1 | **Identity model mismatch.** Camera uses DB-resolved `cameraId`→scene; point-cloud uses arbitrary `sensorId` + explicit `sceneId`. | High | ADR-12's `source_uid`/`source_key` dual identity is the long-term answer but is not implemented. Unified endpoint must accept explicit `sceneId` for all modalities; camera migration needs a resolver. Defer camera folding. |
| R2 | **Terminology overload (registration vs calibration).** "Registration" already means *scene preparation* (`/scenes/{id}/registration`); the point-cloud endpoint reused it for *sensor localization*, which cameras call *calibration*. | Medium | Reviewer-confirmed. Standardize: **registration = scene preparation**, **calibration = sensor localization**. Rename new endpoint accordingly. |
| R3 | **Input contract divergence.** `image`+`intrinsics` vs `pointcloud`+`format`+`initialTransform`. | Medium | Requires a modality-tagged polymorphic body (OpenAPI `discriminator`/`oneOf` keyed on `modality`), per ADR-12 §4. |
| R4 | **Dispatch-source difference.** Cameras route by per-scene `scene.camera_calibration` mode (Manager config); point-cloud routes by request. | Medium | Unified endpoint routes by request `modality`; must preserve camera behavior (strategy from scene mode) as a modality-specific sub-routing. Matches reviewer note that each modality owns its strategy set. |
| R5 | **Payload size / DoS.** Global `MAX_CONTENT_LENGTH` was raised to ~100 MB for point clouds, exposing image routes to oversized bodies. | Medium | Already an open review comment. Per-route/per-modality limits required in the unified design. |
| R6 | **Concurrency / locking.** Camera and point-cloud now use separate locks. | Low | Established pattern; unified design needs per-modality (or per-sensor) locking so modalities don't block each other. |
| R7 | **Backward compatibility.** `/cameras/{cameraId}/calibration` is published, documented, and covered by CALIB API scenarios; consumed by the Manager UI image-calibration flow. | High | ADR-12 mandates a compatibility + deprecation path. Do **not** remove in one shot. |
| R8 | **Manager UI coupling.** UI links every sensor to the camera image-calibration flow and renders camera frustums (ADR-12 Context). | High | Folding cameras pulls Manager/UI into scope, which the current PR deliberately kept decoupled. Defer to a later phase. |

### Recommendation

Proceed with unification **in phases**, mirroring ADR-12's migration strategy:

- **Phase 1 (now):** Introduce a generic, modality-routed **calibration**
  endpoint that currently accepts only point-cloud / perceptual-sensor input.
  Rename it to align with ADR-12 (`perceptual-sensor-calibration`) and adopt the
  registration-vs-calibration terminology split. Keep the legacy
  `/cameras/{cameraId}/calibration` endpoint **unchanged**. Reserve the
  `modality` routing seam.
- **Later phases:** Add the camera modality behind a `CameraStrategy` on the
  generic endpoint, wire dual-identity (`source_uid`/`source_key`), migrate the
  Manager UI, then deprecate and remove the legacy camera-only endpoint.

This keeps the current PR's decoupling intact, avoids breaking published camera
APIs and the Manager UI, and lands the codebase on the ADR-12 target
architecture incrementally.

**Approved** with the direction that the redesign aligns not only the API
endpoint but also the internal **code structures, classes, and methods** with
the modality-agnostic, calibration-terminology approach (below).

---

## Stage 2 — Phase 1 redesign: generic endpoint + naming alignment

**Goal of Phase 1:** introduce a single, modality-routed *perceptual sensor
calibration* endpoint that today accepts **only point-cloud input**, while the
legacy camera calibration endpoint stays **exactly as-is**. All new API surface
*and* internal code (files, classes, methods, locks, events, schemas) are named
for the modality-agnostic future and use the corrected terminology. The
`modality` routing seam is created now so that adding cameras later is a strategy
registration, not a re-architecture.

### Terminology rules (applied everywhere in this phase)

- **Registration** = *scene preparation* only (building/caching the scene model
  before localization). Keep on `/scenes/{sceneId}/registration`.
- **Calibration** = *sensor localization* (computing the sensor-to-scene pose /
  transform). This is what the new endpoint performs.
- The point-cloud ICP math is *algorithmically* "registration"; that term stays
  **contained inside the engine module** and is never exposed in the
  service/API/controller vocabulary.

### 2.1 API surface changes (additive; legacy camera endpoint untouched)

| Aspect | Now (PR) | Phase 1 (redesigned) |
| --- | --- | --- |
| Endpoint | `POST/GET /v1/point-cloud-sensors/{sensorId}/registration` | `POST/GET /v1/perceptual-sensors/{sensorId}/calibration` |
| Request body | `sceneId`, `pointcloud`, `format`, `initialTransform` | adds optional `modality` (default the single supported point-cloud modality); same point-cloud fields |
| Trigger status | `calibrating` / `busy` / `error` | unchanged (already calibration vocabulary) |
| Result payload | `transform`, `fitness`, `inlier_rmse`, `scene_name` | unchanged |
| Socket.IO register event | `register_point_cloud_sensor` | `register_perceptual_sensor` |
| Socket.IO result event | `point_cloud_registration_result` | `perceptual_sensor_calibration_result` |

Routing: the POST handler resolves the request `modality` to a strategy via a
modality→strategy registry. Phase 1 registers only the point-cloud strategy; an
unknown/unsupported modality returns `400`.

### 2.2 Code structure, class, and method renames

**API layer — `autocalibration/src/auto_camera_calibration_api.py`**

| Element | From | To |
| --- | --- | --- |
| Route fn (POST) | `register_point_cloud_sensor_calibration` | `calibrate_perceptual_sensor` |
| Route fn (GET) | `get_point_cloud_registration_status` | `get_perceptual_sensor_calibration_status` |
| Socket.IO handler | `handle_register_point_cloud_sensor` | `handle_register_perceptual_sensor` |
| OpenApi field const | `POINTCLOUD` / `SENSOR_ID` / `FORMAT` / `INITIAL_TRANSFORM` | keep; add `MODALITY` |
| Error class | `InvalidPointCloudError` | keep (point-cloud payload validation) |

**Context layer — `autocalibration/src/auto_camera_calibration_context.py`**

| Element | From | To |
| --- | --- | --- |
| Thread wrapper | `register_point_cloud_thread_wrapper` | `calibrate_perceptual_sensor_thread_wrapper` |
| Worker | `process_point_cloud_registration` | `process_perceptual_sensor_calibration` |
| Direct strategy ref | `point_cloud_strategy` | `sensor_calibration_strategies` (modality→strategy dict) |
| Lock | `point_cloud_thread_lock` (single) | `sensor_calibration_locks` (per-modality dict) |
| Socket result emit | `point_cloud_registration_result` | `perceptual_sensor_calibration_result` |

**Controller / strategy layer**

| Element | From | To |
| --- | --- | --- |
| File | `point_cloud_registration_controller.py` | `point_cloud_calibration_controller.py` |
| Class | `PointCloudRegistrationController` | `PointCloudCalibrationController` |
| Base class | `CameraCalibrationController` | new modality-agnostic `PerceptualSensorCalibrationController` interface (shared `calibration_data_interface`, `notify_scene_registration`, `process_scene_for_calibration`, `generate_calibration`); point-cloud strategy extends it. Camera strategies stay on their current base in Phase 1. |

**Engine layer — `autocalibration/src/point_cloud_registration.py`**

- **Unchanged in name** — this module is the ICP algorithm, where
  "registration" is the correct mathematical term. It is not part of the service
  vocabulary. (De-duplication of the repeated method flagged in review is handled
  in Stage 3.)

**Strategy key — `scene_common/src/scene_common/options.py`**

- Keep `POINTCLOUD = 'PointCloud'` as the point-cloud **modality/strategy key**;
  it becomes one entry in the modality→strategy registry.

### 2.3 Modality routing seam

```
request.modality ──▶ sensor_calibration_strategies[modality] ──▶ strategy.generate_calibration(...)
                     (Phase 1: only "PointCloud" registered)
```

- `sensor_calibration_strategies`: `{ modality_key: PerceptualSensorCalibrationController }`.
- `sensor_calibration_locks`: `{ modality_key: threading.Lock() }` so one
  modality's long job never reports another modality busy (addresses reviewer
  note that each modality owns its strategy set and lifecycle).
- Adding a modality later = register a strategy + lock; no handler edits
  (ADR-12 §3 Open/Closed).

### 2.4 Backward compatibility

- Legacy `POST/GET /v1/cameras/{cameraId}/calibration` and
  `/scenes/{sceneId}/registration` remain **unchanged and fully supported**.
- No Manager DB or UI changes; the new endpoint stays decoupled (`sceneId` in
  body).
- Camera folding, dual-identity (`source_uid`/`source_key`), and legacy
  deprecation are explicitly **out of Phase 1** (later phases).

### 2.5 Docs, OpenAPI, tests to update in Phase 1

- OpenAPI (`.../_assets/autocalibration-api.yaml`): rename schemas
  `PointCloudRegistration*` → `PerceptualSensorCalibration*`; new path
  `/perceptual-sensors/{sensorId}/calibration`; add optional `modality`.
- `api-reference.md` and `auto-calibration.md`: rename section/endpoints;
  clarify registration-vs-calibration terminology.
- Client (`autocalibration_client.py`): `registerPointCloud` →
  `calibratePerceptualSensor`; `getPointCloudRegistrationStatus` →
  `getPerceptualSensorCalibrationStatus`.
- API scenarios (`tests/api/scenarios/autocalibration_api.json`, CALIB/14–18):
  update `method` and path to the new names.
- Unit tests (`tests/sscape_tests/pointcloud/`): update controller class/method
  references; the engine-level algorithm tests are unaffected.
- `autocalibration/Agents.md` and the reference working design document.

> **STOP — awaiting approval of Stage 2 (Phase 1 redesign + naming) before
> extending the plan with Stage 3 (remediation of all unresolved review
> comments).**

---

## Stage 3 — Remediation of unresolved review comments

All unresolved review threads are folded into the Phase 1 work. The five
already-resolved threads (POST status reporting, dedicated point-cloud lock,
binascii/`TypeError` decode hardening, base64 trust-boundary, snake_case
fixtures) are not repeated here. The maintainer timeline request to *post a GIF /
benchmark numbers* is **out of scope** and intentionally skipped.

### 3.1 Remediation map

| # | Thread (author) | Issue | Remediation |
| --- | --- | --- | --- |
| C1 | RolX (copilot) | Raising global `MAX_CONTENT_LENGTH` lets legacy/image routes accept ~100 MB bodies before endpoint validation (DoS/memory risk). | Add an early `before_request` size guard that enforces the small limit on all non perceptual-sensor routes, allowing the large limit only for `/v1/perceptual-sensors/*`. See C6 for the size-constant reconciliation. |
| C2 | RomT (copilot) | Oversize warning logs "bytes" but measures the base64 **string** length (characters), not decoded bytes — misleading. | Fix the log message/units (report characters explicitly, or compute the decoded byte length) so limit tuning is accurate. |
| C3 | Romo (copilot) | `TEST_MEDIA_PATH` built via `os.path.join(__file__, ...)` is brittle. | Use `Path(__file__).resolve().parents[...]` in `tests/sscape_tests/pointcloud/conftest.py`. |
| C4 | RonA (copilot) | The `slow` >1M-point KPI test runs in the default unit target (`run_unit_tests` has no `-m` filter), risking flaky/long CI. | Make it opt-in via an env var gate (skip unless e.g. `RUN_POINTCLOUD_KPI` is set); keep the `slow` marker. |
| C5 | YcmM (saratpoluri) | Class names should reflect purpose. | Covered by the Stage 2 renames (`PointCloudCalibrationController`, new `PerceptualSensorCalibrationController` base, schema renames); audit remaining class names during implementation. |
| C6 | YgDO (saratpoluri) | `MAX_POINTCLOUD_SIZE` assumes a fixed bytes-per-point ratio, which PLY/PCD do not have; drop it and size `MAX_REQUEST_SIZE` for the largest expected payload. | Remove `MAX_POINTCLOUD_SIZE`. Size the perceptual-sensor route limit directly by payload bytes (not point count). Reconciled with C1: single generous global `MAX_CONTENT_LENGTH`, with a tighter per-route limit (e.g. `MAX_IMAGE_REQUEST_SIZE`) enforced for legacy/image routes via the C1 guard. |
| C7 | YidU (saratpoluri) | `fmt` is derivable from the header, so passing it into the validator is redundant. | Make magic-byte detection the single source of truth: drop the `fmt` parameter from `_validate_pointcloud` (detect from bytes). Keep the request `format` field optional, used only as a decode-time consistency assertion in `decode_point_cloud` (mismatch → 400); flag full removal of `format` as an optional follow-up. |
| C8 | ZZXz (saratpoluri) | "registration" is overloaded; point-cloud localization should be *calibration*; on merge it becomes a private method under perceptual-sensor calibration. | Satisfied by Stage 2: the endpoint/method/vocabulary become *calibration*, and the point-cloud path is the strategy invoked internally by `calibrate_perceptual_sensor` via the modality registry (no separate public endpoint). |
| C9 | ZjHd (saratpoluri) | Each modality may own its strategy set; strategy choice should be automated by modality routing, with a per-modality default + static config, not a single user-provided config path. | Build on the Stage 2 modality seam: resolve the strategy/config **by modality** (`sensor_calibration_strategies[modality]`), give each modality a default strategy and its own static config, and remove reliance on a single global config path. Dynamic/auto strategy selection remains future work. |
| C10 | ZmM5 (saratpoluri) | "method content repeated twice" in `point_cloud_registration.py`. | The point-cloud format-detection logic is duplicated between the engine (`detect_format`, line ~64) and the API (`_validate_pointcloud`). Consolidate into the engine's `detect_format` and have the API validator call it. Verify the exact anchored duplication at implementation time and remove any residual repeated block. |

### 3.2 Size-limit reconciliation (C1 + C6)

The copilot (per-route guard) and maintainer (drop point-count bound; enlarge
request size) comments are complementary:

- Remove `MAX_POINTCLOUD_SIZE` (point-count-derived) entirely.
- Set the Flask global `MAX_CONTENT_LENGTH` to a single generous limit sized in
  **bytes** for the largest expected perceptual-sensor payload.
- Add a `before_request` guard enforcing a tighter `MAX_IMAGE_REQUEST_SIZE`
  (renamed from the old `MAX_REQUEST_SIZE`) on every route **except**
  `/v1/perceptual-sensors/*`, so legacy/image endpoints are not exposed to
  oversized bodies.

This satisfies the DoS concern (C1) and the sizing/naming correction (C6)
simultaneously.

### 3.3 Ordering with Phase 1

All remediations land **within** the Phase 1 implementation (same files are
already being renamed/moved), so they are not a separate pass:

1. API renames + size-limit reconciliation (C1, C2, C6, C7) and detection
   consolidation (C10) in `auto_camera_calibration_api.py` /
   `point_cloud_registration.py`.
2. Context/controller renames + modality-scoped strategy & config routing (C5,
   C8, C9).
3. Test + fixture fixes (C3, C4) and scenario/client/doc/OpenAPI renames.

> **STOP — awaiting final approval to begin implementation of Phases described
> above (Stage 2 redesign + Stage 3 remediation).**
