# ADR 9: Tracking Evaluation Strategy (Industry Standard Datasets, Tools, and Metrics)

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorauintc)
- **Date**: 2026-01-26
- **Status**: `Accepted`

## Context

SceneScape relies on multi-camera 3D multi-object tracking (MOT) for key product capabilities (e.g., occupancy, safety, operational analytics). Tracking quality must remain stable across a wide range of motion patterns, densities, occlusions, and camera configurations.

The current automated test coverage primarily validates functional behavior and selected statistical properties, but it does not directly measure core tracking accuracy properties such as spatial position error and trajectory precision. This creates risk during tracker porting, refactoring, or performance work, where regressions may not be detected early.

We need a scalable, comparable, and repeatable evaluation approach that supports state-of-the-art tracking quality assurance without building a bespoke ecosystem that cannot be benchmarked against common references.

### Current Requirements

This evaluation setup targets multi-camera **3D multi-object tracking (MOT)** systems with the following assumptions:

**Input**

- 2D bounding box detections (metadata) from multiple static cameras

**Camera Setup**

- Static cameras
- Known and fixed intrinsics and extrinsics

**Tracking Space**

- Real-world 3D coordinates
- Objects constrained to the ground plane (`z = 0`). This requirement is going to be removed in the future.

**Tracker Output**

- 3D object location
- Fixed-size 3D boxes (size not evaluated for now). This requirement is going to be removed in future.

**Ground Truth Requirement**

- 3D object positions only (ground plane).
- Full 3D box GT is not required yet. This requirement is going to be changed in the future.

**Metrics of Interest**

- **HOTA**
- Localization / precision metrics (distance-based)
- Association quality (ID stability)
- Jitter / smoothness metrics (non-standard but important)

**Future Extensions**

- Full end-to-end offline evaluation tests (coverage of video analytics detection capabilities, input: camera video frames)
- Real-time evaluation tests in production setup (send and synchronize input / GT data via MQTT in real-time)
- Real-time performance + accuracy evaluation benchmarks (evaluate performance and accuracy at the same time on a given hardware setup)
- Dynamic 3D object size (datasets with full 3D boxes become relevant later)
- Objects not limited to the ground plane
- Adopting or supporting well-established data formats rather than maintaining our own variant

## Decision

We will adopt industry-standard datasets, tools, and metrics for SceneScape tracking evaluation and implement a phased strategy to reach state-of-the-art tracking quality assurance.

At a high level, the strategy is:

- **Phase 1: Close critical gaps with minimal effort**
  - Use an offline black-box evaluation harness for the scene controller.
  - Integrate an established evaluation toolkit (e.g., TrackEval) and implement adapters for SceneScape I/O formats.
  - Add localization (position) metrics evaluation (e.g., MOTP, LocA) with TrackEval to complement existing system tests.
  - Add basic trajectory smoothness metrics to detect jitter regressions (e.g., RMS jerk, acceleration variance).
  - Extend Basic Acceptance Tests with threshold-based evaluation of the new metrics.

- **Phase 2: Expand to real-world motion diversity and larger multi-camera scale with end-to-end coverage**
  - Add a real multi-camera pedestrian dataset (e.g., Wildtrack) to validate association and localization under denser scenes and address High-Severity gaps: motion diversity, multi-camera scale (7 vs current 2).
  - Unify and extend the evaluation implementation toward industry-standard metrics: HOTA, association performance, ID consistency, and trajectory precision metrics.
  - End-to-end evaluation with camera video inputs (including upstream analytics pipelines) to cover vector-enhanced tracking and re-identification.
  - Optionally add a real vehicle dataset (e.g., I-24) to validate higher-speed motion and different dynamics.

- **Future: Large-scale, broader coverage, and real-time benchmarking**
  - Adopt larger-scale benchmarks (e.g., AI City Challenge, PhysicalAI-SmartSpaces) for crowded scenes, stress testing, and regression prevention.
  - Evolve toward richer outputs and metrics as requirements expand (e.g., 3D box extents/orientation).
  - Real-time evaluation/benchmarking in production-like setups (send and synchronize input / GT data via MQTT in real-time).

The following datasets and toolkits are selected as the primary basis for the phased implementation.

### Datasets Overview

#### [AI City Challenge](https://www.aicitychallenge.org/) (MTMC / Track 1 – 2024+)

**Type:** Synthetic, large-scale, multi-camera tracking benchmark
**Domain:** People tracking in smart-city and indoor-like spaces
**Official Site:** https://www.aicitychallenge.org/

**Key Properties**

- Static, calibrated cameras (intrinsics + extrinsics provided)
- Multi-camera synchronization
- Ground truth in global world coordinates
- Designed explicitly for multi-camera tracking
- 3D HOTA is an official evaluation metric

**Ground Truth Format**

- 3D object center positions in world coordinates
- Identity-consistent tracks across cameras

**Strengths**

- Closest thing to an industry-standard benchmark for static camera Multi-Target Multi Camera (MTMC) use cases
- Clean geometry and evaluation protocol
- Official evaluation code available
- Directly compatible with center-position-based HOTA

**Limitations**

- Synthetic (domain gap vs real video)
- Large dataset → higher storage and preprocessing cost

**Adoption Effort:** Medium (mainly format conversion + evaluation harness integration)

---

#### [NVIDIA PhysicalAI-SmartSpaces](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces)

**Type:** Synthetic, Omniverse-generated dataset
**Domain:** Warehouses, retail, hospitals, indoor environments
**Official Site:** https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces

**Key Properties**

- Static cameras with perfect calibration
- Large-scale multi-camera setups
- Synchronized multi-view video
- Ground truth available in 3D world coordinates
- Some subsets include full 3D bounding boxes

**Ground Truth Format**

- 3D object center positions
- Optional 3D boxes (useful later)
- Depth and segmentation available in some variants

**Strengths**

- Excellent geometric consistency
- Massive scale → stress-testing association logic
- Clean separation of detection, projection, tracking, evaluation

**Limitations**

- Synthetic only
- Heavy dataset (storage, IO, preprocessing)

**Adoption Effort:** Medium–High (dataset size + schema complexity)

---

#### [I-24 3D Dataset](https://i24motion.org/)

**Type:** Real-world dataset
**Domain:** Highway vehicle tracking
**Official Site:** https://i24motion.org/

**Key Properties**

- Static infrastructure cameras
- Accurate multi-camera calibration
- Full 3D world-coordinate tracking
- Real vehicle motion patterns

**Ground Truth Format**

- 3D object center positions
- Full 3D boxes for vehicles

**Strengths**

- Real data
- True 3D motion
- Excellent for vehicle-centric tracking

**Limitations**

- Domain-specific (vehicles only)
- Less directly aligned with indoor / people-tracking scenarios

**Adoption Effort:** Medium

---

#### [Wildtrack](https://www.epfl.ch/labs/cvlab/data/data-wildtrack/) (Large-Scale Multicamera Detection Dataset)

**Type:** Real-world, static multi-camera dataset
**Domain:** Pedestrian tracking
**Official Site:** https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
**Other links:** https://datasetninja.com/wildtrack

**Key Properties**

- 7 static, overlapping cameras
- Known intrinsics and extrinsics
- Ground-plane world positions encoded via a discrete grid
- Widely used in academic multi-view tracking research

**Ground Truth Format**

- Each person is annotated with a `positionID`
- `positionID` indexes a **480 × 1440** grid
- Grid spacing: **2.5 cm**
- Origin: **(-3.0 m, -9.0 m)**

**Position Reconstruction**

```
X = -3.0 + 0.025 * (ID % 480)
Y = -9.0 + 0.025 * (ID / 480)
Z = 0
```

**Interpretation**

- This yields real-world ground-plane coordinates in meters
- Functionally equivalent to explicit `(x, y, z=0)` Ground Truth positions

**Strengths**

- Real captured video
- Static calibrated cameras
- Simple, precise world-coordinate GT
- Very well aligned with center-position-based tracking

**Limitations**

- No native 3D box dimensions
- HOTA not provided out-of-the-box (needs TrackEval)

**Adoption Effort:** Low (lightweight dataset, simple geometry, easy conversion)

### Dataset Comparison (Against Current Requirements)

| Dataset                | Static Cameras | Known Calibration | 3D Ground Truth positions | Multi-Cam | HOTA Support       | Adoption Effort |
| ---------------------- | -------------- | ----------------- | ------------------------- | --------- | ------------------ | --------------- |
| AI City Challenge      | ✅             | ✅                | ✅                        | ✅        | ✅ (official)      | Medium          |
| PhysicalAI-SmartSpaces | ✅             | ✅                | ✅                        | ✅        | ✅                 | Medium–High     |
| I-24 3D                | ✅             | ✅                | ✅                        | ✅        | ⚠️ (via toolkit)   | Medium          |
| Wildtrack              | ✅             | ✅                | ✅ (ground plane)         | ✅        | ⚠️ (via TrackEval) | Low             |

### Evaluation Toolkits

#### [TrackEval](https://github.com/JonathonLuiten/TrackEval) (Python)

**Status:** Reference implementation for HOTA
**GitHub:** https://github.com/JonathonLuiten/TrackEval

**Supported Metrics**

- HOTA
- DetA (Detection Accuracy)
- AssA (Association Accuracy)
- LocA (Localization Accuracy)
- IDF1, ID switches
- MOTA / MOTP

See the full list here: https://github.com/JonathonLuiten/TrackEval?tab=readme-ov-file#currently-implemented-metrics

**Advantages**

- Metric is coordinate-agnostic
- Works with 3D points just as well as 2D
- Distance function can be Euclidean in world space
- Ideal for center-position evaluation

#### Dataset-Specific Evaluation Code

- **I-24 tooling:** https://github.com/I24-MOTION/I24-3D-dataset
- **AI City Challenge:** https://github.com/NVIDIAAICITYCHALLENGE
- **nuScenes devkit (less relevant now):** https://github.com/nutonomy/nuscenes-devkit

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

3. **Use other popular datasets or toolkits (e.g., MOTChallenge, nuScenes, JRDB (JackRabbot Dataset), KITTI, Argoverse).**
   - Pros:
     - Widely used benchmarks with mature tooling and community references.
   - Cons:
     - **MOTChallenge:** 3D ground truth is not available.
     - **nuScenes, KITTI, Argoverse:** camera extrinsics are defined relative to the vehicle, but the vehicle platform is moving (not aligned with SceneScape’s static-camera assumptions).
     - **JRDB:** egocentric robot dataset (camera motion limits a consistent static reference frame).

## Consequences

### Positive

- Enables accuracy-focused regression detection (localization, association, and stability) during tracker changes.
- Improves comparability against industry benchmarks and reduces ambiguity in quality targets.
- Scales evaluation coverage via phased adoption (from current lightweight scenarios to larger real/synthetic benchmarks).
- Remains consistent with state-of-the-art approaches to MOT and drive toward standards.

### Negative

- Requires integration work (format adapters, harness automation) and adds dependencies on external toolkits.
- External datasets introduce operational overhead (storage, preprocessing, licensing/terms compliance).
- Some metrics and thresholds will need careful standardization to be actionable for CI gating.

## References

- TrackEval (HOTA reference implementation): https://github.com/JonathonLuiten/TrackEval
- Wildtrack dataset: https://www.epfl.ch/labs/cvlab/data/data-wildtrack/
- I-24 Motion dataset: https://i24motion.org/
- AI City Challenge: https://www.aicitychallenge.org/
- NVIDIA PhysicalAI-SmartSpaces: https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces
