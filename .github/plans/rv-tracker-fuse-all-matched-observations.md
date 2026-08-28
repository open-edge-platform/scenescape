<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# PoC: Fuse all matched observations per track

## Goal

Update each track using **all** matched camera observations within a chunk, not only the
last-matched one. This requires per-track (individual) Kalman correction instead of the
current single-shot `correct()` for all tracks. Evaluate for regression on existing datasets
and tracker configurations before deciding whether to productize. Results are non-deterministic;
some variability is expected.

## Root cause (current behavior)

- Batched `MultipleObjectTracker::matchAndAssignMeasurements`
  (`MultipleObjectTracker.cpp`): matches each camera to tracks in parallel, groups all
  matches into `matchesPerTrack[trackIdx]`, but keeps geometry only from `matches.back()`
  (the last matched camera). Calls `mTrackManager.setMeasurement(id, fusedObject)` **once** per track.
- `TrackManager::mMeasurementMap` is `unordered_map<Id, TrackedObject>` (one measurement per id).
- `TrackManager::correct()` applies each stored measurement **once**; counters
  (`mNumberOfTrackedFrames` / `mNonMeasurementFrames`) increment once per frame.
- `MultiModelKalmanEstimator::correct()` **overwrites** `mCurrentState.attributes = measurement.attributes`
  and **combines** classification. => the last-applied measurement's attributes win.

## Consumers of the shared `rv` library (both rebuilt for evaluation)

- Controller (Python via pybind): `ilabs_tracking.py` `update_tracks_batched` -> `tracker.track(per-camera)`.
- Tracker service (C++): `tracking_worker.cpp` `match_and_convert` -> `tracker_.track(per-camera)`.

## Confirmed decisions

1. Classification: keep `combine()` accumulating across all matched observations (Option A).
2. Measurement noise: leave `mDefaultMeasurementNoise` as-is for the first PoC run (Option A);
   only tune if evaluation shows covariance over-confidence.
3. Determinism: sort matches by camera index before applying (Option A).

## Design (minimal)

### Phase 1 — Core change (shared `rv` library)

1. `TrackManager.hpp`: change `mMeasurementMap` to `unordered_map<Id, std::vector<TrackedObject>>`;
   add `addMeasurement(id, obj)` (append). Keep `setMeasurement(id, obj)` as clear+append so the
   single-camera path and other callers are unaffected.
2. `TrackManager.cpp`:
   - `correct()`: for each id with measurements, apply each sequentially via `estimator.correct(m)`
     (sequential Kalman update, same timestamp, no predict between). Counters increment **once**
     per track per frame (preserve reliability/aging). Same for the suspended-track reactivation path.
   - `setMeasurement` / `addMeasurement` maintain the vector; `predict()` already clears the map.
3. Batched `MultipleObjectTracker::matchAndAssignMeasurements`:
   - For each track, iterate all matches in `matchesPerTrack[trackIdx]`, sorted by camera index.
   - Register each matched observation (its own geometry) via `addMeasurement`.
   - Keep metadata fusion: compute fused attributes/classification (`fuseMetadata` +
     `mergeHistoricalMetadata`) and attach to the **last** registered observation so its attributes
     win in `correct()`.
   - Keep the existing `isTrackAssigned` + object-removal + unassigned-track logic.
4. Single-camera path (`matchAndAssignMeasurements` object-vector overload) unchanged (one detection/track).
5. New-track cross-camera grouping in batched `track()` unchanged (out of scope).

### Phase 2 — Tests

6. Add C++ unit tests in `TrackingTests.cpp` / `MetadataFusionTests.cpp`:
   - A track matched by 2+ cameras converges toward the fused position (not just the last camera).
   - 1-camera case is unchanged (no regression).
   - Counters/reliability unchanged.
   - Metadata fusion still passes.

### Phase 3 — Evaluation

7. Rebuild `intel/scenescape-controller` and tracker images (freshness gate); capture a baseline
   run on the unmodified image, then a PoC run.
8. Run the black-box suite from `tools/tracker/evaluation` across all three configs
   (Controller-immediate, Controller-TC, Tracker-Service), collecting HOTA/MOTA/IDF1 (TrackEval),
   DIST_T/LOC (Diagnostic), and jitter (Jitter).
9. Non-determinism: run N repeats per config for baseline and PoC; compare mean +/- std; PoC must
   not regress beyond baseline variability.
10. If covariance over-confidence appears, sweep `mDefaultMeasurementNoise`.

## Critical opens / risks

- Covariance over-confidence: N sequential corrects at one timestamp shrink covariance more than
  one => may need measurement-noise tuning.
- Attribute win order: fused metadata must be applied last (correct overwrites attributes).
- Behavior must be identical when a track matches exactly one camera (no 1-camera regression).

## Relevant files

- `controller/src/robot_vision/src/rv/tracking/MultipleObjectTracker.cpp` (batched match)
- `controller/src/robot_vision/include/rv/tracking/TrackManager.hpp` (map type, API)
- `controller/src/robot_vision/src/rv/tracking/TrackManager.cpp` (`correct`, `setMeasurement`)
- `controller/src/robot_vision/test/MetadataFusionTests.cpp`, `TrackingTests.cpp` (C++ unit tests)
- `tools/tracker/evaluation/pipeline_configs/black_box_unity/*` (regression suite)

## Verification

- `cd controller/src/robot_vision && make cpp-tests` (runs `ctest -V`) — all pass.
- Rebuild images before evaluation (freshness gate).
- Baseline vs PoC black-box evaluation via `tools/tracker/evaluation` (`.venv`,
  `python -m run_black_box_evaluation`) across all three configs; no metric regression beyond
  run-to-run variance.

## Decisions / status

- Scope limited to the batched multi-camera existing-track update path.
- No productization commitment — gated on Phase 3 evaluation results.
