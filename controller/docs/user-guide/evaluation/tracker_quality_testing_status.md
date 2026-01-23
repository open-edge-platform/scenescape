# Multi-Object Tracker Quality Testing: Current State

**Document Version**: 1.0
**Last Updated**: January 23, 2026
**Status**: Current State Assessment

## Executive Summary

This document provides a comprehensive assessment of the current quality testing coverage for SceneScape's multi-object tracking system. The analysis prioritizes **end-to-end system tests** of the Python controller tracker over unit tests, as they provide full-stack validation using production data formats.

**Key Findings:**
- ✅ **Functional correctness**: Well-covered (track lifecycle, object counting, ID consistency)
- ⚠️ **Statistical quality**: Partially covered (velocity consistency, count errors, ID changes)
- ❌ **Spatial accuracy**: **NOT COVERED** - Critical gap
- ❌ **Trajectory precision**: **NOT COVERED** - Critical gap
- ❌ **Robustness**: Minimal coverage for noise, occlusions, complex motion

---

## Current System-Level Test Coverage

### Test Suite: [`tests/system/metric/`](../../../tests/system/metric/)

End-to-end Python tests that validate the complete tracking pipeline:
```
2D Detections (JSON) → Camera Transform → 3D World Coords → Tracker → Tracked Objects
```

#### Test Files

**1. [`tc_tracker_metric.py`](../../../tests/system/metric/tc_tracker_metric.py) - Statistical Quality Metrics**

Executes complete tracking pipeline with two camera views and measures three key metrics:

| Metric | What It Measures | Baseline Threshold | Coverage |
|--------|------------------|-------------------|----------|
| **MSOCE** (Mean Squared Object Count Error) | `(gtCount - predCount)²` averaged across frames | 0.3344 ± tolerance | ✅ Good |
| **IDC** (ID Change Error) | Rate of track ID switches between frames | 0.007 ± tolerance | ✅ Good |
| **Velocity Std Dev** | Standard deviation of velocity estimates | ≤ 0.36 m/s | ⚠️ Partial |

**Test Configurations:**
- ✅ Event-based tracking mode ([`tracker-config.json`](../../../tests/system/metric/test_data/tracker-config.json))
- ✅ Time-chunked tracking mode ([`tracker-config-time-chunking.json`](../../../tests/system/metric/test_data/tracker-config-time-chunking.json))
- ✅ Multiple frame rates (1 FPS, 10 FPS, 30 FPS)
- ✅ Multi-camera fusion (2 overlapping cameras)

**Ground Truth Data:**
- File: [`test_data/gtLoc.json`](../../../tests/system/metric/test_data/gtLoc.json) (2402 frames, ~80 seconds)
- Objects: 3 tracked entities (Person, person, FW190D classes)
- Motion: Slow, nearly linear trajectories (~0.24 m/s average)
- Coverage: Single simple scenario only

**2. [`tc_distance_thresh.py`](../../../tests/system/metric/tc_distance_thresh.py) - Association Parameter Tuning**

Tests impact of tracking parameters on object count accuracy:

| Parameter Varied | Purpose | Validation |
|-----------------|---------|------------|
| `tracking_radius` | Association distance threshold (0.1m vs 2.0m) | Smaller radius should reduce MSOCE ✅ |
| Object dimensions | Bounding box size impact (0.5m vs 10m) | Correct sizing should improve accuracy ✅ |

**Test Scope:**
- ✅ Validates parameter sensitivity
- ✅ Confirms configuration impacts tracking quality
- ❌ Does not measure absolute position accuracy

---

## What These Tests Validate

### ✅ Covered Areas

**1. Track Lifecycle Management**
- Object initialization (unreliable → reliable state transitions)
- Track persistence during detection gaps
- Track termination when objects leave FOV

**2. Object Count Accuracy**
- Detects ghost detections (false positives)
- Detects missed objects (false negatives)
- Detects duplicate tracks for same object
- Validates proper track cleanup

**3. ID Consistency**
- Measures track fragmentation rate
- Detects ID switches during normal tracking
- Quantifies association quality indirectly

**4. Multi-Camera Integration**
- 2D bounding box → 3D world coordinate transformation
- Homography-based camera calibration pipeline
- Multi-view sensor fusion (2 cameras with overlapping FOV)

**5. Temporal Processing Modes**
- Event-based (asynchronous) tracking
- Time-chunked (synchronous) tracking
- Frame rate adaptation (1-30 FPS)

**6. Configuration Robustness**
- Tracking parameter sensitivity
- Object library integration
- Motion model selection (implicit validation)

---

## Critical Gaps by Severity

### 🔴 CRITICAL SEVERITY

**1. No Spatial Position Accuracy Measurement**

**Gap:** Tests never compare predicted 3D positions against ground truth positions.

```python
# Ground truth contains:
"translation": [6.91, 6.93, 0.0]  # Actual 3D position

# But tests only check:
- Object count (yes/no object exists)
- ID consistency (same ID over time)
- Velocity magnitude (not position)

# Missing:
euclidean_error = sqrt((pred_x - gt_x)² + (pred_y - gt_y)² + (pred_z - gt_z)²)
```

**Impact:**
- Cannot verify if objects are tracked in correct physical locations
- No validation of 2D→3D transformation accuracy
- No measurement of Kalman filter state estimation error
- Cannot detect systematic spatial biases

**Evidence:** Ground truth file [`gtLoc.json`](../../../tests/system/metric/test_data/gtLoc.json) contains per-frame 3D positions but metrics library ([`metrics.py`](../../tools/analytics/library/metrics.py)) has no position error calculation functions.

---

**2. No Trajectory Accuracy Validation**

**Gap:** No measurement of path deviation from ground truth trajectories.

**Missing Metrics:**
- RMSE (Root Mean Square Error) of trajectory
- ADE (Average Displacement Error)
- FDE (Final Displacement Error)
- Path smoothness / continuity

**Impact:**
- Cannot validate motion model selection accuracy
- No measure of prediction quality during occlusions
- Cannot detect trajectory drift over time
- No validation of turn/curve tracking

**Current Workaround:** MSOCE indirectly indicates gross trajectory failures (lost tracks), but provides no precision measurement.

---

**3. No Occlusion/Prediction Accuracy Testing**

**Gap:** No validation of position estimates during detection gaps.

**Current Coverage:**
- ✅ Tests verify tracks *survive* gaps (`mNonMeasurementFramesDynamic`)
- ❌ Never verify predicted positions are *accurate* during gaps

**Missing Test:**
```python
# When detections absent for N frames:
1. Compare predicted position vs. actual position when detection resumes
2. Measure extrapolation error as function of gap duration
3. Validate different motion models (CV/CA/CTRV) for different trajectories
```

**Impact:**
- No confidence in track positions during occlusions
- Cannot validate motion model selection effectiveness
- No measurement of prediction divergence rate

---

### 🟠 HIGH SEVERITY

**4. Limited Motion Scenario Diversity**

**Gap:** Test data contains only slow, nearly-linear motion patterns.

**Current Test Characteristics** (from [`gtLoc.json`](../../../tests/system/metric/test_data/gtLoc.json)):
```
Frame rate: 30 FPS (33ms intervals)
Position deltas: ~0.008m per frame
Velocities: ~0.24 m/s (very slow walking speed)
Motion: Linear with minimal direction changes
```

**Missing Scenarios:**
- ❌ Rapid accelerations/decelerations
- ❌ Sharp turns (non-linear trajectories)
- ❌ High-speed motion (vehicles, running)
- ❌ Stationary → moving transitions
- ❌ Complex maneuvers (lane changes, U-turns)
- ❌ Crossing/intersecting trajectories

**Impact:**
- Unknown tracker performance under realistic motion patterns
- Cannot validate motion model switching (CV ↔ CA ↔ CTRV)
- Limited confidence for real-world deployments

---

**5. No Measurement Noise Robustness Testing**

**Gap:** Test inputs are idealized detections without realistic noise.

**Missing Test Conditions:**
- ❌ Detection jitter (noisy bounding boxes)
- ❌ Intermittent detection failures
- ❌ Outlier detections (false positives at wrong locations)
- ❌ Varying confidence scores
- ❌ Systematic detection biases

**Impact:**
- No validation of Kalman filter noise handling
- Unknown robustness to sensor imperfections
- Cannot tune process/measurement noise parameters empirically

---

**6. No Association Accuracy Deep Analysis**

**Gap:** Only high-level ID change rate measured, not association correctness.

**Current:** IDC metric = 0.007 (ID switches per frame)

**Missing:**
- ❌ Association matrix analysis (true/false pairings)
- ❌ Performance in crowded scenes (many objects)
- ❌ Close-proximity scenarios (objects within tracking radius)
- ❌ Comparison of distance metrics (Euclidean vs Mahalanobis vs MCE)

**Impact:**
- Cannot identify association algorithm weaknesses
- No guidance for distance threshold tuning
- Unknown performance degradation in dense scenarios

---

### 🟡 MEDIUM SEVERITY

**7. Velocity Accuracy Not Directly Validated**

**Current Coverage:** Standard deviation of velocity (consistency)

**Missing:** Velocity error vs. ground truth
```python
# Current:
std_velocity = np.std(all_velocities)  # Measures spread

# Missing:
velocity_error = |predicted_velocity - ground_truth_velocity|
```

**Impact:** Can detect unstable tracking but not velocity bias/offset.

---

**8. No 3D/Orientation Tracking Validation**

**Gap:** All test objects at Z=0, no yaw/pitch/roll validation.

**Ground Truth Contains:**
- ✅ 3D positions: `[x, y, z]`
- ❌ Orientations: Never tested
- ❌ Bounding box dimensions: Not validated

**Current Test Coverage:**
- Z-axis: Always 0.0 (ground plane only)
- Yaw/orientation: Not measured in metrics
- Object dimensions: Not compared to ground truth

**Impact:**
- No validation for aerial/underwater scenarios
- Unknown orientation estimation accuracy
- Cannot validate 3D object extent tracking

---

**9. Limited Multi-Camera Scenarios**

**Current:** 2 cameras with overlapping FOV

**Missing:**
- ❌ 3+ camera scenarios
- ❌ Handoff between non-overlapping cameras
- ❌ Varying camera quality/frame rates
- ❌ Camera calibration error sensitivity

**Impact:** Unknown scalability to large multi-camera deployments.

---

### 🟢 LOW SEVERITY

**10. No Performance/Timing Benchmarks**

**Gap:** No measurement of tracker computational performance.

**Missing:**
- Processing latency per frame
- Scalability with object count
- Memory usage patterns

**Impact:** Cannot detect performance regressions.

---

**11. Limited Ground Truth Duration**

**Current:** ~80 seconds of test data

**Missing:** Long-duration scenarios (minutes/hours) to detect:
- Track ID exhaustion
- Memory leaks
- Cumulative drift

---

## C++ Unit Test Coverage (Brief)

**Location:** [`controller/src/robot_vision/test/TrackingTests.cpp`](../../src/robot_vision/test/TrackingTests.cpp)

**Scope:** Tests the underlying C++ tracking library (`rv::tracking`) in isolation.

### What C++ Tests Cover

| Test Category | Tests | Coverage |
|---------------|-------|----------|
| Single object tracking | 2 tests (multi-model + single-model) | ✅ State transitions |
| Multiple objects (5) | 4 tests (each distance metric) | ✅ Count validation |
| Stress test (100 objects) | 1 test | ✅ Scalability |
| Intermittent detections | 1 test | ✅ Track persistence |

**Distance Metrics Tested:**
- ✅ Euclidean
- ✅ MultiClassEuclidean
- ✅ Mahalanobis
- ✅ MCEMahalanobis

**Motion Models Tested:**
- ✅ CV (Constant Velocity)
- ✅ CA (Constant Acceleration) - via multi-model config
- ✅ CTRV (Constant Turn Rate Velocity) - via multi-model config
- ✅ CP (Constant Position) - via multi-model config

### C++ Test Limitations

**Same fundamental gaps as system tests:**
- ❌ No position accuracy validation
- ❌ No trajectory error measurement
- ❌ No velocity accuracy checks
- ❌ No motion model effectiveness comparison
- ❌ Idealized inputs (no noise)
- ❌ Simple motion patterns only

**Assertions Used:**
```cpp
ASSERT_EQ(trackedObjects.size(), expectedCount);  // Only count checks
// Never:
EXPECT_NEAR(tracked.x, groundTruth.x, tolerance);
EXPECT_NEAR(tracked.vx, groundTruth.vx, tolerance);
```

**Value:** Validates core C++ library algorithms work, but doesn't measure tracking *accuracy*.

---

## Test Methodology Analysis

### Strengths

**1. Black-Box End-to-End Testing**
- ✅ Uses production JSON data formats
- ✅ Tests complete pipeline (2D→3D→tracking)
- ✅ Validates multi-camera integration
- ✅ Real camera calibration matrices
- ✅ Pytest framework with parametrization

**2. Statistical Quality Gates**
- ✅ Quantitative thresholds (MSOCE, IDC, velocity std)
- ✅ Regression detection (tests fail if metrics degrade)
- ✅ Multiple tracking mode validation

**3. Reproducible Ground Truth**
- ✅ Fixed test data in version control
- ✅ Deterministic test execution
- ✅ Consistent baseline metrics

### Weaknesses

**1. Single Scenario Limitation**
- Only one ground truth file ([`gtLoc.json`](../../../tests/system/metric/test_data/gtLoc.json))
- Single motion pattern tested
- Limited object interaction complexity

**2. Indirect Accuracy Measurement**
- Metrics measure symptoms (count errors, ID changes) not root causes (position error)
- Cannot isolate failure modes (association vs. prediction vs. 2D→3D)

**3. No Noise/Adversarial Testing**
- Idealized inputs only
- No edge case validation
- No worst-case scenario characterization

---

## Comparison: What Industry Standards Require

### MOT Challenge (Multi-Object Tracking Benchmark)

**Standard Metrics:**
1. **MOTA** (Multi-Object Tracking Accuracy): Combines FP, FN, ID switches ✅ Partially covered
2. **MOTP** (Multi-Object Tracking Precision): **Position error** ❌ **NOT COVERED**
3. **IDF1** (ID F1 Score): ID consistency ✅ Covered (via IDC)
4. **MT/ML/PT** (Mostly Tracked/Lost/Partially Tracked): Track completeness ⚠️ Indirect

**SceneScape Coverage:** ~40% of standard MOT metrics

### CLEAR MOT Metrics (Bernardin & Stiefelhagen)

**Missing from SceneScape:**
- ❌ False Positive Rate (FPR)
- ❌ False Negative Rate (FNR)
- ❌ Precision/Recall curves
- ❌ **Average tracking accuracy (position-based)** ← **Critical**

---

## Quantitative Gap Summary

| Test Aspect | Coverage | Severity | Evidence |
|-------------|----------|----------|----------|
| **Position Accuracy** | 0% | 🔴 CRITICAL | No RMSE/MAE calculation in [`metrics.py`](../../tools/analytics/library/metrics.py) |
| **Trajectory Accuracy** | 0% | 🔴 CRITICAL | No path deviation metrics |
| **Occlusion Prediction** | 0% | 🔴 CRITICAL | No extrapolation validation |
| **Motion Diversity** | ~10% | 🟠 HIGH | Only linear, slow motion tested |
| **Noise Robustness** | 0% | 🟠 HIGH | Idealized inputs only |
| **Association Analysis** | 20% | 🟠 HIGH | ID changes measured, not accuracy |
| **Velocity Accuracy** | 30% | 🟡 MEDIUM | Std dev only, not error |
| **3D/Orientation** | 0% | 🟡 MEDIUM | Z=0, no yaw validation |
| **Multi-Camera Scale** | 40% | 🟡 MEDIUM | 2 cameras only |
| **Object Count** | 90% | ✅ Good | MSOCE well-validated |
| **ID Consistency** | 90% | ✅ Good | IDC metric comprehensive |
| **Track Lifecycle** | 85% | ✅ Good | State transitions validated |

**Overall Coverage Estimate:** ~35% of comprehensive tracking quality validation

---

## Recommendations Priority

### Immediate (Address Critical Gaps)

1. **Implement MOTP-style position accuracy metric**
   - Calculate Euclidean distance between predicted and ground truth positions
   - Report RMSE, MAE, max error per test scenario
   - Add threshold-based test assertions

2. **Add trajectory validation**
   - Implement ADE (Average Displacement Error)
   - Measure path smoothness (jerk/curvature)
   - Validate motion model selection effectiveness

3. **Test occlusion/prediction accuracy**
   - Inject detection gaps into test data
   - Measure position error during gaps
   - Compare motion models (CV vs CA vs CTRV)

### Short-Term (Address High Severity)

4. **Expand ground truth scenarios**
   - Add acceleration/deceleration cases
   - Add curved/turning trajectories
   - Add crossing/dense scenarios
   - Add high-speed motion

5. **Add noise robustness tests**
   - Inject detection jitter
   - Test with intermittent failures
   - Validate outlier rejection

6. **Deep-dive association analysis**
   - Measure true/false association rates
   - Test close-proximity scenarios
   - Compare distance metric effectiveness

### Medium-Term (Medium Severity)

7. Validate velocity accuracy directly
8. Test 3D/orientation tracking
9. Scale multi-camera testing (3+ cameras)

---

## Conclusion

SceneScape's multi-object tracker has **good functional test coverage** but **lacks fundamental accuracy validation**. The current tests answer "does it track?" but not "how well does it track?"

**The most critical missing capability:** No measurement of spatial position accuracy, which is the primary objective of any tracking system.

**Priority:** Implement position-based accuracy metrics (MOTP/RMSE) before expanding scenario diversity.

---

**Document Status:** Living document - update as test coverage evolves
**Owner:** SceneScape Team
**Review Cycle:** Quarterly or after major test additions
