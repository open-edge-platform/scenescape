# 3D Multi-Object Tracking Evaluation Plan for SceneScape

## Dataset & Toolkit Summary (Static Cameras, Ground-Plane 3D)

---

## 1. SceneScape Requirements (Current Phase, as of 2026'Q1)

This evaluation setup targets multi-camera **3D multi-object tracking (MOT)** systems with the following assumptions:

### Input
- 2D bounding box detections from multiple static cameras

### Camera Setup
- Static cameras
- Known and fixed intrinsics and extrinsics

### Tracking Space
- Real-world 3D coordinates
- Objects constrained to the ground plane (`z = 0`). This requirement is going to be removed in future.

### Tracker Output
- 3D object centers
- Fixed-size 3D boxes (size not evaluated for now). This requirement is going to be removed in future.

### Ground Truth Requirement (Current)
- 3D object positions only (center points)
- Full 3D box GT is not required yet. This requirement is going to be removed in future.

### Metrics of Interest
- **HOTA** (primary)
- Localization / precision metrics (distance-based)
- Association quality (ID stability)
- Jitter / smoothness metrics (non-standard but important)

### Future Extension
- Dynamic 3D object size
  → datasets with full 3D boxes become relevant later
- Objects not limited to the ground plane

---

## 2. Datasets Overview

### 2.1 AI City Challenge (MTMC / Track 1 – 2024+)

**Type:** Synthetic, large-scale, multi-camera tracking benchmark
**Domain:** People tracking in smart-city / indoor-like spaces

#### Key Properties
- Static, calibrated cameras (intrinsics + extrinsics provided)
- Multi-camera synchronization
- Ground truth in global world coordinates
- Designed explicitly for multi-camera tracking
- HOTA is an official evaluation metric

#### GT Format
- Object center positions in world coordinates
- Identity-consistent tracks across cameras
- (Some tracks include richer metadata depending on year)

#### Strengths
- Closest thing to an industry standard for static-camera MTMC
- Clean geometry and evaluation protocol
- Official evaluation code available
- Directly compatible with center-position-based HOTA

#### Limitations
- Synthetic (domain gap vs real video)
- Large dataset → higher storage and preprocessing cost

**Adoption Effort:** Medium
(mainly format conversion + evaluation harness integration)

---

### 2.2 NVIDIA PhysicalAI-SmartSpaces

**Type:** Synthetic, Omniverse-generated dataset
**Domain:** Warehouses, retail, hospitals, indoor environments

#### Key Properties
- Static cameras with perfect calibration
- Large-scale multi-camera setups
- Synchronized multi-view video
- Ground truth available in 3D world coordinates
- Some subsets include full 3D bounding boxes

#### GT Format
- 3D object center positions
- Optional 3D boxes (useful later)
- Depth and segmentation available in some variants

#### Strengths
- Excellent geometric consistency
- Massive scale → stress-testing association logic
- Clean separation of detection, projection, tracking, evaluation

#### Limitations
- Synthetic only
- Heavy dataset (storage, IO, preprocessing)

**Adoption Effort:** Medium–High
(dataset size + schema complexity)

---

### 2.3 I-24 3D Dataset

**Type:** Real-world dataset
**Domain:** Highway vehicle tracking

#### Key Properties
- Static infrastructure cameras
- Accurate multi-camera calibration
- Full 3D world-coordinate tracking
- Real vehicle motion patterns

#### GT Format
- 3D object center positions
- Full 3D boxes for vehicles

#### Strengths
- Real data
- True 3D motion
- Excellent for vehicle-centric tracking

#### Limitations
- Domain-specific (vehicles only)
- Less directly aligned with indoor / people-tracking scenarios

**Adoption Effort:** Medium

---

### 2.4 Wildtrack (Large-Scale Multicamera Detection Dataset)

**Type:** Real-world, static multi-camera dataset
**Domain:** Pedestrian tracking

#### Key Properties
- 7 static, overlapping cameras
- Known intrinsics and extrinsics
- Ground-plane world positions encoded via a discrete grid
- Widely used in academic multi-view tracking research

#### Ground-Truth Representation
- Each person is annotated with a `positionID`
- `positionID` indexes a **480 × 1440** grid
- Grid spacing: **2.5 cm**
- Origin: **(-3.0 m, -9.0 m)**

#### Position Reconstruction

```
X = -3.0 + 0.025 * (ID % 480)
Y = -9.0 + 0.025 * (ID / 480)
Z = 0
```


#### Interpretation
- This yields real-world ground-plane coordinates in meters
- Functionally equivalent to explicit `(x, y, z=0)` GT positions

#### Strengths
- Real captured video
- Static calibrated cameras
- Simple, precise world-coordinate GT
- Very well aligned with center-position-based tracking

#### Limitations
- No native 3D box dimensions
- HOTA not provided out-of-the-box (needs TrackEval)

**Adoption Effort:** Low
(lightweight dataset, simple geometry, easy conversion)

---

## 3. Dataset Comparison (Against Current Requirements)

| Dataset | Static Cameras | Known Calibration | 3D GT Positions | Multi-Cam | HOTA Support | Adoption Effort |
|------|------|------|------|------|------|------|
| AI City Challenge | ✅ | ✅ | ✅ | ✅ | ✅ (official) | Medium |
| PhysicalAI-SmartSpaces | ✅ | ✅ | ✅ | ✅ | ✅ | Medium–High |
| I-24 3D | ✅ | ✅ | ✅ | ✅ | ⚠️ (via toolkit) | Medium |
| Wildtrack | ✅ | ✅ | ✅ (ground plane) | ✅ | ⚠️ (via TrackEval) | Low |

---

## 4. Evaluation Toolkits

### 4.1 TrackEval (Python)

**Status:** Reference implementation for HOTA

#### Supported Metrics
- HOTA
- DetA (Detection Accuracy)
- AssA (Association Accuracy)
- LocA (Localization Accuracy)
- IDF1, ID switches
- MOTA / MOTP

#### Advantages
- Metric is coordinate-agnostic
- Works with 3D points just as well as 2D
- Distance function can be Euclidean in world space
- Ideal for center-position evaluation

---

### 4.2 Dataset-Specific Evaluation Code

- **AI City Challenge:** official Python evaluation scripts (HOTA on world coordinates)
- **nuScenes devkit:** less relevant now (moving cameras)
- **I-24 tooling:** dataset-specific evaluation helpers

---

## 5. Recommended Evaluation Strategy

### Phase 1 (2026'Q1)
- Wildtrack + TrackEval
- Center-position-only evaluation
- Add trajectory smoothness metrics
- Fast iteration, real data

### Phase 2
- AI City Challenge
- Large-scale MTMC
- Official HOTA comparison

### Phase 3
- PhysicalAI-SmartSpaces / I-24
- Enable dynamic 3D box sizing
- Switch to box-based localization metrics
