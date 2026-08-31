<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Fuse all matched observations per track

## Goal

Update each track using **all** matched camera observations within a chunk, not only the
last-matched one, applying a sequential per-track Kalman correction instead of a single-shot
`correct()` that keeps only the last camera. This is the default tracker behavior; there is no
configuration toggle. The change targets the batched multi-camera existing-track update path shared
by the Scene Controller and the Tracker service.

## Background (previous behavior)

- Batched `MultipleObjectTracker::matchAndAssignMeasurements`
  (`MultipleObjectTracker.cpp`) matched each camera to tracks in parallel, grouped all matches into
  `matchesPerTrack[trackIdx]`, but kept geometry only from `matches.back()` (the last matched
  camera), calling `mTrackManager.setMeasurement(id, fusedObject)` **once** per track.
- `TrackManager::mMeasurementMap` held one measurement per id.
- `TrackManager::correct()` applied each stored measurement once; counters
  (`mNumberOfTrackedFrames` / `mNonMeasurementFrames`) incremented once per frame.
- `MultiModelKalmanEstimator::correct()` overwrites `mCurrentState.attributes = measurement.attributes`
  and combines classification, so the last-applied measurement's attributes win.

This made the batched/time-chunked result depend on the configured camera order and discarded
information from all but the last matched camera.

## Consumers of the shared `rv` library (both rebuilt and validated)

- Scene Controller (Python via pybind): `ilabs_tracking.py` `update_tracks_batched` ->
  `tracker.track(per-camera)`.
- Tracker service (C++): `tracking_worker.cpp` `match_and_convert` -> `tracker_.track(per-camera)`.

## Design decisions

1. Default-on, no configuration toggle. Evaluation shows a strict improvement on the batched paths
   and no regression on the single-observation path, so the behavior ships as the default with no
   opt-out.
2. Classification: `combine()` continues to accumulate across all matched observations. A track
   matched by multiple cameras accumulates classification evidence once per observation; this is
   intentional and documented.
3. Measurement noise: `mDefaultMeasurementNoise` is unchanged. Sequential per-observation updates
   are guarded by a covariance regression test rather than a noise adjustment.
4. IMM: the multi-model estimator is validated by unit tests only; the sequential-correct behavior
   is changed only if a regression surfaces (see risks).
5. Determinism: matches are sorted by camera index before being applied so repeated runs fuse
   observations identically and the result is independent of the configured camera order.

## Scope

In scope: the batched multi-camera existing-track update path.

Out of scope: the single-camera `matchAndAssignMeasurements` overload (one detection per track), the
new-track cross-camera grouping in batched `track()`, and any change to `TrackManagerConfig`
defaults. `addMeasurement` is not exposed through the Python pybind surface.

## Implementation

### Phase 1 — Core change (shared `rv` library)

1. `TrackManager.hpp`: `mMeasurementMap` is `unordered_map<Id, std::vector<TrackedObject>>`;
   `addMeasurement(id, obj)` appends. `setMeasurement(id, obj)` clears and sets a single element so
   the single-camera path and other callers (`TrackTracker.cpp`, pybind) are unaffected.
2. `TrackManager.cpp`:
   - `correct()`: for each id with measurements, apply each sequentially via `estimator.correct(m)`
     (sequential Kalman update, same timestamp, no predict between). Counters increment **once** per
     track per frame to preserve reliability/aging. Same for the suspended-track reactivation path.
   - `setMeasurement` / `addMeasurement` maintain the vector; `predict()` clears the map.
3. Batched `MultipleObjectTracker::matchAndAssignMeasurements`:
   - For each track, iterate all matches in `matchesPerTrack[trackIdx]`, sorted by camera index.
   - Register each matched observation (its own geometry) via `addMeasurement`.
   - Compute fused attributes/classification (`fuseMetadata` + `mergeHistoricalMetadata`) and attach
     them to the **last** registered observation so its attributes win in `correct()`.
   - Preserve the existing `isTrackAssigned` + object-removal + unassigned-track logic.
   - Sort `matchesPerTrack[trackIdx]` in place (no extra copy).
4. Single-camera path (`matchAndAssignMeasurements` object-vector overload) unchanged.
5. New-track cross-camera grouping in batched `track()` unchanged.

### Phase 2 — Test hardening

6. C++ unit tests (`MultiObservationFusionTests.cpp`, `TrackingTests.cpp`,
   `MetadataFusionTests.cpp`):
   - A track matched by 2+ cameras converges toward the fused position (not just the last camera).
   - The single-camera case is identical to the single-object path (no regression).
   - Counters, reliability, and aging are unchanged under multi-observation input (once-per-frame).
   - Suspended-track reactivation applies all queued observations.
   - IMM multi-model (CV/CA/CTRV) fusion sanity check; a regression here is the trigger to revisit
     the IMM update (see risks).
   - Covariance regression: the multi-observation update does not collapse covariance to an
     over-confident/unusable state.
   - Metadata fusion selects the highest-confidence field across **all** matched cameras (not just
     the last); classification accumulation across observations is asserted as intentional.

### Phase 3 — Documentation

7. Update the Scene Controller and Tracker service documentation
   (`docs/user-guide/microservices/…`, service `README`/`Agents.md`, controller docs) to describe
   the multi-observation fusion behavior, its default-on status, order-invariance, and the
   classification-accumulation semantics. Follow the documentation-how skill for exact locations.

### Phase 4 — Verification and evaluation gate

8. `cd controller/src/robot_vision && make cpp-tests` (runs `ctest -V`) — all pass.
9. Rebuild `intel/scenescape-controller` and the tracker image (freshness gate) before any runtime
   evaluation.
10. Re-run the black-box suite from `tools/tracker/evaluation` (`.venv`,
    `python -m run_black_box_evaluation`) across all three configs (Controller-immediate,
    Controller-TC, Tracker-Service); confirm no accuracy/jitter regression beyond run-to-run
    variance and reproduce the order-invariance result.

## Risks

- IMM probability distortion: `MultiModelKalmanEstimator::correct()` consumes
  `predictedMeasurementMean` computed once in `predict()`; applying N observations at one timestamp
  reuses that prediction and compounds model probabilities. Validated by unit tests; reworked only
  if a regression is observed.
- Covariance over-confidence: N sequential corrects at one timestamp shrink covariance more than a
  single fused update. Statistically sound for independent per-camera observations; guarded by a
  covariance regression test.
- Attribute win order: fused metadata must be applied on the last observation because `correct()`
  overwrites attributes.
- No single-camera regression: behavior must be identical when a track matches exactly one camera.

## Relevant files

- `controller/src/robot_vision/src/rv/tracking/MultipleObjectTracker.cpp` (batched match)
- `controller/src/robot_vision/include/rv/tracking/TrackManager.hpp` (map type, API)
- `controller/src/robot_vision/src/rv/tracking/TrackManager.cpp` (`correct`, `setMeasurement`)
- `controller/src/robot_vision/src/rv/tracking/MultiModelKalmanEstimator.cpp` (`correct`)
- `controller/src/robot_vision/test/MultiObservationFusionTests.cpp`,
  `controller/src/robot_vision/test/TrackingTests.cpp`,
  `controller/src/robot_vision/test/MetadataFusionTests.cpp` (C++ unit tests)
- `tools/tracker/evaluation/pipeline_configs/black_box_unity/*` (regression suite)
- Scene Controller and Tracker service documentation

## Validation evidence

Unity dataset (`tests/system/metric/unity_dataset`), two cameras. Baseline images built from the
branch merge-base `origin/main` (`074d2073`); updated images from this branch. OTEL metrics disabled
to isolate tracking quality. All C++ unit tests (including the multi-observation fusion tests) pass.

### Regression, baseline vs updated (normal camera order, N=3, reproduced across two runs)

- **Controller-immediate (control, one camera per chunk): within noise.** Accuracy deltas
  <= 0.13% relative (HOTA -0.0010, IDF1 -0.0005, MOTA -0.0010); jitter deltas flip sign between
  runs, i.e. dominated by run-to-run variance. As expected, the change is a no-op here since each
  camera is processed in its own chunk.
- **Controller-TC (time-chunked): large improvement.**

  | metric | baseline | updated | delta |
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

  | metric | baseline | updated | delta |
  |---|---|---|---|
  | HOTA | 0.6893 | 0.7479 | +0.059 |
  | IDF1 | 0.9361 | 0.9819 | +0.046 |
  | MOTA | 0.8745 | 0.9645 | +0.090 |
  | DIST_T_mean | 0.5515 | 0.4486 | -0.103 |
  | LOC_T_X_mae | 0.4101 | 0.3771 | -0.033 |
  | LOC_T_Y_mae | 0.2807 | 0.1966 | -0.084 |
  | rms_jerk_ratio | 1.62 | 0.86 | -0.76 |
  | acceleration_variance_ratio | 4.22 | 1.00 | -3.22 |

### Camera-order sensitivity, normal vs reversed camera list (N=2)

`|d|` = absolute shift of a metric when the camera list is reversed; smaller = more order-invariant.

- **Controller-TC: baseline is heavily order-dependent; updated is order-invariant.**

  | metric | base normal -> rev | \|d\| base | updated normal -> rev | \|d\| updated |
  |---|---|---|---|---|
  | MOTA | 0.536 -> 0.911 | **0.375** | 0.974 -> 0.974 | **0.0004** |
  | IDF1 | 0.765 -> 0.955 | **0.190** | 0.987 -> 0.987 | **0.0002** |
  | LOC_T_X_mae | 0.506 -> 0.328 | 0.178 | 0.386 -> 0.380 | 0.007 |
  | LOC_T_Y_mae | 0.192 -> 0.375 | 0.183 | 0.184 -> 0.190 | 0.006 |
  | acceleration_variance_ratio | 12.13 -> 8.77 | 3.37 | 3.88 -> 3.64 | 0.24 |

  Reversing the config's camera list swings baseline MOTA by 0.37 and localization error by ~0.18 m
  because the old code keeps only the last matched camera. The updated behavior is essentially
  unchanged.

- **Tracker-Service: same direction on localization/jitter; updated dominates in either order.**
  LOC_T_Y_mae \|d\| base 0.037 vs updated 0.014; DIST_T_mean \|d\| base 0.015 vs updated 0.005;
  jitter ratios ~2x more stable. A couple of accuracy metrics (MOTA/IDF1) show slightly larger
  updated shifts, but the updated worst order still beats the baseline best order (updated-reversed
  MOTA 0.949 / IDF1 0.974 > baseline-best MOTA 0.877 / IDF1 0.937).

- **Controller-immediate (control): both arms order-insensitive** (all accuracy shifts <= 0.0015),
  confirming the effect is specific to the batched/time-chunked paths.

### Conclusion

The change substantially improves accuracy and smoothness on the batched paths (Controller-TC,
Tracker-Service) with no real regression on the single-observation path, and it removes the
unintended dependency on the configured camera order for the time-chunked controller.

## Status

- Phase 1 (core change) implemented.
- Phase 2 (test hardening) in progress.
- Phases 3–4 (documentation, verification/evaluation gate) pending.
