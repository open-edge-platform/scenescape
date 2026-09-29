<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Reconstruction Adapter Review

## VGGT Follow-Up

- Fixed: `scale_intrinsics_to_original_size` now inverts the actual
  shorter-side resize + center crop via `image_transforms.vggt_transform`,
  which `_preprocess_images` also uses so both sides share one arithmetic.
- Fixed: metric scaling now takes the median metric/model distance ratio over
  frame pairs matched by index (`_metric_scale_from_camera_locations`), instead
  of dividing the shortest supplied baseline by the model's first two cameras.
  Scale is still skipped (and logged) when fewer than two frames carry a prior.

## MapAnything Review

- The image-only path is relatively direct: `infer` supplies per-view depth,
  camera-to-world poses, recovered pinhole intrinsics, and a combined validity
  and geometry-edge mask. The adapter reconstructs world points from depth,
  intrinsics, and poses, and uses MapAnything's image-grid mesh exporter. The
  exporter and returned poses receive the same 180-degree world-X rotation.
- Fixed: original-image intrinsics are restored with
  `image_transforms.mapanything_transform`, which mirrors the vendor
  `crop_resize_if_necessary` path (cover-scale with the **maximum** ratio,
  floor, center crop). The earlier adapter used the minimum ratio and no crop;
  for a 1920x1080 frame targeting 518x392 that meant scale 0.270 instead of
  0.363 and a missing 89 px offset.
- Implemented: `camera_intrinsics` (per uploaded image, in its pixels) and
  `camera_location` (camera-to-world, OpenCV axes, quaternion `[x,y,z,w]`) are
  now forwarded by the API and attached to MapAnything views as `intrinsics`
  (transformed into model pixels) and `camera_poses`. Pose priors are dropped
  with a warning when view 0 has none, per the vendor constraint. The handheld
  client rescales manifest intrinsics to the uploaded size (`upload_intrinsics`)
  so `max_upload_side_px` no longer desynchronizes calibration from pixels.
- Returned intrinsics are still pinhole estimates recovered from predicted
  rays. The API does not yet label the export world frame or the provenance of
  scale/intrinsics; treat them as estimates before updating camera records.

## Regression Checks

- Done (host-runnable): `tests/test_image_transforms.py` round-trips synthetic
  intrinsics through both transforms for square, landscape, portrait, odd, and
  mixed-aspect targets; `test_api_service.py` covers `camera_intrinsics`
  forwarding and rejection (needs the mapping container for Flask).
- Open: with synthetic depth and known camera poses, assert exported GLB
  vertices and returned camera poses share one world frame for mesh and
  pointcloud modes. With pose conditioning, MapAnything expresses outputs in
  the reference (view 0) frame; the handheld `estimate_map_T_model` alignment
  still applies and should now fit a near-rigid transform with scale ~1.
- Open: adapter-level tests for image order, camera IDs, masks, and
  empty/invalid model outputs; these need the container environment.
- Field check for the repeated-surface symptom: re-run a handheld session with
  `max_upload_side_px` set and confirm the service logs
  `N with intrinsics, N with poses`, then compare the alignment diagnostics
  (rel-rotation spread, similarity scale) against the previous image-only run.