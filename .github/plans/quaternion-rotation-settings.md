<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Quaternion Rotation Settings

## Status

Proposed follow-up to PR #2117. The live camera output and unified Analytics
camera-state changes are separate from this migration. This document proposes
implementation and release gates; it does not change existing contracts.

## Problem

Live regulated camera messages now publish normalized quaternions, while
persisted settings expose Euler angles through REST, forms, and scene archives.
Camera REST even accepts quaternion input and converts it to Euler for storage.
Consumers must know implicit units, rotation order, and representation-specific
behavior. Changing live output alone does not resolve those durable contracts.

The goal is one canonical quaternion representation for stored rotational
components and new machine-facing interfaces. Euler angles remain appropriate
for human-editable controls and temporary compatibility projections.

## Current Surfaces

Paths below are relative to the repository root.

| Domain                      | Storage and exposure                                                                                                                                                         | Owning implementation                                                                                                                                                                      |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Camera calibration          | `Cam.transforms` and `transform_type`; REST `rotation`; cameras nested in scene responses. Quaternion writes become Euler degrees. Point correspondences are also supported. | `manager/src/manager/models.py`, `manager/src/manager/serializers.py` (`CamSerializer`)                                                                                                    |
| Scene mesh placement        | `Scene.rotation_x/y/z` in degrees; REST `mesh_rotation`; Scene Settings and scene-edit forms.                                                                                | `manager/src/manager/serializers.py` (`handleMeshTransform`), `manager/src/manager/static/js/thing/scene.js`                                                                               |
| Source-map placement        | Per-method JSON `transform.rotation` copies scene Euler degrees; map APIs expose it and activation restores it.                                                              | `manager/src/manager/mapping_store.py`, `manager/src/manager/api.py`                                                                                                                       |
| Child-scene alignment       | Raw transform fields support multiple representations; scene-level updates store Euler degrees and derived transforms expose Euler through `CameraPose.asDict`.              | `manager/src/manager/serializers.py` (`ChildSceneSerializer`, `update_child_transform`), `scene_common/src/scene_common/transform.py`                                                      |
| Asset alignment             | `Asset3D.rotation_x/y/z` in degrees; asset REST, edit forms, and viewer configuration.                                                                                       | `manager/src/manager/models.py`, `manager/src/manager/serializers.py`, `manager/src/manager/templates/scene/scene_detail.html`                                                             |
| Archives and calibration UI | Export embeds scene REST JSON; import treats non-correspondence camera transforms as Euler; calibration initialization and camera Save use Euler.                            | `manager/src/manager/scene_import.py`, `manager/src/manager/static/js/sscape.js`, `manager/src/manager/static/js/cameracalibrate.js`, `manager/src/manager/static/js/thing/scenecamera.js` |

The related `/api/v1/calculateintrinsics` result exposes `euler` in radians,
not stored degrees. Include it in consumer migration, but distinguish this
calculated result from persisted calibration.

## Scope and Non-goals

- Cover all five stored domains, their REST and form writers, import/export,
  and services that hydrate those settings.
- Preserve existing coordinate frames, transform direction, handedness,
  translation, scale, camera optics, and projection behavior.
- Do not replace point-correspondence calibration inputs with a quaternion.
  Retain correspondences as calibration source data and derive orientation.
- Do not reduce arbitrary matrices to quaternions. Preserve matrix transforms
  where shear, reflection, or other non-rotational content would be lost.
- Do not redesign live tracking, camera-state ownership, or MQTT topics.
  Existing supported Euler telemetry inputs are outside this migration.
- Do not migrate scalar geospatial `map_bearing` or unrelated 2D headings.
- Do not remove Euler UI controls or compatibility fields in the initial PR.

## Target Contract

### Rotation Semantics and Validation

- Use scalar-last `[x, y, z, w]`, matching SciPy and Three.js. Quaternions
  represent active rotations from each object's local frame into its owning
  scene or parent frame; verify existing conventions per domain before coding.
- Publish each domain's frame definition and multiplication order explicitly.
  A representation migration must not introduce a Y-up/Y-down conversion.
- Require exactly four finite numeric components; reject booleans, zero or
  near-zero norm, and inputs that cannot be safely normalized. Agree a shared
  norm threshold and angular comparison tolerance in the contract tests.
- Normalize accepted values using existing math libraries. Treat `q` and `-q`
  as the same rotation. Define deterministic sign selection for persisted
  values without imposing discontinuities on live interpolation.
- Keep legacy units explicit: persisted Euler settings use degrees; the
  calibration-result `euler` field uses radians. Verify each legacy rotation
  order from its current conversion code instead of assuming all are alike.
- Preserve omitted fields on partial updates. Reject invalid or conflicting
  input before changing stored state; never silently replace it with identity.

### REST Compatibility

Use additive, explicitly named fields in the initial release. Proposed names
are `rotation_quaternion` for poses, assets, and transform objects, and
`mesh_rotation_quaternion` for scene mesh alignment. Approve names and OpenAPI
schemas before implementation.

1. Keep existing v1 Euler fields and their units unchanged. Do not silently
   change a three-element `rotation` into a four-element array.
2. Return canonical quaternion fields alongside derived legacy fields.
   Preserve existing `transform_type` and raw-transform response semantics
   through compatibility serialization, not accidental storage leakage.
3. Accept legacy-only writes through an explicit boundary conversion. Accept
   quaternion-only writes directly. If both representations are supplied,
   require equivalent rotations within the agreed angular tolerance or return
   a field-specific validation error. Do not silently choose one.
4. Document how read-modify-write clients must omit stale alternate rotation
   fields. Test partial updates and responses reposted without modification.
5. Add a quaternion result to `calculateintrinsics`; retain its existing
   `euler` radians field until separately deprecated.
6. Route forms, REST, imports, source-map activation, and calibration saves
   through the same domain validation and persistence paths.

Removing legacy fields requires an explicitly versioned contract or approved
breaking-release policy, a published deprecation period, and consumer migration
evidence. It is not part of the additive rollout.

### Canonical Storage and Migration

- Add nullable canonical quaternion storage using existing model field
  conventions. For JSON transforms, add an explicitly named quaternion field
  and a documented format version. Null during migration means not converted,
  not identity.
- Use canonical quaternions as the sole orientation authority once backfilled.
  Any retained Euler columns or JSON fields are compatibility projections,
  updated transactionally by the same writer, never independent authorities.
- For point-correspondence cameras, derive orientation from the calibrated
  pose without replacing source correspondences. If a derived pose is cached,
  define invalidation on correspondence, intrinsics, and distortion changes.
- Inventory every writer, including forms, management commands, fixtures,
  direct ORM updates, source-map activation, and calibration services. Do not
  enable canonical reads while old writers can leave stale values behind.
- Generate and commit reviewed Django migrations following
  `manager/MIGRATIONS.md`; never generate migrations during deployment.
- Backfill each representation using its existing semantics. Use historical
  Django models and migration-stable conversion logic. Record malformed or
  unsupported records by identifier without exposing private data; abort the
  affected migration safely rather than silently dropping a rotation.
- Preserve original calibration and matrix data. Verify reconstructed
  transforms before replacing authority, including negative scale and
  reflection cases. Leave unsupported general matrices in their native form.
- Make backfill/recovery bounded and restart-safe. Protect source-map and scene
  alignment updates with the existing scene-row locking discipline so activation
  and replacement cannot leave mismatched representations.
- Retain legacy projections through the rollback window. Reconcile from
  canonical data when rolling back; Euler triples need not match original
  numbers, but their rotations must be equivalent. Back up the database and
  stored source-map metadata before rollout.

## Implementation Sequence

### 1. Freeze Contracts and Characterize Existing Behavior

- Confirm the surface inventory and all readers/writers, especially Controller,
  Analytics, Autocalibration, shared `CameraPose`, and sample/config consumers.
- Add characterization coverage for current rotations, units, transform
  composition, and camera frame conversions before changing serialization.
- Approve field names, normalization/sign rules, tolerances, archive versioning,
  compatibility duration, and the exact database expansion/backfill design.
- Add explicit quaternion serialization without changing `CameraPose.asDict`
  globally; audit its call sites before any later removal of Euler output.

### 2. Add Storage and Backward-compatible APIs

- Land shared conversion/validation helpers, additive schema, migrations,
  canonical writers, and compatibility serializers with regression tests.
- Cover cameras, scene meshes, child scenes, assets, and source maps together
  before declaring persisted settings consistent. Keep changes in reviewable
  domain-focused commits with shared helpers first.
- Ensure camera quaternion writes no longer make an Euler round trip before
  canonical persistence. Legacy Euler output is a derived view only.

### 3. Migrate Consumers and Archives

- Update service hydration to prefer explicit quaternion fields, with a
  narrowly scoped fallback for older Manager responses during transition.
- Update camera calibration, 3D settings, scene forms, asset forms, and viewer
  initialization. Convert to Euler only at angle controls; preserve canonical
  orientation unless the user actually edits those controls.
- Preserve existing camera frame conversions exactly once. Save and reload,
  preview/cancel, and live-pose updates must not overwrite configured poses.
- Version archive rotation semantics. New importers accept existing unversioned
  Euler archives and the new quaternion format; reject unsupported future
  versions clearly. Provide a documented legacy export during the transition
  for older installations, and test it with the old import contract.
- Update source-map save, listing, activation, replacement, and deletion flows
  to keep the canonical transform and compatibility output consistent.

### 4. Document, Roll Out, and Deprecate Separately

- Update `docs/user-guide/api-docs/api.yaml`,
  `docs/user-guide/api-reference.md`, relevant service data-format docs,
  calibration/settings guides, sample configurations, and archive migration
  instructions with field names, units, frames, and compatibility examples.
- Rehearse expansion, backfill, application upgrade, and rollback on a copy of
  a representative PostgreSQL database and stored map metadata.
- Default to a maintenance window with all legacy writers stopped for the
  backfill/cutover. Do not claim mixed-version writes are supported unless
  explicitly designed and verified. Additive REST alone is insufficient.
- Check migrated record counts, invalid-record reports, and transform
  equivalence before reopening writes. Exercise existing consumers against
  the new API and new consumers against the documented fallback.
- Remove legacy storage/fields only in a subsequent approved release after
  the compatibility window and migration evidence are complete.

## Verification and Acceptance

- Rotation tests: identity, nontrivial multi-axis rotations, 180-degree turns,
  gimbal-lock neighborhoods, angle wraparound, `q` versus `-q`, non-unit input,
  malformed arrays, booleans, non-finite numbers, and near-zero norm.
- Compare rotation matrices or angular distance, not Euler component equality
  or exact quaternion sign. Include basis-vector and projected-pixel checks
  to catch inverse rotations, axis swaps, and duplicate frame conversions.
- API tests: all five domains, nested responses, legacy/quaternion writes,
  conflicting dual input, partial updates, and invalid-write nonmutation.
- Migration tests: existing Euler, quaternion, matrix, and correspondence
  records; incomplete/malformed records; backfill recovery and rollback;
  equivalent translation/rotation/scale and unchanged camera projections.
- PostgreSQL integration tests: concurrent source-map activation/replacement
  and settings updates. SQLite-only coverage does not satisfy this gate.
- Archive tests: historical ZIP import, new-format round trip, legacy export,
  unsupported-version rejection, and nested child/camera settings preservation.
- UI tests: load/edit/save/reload for cameras, meshes, child scenes, and assets;
  calibration results; source switching; preview/cancel; and live camera motion
  without modifying persisted calibration. Include singular-angle cases.
- Reuse existing suites and helpers. Execute the appropriate repository
  Makefile test targets, including the affected unit and integration targets;
  static checks alone do not satisfy runtime acceptance. Follow
  `.github/skills/testing/SKILL.md` and the image freshness/rebuild requirements
  in `.github/skills/test-verification-gate/SKILL.md`.
- Run required Python complexity checks for touched services, indentation and
  changed-code lint checks, and `make prettier-check` for documentation.
  Report commands, pass/fail counts, skips, and any unverified rollout gates.

Complete the additive migration only when every in-scope writer maintains the
canonical quaternion authority, old supported clients remain functional,
existing transforms are geometrically equivalent, and upgrade/rollback have
been demonstrated. Keep legacy-field removal tracked as a separate milestone.
