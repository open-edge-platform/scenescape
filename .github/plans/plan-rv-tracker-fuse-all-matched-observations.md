<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Fuse all matched observations per track

## Goal

Update each track using **all** camera observations matched to it within a chunk, not only the
last-matched one. All matched observations are fused into a single measurement and applied with one
Kalman correction per frame. This is the default tracker behavior; there is no configuration toggle.
The change targets the batched multi-camera existing-track update path shared by the Scene
Controller (Python via pybind) and the Tracker service (C++).

## Design decisions

1. Default-on, no configuration toggle.
2. Fuse into a single measurement: geometric fields are averaged (yaw as a circular mean) and
   classification is combined across matched observations, then one Kalman correction is applied per
   frame. This keeps the covariance PSD (positive semi-definite) and makes the result independent of
   the configured camera order.
3. Measurement noise `R` unchanged (fixed `1e-2 * I`). Averaging matched observations keeps `R`
   conservative (no `R/N`), improving the state mean without over-claiming certainty for correlated
   multi-camera errors.
4. Metadata/classification fusion (`fuseMetadata` + `mergeHistoricalMetadata`) is applied once to
   the fused measurement, decoupled from Kalman correction order.
5. Counters (`mNumberOfTrackedFrames` / `mNonMeasurementFrames`) increment once per frame.

## Measurement model note

The measurement vector is purely geometric — `[x, y, z, length, width, height, yaw]`
(`TrackedObject::measurementVector()`); detection confidence is not part of it. `R` is a fixed
scalar-times-identity set once in `MultiModelKalmanEstimator::initialize()`. Because every matched
observation shares the same geometric measurement model, fusing them into one averaged measurement
is the closed form of a joint multi-observation update and applies exactly one correction.

## Alternatives considered

- **Sequential per-observation correction (PoC).** The initial PoC applied one Kalman `correct()`
  per matched observation within a frame (no re-predict between). It improved point-estimate
  metrics, but each correction after the first reused stale prediction statistics
  (predicted-measurement mean, `Pyy`, sigma points) cached by `predict()`, driving the covariance
  non-PSD and then divergent (trace ran to ~5e5 within a few frames). Dropped because a corrupt
  covariance silently breaks gating, IMM likelihoods, and downstream consumers even while the mean
  still tracks; fusing into a single measurement keeps one numerically stable correction instead.
- **Re-predict with `dt=0` between corrects.** Recompute the prediction statistics before each
  correction so no correction runs on stale sigma points. It fixes the divergence but re-runs IMM
  mixing and adds process noise `Q` per observation (spurious uncertainty growth within one frame),
  and stays order-dependent through the nonlinear re-prediction. It also carries higher
  implementation and validation complexity (per-correction re-prediction plumbing plus consistency
  checks). Dropped in favor of single-measurement fusion, which is order-invariant, adds `Q` only
  once per frame, and reuses the already-validated single-correction path.

## Scope

In scope: the batched multi-camera existing-track update path.

Out of scope: the single-camera `matchAndAssignMeasurements` overload (one detection per track), the
new-track cross-camera grouping in batched `track()`, and any change to `TrackManagerConfig`
defaults.

## Implementation

1. `TrackManager::fuseObservations` (`TrackManager.cpp`, declared in `TrackManager.hpp`): fuses a
   vector of same-timestamp observations into one — per-field mean, circular mean for yaw, and
   classification combined across observations. A single observation is returned unchanged.
2. `TrackManager::correct()`: applies one `estimator.correct(fuseObservations(...))` per track in
   both the existing-track and suspended-track reactivation paths. `mMeasurementMap` keeps
   `Id -> vector<TrackedObject>` (populated by `setMeasurement`/`addMeasurement`); `predict()`
   clears it.
3. Batched `MultipleObjectTracker::matchAndAssignMeasurements`: gathers all matched observations per
   track, fuses them with `fuseObservations`, layers metadata via `fuseMetadata` +
   `mergeHistoricalMetadata`, and calls `setMeasurement` once. `matchesPerTrack` is in ascending
   camera order, so fusion is deterministic.
4. Single-camera path and new-track cross-camera grouping are unchanged.

## Tests

`MultiObservationFusionTests.cpp` — all `RobotVisionTests` pass via
`cd controller/src/robot_vision && make cpp-tests`:

- A track matched by 2+ cameras converges toward the fused position.
- The single-camera match is identical to the single-object path (no regression).
- Counters/reliability/aging are unchanged under multi-observation input (once per frame).
- Suspended-track reactivation fuses all queued observations.
- IMM model probabilities stay a valid distribution.
- Covariance regression (`MultiObservationDoesNotCollapseCovariance`): the multi-observation update
  stays finite/PSD and no more uncertain than the single-observation baseline.
- Metadata fusion selects the highest-confidence field across all matched cameras; classification
  accumulation across observations is asserted.

## Future enhancements

- **Observation-variance-aware measurement noise.** Give each observation its own `R` derived from
  its localization variance so more precise sensors weigh more; requires plumbing a per-observation
  `R` into `MultiModelKalmanEstimator::correct()` and `UnscentedKalmanFilterMod::correct()`, which
  today accept only the measurement vector. Caveat: detection confidence (probability the object
  exists) is not localization variance — map confidence to `R` only if localization error is
  demonstrably correlated with confidence, otherwise use sensor-specific variance. Blocked on
  (1) sensor-specific measurement-variance data and/or (2) evidence of a confidence/localization-
  error correlation. Note: correlated multi-camera errors (shared ego/calibration/frame-alignment)
  mean equal-weight fusion with a fixed `R` is conservative by design.
- **Filter-consistency monitoring** (NIS, covariance PSD/consistency checks) for stronger
  regression guarantees.
- **Decouple metadata/attribute fusion from the Kalman correction path.** Fusion is now
  order-independent (applied once to the fused measurement), but attributes still ride on the
  measurement object and are set as a side-effect of `correct()`. Making state estimation and
  metadata fusion fully separate concerns is remaining architectural debt.

## Relevant files

- `controller/src/robot_vision/src/rv/tracking/MultipleObjectTracker.cpp` (batched match, fusion call)
- `controller/src/robot_vision/include/rv/tracking/TrackManager.hpp` (`fuseObservations` decl, API)
- `controller/src/robot_vision/src/rv/tracking/TrackManager.cpp` (`fuseObservations`, `correct`)
- `controller/src/robot_vision/test/MultiObservationFusionTests.cpp` (C++ unit tests)
- `tools/tracker/evaluation/` (black-box evaluation suite)
- Scene Controller and Tracker service documentation

## Validation evidence

Unity dataset (`tests/system/metric/unity_dataset`), two cameras. Baseline images built from the
branch merge-base `origin/main` (`074d2073`), updated images from this branch. OTEL metrics disabled
to isolate tracking quality. N=1. All C++ unit tests pass, including the covariance regression test.

- **Controller-immediate (control, one camera per chunk): within noise.** Fusion is a no-op here.
  HOTA +0.0011, MOTA +0.0004, IDF1 +0.0002; localization within 0.002 m; jitter within run-to-run
  variance.
- **Controller-TC (time-chunked): large improvement.**

  | metric | baseline | updated | delta |
  |---|---|---|---|
  | HOTA | 0.6911 | 0.7488 | +0.058 |
  | IDF1 | 0.7438 | 0.9867 | +0.243 |
  | MOTA | 0.4944 | 0.9738 | +0.479 |
  | DIST_T_mean | 0.5773 | 0.4568 | -0.121 |
  | LOC_T_X_mae | 0.5096 | 0.3890 | -0.121 |
  | LOC_T_Y_mae | 0.1952 | 0.1991 | +0.004 |
  | rms_jerk_ratio | 2.71 | 1.85 | -0.86 |
  | acceleration_variance_ratio | 10.01 | 3.81 | -6.20 |

- **Tracker-Service: large improvement.**

  | metric | baseline | updated | delta |
  |---|---|---|---|
  | HOTA | 0.6812 | 0.7424 | +0.061 |
  | IDF1 | 0.9224 | 0.9822 | +0.060 |
  | MOTA | 0.8477 | 0.9650 | +0.117 |
  | DIST_T_mean | 0.5642 | 0.4581 | -0.106 |
  | LOC_T_X_mae | 0.4326 | 0.3906 | -0.042 |
  | LOC_T_Y_mae | 0.2786 | 0.1976 | -0.081 |
  | rms_jerk_ratio | 1.67 | 0.84 | -0.83 |
  | acceleration_variance_ratio | 4.27 | 0.90 | -3.37 |

### Conclusion

Substantial accuracy and smoothness gains on the batched paths (Controller-TC, Tracker-Service),
no regression on the single-observation path, and camera-order independence for the time-chunked
controller. Every frame applies exactly one numerically stable correction, so the covariance stays
PSD.

## Status

- Core change and test hardening implemented; all C++ unit tests pass, including the re-enabled
  covariance regression test (`MultiObservationDoesNotCollapseCovariance`).
- Evaluation gate passed (baseline vs updated above).
- Documentation (Phase 3) pending: describe multi-observation fusion, its default-on status,
  order-invariance, and single-correction-per-frame behavior in the Scene Controller and Tracker
  service docs (follow the documentation-how skill).
