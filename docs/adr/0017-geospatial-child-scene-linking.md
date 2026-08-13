<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 17: Geospatial Child-Scene Linking

- **Author(s)**: Scenescape
- **Date**: 2026-08-13
- **Status**: `Accepted`

## Context

Linking a child scene required the user to type a 9-number Euler pose
(translation, rotation, scale) that maps child-local meters into parent-local
meters. That pose is stored on `ChildScene` and applied by the Scene Controller
and Manager overlays. When both scenes already have four-corner geospatial
calibration (`output_lla` + `map_corners_lla`), the pose is determined by
Earth's frame and should not be a survey problem for the operator.

## Decision

- Compute the child-to-parent pose **on the Manager at save time** from each
  scene's local XYZ map corners and `map_corners_lla`, via
  `inv(T_parent_xyz_to_ecef) @ T_child_xyz_to_ecef`.
- Decompose the result to Euler translation / rotation / scale and **store it
  on `ChildScene`** in the existing transform columns. The controller contract
  is unchanged.
- Record `transform_source`: `manual` (default, backward compatible) or
  `geospatial`. Geospatial links are recomputed when either scene's map,
  scale, or corners change. Manual links are never overwritten.
- Preview: `POST /api/v1/childscene/preview-geospatial-transform/` returns the
  pose without writing the database.

## Alternatives Considered

- **Runtime-only derivation in the controller** — single source of truth from
  corners, but remote children still need a stored matrix and the controller
  already consumes `transform` from scene REST. Deferred.
- **Trust cached `trs_matrix`** — often stale or unset until the controller
  writes it back. Rejected; always refit from corners.
- **Interactive overlay / point correspondence for non-geo scenes** — better UX
  when there is no Earth frame; follow-on as 3D gizmo placement
  ([ADR 18](./0018-3d-child-scene-placement.md)), not 2D map snap.

## Consequences

### Positive

- Georeferenced campuses can link buildings without typing meters and degrees.
- Existing MQTT / overlay transform application stays the same.
- Operators can still override with manual Euler values.

### Negative

- Remote children cannot auto-link until the parent has the child's corners
  (REST-to-remote is still unimplemented).
- Pose accuracy is bounded by the existing geospatial assumptions (~1 m for
  locally flat scenes under ~400 m). The save-time residual gate is
  ``max(2 m, 0.5% of the larger map span)`` so intersection→block stays
  tight while block→campus is not rejected solely because the parent grew.

## References

- [Configure a hierarchy of scenes](../user-guide/how-to-guides/build-a-scene/configure-hierarchy-of-scenes.md)
- [Configure geospatial coordinates](../user-guide/how-to-guides/build-a-scene/configure-geospatial-coordinates.md)
