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
11. Camera-order sensitivity: re-run the suite with the dataset `cameras` list reversed
    (`[Cam_x2_0, Cam_x1_0]` instead of `[Cam_x1_0, Cam_x2_0]`) for both baseline and PoC, and
    quantify how much reversing the order shifts each metric per arm. Because the baseline keeps
    only the last matched camera in a chunk, its results are expected to depend heavily on the
    configured camera order for the batched/time-chunked paths; the PoC should be order-invariant.

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

## Evaluation results

Unity dataset (`tests/system/metric/unity_dataset`), two cameras. Baseline images built from the
branch merge-base `origin/main` (`074d2073`); PoC images from this branch. OTEL metrics disabled to
isolate tracking quality. All C++ unit tests (including the two new multi-observation fusion tests)
pass.

### Phase 3a — regression, baseline vs PoC (normal camera order, N=3, reproduced across two runs)

- **Controller-immediate (control, one camera per chunk): within noise.** Accuracy deltas
  <= 0.13% relative (HOTA -0.0010, IDF1 -0.0005, MOTA -0.0010); jitter deltas flip sign between
  runs, i.e. dominated by run-to-run variance. As expected, the change is a no-op here since each
  camera is processed in its own chunk.
- **Controller-TC (time-chunked): large improvement.**

  | metric | baseline | PoC | delta |
  |---|---|---|---|
  | HOTA | 0.6922 | 0.7563 | +0.064 |
  | IDF1 | 0.7520 | 0.9869 | +0.235 |
  | MOTA | 0.5103 | 0.9742 | +0.464 |
  | DIST_T_mean | 0.5757 | 0.4454 | -0.130 |
  | LOC_T_X_mae | 0.5075 | 0.3847 | -0.123 |
  | LOC_T_Y_mae | 0.1938 | 0.1856 | -0.008 |
  | rms_jerk_ratio | 2.74 | 1.85 | -0.89 |
  | acceleration_variance_ratio | 10.07 | 3.97 | -6.11 |

- **Tracker-Service: large improvement.**

  | metric | baseline | PoC | delta |
  |---|---|---|---|
  | HOTA | 0.6893 | 0.7479 | +0.059 |
  | IDF1 | 0.9361 | 0.9819 | +0.046 |
  | MOTA | 0.8745 | 0.9645 | +0.090 |
  | DIST_T_mean | 0.5515 | 0.4486 | -0.103 |
  | LOC_T_X_mae | 0.4101 | 0.3771 | -0.033 |
  | LOC_T_Y_mae | 0.2807 | 0.1966 | -0.084 |
  | rms_jerk_ratio | 1.62 | 0.86 | -0.76 |
  | acceleration_variance_ratio | 4.22 | 1.00 | -3.22 |

### Phase 3b — camera-order sensitivity, normal vs reversed camera list (N=2)

`|d|` = absolute shift of a metric when the camera list is reversed; smaller = more order-invariant.

- **Controller-TC: baseline is heavily order-dependent; PoC is order-invariant.**

  | metric | base normal -> rev | \|d\| base | PoC normal -> rev | \|d\| PoC |
  |---|---|---|---|---|
  | MOTA | 0.536 -> 0.911 | **0.375** | 0.974 -> 0.974 | **0.0004** |
  | IDF1 | 0.765 -> 0.955 | **0.190** | 0.987 -> 0.987 | **0.0002** |
  | LOC_T_X_mae | 0.506 -> 0.328 | 0.178 | 0.386 -> 0.380 | 0.007 |
  | LOC_T_Y_mae | 0.192 -> 0.375 | 0.183 | 0.184 -> 0.190 | 0.006 |
  | acceleration_variance_ratio | 12.13 -> 8.77 | 3.37 | 3.88 -> 3.64 | 0.24 |

  Reversing the config's camera list swings baseline MOTA by 0.37 and localization error by ~0.18 m
  because the old code keeps only the last matched camera. The PoC is essentially unchanged.

- **Tracker-Service: same direction on localization/jitter; PoC dominates in either order.**
  LOC_T_Y_mae \|d\| base 0.037 vs PoC 0.014; DIST_T_mean \|d\| base 0.015 vs PoC 0.005; jitter
  ratios ~2x more stable under PoC. A couple of accuracy metrics (MOTA/IDF1) show slightly larger
  PoC shifts, but PoC's worst order still beats baseline's best order (PoC-reversed MOTA 0.949 /
  IDF1 0.974 > baseline-best MOTA 0.877 / IDF1 0.937).

- **Controller-immediate (control): both arms order-insensitive** (all accuracy shifts <= 0.0015),
  confirming the effect is specific to the batched/time-chunked paths.

### Conclusion

The PoC substantially improves accuracy and smoothness on the batched paths (Controller-TC,
Tracker-Service) with no real regression on the single-observation path, and it removes the
unintended dependency on camera order in the configuration for the time-chunked controller. This
supports productization.

## Decisions / status

- Scope limited to the batched multi-camera existing-track update path.
- Phase 1 (core change), Phase 2 (tests), and Phase 3 (evaluation) complete; evaluation supports
  productization.
