<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 17: Probabilistic Tracking Association

- **Author(s)**: [Sarat Poluri](https://github.com/spoluri)
- **Date**: 2026-06-06
- **Status**: `Accepted` (Phase 1 scope)
- **Related**: [ADR-0007](./0007-tracker-service.md), [ADR-0009](./0009-tracking-evaluation.md)
- **Design**: [Probabilistic Tracking Association](../design/probabilistic-tracking-association.md)
- **Implementation plan**: [plan-probabilistic-tracking.md](../../.github/plans/plan-probabilistic-tracking.md)

## Context

SceneScape tracking uses `robot_vision`'s `MultipleObjectTracker` (predict → associate → correct). Production association used Euclidean distance with a fixed meter threshold (`tracking_radius` / 2 m default), while the UKF already produces predicted measurement covariance after predict. Detections are point estimates from camera calibration with no measurement uncertainty. Detector confidence is available but unused for gating or filter noise.

That leaves association inconsistent with the filter: gates ignore motion and coast, meter radii conflate object semantics with kinematics, camera geometry is unused for uncertainty, and multi-camera world-position disagreement is handled with ad-hoc fusion stopgaps rather than measurement noise.

## Decision

Replace Euclidean association gated by per-object `tracking_radius` with **covariance-aware Mahalanobis gating**, rolled out in three independently shippable phases:

1. **Track-side position Mahalanobis** — gate on UKF `S_pred` (xy) with a χ² threshold; optional Euclidean `max_radius_m` as a safety ceiling only. Addresses motion/coast-aware association. Does **not** model multi-camera pose disagreement.
2. **Geometry-derived measurement covariance** — propagate bbox/pixel uncertainty through camera geometry to world-space `R_meas`; associate with `S_pred + R_meas`. Addresses multi-view / range-dependent localization disagreement.
3. **Per-measurement UKF update** — use the same `R` in filter correct as in association, completing the probabilistic pipeline. Detector confidence / richer multi-cam metadata fusion may land here or later.

Additional decisions locked with this ADR:

- Prefer a **position-only** (2×2) Mahalanobis gate over full 7D Mahalanobis for association.
- Prefer geometry-derived `R` over TYPE_2 / ad-hoc multi-cam pose heuristics for disagreement.
- Deprecate `tracking_radius` as an association knob (retain in object library metadata during transition).
- Keep controller and tracker service behaviorally aligned via shared config / shared `robot_vision`.
- Until Phase 2: equal-weight multi-cam geometry averaging and Euclidean ~2 m detection↔detection birth clustering are accepted stopgaps (raw detections lack track `S_pred`).

Phase 1 is accepted and is the production default (`position_mahalanobis`). Phases 2–3 remain proposed. Engineering detail lives in the [design document](../design/probabilistic-tracking-association.md); task tracking in the [implementation plan](../../.github/plans/plan-probabilistic-tracking.md).

## Alternatives Considered

- **Keep Euclidean + per-object `tracking_radius`** — simple operator model; does not adapt to velocity, coast, or camera geometry; inconsistent with UKF predict.
- **Full 7D Mahalanobis** (`DistanceType.Mahalanobis`) — minimal code change; gates on unreliable size/yaw dimensions and still lacks per-detection `R`.
- **Per-camera fixed meter radius in config** — easier migration; still ignores motion/coast and lacks statistical basis.
- **Learned per-detection covariance from the detector** — best if available; current detectors do not emit localization covariance; out of tracker scope.

## Consequences

### Positive

- Association adapts to motion and coast (Phase 1) and to range/viewing geometry (Phase 2+) without per-object meter tuning.
- Aligns association with the UKF probabilistic predict (and, in Phase 3, correct) step.
- Leverages existing camera calibration; phased rollout is measurable via [ADR-0009](./0009-tracking-evaluation.md).

### Negative

- Operators lose an intuitive meter radius; replaced by `gate_probability` and calibrated pixel-sigma parameters.
- Requires `robot_vision` API changes and approximate bbox→world covariance heuristics (offline α calibration).
- Controller and tracker must stay aligned during migration.

## References

- [Design: Probabilistic Tracking Association](../design/probabilistic-tracking-association.md)
- [Implementation plan](../../.github/plans/plan-probabilistic-tracking.md)
- [Tracker Service Design](../design/tracker-service.md)
- [Tracking Evaluation Strategy (ADR-0009)](./0009-tracking-evaluation.md)
- [Tracker Evaluation Pipeline Design](../design/tracker-evaluation-pipeline.md)
