<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 18: 3D Child-Scene Placement (Non-Georeferenced)

- **Author(s)**: Scenescape
- **Date**: 2026-08-13
- **Status**: `Accepted`

## Context

When both parent and child scenes are georeferenced, ADR 17 computes the
stored Euler pose from map corners. When they are not, operators still had
to type nine Euler numbers. Non-geo linking is a 3D placement problem in
scene-local meters (X along map width, Y along map height, Z up) — the same
AABB used by geospatial hierarchy — not a 2D overlay or 2-point snap on the
scene map.

A full React 3D viewport that replaces `scenescape3d.js` (~4.3k LOC) is a
later epic ([manager-ui.md](../../.github/plans/manager-ui.md) §3). Hierarchy
linking should not wait on that rewrite and must not stretch the 2D SVG map.

## Decision

- Ship a **thin 3D placement widget** in the Manager UI: parent map or GLB is
  the world; the child is a second `Object3D` with TransformControls.
- Run the canvas **Z-up** (`camera.up = (0,0,1)`) so gizmo axes match stored
  Euler. Do not reuse camera `togglePoseYupYdown` (that is CV Y-down).
- Persist the same `ChildScene` Euler contract as today
  (`p_parent = R @ (s * p_child) + t`). Add `transform_source=visual`
  (alongside `geospatial` / `manual`). Visual links are never auto-refreshed
  when corners or scale change.
- Isolate Euler ↔ Three conversion in `manager/ui/src/placement/poseThree.ts`
  with roundtrip tests so §3 can remount the same module.
- If either scene has no map image or GLB, keep numeric Advanced fields only.

## Alternatives Considered

- **2-point / overlay snap on the 2D map** — cheaper UI, but the stored pose
  is 3D (including Z and yaw about Z). Rejected as the lead path.
- **Rewrite or wrap `scenescape3d.js`** — too large a surface for child
  linking; deferred to the viewport epic.
- **Stretch `#svgout` / Snap** — 2D only; does not match scene-local meters.

## Consequences

### Positive

- Non-geo campuses can place a child without typing meters and degrees.
- Controller / MQTT contract unchanged.
- Future 3D viewport can reuse the pose and gizmo helpers.

### Negative

- Remote children get the widget only when a child map is already on the
  parent; no auto-fetch of remote maps.
- Placement requires WebGL in the browser (CI functional tests use REST only).

## References

- [ADR 17: Geospatial Child-Scene Linking](./0017-geospatial-child-scene-linking.md)
- [Configure a hierarchy of scenes](../user-guide/how-to-guides/build-a-scene/configure-hierarchy-of-scenes.md)
- [Manager UI plan §3](../../.github/plans/manager-ui.md)
