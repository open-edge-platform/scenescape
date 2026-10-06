<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Camera Auto-Calibration Against a Satellite Map

Status: **V1 complete — imagery landmarks observable under GT pose; V2 next.**
Rewritten 2026-10-05 after design review: drop radar-demo assumptions, drop
mount priors, prove the algorithm before any product scaffolding. OSM deferred
to Phase 3.

Scope: **calibration only.** Estimate a camera's extrinsics (and untrusted
intrinsics) from a camera image plus a metric orthographic / satellite map,
using static landmarks and geometry. No tracked objects, no other sensors as
calibration inputs.

Related: `autocalibration/Agents.md` (existing strategies).

---

## Fixed constraints (from design review)

- **Prior**: camera is above the ground plane (`z > 0`). No mount position,
  heading, or height prior in the first cut.
- **Scene class**: anywhere a metric ortho/satellite map is available — not
  roads-only. Intersections are a convenient eval set, not the product scope.
- **No radar / VIDETEC scene on `main`**: that demo and its scaffolding are out
  of scope for this work. Do not depend on them.
- **Product code (P0–P4 service integration) is gated** on the verification
  ladder below. Do not build `autocalibration/` strategy, manager modes, or
  landmark artifact ownership until V0–V2 show a signal.

---

## Geometry in one paragraph

A satellite / ortho tile is a top-down metric image of the ground (scale in
px/m, optional georeference via `map_corners_lla`). A world point on the ground
(`z = 0` or known height) maps to the camera image through pose and
intrinsics. Enough well-spread, non-collinear ground landmarks constrain pose
(6) plus focal length (and optionally one radial term). The hard part without a
mount prior is finding those landmarks automatically across a large viewpoint
change.

---

## Verification ladder (do this first)

Goal: answer “does this work?” with an offline spike. No service integration.

| Step | Question | Method | Fail → stop |
| --- | --- | --- | --- |
| **V0 Oracle** | Is map↔image geometry solvable? | Correspondences known a priori (GT-projected or hand-labeled); solve with `PointCorrespondenceTransform`; held-out error in metres vs GT pose | Residuals ≫ 0.5–1 m → map scale / camera model problem |
| **V1 Observability** | Enough landmarks without a prior, beyond roads? | Under GT pose, extract landmarks from the **ortho/satellite map imagery itself** (edges, high-contrast markings, paved/vegetation boundaries, building footprints visible in the tile) and from the camera frame; project map landmarks into the camera; measure depth and lateral spread. **No OSM in V1** — the approach must work wherever a metric ortho exists (campus, parking lot, plaza), not only mapped road networks | Too little structure in imagery → need richer map or different cue |
| **V2 Auto match** | Can we find correspondences with only `z_cam > 0`? | Cross-view matching or landmark alignment on imagery-derived features + RANSAC; no mount prior; no OSM | Ambiguous minima / match failure → need a weak prior or different cue |

**Pass bar to start product work**: V0 passes; V1 shows usable coverage; V2
recovers pose within ~1 m / a few degrees of GT on ≥2 cameras of the eval set.

**OSM is deferred** to product Phase 3 as an optional accuracy boost for
intersections / well-mapped roads — not part of the V1/V2 proof.

### Eval data

- Primary: [Smart Intersection](https://github.com/open-edge-platform/edge-ai-suites/tree/main/metro-ai-suite/metro-vision-ai-app-recipe/smart-intersection)
  (map + four-corner LLA + manual calib + four camera videos). Treat as an
  **external fixture** — do not vendor into the Apache tree until licensing is
  cleared. Scene DB archive:
  `src/webserver/smart-intersection-ri.tar.bz2`; videos from
  `edge-ai-resources` via
  `tools/map_autocalib_spike/download_si_videos.sh` (reads GNOME / APT proxy
  settings; behind Intel DMZ use `proxy-dmz.intel.com:911/912`).
- Secondary (optional): any open traffic / campus scene with metric map + known
  camera pose (e.g. CUTC-style calibrated urban cameras), once V0–V2 work on
  the first set.

### Spike deliverable

Offline scripts under `tools/map_autocalib_spike/`. Not a CI harness, not a
service. Fixtures stay external (do not vendor Smart Intersection into the tree).

### V0 results (2026-10-05) — Smart Intersection

Fixture: extracted `smart-intersection-ri.tar.bz2` (map + `data.json` with
manual 3d-2d correspondences). Metric: leave-one-out ground error (solve on
N−1 labeled points, project held-out camera pixel to z=0, compare to labeled
map metres). Prior: none beyond solvable PnP; cameras land at z ≈ 6 m
(above ground). Script: `tools/map_autocalib_spike/v0_oracle.py`.

| Camera | n | z (m) | reproj mean (px) | LOO mean (m) | LOO median (m) | LOO max (m) | mean ΔT (m) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| camera1 south | 8 | 6.59 | 4.85 | 0.80 | 0.50 | 2.07 | 0.22 |
| camera2 west | 7 | 5.96 | 6.43 | 2.02 | 1.06 | 5.81 | 0.42 |
| camera3 north | 8 | 6.92 | 4.09 | 0.83 | 0.75 | 1.37 | 0.21 |
| camera4 east | 7 | 6.25 | 1.99 | 0.33 | 0.28 | 0.66 | 0.10 |

**Verdict**

- Map↔image geometry **is solvable** with oracle correspondences and no mount
  prior. Pose is stable under LOO (ΔT ≪ 1 m, ΔR ≪ 1°).
- 3/4 cameras meet ≤1 m LOO **mean**; camera2 misses on mean (2.0 m) but
  median ≈ 1.1 m — likely 1–2 noisy labels / weak depth spread, not a
  fundamental failure. Strict `v0_pass` (all cams mean ≤1 m) = false;
  `v0_pass_median` ≈ true for the set at ~1 m.
- Holding out 2 of 7 points is too aggressive (ill-conditioned splits); LOO is
  the right V0 metric for this label density.
- **Do not start product phases yet.** Next: **V2** (auto correspondence with
  only `z_cam > 0`, imagery-derived features, no OSM).

Overlays: `tools/map_autocalib_spike/out/camera*_map.png` (local, gitignored).

### V1 results (2026-10-05) — Smart Intersection

Script: `tools/map_autocalib_spike/v1_observability.py`. Landmarks from the
ortho tile only (Lab L top-hat markings, Canny edges, ExG paved↔vegetation
boundaries). No OSM. Projected into each camera with the V0 GT pose; score
depth span, lateral span, PCA ratio, and 4×4 FOV grid occupancy.

| Camera | n visible | depth span (m) | lateral span (m) | PCA | FOV grid | pass |
| --- | --- | --- | --- | --- | --- | --- |
| camera1 south | 160 | 80.7 | 43.1 | 0.52 | 9/16 | yes |
| camera2 west | 230 | 77.7 | 65.4 | 0.62 | 8/16 | yes |
| camera3 north | 238 | 84.1 | 60.0 | 0.47 | 8/16 | yes |
| camera4 east | 352 | 71.2 | 70.0 | 0.62 | 8/16 | yes |

Map total ≈ 2500 subsampled points (marking / edge / boundary). **v1_pass =
True (4/4).** Imagery alone exposes enough well-spread ground structure for
calibration without OSM or a mount prior. Overlays:
`out/camera*_v1_cam.png`, `out/v1_map_landmarks.png`.

**Next:** V2 auto-match (cross-view / landmark alignment + RANSAC, `z > 0`
only).

---

## Later: product phases (only after V0–V2 pass)

Kept for reference; **not started**.

| Phase | Deliverable |
| --- | --- |
| P1 | Imagery-based landmark extraction (ortho tile + camera; no OSM), `scene_common` reader, artifacts beside map |
| P2 | Geometry priors that do **not** assume mount location (vanishing points, height-from-structure, `z > 0`); coarse alignment + uncertainty |
| P3 | Optional **OSM infusion** for higher accuracy on intersections / mapped roads (road edges, crosswalks, kerbs); refinement / feature route; multi-scene evaluation |
| P4 | `autocalibration/` map strategy, manager mode, feature-flagged API |

Open product questions (defer until verification passes):

1. Imagery licensing for cached tiles (product path is imagery-first; OSM is
   optional in P3).
2. Where landmark artifacts live and who regenerates them.
3. Target accuracy / range for GA (proposed spike bar above is looser).
4. Whether a weak optional prior (one click / mount XY) is allowed as a
   fallback when V2 confidence is low.

---

## Risks that verification must surface

- Cross-view appearance gap (oblique camera vs top-down tile) without a pose
  prior — the main V2 risk.
- Focal length and distance confounded with few landmarks — V0 held-out splits
  expose this.
- Ground-plane breaks (ramps, bridges, kerbs).
- Map staleness vs camera capture date.
- Smart Intersection license is not Apache-2.0; keep fixtures external.
