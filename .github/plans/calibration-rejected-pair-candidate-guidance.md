<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Candidate Guidance for Rejected Calibration Pairs

## Status

Future extension. This document records a possible design for someone to try
later; it does **not** describe current behavior.

Related current work (already landed or in progress on calibration fit
diagnostics):

- RANSAC outlier rejection for manual calibration / point correspondence pose
- Fit diagnostics in the Manager UI (RMS, per-point residuals, rejected indices)
- Visual **halos** (red = rejected, orange = high residual) that preserve each
  point’s identity color
- Shared threshold / min-point constants from
  `scene_common.transform` (`RANSAC_REPROJECTION_THRESHOLD_PX`,
  `MIN_POINTS_FOR_RANSAC`) mirrored in Manager JS as needed

## Problem

When RANSAC rejects a map↔camera pair (or a pair has a high final residual),
the UI today only says the pair is bad. The user must **blindly** rematch or
reposition until RANSAC and reprojection fall within thresholds—guessing
whether to move the camera point, move the map point, or swap partners.

Goal: turn “reject → guess → retry” into “reject → try this candidate →
confirm.”

## Important constraints

### Hard floor: ≥ 4 correspondences

PnP / `solvePnPRansac` need at least `MIN_POINTS_FOR_RANSAC` (4) pairs before a
pose exists. Without a pose there is no trustworthy projection of map points
into the camera image, so **no candidate locations or rematches** can be
offered.

- **≥ 4 pairs**: candidates become *possible*.
- **Best case**: RANSAC finds a solid inlier set (≥ 4 inliers), then suggest
  fixes for rejected / high-residual pairs under that pose.
- **Exactly 4, all borderline**: pose exists but suggestions are fragile; one
  wrong pair can pull the model. Prefer gating suggestions on a usable inlier
  set, not merely “four points placed.”

### What RANSAC and reprojection error do *not* do today

- **Reprojection error** scores an *assumed* pairing under a fitted model. It
  does not invent better assignments.
- **RANSAC** (pixel reprojection threshold) finds inliers among the *current*
  claimed pairs. It does not search alternate map↔camera assignments.

The same **pure pixel** cost RANSAC uses *can* score candidate rematches or
target locations after a pose is available. That is a separate
matching / projection step, not something RANSAC emits by itself.

## Proposed algorithm (combo)

1. Fit pose with RANSAC on the user’s current pairing → inliers / outliers and
   a pose (when `rejectionApplied` or an equivalent stable inlier set exists).
2. Using that pose (+ intrinsics / distortion), project map points into the
   camera image.
3. For each rejected (and optionally high-residual) camera point, build a
   pixel-distance cost to every projected map point.
4. Propose:
   - **Rematch**: another existing map point whose projection is much closer
     than the current partner; and/or
   - **Relocate**: the image location where the *current* map partner *should*
     appear (ghost target).
5. Optionally re-run RANSAC on an accepted rematch / after the user snaps to
   the ghost; keep the change only if inlier count / RMS improves.
6. Iterate a few times if needed (RANSAC → rematch/relocate → RANSAC).

Stay quiet when ambiguous (e.g. top two candidates within a few pixels) so
confident wrong suggestions do not replace blind matching.

## Visual guidance (primary design question)

Two different “candidate locations” need different visuals.

### A. Rematch to an existing point

Candidate is another already-placed map or camera point (wrong partner /
labels).

Suggested cues:

- **Paired highlight**: selecting rejected camera `p3` also highlights
  candidate map `p5` (shared accent: dashed cyan halo / pulse)—do **not**
  recolor identity fills (halos already own diagnostic color).
- **Cross-view link**: temporary leader or “`p3` ↔ `p5`” badge on both views.
- **Ghost twin**: faint marker at the candidate point labeled `try p5`.
- **Dim the rest**: lower opacity on uninvolved points.

Offer an action: “Rematch `p3` → map `p5`” (swap / reassign names), then
re-run fit immediately.

### B. Move this point to a better place

Candidate is a **position** under the current pose (project map → image).

Suggested cues:

- **Ghost target** in the camera view: empty ring / crosshair where that map
  point should appear, with a short arrow from the current point to the ghost.
- **Snap preview on drag**: live residual (“22 px → 4 px”) as the user moves
  toward the ghost.
- Show for **one active rejected point at a time** so the canvas does not fill
  with ghosts.

### Recommended first UX combo

For a rejected pair, on demand (click rejected point / “Suggest fix”):

1. Default: **ghost target in the camera view** for “move here to satisfy the
   current map partner.”
2. If another map point scores much better: also show **“or rematch to pN”**
   with linked highlight in the map view.
3. Suppress both when the top candidates are within a small pixel margin
   (ambiguous).

Avoid: recoloring identity fills; showing candidates for every point at once;
strong arrows when the match is ambiguous.

## Suggested implementation slices

Smallest useful slice for a first experiment:

1. **API / backend** (Manager `calculateintrinsics` and/or shared helper next
   to RANSAC in `scene_common`): given pose + points, return per-rejected-index
   suggestions, e.g. `{ cameraIndex, currentMapIndex, candidateMapIndex,
   currentErrorPx, candidateErrorPx, ghostCamPoint: [x, y] }` gated on a
   usable inlier pose.
2. **UI text** in the existing fit-status details: one line per rejected pair
   with rematch / relocate numbers (no new canvas chrome yet).
3. **Visuals**: ghost target in `CamCanvas` for relocate; linked halo /
   connector for rematch in camera + map views.
4. **Action**: one-click rematch (rename/swap correspondence) or “snap to
   ghost,” then re-invoke fit.

Reuse existing constants (`RANSAC_REPROJECTION_THRESHOLD_PX` /
`CALIBRATION_OUTLIER_THRESHOLD_PX`, `MIN_POINTS_FOR_RANSAC` /
`CALIBRATION_MIN_POINTS_FOR_FIT`). Do not reintroduce duplicate thresholds.

## Likely touch points

- `manager/src/manager/calculate_intrinsics_view.py` — fit response payload
- `scene_common/src/scene_common/transform.py` — shared projection / cost helper
  if pose-side reuse is desired
- `manager/src/manager/static/js/cameracalibrate.js` — consume suggestions,
  actions, fit re-run
- `manager/src/manager/static/js/camcanvas.js` — ghost target / arrows
- `manager/src/manager/static/js/viewport.js` / `draw.js` — linked highlight for
  rematch candidates (halo-style, not fill recolor)
- Fit status section in `cam_calibrate.html`
- Docs under
  `docs/user-guide/how-to-guides/calibrate-cameras/use-2D-UI-for-calibration.md`
- UI coverage in `tests/ui/test_manual_camera_calibration_ui.py` and unit tests
  for the suggestion helper

## Non-goals (first version)

- Semantic / landmark understanding (geometry ≠ “correct corner of the room”)
- Auto-applying rematches without user confirmation
- Suggestions before a usable RANSAC inlier pose exists
- Full automatic global reassignment of all pairs every frame
- Changing the default RANSAC threshold solely for this feature

## Success criteria

- After a rejected pair appears, the user can see a concrete candidate
  (location and/or alternate point) instead of guessing.
- Accepting a suggestion and re-fitting either promotes the pair into the
  inlier / below-threshold set or clearly fails without leaving the
  calibration in a worse silent state.
- Identity point colors remain stable; diagnostics stay on halos / ghosts /
  connectors.
- Ambiguous geometry produces no suggestion rather than a misleading one.

## Open questions

- Gate suggestions on `rejectionApplied` only, or also on “RANSAC fell back but
  still returned flagged indices”?
- Cost matrix: greedy nearest vs Hungarian assignment for multiple outliers?
- Should ghost targets appear in the map view (back-projection) as well as the
  camera view?
- How large a margin between best and second-best pixel costs is required
  before showing a rematch?
