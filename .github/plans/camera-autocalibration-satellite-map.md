<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Camera Auto-Calibration Against a Satellite Map

Status: **V0–V2 verification complete; V2 blocked without a prior.** Path
forward is the prioritized unblock stack below (human click prior first).
Product phases restart against that stack, not against fully unattended
imagery-only matching.

Scope: **calibration only.** Estimate a camera's extrinsics (and untrusted
intrinsics) from a camera image plus a metric orthographic / satellite map,
using static landmarks and geometry. No tracked objects, no other sensors as
calibration inputs.

Related: `autocalibration/Agents.md` (existing strategies).

---

## Fixed constraints (from design review)

- **Hard prior**: camera is above the ground plane (`z > 0`).
- **Soft prior (accepted)**: a human may supply a weak pose cue via the UI —
  typically **one click** on the map (look-at / ground point under the view, or
  approximate camera foot) and/or an approximate heading. Fully unattended
  matching with only `z > 0` was tested and failed on Smart Intersection.
- **Scene class**: anywhere a metric ortho/satellite map is available — not
  roads-only. Intersections are a convenient eval set, not the product scope.
- **No radar / VIDETEC scene on `main`**: that demo and its scaffolding are out
  of scope for this work. Do not depend on them.

---

## Geometry in one paragraph

A satellite / ortho tile is a top-down metric image of the ground (scale in
px/m, optional georeference via `map_corners_lla`). A world point on the ground
(`z = 0` or known height) maps to the camera image through pose and
intrinsics. Enough well-spread, non-collinear ground landmarks constrain pose
(6) plus focal length (and optionally one radial term). The hard part across
oblique camera ↔ top-down map is finding those landmarks automatically; humans
do it by semantic identity (crosswalk corner, curb kink), not by local patch
similarity.

---

## Unblock stack (priority order)

Verified gap: camera model and landmark **coverage** are fine (V0, V1);
**correspondence / heading** fails without a cue (V2). Local descriptors
(AKAZE; SIFT/SuperPoint-class) are a poor fit for this viewpoint change.
Proceed with all three approaches below, in this order:

| Priority | Approach | Role | Notes |
| --- | --- | --- | --- |
| **1** | **Human click prior** | Primary product path | Operator clicks once on the map (and optionally sets heading). That weak prior seeds the existing BEV / structure alignment that already recovers ~2.5 m XY when orientation is known (cam2/4 diagnostic). Closest to how manual calib works today, with far fewer points. |
| **2** | **Learned cross-view matcher** | Automatic / reduce clicks | LoFTR / RoMa-class dense matching between camera (or BEV warp) and ortho. Aims at human-like correspondences under extreme viewpoint change. Heavier deps; evaluate after (1) ships a usable path. |
| **3** | **Map topology (OSM optional)** | Accuracy / disambiguation | Road graph, buildings, crossings when OSM (or similar) is rich enough. Helps asymmetric junctions; **does not** replace (1) on Smart Intersection and will not help sparse campus maps. Keep optional and off by default for non-road scenes. |

**UI expectation for (1):** human remains in the loop for the prior — one map
click (required in v1 of the feature), optional heading tweak, then the service
solves and reports confidence. Full multi-point manual correspondence stays
available as fallback.

---

## Verification ladder (done)

Goal was: answer “does this work?” with an offline spike before service work.

| Step | Question | Result |
| --- | --- | --- |
| **V0 Oracle** | Is map↔image geometry solvable? | **Pass** (LOO ~0.3–1 m on 3/4 cams; cam2 noisier) |
| **V1 Observability** | Enough imagery landmarks without OSM? | **Pass** (4/4; well-spread depth/lateral) |
| **V2 Auto match** | Correspondences with only `z > 0`? | **Fail** (0/4); heading ambiguity |
| **V2 + OSM** | Does topology clear the fail? | **Fail** (0/4); optional later only |

**Pass bar to start product work (revised):** V0 + V1 pass, and either V2
signal **or** a chosen unblock from the stack above is designed in. **Stack
item 1 (click prior) is the gate to restart product phases.**

### Eval data

- Primary: [Smart Intersection](https://github.com/open-edge-platform/edge-ai-suites/tree/main/metro-ai-suite/metro-vision-ai-app-recipe/smart-intersection)
  as an **external fixture** (do not vendor into Apache tree until licensing is
  cleared). DB archive `smart-intersection-ri.tar.bz2`; videos via
  `tools/map_autocalib_spike/download_si_videos.sh` (GNOME/APT proxy; Intel DMZ
  `proxy-dmz.intel.com:911/912`).
- Spike code: `tools/map_autocalib_spike/` (offline only).

### V0 results (2026-10-05)

Script: `v0_oracle.py`. Leave-one-out ground error vs manual correspondences.

| Camera | n | z (m) | reproj mean (px) | LOO mean (m) | LOO median (m) | mean ΔT (m) |
| --- | --- | --- | --- | --- | --- | --- |
| camera1 south | 8 | 6.59 | 4.85 | 0.80 | 0.50 | 0.22 |
| camera2 west | 7 | 5.96 | 6.43 | 2.02 | 1.06 | 0.42 |
| camera3 north | 8 | 6.92 | 4.09 | 0.83 | 0.75 | 0.21 |
| camera4 east | 7 | 6.25 | 1.99 | 0.33 | 0.28 | 0.10 |

Geometry solvable; pose stable under LOO.

### V1 results (2026-10-05)

Script: `v1_observability.py`. Ortho-only landmarks under GT pose. **4/4 pass.**

| Camera | n visible | depth span (m) | lateral span (m) | PCA | FOV grid |
| --- | --- | --- | --- | --- | --- |
| camera1 | 160 | 80.7 | 43.1 | 0.52 | 9/16 |
| camera2 | 230 | 77.7 | 65.4 | 0.62 | 8/16 |
| camera3 | 238 | 84.1 | 60.0 | 0.47 | 8/16 |
| camera4 | 352 | 71.2 | 70.0 | 0.62 | 8/16 |

### V2 results (2026-10-06)

Script: `v2_automatch.py`. Structure BEV + NCC; no mount/heading prior.
**0/4 pass, 0/4 signal.** Wrong heading dominates. With GT orientation given
(diagnostic), cam2/4 XY ≈ 2.5 m — confirms the gap is correspondence, not the
camera model. AKAZE ≈ 1–2 inliers (local features inadequate here).

### V2 + OSM experiment (2026-10-06)

Scripts: `osm_topology.py`, `v2_osm_assist.py`. OSM map API fixture
`fixtures/osm/map.osm` (gitignored). Roads ≈ 0°/90° plus 4 buildings. All
modes **0/4**. OSM does not unblock this scene; keep as optional Phase 3 for
asymmetric, well-mapped junctions only.

---

## Product phases (restart with click prior)

| Phase | Deliverable |
| --- | --- |
| P1 | Imagery landmark extraction + `scene_common` reader; artifacts beside map |
| P2 | **Click-prior solver**: ingest one map click (+ optional heading); coarse BEV/structure alignment + uncertainty; Manager UI hook for the click |
| P3 | Learned cross-view matcher (priority 2) and/or optional OSM topology (priority 3); multi-scene eval including a non-road campus-like map |
| P4 | `autocalibration/` map strategy, manager mode, feature-flagged API |

Open product questions:

1. Imagery licensing for cached tiles.
2. Where landmark artifacts live and who regenerates them.
3. Target accuracy / range for GA (spike bars were looser).
4. Click UX: one ground point vs camera foot vs “look toward”; whether heading
   is inferred from click+image or typed/dragged.

---

## Risks

- Cross-view appearance gap without a prior — confirmed by V2.
- Focal length ↔ distance confounding with few landmarks.
- Ground-plane breaks (ramps, bridges, kerbs).
- Map staleness vs camera capture date.
- Smart Intersection license is not Apache-2.0; keep fixtures external.
- OSM sparsity on campuses — do not require OSM for the default path.
