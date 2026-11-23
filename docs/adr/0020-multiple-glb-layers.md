<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 0020: Multiple GLB Layers per Geospatial Scene

- **Author(s)**: Emilia Anna Lukasiuk
- **Date**: 2026-10-07
- **Status**: `Accepted`
- **Supersedes**: none

## Context

A geospatial scene holds one GLB model applied over its flat base map. Sites often need several
models (for example one per building). The scene artifact that the controller and viewers read is a
single map with a single pose, so more than one model needs a single combined artifact.

## Decision

- Each scene stores zero or more GLB layers. Each layer has its own anchor, its own enabled flag and an order
  equal to upload order. The order is the merge order.
- Scene artifact: bake. With exactly one enabled layer, the artifact is today's: `scene.map` is a copy of the raw
  GLB and the pose stays in `rotation_*` and `translation_*`. With two or more enabled layers, each layer is posed
  with `CameraPose._poseToPoseMat(translation, rotation, [1,1,1])`, the layers are merged with `mergeMesh` and
  concatenated, the result is written to `scene.map`, and the scene pose is identity.
- `Scene.use_glb_map` stays a stored field. It is written only by the single writer `build_scene_map` and always
  equals `any(layer.enabled)`.
- The layers are the only source of truth. The earlier dual-write, mirror, adapter and contract phases are not
  needed because the GLB work is unreleased on this branch. Migration 0012 is edited in place.
- Maximum layer count comes from `GLB_MAX_LAYERS` (default `1`, which keeps today's behaviour).

### Bake spike (M0)

Spike under `/tmp` with two and four textured GLBs of about 50k faces each, using the exact mesh and pose
functions above:

- Texture kind is kept after the merge, and the colour of each layer's texture is present in the atlas.
- The baked XY footprint at identity pose equals the union of the posed footprints (error 0.0 m, tolerance 1e-3 m).
- Bake time (trimesh merge, pose and concatenate, no export): N=1 0.03 s, N=2 0.06 s, N=4 0.12 s.
  Export time for N=4 is 0.04 s.

## Alternatives Considered

- Native multi-GLB artifact (controller and viewers render several models): needs a controller and viewer
  contract change and a new artifact format. Out of scope for this feature.
- Per-layer pose stored on the layer: rejected. The pose is derived from the flat frame and the anchor at apply,
  move and rebuild time, so a cached value would go stale when the frame changes.
- Dual-write and adapter phases from the design plan: rejected. No deployed data holds the new fields.

## Consequences

### Positive

- Single-layer scenes keep byte-for-byte today's artifact and pose.
- Viewers, the controller and the hybrid thumbnail need no change: a baked scene is one map with corners.
- Bake cost is small at the sizes measured.

### Negative

- With two or more layers, the posed layer geometry is baked into one file, so the individual pose of a layer is
  no longer visible in the scene artifact. Each layer's pose is recomputed from its anchor.
- Each layer change rebuilds the whole artifact. This cost grows with the layer count and the face count.
