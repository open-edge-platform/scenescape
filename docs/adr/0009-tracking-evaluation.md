# ADR 9: Tracking Evaluation Strategy (Industry Standard Datasets, Tools, and Metrics)

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorauintc)
- **Date**: 2026-01-26
- **Status**: `Proposed`

## Context

SceneScape relies on multi-camera 3D multi-object tracking (MOT) for key product capabilities (e.g., occupancy, safety, operational analytics). Tracking quality must remain stable across a wide range of motion patterns, densities, occlusions, and camera configurations.

The current automated test coverage primarily validates functional behavior and selected statistical properties, but it does not directly measure core tracking accuracy properties such as spatial position error and trajectory precision. This creates risk during tracker porting, refactoring, or performance work, where regressions may not be detected early.

We need a scalable, comparable, and repeatable evaluation approach that supports state-of-the-art tracking quality assurance without building a bespoke ecosystem that cannot be benchmarked against common references.

## Decision

We will adopt industry-standard datasets, tools, and metrics for SceneScape tracking evaluation and implement a phased strategy to reach state-of-the-art tracking quality assurance.

At a high level, the strategy is:

- **Phase 1: Close critical gaps with minimal effort**
  - Use an offline black-box evaluation harness for the scene controller.
  - Integrate an established evaluation toolkit (e.g., TrackEval) and implement adapters for SceneScape I/O formats.
  - Add localization (position) metrics to complement existing system tests.
  - Add basic trajectory smoothness metrics to detect jitter regressions.

- **Phase 2: Expand to real-world motion diversity and larger multi-camera scale with end-to-end coverage**
  - Add a real multi-camera pedestrian dataset (e.g., Wildtrack) to validate association and localization under denser scenes.
  - Unify and extend the evaluation implementation toward industry-standard metrics: HOTA, association performance, ID consistency and trajectory precision metrics.
  - End-to-end evaluation with camera video inputs (including upstream analytics pipelines) to cover vector-enhanced tracking and re-identification.
  - Optionally add a real vehicle dataset (e.g., I-24) to validate higher-speed motion and different dynamics.

- **Future: Large-scale, broader coverage, and real-time benchmarking**
  - Adopt larger-scale benchmarks (e.g., AI City Challenge, PhysicalAI-SmartSpaces) for crowded scenes, stress testing, and regression prevention.
  - Evolve toward richer outputs and metrics as requirements expand (e.g., 3D box extents/orientation).
  - Real-time evaluation/benchmarking in production-like setups.

## Alternatives Considered

1. **Extend the current tests with a custom evaluation framework (custom metrics, bespoke GT formats, and custom harness).**
   - Pros:
     - Tailored tightly to current SceneScape internals.
   - Cons:
     - Time-consuming to design, implement, validate, and maintain.
     - Reinvents well-established tooling.
     - Harder to compare results against publicly known benchmarks and industry baselines.

2. **Create or curate custom datasets and evaluation protocols only.**
   - Pros:
     - Full control over scenarios and data formats.
   - Cons:
     - High long-term cost (collection, annotation, iteration).
     - Comparability and external validation remain limited.

## Consequences

### Positive

- Enables accuracy-focused regression detection (localization, association, and stability) during tracker changes.
- Improves comparability against industry benchmarks and reduces ambiguity in quality targets.
- Scales evaluation coverage via phased adoption (from current lightweight scenarios to larger real/synthetic benchmarks).

### Negative

- Requires integration work (format adapters, harness automation) and adds dependencies on external toolkits.
- External datasets introduce operational overhead (storage, preprocessing, licensing/terms compliance).
- Some metrics and thresholds will need careful standardization to be actionable for CI gating.

## References

- SceneScape evaluation strategy and dataset/tooling summary: [controller/docs/evaluation/3d_mot_evaluation_plan.md](../../controller/docs/evaluation/3d_mot_evaluation_plan.md)
- TrackEval (HOTA reference implementation): https://github.com/JonathonLuiten/TrackEval
- Wildtrack dataset: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
- I-24 Motion dataset: https://i24motion.org/
- AI City Challenge: https://www.aicitychallenge.org/
- NVIDIA PhysicalAI-SmartSpaces: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
