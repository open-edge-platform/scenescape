<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Camera Auto-Calibration Against a Satellite Map

Status: **V0–V2 done; P2 cross-view + semantic spikes run — both fail the
signal bar on Smart Intersection.** Correspondence remains the blocker.
Next: stronger semantic classes / RoMa-class matcher, or productize click
prior (stack item 4) while continuing matcher research.

Scope: **calibration only.** Estimate a camera's extrinsics (and untrusted
intrinsics) from a camera image plus a metric orthographic / satellite map,
using static landmarks and geometry. No tracked objects, no other sensors as
calibration inputs.

Related: `autocalibration/Agents.md` (existing strategies).

---

## Fixed constraints (from design review)

- **Hard prior**: camera is above the ground plane (`z > 0`).
- **Human click (fallback)**: operator may supply a weak pose cue via the UI
  (one map click and/or heading) when automatic methods are low-confidence or
  unavailable. Preferred path is automatic; click is not required for the
  default happy path once higher-priority methods work.
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
**correspondence / heading** fails with structure+NCC alone (V2). Local
descriptors (AKAZE; SIFT/SuperPoint-class) are a poor fit for this viewpoint
change. Proceed with all four approaches below, in this order:

| Priority | Approach | Role | Notes |
| --- | --- | --- | --- |
| **1** | **Learned cross-view matcher** | Primary automatic path | LoFTR outdoor: **fail** (0/4; ~90 matches, 0 PnP inliers). RoMa tiny + outdoor (`p2_roma.py`): **fail** (0/4); outdoor finds hundreds of inliers but wrong pose (heading flip / 30–50 m XY). BEV+DINO / SuperPoint+LightGlue probes also failed. Needs warp/prior or a true cross-view-trained model. |
| **2** | **Semantic landmarks** | Automatic, interpretable | Marking corners (tophat + Shi-Tomasi) + ORB: **fail** (0/4). Under GT pose, median nearest corner ≈ 35–50 px — detections do not coincide across views. Need class-aware detectors (crosswalk / stop-bar), not generic corners. |
| **3** | **Map topology (OSM optional)** | Accuracy / disambiguation | Road graph, buildings, crossings when OSM (or similar) is rich enough. Helps asymmetric junctions; failed alone on Smart Intersection; will not help sparse campus maps. Optional, off by default for non-road scenes. |
| **4** | **Human click prior** | Fallback / assist | Operator clicks once on the map (and optionally sets heading) when (1)–(3) are low-confidence or unavailable. Seeds BEV/structure alignment (cam2/4 diagnostic ≈ 2.5 m XY given orientation). **Ready to productize** while (1)–(2) continue. Full multi-point manual correspondence remains the last resort. |

**UI expectation:** prefer unattended solve via (1)+(2), optionally boosted by
(3). If confidence is low, prompt for one map click (4) rather than a full
manual point set.

---

## Verification ladder (done)

Goal was: answer “does this work?” with an offline spike before service work.

| Step | Question | Result |
| --- | --- | --- |
| **V0 Oracle** | Is map↔image geometry solvable? | **Pass** (LOO ~0.3–1 m on 3/4 cams; cam2 noisier) |
| **V1 Observability** | Enough imagery landmarks without OSM? | **Pass** (4/4; well-spread depth/lateral) |
| **V2 Auto match** | Correspondences with only `z > 0`? | **Fail** (0/4); heading ambiguity |
| **V2 + OSM** | Does topology clear the fail? | **Fail** (0/4); optional later only |
| **P2 LoFTR** | Cross-view dense match? | **Fail** (0/4); `p2_crossview.py` |
| **P2 RoMa** | RoMa tiny/outdoor dense match? | **Fail** (0/4); `p2_roma.py` |
| **P2 Semantic** | Marking corners + ORB? | **Fail** (0/4); `p2_semantic.py` |

**Pass bar to start product work (revised):** V0 + V1 pass (done), and a spike
signal from stack item **1** (cross-view matcher) and/or **2** (semantic
landmarks). **Not met yet.** Item **4** (click) remains the product fallback
and is the only stack item with a proven XY seed (V2 oracle orient).

### P2 results (2026-10-06)

Scripts: `p2_crossview.py` (LoFTR outdoor), `p2_semantic.py` (marking corners).
Weights under `fixtures/weights/` (gitignored): `loftr_outdoor.ckpt`,
SuperPoint/LightGlue used only in offline probes.

| Approach | Result | Notes |
| --- | --- | --- |
| LoFTR direct | 0/4 | ~84–105 matches/cam; PnP RANSAC never reaches 6 inliers |
| RoMa tiny | 0/4 | Inliers present; pose wrong (tens–hundreds of metres) |
| RoMa outdoor | 0/4 | Up to ~800 inliers/cam; still wrong heading/XY (e.g. cam1 dR≈179°) |
| Semantic corners+ORB | 0/4 | GT association median 35–50 px; wrong corners |
| DINO BEV / SP+LightGlue | no suite signal | Probes only; unstable / empty BEV coverage |

RoMa weights (gitignored): `fixtures/weights/{tiny_roma_v1_outdoor,roma_outdoor}.pth`;
env: `tools/map_autocalib_spike/.venv-roma` (romatch).

Do **not** start P4 service wiring until (1) or (2) shows signal, unless the
product decision is to ship click-prior first.

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

## Product phases (automatic first, click as fallback)

| Phase | Deliverable |
| --- | --- |
| P1 | Imagery landmark extraction + `scene_common` reader; artifacts beside map |
| P2 | **Cross-view + semantic spikes done (both fail signal bar).** Iterate matcher (RoMa / better BEV) and class-aware landmarks; optionally start click-prior UI in parallel |
| P3 | Optional OSM topology (priority 3); click-prior fallback UI/API (priority 4); multi-scene eval including a non-road campus-like map |
| P4 | `autocalibration/` map strategy, manager mode, feature-flagged API — **gated on P2 signal or explicit click-first product decision** |

Open product questions:

1. Imagery licensing for cached tiles.
2. Where landmark artifacts live and who regenerates them.
3. Target accuracy / range for GA (spike bars were looser).
4. Which cross-view model (LoFTR / RoMa / other) fits the autocalibration image
   and license constraints.
5. Click UX for the fallback: one ground point vs camera foot vs “look toward”.

---

## Risks

- Cross-view appearance gap without a prior — confirmed by V2.
- Focal length ↔ distance confounding with few landmarks.
- Ground-plane breaks (ramps, bridges, kerbs).
- Map staleness vs camera capture date.
- Smart Intersection license is not Apache-2.0; keep fixtures external.
- OSM sparsity on campuses — do not require OSM for the default path.
