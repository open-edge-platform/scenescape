<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Camera Auto-Calibration Against a Satellite Map

Status: **proposed, not started.** Written 2026-10-05 after the radar-intersection
investigation on `feature/radar-support`.

Scope: **calibration only.** Estimate a camera's extrinsics (and the intrinsics
that cannot be trusted) from a single image plus the scene's satellite/ortho map,
using **static landmarks** and **geometry priors**. This plan deliberately does
not use tracked or moving objects, and does not use other sensors (radar, LiDAR,
GNSS) as calibration inputs. Map-derived analytics, tracking priors, and other
uses of the map are out of scope.

Related: `autocalibration/Agents.md` (existing calibration strategies),
[`radar-first-class-and-g3dinference.md`](radar-first-class-and-g3dinference.md).

---

## 0. Why this is needed (evidence from the radar demo)

- Camera-projected pedestrians sat about **1 m off the footpath centre**
  (south bias), while independent radar positions agreed with the camera to
  0.4-0.6 m. The camera pose, its intrinsics, or the map scale is off by about
  a metre; today there is no way to tell which.
- `sample_data/radar_intersection/videtec_map_calibration.json` records
  `reproj_mean_px: 78.93` for the manual point-correspondence solve for the
  camera, i.e. far from pixel accurate.
- Two different poses and focal lengths exist on disk for the same
  `radar-cam1` sensor (`videtec_map_calibration.json` vs
  `RadarIntersection.json`). There is no record of which is authoritative and
  no confidence value attached to either.
- A pre-made blueprint, GLB, or geospatial map currently has no automatic
  camera calibration path: `scene-map-alternatives.md` states cameras "must be
  calibrated manually through the SceneScape web UI". Markerless calibration
  needs a mesh/RGB-D reconstruction, which a satellite scene does not have.

## 1. Geometry in one paragraph

A satellite tile is an orthographic top-down image of the ground plane (here
1280 px, 9.142857 px/m, georeferenced via `origin_lat/lon`; scene `x = px / S`,
`y = (H - py) / S`). A world point on the ground (z = 0 or a known height) maps to
the image through the camera pose and intrinsics, so each identified ground
landmark gives two equations. Six pose unknowns plus focal length (and
optionally one radial term) are recoverable from enough well-spread, non-collinear
landmarks. The work is in finding those landmarks **automatically** across a very
large viewpoint change.

---

## Part A. Map landmark extraction (preprocessing, calibration-only)

Only what calibration needs; no general semantic-analytics layers.

### A1. Inputs

- Scene map image, scale, and georeference already stored on the scene
  (`Scene.map_type`, `map_corners_lla`, `geospatial_provider` in
  `manager/src/manager/models.py`; `scene_common/earth_lla.py` for LLA <-> scene).
- Optional OpenStreetMap vector data for the map bounding box (road edges,
  `highway=footway` + `footway=crossing`, `crossing=zebra`, kerbs, lane counts),
  fetched once and cached; ODbL attribution; offline path required.

### A2. Landmark types, in order of reliability

1. **Crosswalk bars and stop lines**: high contrast, regular, rectangular, visible
   from both a top-down tile and an oblique camera.
2. **Lane markings and arrows**: thin bright linear structure
   (top-hat on luminance; the prototype used a 15 px elliptical kernel on the
   Lab L channel).
3. **Road edges / kerbs / paved vs vegetation boundaries**: from the vegetation
   index (Lab a*, ExG) prototype plus OSM road edges.
4. **Fixed structures with known footprints**: buildings, poles, medians, when
   present in OSM or the tile.

Output: a **ground mask** (road / crosswalk / sidewalk vs vegetation, buildings,
water; used to restrict matching to ground-plane pixels) and **vector landmarks**
(polylines and polygons with type and confidence) in scene metres. Heuristics
from the prototype are a starting point only; they missed the shaded footpath
and the crosswalks, so OSM vectors are preferred where available, with hand
polygons as an override.

### A3. Artifacts

- `landmarks.geojson` + `ground_mask.png` beside the map file, with `meta.json`
  (map hash, generator version, input sources, scale, georeference) so they
  regenerate when the map changes.
- A small reader in `scene_common` (e.g. `SceneLandmarks`) so
  `autocalibration/` does not parse files itself.

### A4. Acceptance

- Crosswalks and stop lines for the radar-intersection tile are recovered
  without the hand-drawn polygons used in the prototype.
- Deterministic output for identical inputs. Runs on CPU in under a minute for
  a 1280x1280 tile.
- Tests under `tests/sscape_tests/` including negative cases (no OSM data, no
  network, map without a georeference, blueprint maps with no road markings).

---

## Part B. Auto-calibration solver

Two signals only.

### B1. Signal 1: static landmarks

- **Coarse alignment**: warp the camera image to an approximate bird's-eye view
  using a rough pose prior; extract the same landmark classes from the warped
  image; align to the map landmarks by maximising overlap (chamfer distance or a
  differentiable renderer) over pose and focal length. Search the prior's
  neighbourhood on a coarse grid first to avoid local minima.
- **Feature route (alternative or complement)**: dense cross-view matching
  (LoFTR/RoMa class; `hloc` is already a dependency of the markerless
  strategy) between the bird's-eye warp and the map tile, with RANSAC on a
  planar homography; decompose into pose given intrinsics.
- **Refinement**: once within a few pixels, refine with edge-based or
  photometric alignment restricted to the ground mask.
- Known weak points: texture-poor roads, night, shadows, parked vehicles in the
  tile, tile date vs video date.

### B2. Signal 2: geometry priors

Cheap constraints that remove most of the ambiguity left by landmarks:

- **Vanishing points / horizon** from lane-line parallelism and crosswalk bars:
  gives focal length and camera tilt/roll.
- **Camera height prior** from the mounting description, or from the apparent
  size of crosswalk bars and lane widths (standard widths per road class).
- **Mounting position prior**: sensor location on the map (gantry/pole), as a
  weak position prior and as the starting point of the search.
- **Ground plane**: z = 0, or a per-cell height if a DEM is supplied.
- **Principal point** fixed at image centre unless there is evidence otherwise;
  optional single radial distortion term.

### B3. Solver structure

```
rough prior (mount position, heading, optional one click)
   -> B2 priors (focal, tilt/roll, height)
   -> B1 landmark alignment  (coarse, global)
   -> B1 refinement          (fine, ground mask only)
   -> robust joint fit over {pose(6), f, k1} with per-landmark weights
   -> report: pose, intrinsics, covariance, inlier landmarks,
      confidence score, pass/fail vs thresholds
```

Return **uncertainty**, not just a pose. Report low confidence when the view
contains too little road structure (indoor, heavy occlusion, overpass) rather
than returning a wrong answer.

### B4. Observability

- Landmarks must be spread over depth and lateral position; a single lane line
  or a collinear set leaves the pose unobservable along that line.
- A rough prior is assumed at first; whether the first release can be fully
  unattended is an open question below.
- State the failure signatures: too few inliers, large reprojection residuals,
  focal length outside plausible bounds, camera below horizon or above the
  ground, and a wide covariance.

### B5. Integration with the existing service

`autocalibration/` routes by sensor modality through
`PerceptualSensorCalibrationController` (AprilTag, markerless/hloc,
point-cloud). Add a **map-based strategy**:

- `map_camera_calibration.py` + `map_camera_calibration_controller.py`,
  selectable per camera in the manager.
- Reuse `scene_common/transform.py` (`CameraPose`, `CameraIntrinsics`,
  `PointCorrespondenceTransform`) for projection and pose conversion; do not
  reimplement the camera model.
- Same REST/MQTT contract as the other strategies
  (`calibration/request/<camera_id>` -> `calibration/result/<camera_id>`), plus
  a result block with confidence and covariance.
- Applicable to metric orthographic maps (satellite tiles, scaled blueprints).
  Not applicable to free-form GLB meshes, where markerless remains the path.

### B6. Evaluation and validation

Validation is independent of the solver and never fed back into it.

- **Held-out landmark error**: hand-label 8-12 ground landmarks per camera that
  the solver does not use; report metres after projection. This is the primary
  metric.
- **Reprojection error** of the solver's own inlier landmarks, in pixels.
- **External cross-check (evaluation only)**: compare projected positions of
  independently surveyed or GNSS-tagged ground points where such data exists,
  e.g. the VIDETEC VRU, to test for residual bias such as the 1 m offset
  observed in the radar demo. These are used to score the result, not to fit it.
- **Leave-one-camera-out** across the VIDETEC gantry cameras and the other
  sample scenes in the repo, including shadow and time-of-day variation where
  data allows.
- Regression harness in `tests/` using recorded frames and stored landmarks, so
  it runs in CI without GPU or live video.

### B7. Acceptance

- Held-out ground error at or under a target (proposed: 0.5 m at 30 m range)
  from a rough prior, with no manual correspondences.
- Better than the current manual solve on held-out landmarks for `radar-cam1`.
- A defined, tested low-confidence outcome for unsuitable scenes.
- Runs within the existing calibration service time budget on CPU.

### B8. Risks

- Cross-view appearance gap between an oblique camera and a top-down tile.
- Satellite imagery licence and storage terms (check Mapbox or other provider
  terms before caching tiles or using them in tests; prefer open ortho sources
  where available).
- Ground-plane assumption breaks with ramps, bridges, and kerbs; mitigate with
  the optional DEM and by weighting landmarks that lie on flat ground.
- Map staleness (construction, repainted markings) relative to the camera.
- Focal length and distance are partly confounded when only a few landmarks are
  visible; the priors in B2 and an explicit covariance are the mitigation.

---

## Phasing

| Phase | Deliverable |
| --- | --- |
| P0 | Move the prototype landmark/segmentation code into the repo as a tool with tests; build the held-out landmark set for `radar-cam1` and measure the current manual calibration as the baseline |
| P1 | Part A: landmark extraction (OSM + imagery), `scene_common` reader |
| P2 | B2 priors and B1 coarse alignment, offline, with uncertainty output |
| P3 | B1 refinement and feature route; leave-one-camera-out evaluation |
| P4 | Service integration (map strategy in `autocalibration/`, manager mode, API fields), feature-flagged |

## Open questions for design review

1. Imagery licensing: which satellite/ortho sources can be cached and used in
   the product and in tests? Is OSM-only acceptable as the default landmark
   source?
2. Does the first release require a rough human prior (one click, or mount
   location), or must it be fully unattended?
3. Target accuracy and range, and which scenes are in scope (roads only, or
   also parking lots and campuses).
4. Where landmark artifacts live: beside the map file or in the manager
   database, and who owns regeneration when the map changes.
5. Which cameras and scenes provide the ground-truth landmark set for the
   evaluation, and who labels it.
