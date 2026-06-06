<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Implementation Plan: Probabilistic Tracking Association

- **Author(s)**: [Sarat Poluri](https://github.com/spoluri)
- **Date**: 2026-06-06
- **Status**: `Proposed`
- **ADR**: [ADR-0012: Probabilistic Tracking Association](../../adr/0012-probabilistic-tracking-association.md)
- **Evaluation baseline**: [ADR-0009](../../adr/0009-tracking-evaluation.md), [Tracker Evaluation Pipeline](../tracker-evaluation-pipeline.md)

---

## Overview

This plan implements the three phases defined in ADR-0012. Each phase is independently shippable behind a feature flag, validated against the existing tracker evaluation pipeline before the next phase begins.

### Success criteria (all phases)

| Metric | Tool | Regression threshold (initial) |
|--------|------|--------------------------------|
| HOTA | TrackEval | ≥ baseline − 2% |
| AssA (association) | TrackEval | ≥ baseline − 3% |
| LocA | TrackEval | ≥ baseline − 2% |
| ID switches | TrackEval | ≤ baseline + 5% |
| RMS jerk / jitter | DiagnosticEvaluator | ≤ baseline + 10% |
| Unit / service tests | `make test-unit`, `make test-service` | All pass |
| Line / branch coverage | tracker CI | ≥ existing thresholds |

Capture **baseline metrics on `main`** with current Euclidean + fixed threshold before Phase 1 merges.

### Feature flag

Add to `tracker-config.json` and controller tracker config:

```json
{
  "association": {
    "method": "euclidean",
    "gate_probability": 0.99,
    "max_radius_m": 10.0
  }
}
```

| `method` value | Phase |
|----------------|-------|
| `euclidean` | Current behavior (default until Phase 1 validated) |
| `position_mahalanobis` | Phase 1 |
| `position_mahalanobis_combined` | Phase 2+ |

---

## Phase 1 — Track-side position Mahalanobis

**Goal:** Use UKF predicted covariance for association; replace meter thresholds with chi-squared gating. No measurement covariance yet.

### 1.1 robot_vision changes

| Task | Location | Notes |
|------|----------|-------|
| Add `DistanceType::PositionMahalanobis` | `ObjectMatching.hpp/.cpp` | 2×2 block on (x,y); innovation = z_xy − ŷ_xy |
| Chi-squared gate helper | `ObjectMatching.cpp` or `Utils.hpp` | `threshold = chi2_inv(gate_probability, df=2)` |
| Keep `max_radius_m` as hard ceiling | `ObjectMatching.cpp` | Reject pair if Euclidean xy > max_radius_m regardless of Mahalanobis |
| Unit tests | `TrackingTests.cpp`, `tracking_test.py` | Stationary vs fast mover: gate widens with Δt |
| Python binding | `tracking.cpp` | Expose new enum value |

**Association cost:**

```text
d² = (z_xy − ŷ_xy)ᵀ S_pred[0:2,0:2]⁻¹ (z_xy − ŷ_xy)
valid if d² ≤ χ²(p, 2) and ||z_xy − ŷ_xy|| ≤ max_radius_m
```

### 1.2 Tracker service changes

| Task | Location |
|------|----------|
| Add `AssociationConfig` to `TrackingConfig` | `inc/config_loader.hpp` |
| Schema + defaults | `schema/config.schema.json`, `config/tracker.json` |
| Env var overrides | `inc/env_vars.hpp`, `src/config_loader.cpp` |
| Wire method + gate_probability | `src/tracking_worker.cpp` |
| Remove hardcoded `kTrackingDistanceThreshold = 2.0` | `src/tracking_worker.cpp` |

Follow [Tracker Agents.md](../../../tracker/Agents.md) config checklist (schema, struct, env var, docs).

### 1.3 Controller changes

| Task | Location |
|------|----------|
| Read association config from tracker config / scene params | `ilabs_tracking.py` |
| Stop averaging `tracking_radius` for association | `ilabs_tracking.py` |
| Feature flag parity with tracker service | controller tracker config JSON |

### 1.4 Deprecation (soft)

| Task | Location |
|------|----------|
| Log warning when `tracking_radius` differs from default and association method ≠ euclidean | controller |
| Document deprecation in object library API docs | manager / user guide (follow-up PR) |

Do **not** remove `tracking_radius` DB field in Phase 1.

### Phase 1 validation

#### Automated

```bash
# robot_vision
cd controller/src/robot_vision && make test

# tracker unit + service
cd tracker && make test-unit test-service
```

**New unit tests:**

- `ObjectMatching`: gate accepts detection along velocity axis, rejects equal-distance lateral jump for fast track
- `ObjectMatching`: gate tightens for recently corrected slow track
- `tracking_worker_test`: feature flag selects distance type

#### Evaluation harness

```bash
cd tools/tracker/evaluation
# Run against metric test dataset with euclidean baseline saved, then position_mahalanobis
python run_pipeline.py pipeline_configs/controller_evaluation.yaml
```

Compare HOTA, AssA, LocA, IDF1, jitter vs baseline. Phase 1 passes if association metrics improve or hold within regression thresholds, with no LocA degradation on static scenes.

#### Manual smoke

1. Single pedestrian walking → stable ID, no excess switches vs baseline
2. Two pedestrians crossing → no swaps (AssA stable)
3. Brief occlusion (2–3 chunks no detection) → re-acquire without new ID

#### Exit criteria

- [ ] Feature flag defaults to `euclidean`; `position_mahalanobis` opt-in validated
- [ ] Evaluation metrics within thresholds on metric test dataset
- [ ] CI green (unit, service, coverage)
- [ ] ADR-0012 status → `Accepted` for Phase 1 scope

---

## Phase 2 — Geometry-derived measurement covariance

**Goal:** Propagate bbox pixel uncertainty to world-space R_meas; use S_pred + R_meas for association.

### 2.1 Uncertainty model

Implement in `CoordinateTransformer`:

```text
σ_px = max(min_pixel_sigma, α · bbox_height_px · f(confidence))
Σ_pixel = diag(σ_px², σ_px²)   # foot point (u, v)

J = ∂(x_world, y_world) / ∂(u, v)   # 2×2, numerical or analytic
Σ_xy = J · Σ_pixel · Jᵀ

Optional incidence scaling: Σ_xy *= (1 / cos(θ))²  where θ = angle between ray and ground normal
```

Calibrate **α** offline from evaluation dataset (grid search minimizing LocA error or ID switches).

### 2.2 Data model changes

| Task | Location |
|------|----------|
| Add `position_covariance_xy` (optional 2×2) | `tracker/inc/tracking_types.hpp` (`Detection`) |
| Populate in transform | `tracker/src/coordinate_transformer.cpp` |
| Pass through to `TrackedObject` | attributes or new field on `rv::tracking::TrackedObject` |
| JSON schema (if surfaced on output) | `tracker/schema/` — only if needed for debug |

**robot_vision:** extend `TrackedObject` with optional `measurementCovariance` (7×7 or 2×2 block metadata).

### 2.3 Association changes

| Task | Location |
|------|----------|
| Add `DistanceType::PositionMahalanobisCombined` | `ObjectMatching.cpp` |
| S_assoc = S_pred[xy] + R_meas[xy]; invert via 2×2 direct formula | `ObjectMatching.cpp` |
| Fallback when R_meas absent: Phase 1 behavior | `ObjectMatching.cpp` |
| Config: `measurement_uncertainty.*` | schema, config loader, controller |

### 2.4 Config schema additions

```json
{
  "association": {
    "method": "position_mahalanobis_combined",
    "gate_probability": 0.99,
    "max_radius_m": 10.0
  },
  "measurement_uncertainty": {
    "pixel_sigma_fraction_of_bbox_height": 0.03,
    "scale_by_confidence": true,
    "min_pixel_sigma": 2.0,
    "incidence_angle_scaling": true
  }
}
```

### Phase 2 validation

#### Automated

```bash
cd tracker && make test-unit-coverage
```

**New tests:**

- `coordinate_transformer_test`: Σ_xy grows with bbox height and range
- `coordinate_transformer_test`: lower confidence → larger Σ_xy
- `coordinate_transformer_test`: Jacobian sanity (finite-difference vs analytic)
- `ObjectMatching`: combined covariance gate wider at long range

#### Calibration procedure

1. Run evaluation pipeline on metric test dataset with α ∈ {0.01, 0.02, 0.03, 0.05, 0.08}
2. Select α maximizing AssA subject to LocA ≥ baseline
3. Record chosen α in config default and plan appendix

#### Evaluation harness

Run full pipeline on:

- **Metric test dataset** (regression)
- **Wildtrack subset** (if available in harness) — multi-camera, varying range

Focus metrics:

- **AssA** should improve (better gating at range and speed)
- **ID switches** should decrease on occlusion/re-entry scenarios
- **LocA** should hold or improve

#### Manual smoke

1. Same object at near vs far camera — single track, no duplicate births
2. Low-confidence noisy detections — less likely to steal tracks from high-confidence matches
3. Multi-camera same object — dedup improved (related to foot-point offset work already in transformer)

#### Exit criteria

- [ ] α calibrated and documented
- [ ] `position_mahalanobis_combined` passes evaluation thresholds
- [ ] Per-object `tracking_radius` unused in association code paths
- [ ] Debug logging can emit Σ_xy for sampled detections (optional observability)

---

## Phase 3 — Per-measurement UKF update

**Goal:** Filter correction uses the same R as association, completing the probabilistic pipeline.

### 3.1 robot_vision changes

| Task | Location |
|------|----------|
| `TrackedObject::measurementCovariance` field | `TrackedObject.hpp/.cpp` |
| `MultiModelKalmanEstimator::correct(measurement, R_optional)` | `MultiModelKalmanEstimator.hpp/.cpp` |
| Per-model UKF correct with varying R | `UnscentedKalmanFilterMod` (if needed) |
| Default R from `TrackManagerConfig` when not provided | backward compatible |
| Python bindings + tests | `tracking.cpp`, `tracking_test.py` |

### 3.2 Tracker / controller integration

| Task | Location |
|------|----------|
| Set measurement covariance on `TrackedObject` before `setMeasurement` | `tracking_worker.cpp`, `ilabs_tracking.py` |
| Global `filter.process_noise`, `filter.base_measurement_noise` in config | schema, config loader |
| Remove fixed hardcoded noise in `build_tracker_config` | `tracking_worker.cpp` |

### 3.3 Object library cleanup

| Task | Location |
|------|----------|
| Mark `tracking_radius` deprecated in manager model + API | `manager/models.py` |
| Migration note in user guide | `docs/user-guide/` |
| Remove radius from association code (already done Phase 2) | — |

### Phase 3 validation

#### Automated

Full robot_vision + tracker test suites. New tests:

- Low R measurement pulls state strongly; high R weakly
- Filter smoothness: jerk metrics improve vs Phase 2 on noisy detections

#### Evaluation harness

Full pipeline comparison Phase 2 vs Phase 3:

- **LocA** and jitter metrics primary gain expected here
- **AssA** should hold (association unchanged from Phase 2)

#### Soak / load

```bash
cd tracker && make test-load
```

Ensure covariance computation does not regress chunk processing latency (target: transform + track overhead ≤ 10% vs Phase 1 baseline).

#### Exit criteria

- [ ] End-to-end probabilistic pipeline: predict → associate(S_pred + R_meas) → correct(R_meas)
- [ ] `tracking_radius` deprecated in object library documentation
- [ ] Default association method → `position_mahalanobis_combined` in tracker-config.json
- [ ] Evaluation metrics meet or exceed Phase 2 on all gated datasets

---

## Rollout strategy

```mermaid
gantt
    title Probabilistic Tracking Rollout
    dateFormat YYYY-MM-DD
    section Phase1
    robot_vision PositionMahalanobis     :p1a, 2026-06-09, 7d
    tracker config + feature flag        :p1b, after p1a, 5d
    evaluation baseline + validation     :p1c, after p1b, 5d
    section Phase2
    CoordinateTransformer covariance     :p2a, after p1c, 10d
    combined association + calibration   :p2b, after p2a, 7d
    evaluation Wildtrack/metric          :p2c, after p2b, 5d
    section Phase3
    robot_vision per-measurement R       :p3a, after p2c, 10d
    integration + deprecation            :p3b, after p3a, 7d
    final evaluation + default flip      :p3c, after p3b, 5d
```

1. **Phase 1** ships with flag default `euclidean`; ops opt in via config.
2. **Phase 2** ships with flag default `position_mahalanobis`; combined opt in.
3. **Phase 3** flips default to `position_mahalanobis_combined` after evaluation sign-off.

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Misspecified Σ_xy causes wrong merges | `max_radius_m` ceiling; offline α calibration; Phase 1 fallback |
| Chi-squared gate too opaque for operators | Document `gate_probability`; expose AssA/LocA in evaluation dashboards |
| Controller / tracker service divergence | Shared config schema; same robot_vision version; cross-service evaluation runs |
| Performance cost of Jacobian | Analytic J; compute only foot point; benchmark in `make test-load` |
| Confidence not calibrated as uncertainty | Treat as monotonic scale; tune via α; do not claim calibrated Bayesian semantics in docs |

---

## File touch list (summary)

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

---

## Appendix: Chi-squared gate reference

| gate_probability | χ² threshold (2 DOF) |
|------------------|------------------------|
| 0.90 | 4.605 |
| 0.95 | 5.991 |
| 0.99 | 9.210 |
| 0.999 | 13.816 |

Default recommendation: **0.99** (matches common gating practice for 2D position).
