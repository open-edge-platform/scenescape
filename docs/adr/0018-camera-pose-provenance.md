<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 18: Camera Pose Provenance (`class` + `origin`)

- **Author(s)**: Sarat Poluri
- **Date**: 2026-11-03
- **Status**: `Accepted`
- **Related**: [Camera Pose Lock](../user-guide/api-reference.md#camera-pose-lock),
  [Analytics regulated cameras](../user-guide/microservices/analytics/data_formats.md),
  [ADR 16 — Unified External-Source Ingestion](./0016-unified-external-source-ingestion.md)

## TLDR

Publish **pose provenance** on runtime camera state as `{ class, origin }`
(plus optional `updated_at`). Keep a single effective runtime pose for all
consumers. Replace regulated `dynamic_pose` with UI follow derived from
`class === "live"`. Keep today’s unary `pose_locked` write gate for now.
**Phase 2** (later): express write authority as a policy over provenance
`origin` values, with `pose_locked` as a preset.

**Out of scope:** intrinsics / distortion / resolution provenance. This ADR
covers only the sensor **pose** (extrinsics). MQTT optics may share the
unlocked ephemeral apply path with extrinsics, but they do **not** get a
separate provenance object, do **not** stamp `pose_provenance` on optics-only
updates, and `pose_provenance` must not be read as “who last wrote
intrinsics.”

**Modalities:** Manager models posed perceptual sensors as `Cam` (topic
`scenescape/data/camera/{id}`). The same lock, ephemeral pose/optics, and
pose-only provenance rules apply whether the physical device is an RGB camera,
depth camera, or a LiDAR/radar (or similar) detector registered as a `Cam`.
Dynamic agents and other sources that publish via ADR 16 use a separate TTL
pose/intrinsics cache that is also ephemeral and also lacks optics provenance;
they are not yet stamped with regulated `pose_provenance`.

## Context

Runtime camera pose already has two concerns that share vocabulary poorly:

1. **Authority** — who may change the effective pose (`pose_locked` today:
   calibration-only vs allow live extrinsics).
2. **Provenance / UI follow** — whether the current effective pose came from
   durable calibration or from an accepted live message, and whether the 3D UI
   should apply that pose this frame.

Previously, Analytics published `dynamic_pose` as a derived bit
(`!pose_locked && pose_source == observation`) so the Manager 3D UI could skip
static cameras and avoid overwriting unsaved gizmo edits until a live
observation had actually taken the runtime pose. Internally,
`pose_source` was only the coarse pair `configured` | `observation`.

Problems:

- `dynamic_pose` sounds like a second pose mode; tracking already uses one
  effective pose either way.
- `configured` / `observation` lose writer fidelity (REST, mesh, detector
  extrinsics, external source, … all collapse).
- Richer write ACLs (who may write) need named origins; a boolean lock cannot
  express channel-specific policy without growing special cases.

We want provenance that is traceable end-to-end, enough structure for the UI
to drop `dynamic_pose`, and a clear deferral for origin-scoped write policy.

## Decision

### Single effective pose

Controller, Analytics, and UI continue to treat **one** runtime pose per
camera for projection, visibility, and display. Provenance describes that
pose; it does not create a parallel pose channel.

### Provenance shape

Runtime camera state (and regulated `cameras[]` entries) carry:

```json
{
  "pose_provenance": {
    "class": "calibration",
    "origin": "manager.rest",
    "updated_at": "2026-11-03T20:00:00Z"
  }
}
```

`class` is `"calibration"` or `"live"`; `origin` is an extensible string;
`updated_at` is optional ISO 8601.

| Field        | Role                                                                                          |
| ------------ | --------------------------------------------------------------------------------------------- |
| `class`      | Stable behavioral bucket. UI and simple consumers gate on this.                               |
| `origin`     | Extensible writer identity for forensics and (phase 2) write policy.                          |
| `updated_at` | Optional time of last accepted write to the runtime pose (implementation may omit initially). |

**`class` values:**

- `calibration` — effective pose is still the durable Manager calibration
  (or equivalent config refresh), even if the camera is unlocked.
- `live` — a live ingestion path has superseded calibration in runtime.

**Initial `origin` catalog** (non-exhaustive; unknown writers use
`unknown` until tagged):

| Origin                | Typical writer                               |
| --------------------- | -------------------------------------------- |
| `manager.rest`        | Camera create/update via REST / 3D save      |
| `manager.mesh`        | Generate Mesh pose install                   |
| `manager.import`      | Scene archive import                         |
| `detector.extrinsics` | Camera MQTT detection `extrinsics`           |
| `external_source`     | Unified external-source path (ADR 16)        |
| `unknown`             | Untagged until the path stamps a real origin |

Stamp provenance on every accepted runtime pose write. Config refresh that
reloads calibration resets `class` to `calibration` with an appropriate
`manager.*` origin (from persisted `Cam.calibration_origin`, or `unknown` when
untagged) unless phase-1 retention rules keep a prior live pose (same retention
behavior as today for unlocked observed poses).

### Replace `dynamic_pose`

- Regulated camera entries publish `pose_provenance` instead of relying on
  `dynamic_pose` as the UI contract.
- Manager 3D UI applies regulated poses when
  `!pose_locked && pose_provenance.class === "live"`
  (and existing unlock checks), not when `dynamic_pose === true`.
- **Compatibility:** during rollout, Analytics may still emit
  `dynamic_pose` as a deprecated alias of `class === "live"`. New consumers
  must use `pose_provenance`. Remove the alias once UI and tests no longer
  read `dynamic_pose`.
- Internal `pose_source` constants may map onto `class` during migration;
  new code should prefer provenance objects.

### Phase 1 write authority (unchanged product behavior)

Keep unary `pose_locked`:

- `true` — ignore live extrinsics/optics overrides; durable calibration wins
  on refresh.
- `false` — valid live extrinsics may update the runtime pose and set
  `class: "live"` with the writer’s `origin`. Unlocked MQTT optics
  (`intrinsics` / `distortion` / `resolution`) may update the runtime
  observation on the same ephemeral path, but optics-only acceptance does
  **not** change `pose_provenance`.

Do **not** implement origin allow/deny lists in phase 1.

### Non-goal: intrinsics provenance

`pose_provenance` describes the effective **pose** only. There is no
`intrinsics_provenance`, `optics_provenance`, or equivalent field in this
ADR. Durable Manager saves still persist calibration optics without a
parallel provenance channel for who last wrote `fx`/`fy`/`cx`/`cy`,
distortion, or resolution. A future ADR may introduce optics provenance if
forensics or UI follow need it; until then, consumers must not infer optics
authorship from `pose_provenance`.

### Phase 2 (later): write authority as policy over origins

Defer implementation. Intent when scheduled:

- Express who may write the runtime pose as a policy over `origin` values
  (allow-list and/or deny-list), optionally plus principal/role for REST.
- Treat `pose_locked` as a **preset** (“calibration-only” ≈ allow only
  `manager.*` origins), not as a competing model.
- Enforce policy **before** write; provenance remains a **fact** about the
  last accepted write (never infer permission from the last writer alone).

Phase 2 is out of scope for the first landing of this ADR’s code changes.

## Alternatives Considered

- **Keep `dynamic_pose` only** — preserves UI optimization but blocks
  traceability and origin-scoped ACLs; naming continues to imply a second
  pose mode.
- **Flat high-cardinality enum** (e.g. `manager_rest`, `detector_extrinsics`)
  without `class` — every consumer re-implements “is this live?”; UI gate
  becomes fragile.
- **Apply-by-delta UI only** (no provenance) — treats poses uniformly on the
  wire but cannot distinguish “still on calibration” from “live claimed,” so
  regulated calibration poses can undo unsaved gizmo edits before the first
  observation.
- **Ship origin write ACL in the same change** — desirable long-term, but
  couples rollout risk; defer as phase 2 while replacing `dynamic_pose` and
  introducing provenance now.

## Consequences

### Positive

- Clear split: one pose value; provenance for traceability; lock for phase-1
  authority; UI follow derived from `class`.
- `origin` vocabulary ready for phase-2 write policy and forensics.
- Removes conceptual conflict between “pose is always the same” and
  “UI should not thrash static cameras.”
- Aligns with existing provenance-minded ADRs (e.g. ADR 15/16) without
  requiring those systems to change in phase 1.

### Negative

- Wire and docs churn: regulated schema, Analytics serialization, 3D
  `CameraManager.updatePoses`, tests, user-guide data formats.
- Temporary dual field (`dynamic_pose` alias) during migration.
- Origin tagging will be incomplete until each writer path is updated;
  early `unknown` origins reduce forensic value.
- Phase-2 ACL design (channel vs principal, presets, defaults) remains
  unresolved until that work starts.
- Intrinsics / optics writers remain untracked: MQTT and Manager optics
  updates are not attributable via `pose_provenance`, so pose follow and
  pose forensics do not answer “whose intrinsics are these?”

## References

- UI follow gate:
  `manager/src/manager/static/js/thing/managers/cameramanager.js`
  (`updatePoses` follows `pose_provenance.class === "live"`, with
  deprecated `dynamic_pose` alias)
- Regulated serialization:
  `analytics/src/analytics/service.py` (`_camera_state` publishes
  `pose_provenance`; `dynamic_pose` aliases `class === "live"`)
- Runtime stamp sites:
  `scene_common/src/scene_common/scene_model.py`
  (`updateCameraPose`, `_retainObservedPose`) and
  `scene_common/src/scene_common/camera.py`
- Durable origin persistence: `Cam.calibration_origin` (Manager REST /
  mesh / import)
- `docs/user-guide/api-reference.md` — Camera Pose Lock
- `docs/user-guide/microservices/analytics/data_formats.md` — regulated
  `cameras` list
