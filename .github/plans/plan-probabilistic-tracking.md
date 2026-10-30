<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: Probabilistic Tracking Association

- **Author(s)**: [Sarat Poluri](https://github.com/spoluri)
- **Date**: 2026-06-06
- **Status**: Phase 1 complete; Phases 2–3 open
- **ADR**: [ADR-0017](../../docs/adr/0017-probabilistic-tracking-association.md)
- **Design**: [Probabilistic Tracking Association](../../docs/design/probabilistic-tracking-association.md)
- **Evaluation**: [ADR-0009](../../docs/adr/0009-tracking-evaluation.md), [Tracker Evaluation Pipeline](../../docs/design/tracker-evaluation-pipeline.md)

This plan tracks **tasks, validation, and exit criteria**. Architecture and design detail live in the ADR and design doc above.

---

## Phase 1 — Track-side position Mahalanobis

**Status:** Complete (production default `position_mahalanobis`, `max_radius_m: 10`).

### 1.1 robot_vision

| Task | Location | Notes |
|------|----------|-------|
| Add `DistanceType::PositionMahalanobis` | `ObjectMatching.hpp/.cpp` | 2×2 block on (x,y) |
| Chi-squared gate helper | `ObjectMatching.cpp` / `Utils.hpp` | `df=2` |
| Keep `max_radius_m` as hard ceiling | `ObjectMatching.cpp` | Independent of χ² |
| Velocity-aligned kinematic process noise | `MultiModelKalmanEstimator.cpp` | Along-track ≫ cross-track Q |
| UKF / IMM association covariance fixes | UKF + IMM | Top-model S; Sxy sigma points; yaw-rate init |
| Unit tests | `TrackingTests.cpp`, `tracking_test.py` | Along-track vs lateral preference |
| Python binding | `tracking.cpp` | Expose enum |

### 1.2 Tracker service

| Task | Location |
|------|----------|
| `AssociationConfig` on `TrackingConfig` | `inc/config_loader.hpp` |
| Schema + defaults | `schema/config.schema.json`, `config/tracker.json` |
| Env var overrides | `inc/env_vars.hpp`, `src/config_loader.cpp` |
| Wire method + gate | `src/tracking_worker.cpp` |
| Remove hardcoded 2.0 m association threshold | `src/tracking_worker.cpp` |

Follow [Tracker Agents.md](../../tracker/Agents.md) config checklist.

### 1.3 Controller

| Task | Location |
|------|----------|
| Read association config | `ilabs_tracking.py` |
| Stop averaging `tracking_radius` for association | `ilabs_tracking.py` |
| Feature-flag parity with tracker service | controller tracker config JSON |
| Birth clustering Euclidean ~2 m; equal-weight multi-cam geometry | `MultipleObjectTracker` / fuse path |

### 1.4 Soft deprecation

| Task | Status |
|------|--------|
| Warn when `tracking_radius` differs and method ≠ euclidean | Done / follow-up as needed |
| Document deprecation in object library / user guide | Follow-up PR |
| Do **not** remove `tracking_radius` DB field in Phase 1 | Held |

### Phase 1 exit criteria

- [x] Feature flag ships; `position_mahalanobis` validated vs Euclidean
- [x] Evaluation metrics within thresholds on gated datasets
- [x] CI unit coverage for association wiring
- [x] ADR-0017 → `Accepted` for Phase 1 scope
- [x] Default flip → `position_mahalanobis` after Controller-TC + Wildtrack re-signoff

### Phase 1 validation notes

Artifacts under `/tmp/phase1-signoff/`, `/tmp/phase1-tc-vs-tracker/`, `/tmp/phase1-default-flip/`.

- **Unity Controller-Immediate 10 fps** (2026-08-15): Mahalanobis matched or slightly improved AssA/LocA; lower jitter once config reached category trackers.
- **Covariance shaping** (2026-08-16): fixed isotropic Q / broken Sxy / IMM inflation → velocity-aligned coast ellipses (unit-tested).
- **Unity Immediate 1 fps / Tracker-Service 10 fps** (2026-08-16): essentially tied vs Euclidean.
- **Controller-TC vs Tracker** (2026-08-16): Fix 1 birth Euclidean ~2 m; Fix 2 equal-weight geometry average — CLR HOTA 71→77, IDF1 71→99.
- **Default-flip re-signoff** (2026-08-16):

| Suite | HOTA Δ | AssA Δ | LocA Δ | IDSW Δ | Gate |
|-------|--------|--------|--------|--------|------|
| Unity Controller-TC 10 fps | −0.03 | −0.04 | −0.01 | 0 | **PASS** |
| Wildtrack Tracker-Service 2 fps | **+0.69** | **+0.92** | **+0.51** | +23 | **PASS** primary; IDSW over +5% budget |

Residual: Controller-TC `rms_jerk_ratio` +17% vs +10% budget; Wildtrack IDSW. Accepted for Phase 1; revisit with Phase 2 R.

---

## Phase 2 — Geometry-derived measurement covariance

**Goal:** See [design §5.3](../../docs/design/probabilistic-tracking-association.md#53-phase-2--geometry-derived-measurement-covariance).

### 2.1 Tasks

| Task | Location |
|------|----------|
| Pixel→world Σ_xy in `CoordinateTransformer` | `tracker/src/coordinate_transformer.cpp` |
| `position_covariance_xy` on `Detection` | `tracker/inc/tracking_types.hpp` |
| Optional `measurementCovariance` on `TrackedObject` — **done** as 7×7 `measurementNoiseCov` (Python `measurement_noise_covariance`) | `robot_vision` |
| `DistanceType::PositionMahalanobisCombined` | `ObjectMatching.cpp` |
| `measurement_uncertainty.*` config | schema, loader, controller |
| Calibrate α offline; record default | eval harness + design/plan appendix |

### Phase 2 validation

```bash
cd tracker && make test-unit-coverage
```

- Transformer tests: Σ grows with bbox height, range, lower confidence; Jacobian FD vs analytic
- Matching: combined gate wider at long range
- Eval: metric test + Wildtrack; AssA up, ID switches down, LocA hold/improve

### Phase 2 exit criteria

- [ ] α calibrated and documented
- [ ] `position_mahalanobis_combined` passes evaluation thresholds
- [ ] Per-object `tracking_radius` unused in association paths
- [ ] Optional debug emit of Σ_xy for sampled detections

---

## Phase 3 — Per-measurement UKF update

**Goal:** See [design §5.4](../../docs/design/probabilistic-tracking-association.md#54-phase-3--per-measurement-ukf-update).

### 3.1 Tasks

| Task | Location |
|------|----------|
| `correct(measurement, R_optional)` — **done**: R is read from the measurement's `measurementNoiseCov` | `MultiModelKalmanEstimator.*`, `UnscentedKalmanFilter.*` |
| Thread R onto `TrackedObject` before correct | `tracking_worker.cpp`, `ilabs_tracking.py` |
| Global filter noise knobs in config | schema, loader |
| Deprecate `tracking_radius` in manager + user guide | `manager/`, `docs/user-guide/` |
| (Later) multi-cam class/confidence fusion | `fuseMetadata` |

**Status (robot_vision, `feature/prob-tracking-extracted-3d-R`):** a detection that carries R gets information-weighted multi-camera fusion (`fuseGeometry`), association with S = H P Hᵀ + R in `PositionMahalanobis` and `Mahalanobis`, the UKF / IMM update (gain and model likelihood) with its R, and a birth P seeded from it. Without R every path is unchanged. Nothing sets R yet (Controller, Tracker Service), so production behaviour is unchanged. The gate becomes R-aware whenever R is present, not through a separate `position_mahalanobis_combined` method.

### Phase 3 validation

- Unit: low R pulls strongly; high R weakly; jerk improves vs Phase 2 on noisy detections
- Eval: LocA/jitter gain; AssA holds vs Phase 2
- Load: `cd tracker && make test-load` — transform+track overhead ≤ 10% vs Phase 1

### Phase 3 exit criteria

- [ ] End-to-end: predict → associate(S_pred + R) → correct(R)
- [ ] `tracking_radius` deprecated in object-library docs
- [ ] Default method → `position_mahalanobis_combined`
- [ ] Metrics meet or exceed Phase 2 on gated datasets

---

## Non-planar Z / `vz` tracking (controller + tracker)

**Status:** Controller + tracker Z/`vz` tracking on `feature/prob-tracking-extracted-3d`. Tracker 3D detection input (`translation` / `size` / `rotation`) came through main (#2050) and is merged.  
**Out of scope here:** mesh/DEM foot-ray for plain 2D cameras (separate PR). Issue 1 from the `vz` review (ground-plane pixel path) stays deferred.

### Shared (`robot_vision`) — done with controller

Tracker builds `controller/src/robot_vision` in-tree (`tracker/CMakeLists.txt`), so these apply on tracker rebuild:

| Item | Detail | Commit / notes |
|------|--------|----------------|
| State `vz` | Layout `[… z, vz, length, width, height, yaw, yaw_rate]`; CV/CA/CTRV integrate `z += vz·dt`; CP zeros `vz` | `ee393034` |
| Process noise | Independent `Q[vz,vz]` | same |
| 3D association | Euclidean + `PositionMahalanobis` on `(x,y,z)`; birth cluster Euclidean is 3D | `0f4c1b5a` |
| χ² gate | Matching uses `df=3` (~11.34 @ p=0.99); UI XY ellipse stays `df=2` | same |
| Named indices | `StateIndex` / `MeasurementIndex` | same |
| `isDynamic` | `vx²+vy²+vz² > 1` (vertical counts toward coast aging) | same |
| Unit tests | Climb, coast, `|vz|≈0`, stacked-floor association | same |

### Controller-only — done (skip for tracker)

| Item | Location |
|------|----------|
| Association params use `chi2_threshold(p, 3)` | `ilabs_tracking.association_match_params` |
| Association window viz uses `chi2_threshold(p, 2)` | `ilabs_tracking.build_association_window` |
| Publish `velocity[2]` from UKF `vz` | `ilabs_tracking` |
| Prefer detection `translation` / 3D bbox Z when present | `moving_object.mapObjectDetectionToWorld` (already) |
| Functional climb via external-source MQTT | `tests/functional/test_z_tracking.py` |

### Tracker service

**Do not re-implement** shared filter/association math; rebuild against updated `robot_vision`.

| # | Task | Location | Status |
|---|------|----------|--------|
| T1 | χ² `df=3` for match cost; `df=2` for association-window ellipse | `association_config.hpp`, `association_window.hpp` | Done |
| T2 | Detection `translation` / `size` / `rotation` input, translation path preserves Z | #2050 (through main) | Done |
| T3 | Set `zMeasured = true` on the translation path | `coordinate_transformer.cpp` | Done |
| T5 | Assert published `velocity[2]` / `translation[2]` | `track_publisher_test.cpp` | Done |
| T6 | End-to-end: stacked-floor 3D detections stay separate; climbing 3D detection publishes `translation[2]` / `velocity[2]` | `tracking_worker_test.cpp`, `coordinate_transformer_test.cpp` | Done |

**Still deferred / follow-ups from Z review:**

| # | Item | Notes |
|---|------|-------|
| F1 | 3D detection input (`translation` / `size` / `rotation`, bbox-less detections) | **Done:** #2050. |
| F2 | Wildtrack (planar) eval after χ² `df=3` | Gate loosened ~9.21→11.34 at p=0.99 for planar scenes. **Run Wildtrack eval; mitigate from results** (do not pre-mitigate). |
| F3 | Ingest 3D detection `rotation` into tracker / UKF yaw | **Done:** #2050. |
| F4 | Size for 3D detections | **Done:** #2050 requires `size` with `translation`. |
| F5 | Mesh / DEM foot-ray for bbox-only cameras | Separate PR. |
| F6 | Schema `distance` alone without `translation` | Deferred. |
| F8 | One z reference for pixel (ground point) and 3D (box centre) detections | **TODO:** a mixed track publishes a midpoint height, splits on a camera → 3D handover at ≥ ~2 m centre height, and gets spurious `vz` when sensors alternate. |
| F7 | Hybrid birth: `EuclideanBirth` + `zMeasured` | **Done:** XY if either planar; XYZ when both measured. Revisit after metrics. Tracker sets `zMeasured` on translation detections (T3). |

**Birth clustering note (not association default):** Unmatched detection→detection fusion uses `DistanceType::EuclideanBirth` ~`kDefaultBirthClusterRadiusM` (2 m), even when track→detection association is `position_mahalanobis`. Raw detections lack `predictedMeasurementCov`, so Mahalanobis cannot birth-cluster. `EuclideanBirth` is XY when either side lacks `zMeasured` (planar + 3D OD still fuse); XYZ when both have measured Z (stacked floors stay separate). Revisit after metrics / multi-floor datasets.

### Tracker validation

```bash
cd tracker && make test-unit test-robot-vision
```

---

## Rollout checklist

1. [x] Phase 1 default flip (`position_mahalanobis`); `euclidean` rollback retained
2. [ ] Phase 2 opt-in combined; default stays Phase 1 until sign-off
3. [ ] Phase 3 default flip to combined
4. [x] Controller non-planar Z/`vz` + 3D association (`0f4c1b5a` / `ee393034`)
5. [x] Tracker χ² df=3 parity + `vz` publish tests
6. [ ] F2: Wildtrack eval post–χ² df=3; mitigate from results
7. [x] F1: Tracker 3D detection input (#2050) + `zMeasured` (T3)
8. [x] F7: Hybrid birth clustering (`EuclideanBirth` / `zMeasured`)
9. [ ] F8: One z reference for pixel and 3D detections

```mermaid
gantt
    title Probabilistic Tracking Rollout
    dateFormat YYYY-MM-DD
    section Phase1
    robot_vision PositionMahalanobis     :done, p1a, 2026-06-09, 7d
    tracker config + feature flag        :done, p1b, after p1a, 5d
    evaluation baseline + validation     :done, p1c, after p1b, 5d
    section Phase2
    CoordinateTransformer covariance     :p2a, after p1c, 10d
    combined association + calibration   :p2b, after p2a, 7d
    evaluation Wildtrack/metric          :p2c, after p2b, 5d
    section Phase3
    robot_vision per-measurement R       :p3a, after p2c, 10d
    integration + deprecation            :p3b, after p3a, 7d
    final evaluation + default flip      :p3c, after p3b, 5d
```

---

## File touch list

| Component | Phase 1 | Phase 2 | Phase 3 |
|-----------|---------|---------|---------|
| `robot_vision/ObjectMatching.*` | ✓ | ✓ | |
| `robot_vision/TrackedObject.*` | | ✓ | ✓ |
| `robot_vision/MultiModelKalmanEstimator.*` | | | ✓ |
| `tracker/coordinate_transformer.*` | | ✓ | |
| `tracker/config_loader.*`, schema | ✓ | ✓ | ✓ |
| `tracker/tracking_worker.cpp` | ✓ | ✓ | ✓ |
| `controller/ilabs_tracking.py` | ✓ | ✓ | ✓ |
| `manager/models.py` (deprecation) | | | ✓ |
| `tools/tracker/evaluation/` | ✓ | ✓ | ✓ |
