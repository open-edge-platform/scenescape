# frustum-gaussian

A fast C++/Python library that converts 2D bounding box detections and oriented 3D bounding boxes into Gaussian observations suitable for multi-camera object tracking.

> **How it works:** [ALGORITHM.md](ALGORITHM.md) — projection derivation, depth bounds, object modes, pipeline architecture
> **Performance:** see the summary table under **Benchmarks** below

## Concept

Classical multi-camera trackers collapse each bounding box to a single 3D point by projecting the bounding-box bottom-center onto the scene plane — either via a precomputed homography or by casting a ray through the bottom-center pixel and intersecting it with a floor model. This works for objects resting on a known flat surface, but discards nearly everything the bounding box encodes: its angular size (a direct depth cue), which edges are clipped (indicating partial visibility), and any representation of measurement uncertainty. It also fails entirely for objects that are not on the floor.

This library instead produces a **ray-elongated 3D Gaussian** for each detection — an ellipsoid narrow across the image plane (angular extent is well-measured) and elongated along the camera ray (depth is estimated from shape knowledge, not directly observed). Each Gaussian carries a full 3×3 covariance, a depth confidence score, and geometric near/far depth bounds. For detectors that already output an oriented 3D bounding box (LiDAR, stereo, monocular-3D DNN), `project_frustum_3d` converts it into the same representation with a tight covariance derived directly from the detection. In both cases the result is the natural input for information-form multi-camera fusion, where independent ray constraints from different cameras intersect to resolve depth precisely — without assuming the object is on the floor.

The library is **stateless and mode-agnostic**. It does not decide whether an object is on the ground or flying — that is handled downstream. It simply projects, as accurately and quickly as possible.

## Quick start

### C++

From the repository root, build the standalone C++ library and run its native
tests with the local Makefile targets:

```bash
make -C spatial_performance_primitives/frustum_gaussian build-cpp
make -C spatial_performance_primitives/frustum_gaussian test-cpp
```

To consume the library from another CMake project, add it with `FetchContent`:

```cmake
include(FetchContent)
FetchContent_Declare(frustum_gaussian
  GIT_REPOSITORY https://github.com/open-edge-platform/scenescape.git
  GIT_TAG        main
  SOURCE_SUBDIR  spatial_performance_primitives/frustum_gaussian
)
FetchContent_MakeAvailable(frustum_gaussian)
target_link_libraries(my_target PRIVATE frustum_gaussian_core)
```

```cpp
#include <frustum_gaussian/frustum.hpp>

fg::Intrinsics K(fx, fy, cx, cy, width, height);benchmarks
fg::ShapePrior prior(0.5f, 0.5f, 1.7f,   // mu_x, mu_y, mu_z (meters)
                     0.1f, 0.1f, 0.15f);  // sigma_x, sigma_y, sigma_z (meters)

fg::FrustumObservation obs =
    fg::project_frustum(fg::BoundingBox(u_min, v_min, u_max, v_max), K, prior);
// obs.mu       — 3D position in camera frame (meters)
// obs.Sigma    — 3×3 covariance (meters²)
// obs.score    — depth constraint quality ∈ [0, 1]
// obs.depth_lo — geometric near bound (m)
// obs.depth_hi — geometric far bound (m)

// Transform to world frame
fg::FrustumObservation obs_w = fg::transform_to_world(obs, pose_mat);
```

### Python

```python
import numpy as np
import frustum_gaussian as fg

K = fg.Intrinsics(fx=946.0, fy=946.0, cx=640.0, cy=360.0,
                  width=1280.0, height=720.0)
prior = fg.ShapePrior(mu_x=0.5, mu_y=0.5, mu_z=1.7,
                      sigma_x=0.1, sigma_y=0.1, sigma_z=0.15)

# Single detection
obs = fg.project_frustum(fg.BoundingBox(300, 100, 600, 700), K, prior)

# Batch (TBB-parallel) — preferred for real-time use
boxes  = np.array([[300, 100, 600, 700],
                   [100,  50, 250, 500]], dtype=np.float32)
priors = np.tile([0.5, 0.5, 1.7, 0.1, 0.1, 0.15], (len(boxes), 1)).astype(np.float32)
result = fg.project_frustum_batch(
    {"boxes": boxes, "priors": priors},
    intrinsics = np.array([K.fx, K.fy, K.cx, K.cy], dtype=np.float32),
    img_size   = np.array([K.width, K.height], dtype=np.float32),
)
# result['mu']        (N, 3)    — camera-frame positions (m)
# result['Sigma']     (N, 3, 3) — covariances (m²)
# result['depth_est'] (N,)      — depth estimates (m)
# result['depth_lo']  (N,)      — geometric near bound (m)
# result['depth_hi']  (N,)      — geometric far bound (m)
# result['score']     (N,)      — confidence ∈ [0, 1]

pose_mat = np.eye(4, dtype=np.float32)   # replace with your camera-to-world pose
world = fg.transform_to_world_batch(result, pose_mat)
```

### 3D bounding-box detectors

When a 3D detector (LiDAR, stereo, monocular-3D DNN, or a foundation model) already provides an oriented bounding box, use `project_frustum_3d` instead of the angular path. Depth is read directly from the translation, giving a much tighter covariance than shape-prior estimation.

```python
import numpy as np
import frustum_gaussian as fg

K = fg.Intrinsics(fx=946.0, fy=946.0, cx=640.0, cy=360.0,
                  width=1280.0, height=720.0)

translation  = np.array([1.2, 0.3, 8.5], dtype=np.float32)   # geometric center, camera frame (m)
half_extents = np.array([1.0, 2.25, 0.75], dtype=np.float32) # half of [l, w, h] (m)
rotation     = np.eye(3, dtype=np.float32)                    # R_body_to_cam, row-major

obs = fg.project_frustum_3d(translation, half_extents, rotation, K,
                             range_sigma_m=0.05)  # isotropic detector noise
# obs.mu        — geometric center in camera frame (= translation)
# obs.Sigma     — 3×3 covariance from detector uncertainty
# obs.depth_lo  — box near surface along ray (m)
# obs.depth_hi  — box far surface along ray (m)
# obs.edge_valid — EDGE_ALL (3D detectors are not image-edge limited)

# Anisotropic uncertainty (e.g. LiDAR: tighter laterally than in range)
obs = fg.project_frustum_3d(translation, half_extents, rotation, K,
                             body_sigmas=np.array([0.03, 0.03, 0.10], dtype=np.float32))
```

**Center convention.** `project_frustum_3d` expects the **geometric center** of the box (nuScenes / Waymo / OpenPCDet convention: corners symmetric about center, `corners_z = ±h/2`). KITTI-convention monocular detectors (SMOKE, MonoCon, PGD, CenterNet3D, …) report the **bottom-center** instead (`corners_z = [0 … h]`). Use `from_3d_annotation` to convert automatically:

```python
ann = {
    "translation": [1.2, 1.8, 8.5],       # bottom-center in camera frame (KITTI convention)
    "rotation":    [0.0, 0.0, 0.0, 1.0],   # [qx, qy, qz, qw]
    "dimension":   [2.0, 4.5, 1.5],        # [l, w, h] in meters
}

# center_is_bottom=True (default) — KITTI convention
obs = fg.from_3d_annotation(ann, K)

# center_is_bottom=False — nuScenes / Waymo convention (translation is already center)
obs = fg.from_3d_annotation(ann, K, center_is_bottom=False)

# Batch
observations = fg.from_3d_annotations(list_of_anns, K,
                                       detection_sigma_m=0.05,
                                       center_is_bottom=True)
```

## Inputs

**Camera intrinsics** (`Intrinsics`) describe the pinhole camera model after lens undistortion: focal lengths `(fx, fy)` in pixels, principal point `(cx, cy)`, and image dimensions. These are fixed per camera and can be reused across frames.

**Shape priors** (`ShapePrior`) describe the expected physical size of an object class in meters — mean `(mu_x, mu_y, mu_z)` and 1-σ uncertainty `(sigma_x, sigma_y, sigma_z)`. The axes follow camera-frame convention: x = width (left–right), y = depth (near–far along the ray), z = height (up–down). Setting `sigma = 0` on any axis activates an automatic wide prior (`mu × 0.40`), appropriate when true size is unknown.

**Detector noise** (`DetectorNoise`) captures bounding-box edge localization uncertainty. The single field `sigma_px` (default 2 px) controls the lateral covariance; tighter detectors can use 1 px or less.

**Range sensor** (`RangeSensorConfig`, optional) calibrates a co-registered ranging modality. `range_m` is the distance in meters to the nearest visible surface of the object. The `convention` field selects how that distance is interpreted: `RangeConvention.CARTESIAN_DEPTH` (default — perpendicular z-depth to the image plane, as reported by stereo and structured-light cameras such as Intel RealSense) or `RangeConvention.SLANT_RANGE` (distance from the camera origin along the line of sight, as reported by scanning LiDAR, radar, and single-point ToF). Cartesian depth is converted internally to slant range via `r = z / ray_z`. Measurements outside `(range_min_m, range_max_m]` or NaN are silently discarded and the projection falls back to angular-only estimation.

**3D bounding box** — for `project_frustum_3d` the depth comes directly from the detector:

| Parameter       | Type                    | Description                                                           |
| --------------- | ----------------------- | --------------------------------------------------------------------- |
| `translation`   | `(3,) float32`          | Geometric center of the box in camera frame (m)                       |
| `half_extents`  | `(3,) float32`          | `[a, b, c]` half-sizes in the object's body frame (m)                 |
| `rotation`      | `(3,3) or (9,) float32` | `R_body_to_cam`, row-major                                            |
| `body_sigmas`   | `(3,) float32`          | Anisotropic 1-σ uncertainty per body axis (m); optional               |
| `range_sigma_m` | `float`                 | Isotropic fallback noise when `body_sigmas` is `None` (default 0.5 m) |

For KITTI-convention detectors the `from_3d_annotation` / `from_3d_annotations` helpers assemble these fields from the standard `{translation, rotation, dimension}` dict and apply the bottom-center → geometric-center conversion when `center_is_bottom=True`.

## Batch rules

`project_frustum_batch` takes an observation dict as its first positional argument:

```python
result = fg.project_frustum_batch(
    {
        "boxes":   boxes,    # (N, 4) float32 — required
        "priors":  priors,   # (N, 6) float32 — required
        "ranges":  ranges,   # (N,)   float32 — optional; NaN = no measurement
        "clipped": clipped,  # (N,)   uint8   — optional; 0xFF = auto-detect
    },
    intrinsics = K_arr,   # (4,) float32 [fx, fy, cx, cy]
    img_size   = img_arr, # (2,) float32 [width, height]
    sigma_px   = 2.0,
    sensor     = fg.RangeSensorConfig(sigma_m=0.05),  # omit if no ranging
)
```

- **One camera per call.** All boxes must come from the same camera.
- **Per-row priors.** Mixed-class batches are fully supported — one prior row per box.
- **Concatenate classes.** For pedestrians + vehicles in one frame, stack their boxes and priors into a single call and split the result dict by index afterward. This is always faster than separate calls.
- **`ranges` is optional.** Omit the key for angular-only estimation. Per-element `NaN` or out-of-window values are skipped without any pre-filtering.

### Mixed-class example

```python
PEDESTRIAN = [0.55, 0.55, 1.70, 0.10, 0.10, 0.15]
VEHICLE    = [2.00, 4.50, 1.50, 0.20, 0.50, 0.20]

boxes  = np.vstack([ped_boxes, veh_boxes])           # (N, 4)
priors = np.array([PEDESTRIAN] * n_ped +
                  [VEHICLE]    * n_veh, dtype=np.float32)

result     = fg.project_frustum_batch({"boxes": boxes, "priors": priors},
                                      intrinsics=K_arr, img_size=img)
ped_result = {k: v[:n_ped] for k, v in result.items()}
veh_result = {k: v[n_ped:] for k, v in result.items()}
```

For multiple cameras, call once per camera and merge world-frame results before the downstream fuser.

## Reference values

### Shape priors by class

The axes are: x = width (lateral), y = depth (along the optical axis when upright),
z = height. Values are starting points; tighten sigmas as the tracker accumulates
confident observations.

| Class            | mu_x (m) | mu_y (m) | mu_z (m) | sigma_x (m) | sigma_y (m) | sigma_z (m) |
| ---------------- | -------- | -------- | -------- | ----------- | ----------- | ----------- |
| Pedestrian       | 0.55     | 0.55     | 1.70     | 0.10        | 0.10        | 0.15        |
| Cyclist          | 0.65     | 1.10     | 1.60     | 0.10        | 0.15        | 0.10        |
| Car              | 2.00     | 4.50     | 1.50     | 0.20        | 0.50        | 0.15        |
| Van / SUV        | 2.20     | 5.00     | 1.90     | 0.25        | 0.60        | 0.20        |
| Bus              | 2.50     | 9.00     | 3.20     | 0.30        | 1.00        | 0.30        |
| Drone (consumer) | 0.30     | 0.30     | 0.10     | 0.05        | 0.05        | 0.03        |
| Retail product   | 0.12     | 0.08     | 0.20     | 0.05        | 0.04        | 0.12        |

> These are class-level defaults, not calibrated ground truth. For production use, derive priors from a representative dataset for your camera setup and object population.

### Range sensor noise by modality

`sigma_m` is the 1-σ range measurement noise. Set `range_min_m` to exclude near-field
returns (e.g. the sensor housing) and `range_max_m` to the reliable operating distance.

| Modality                               | sigma_m      | Typical range_max_m |
| -------------------------------------- | ------------ | ------------------- |
| Structured light (e.g. RealSense D4xx) | 0.005–0.01 m | 3–5 m               |
| ToF (consumer, e.g. OAK-D)             | 0.02–0.05 m  | 5–10 m              |
| LiDAR (automotive, e.g. Ouster OS1)    | 0.01–0.03 m  | 100 m               |
| Radar (automotive)                     | 0.10–0.50 m  | 200 m               |
| Stereo / DNN depth                     | 0.20–1.00 m  | 20–50 m             |

### Range sensor example

```python
# ToF camera co-registered with an RGB camera
sensor = fg.RangeSensorConfig(
    sigma_m     = 0.03,   # 3 cm noise
    range_min_m = 0.3,    # discard returns closer than 30 cm
    range_max_m = 8.0,    # discard returns beyond 8 m
)

ranges = np.array([2.8, float("nan"), 1.4], dtype=np.float32)  # NaN = no reading
result = fg.project_frustum_batch(
    {"boxes": boxes, "priors": priors, "ranges": ranges},
    intrinsics=K_arr, img_size=img,
    sensor=sensor,
)
# depth_lo[i] >= ranges[i] for valid readings
# depth_hi[i] tightened to ranges[i] + dim_hi
```

## Build

### Requirements

| Dependency   | Version                       | Notes                                                 |
| ------------ | ----------------------------- | ----------------------------------------------------- |
| CMake        | ≥ 3.20                        |                                                       |
| C++ compiler | C++20                         | GCC ≥ 12, Clang ≥ 15, Intel oneAPI DPC++ ≥ 2024.0     |
| Eigen3       | ≥ 3.4                         | Header-only                                           |
| Intel TBB    | 2021+ (oneTBB) or classic TBB | `libtbb-dev` on Ubuntu                                |
| GoogleTest   | 1.17.0                        | Installed by the `test-cpp` Makefile target via Conan |
| gcovr        | Current Python package        | Required by `test-cpp-coverage`                       |
| pybind11     | ≥ 2.12                        | Python bindings only                                  |
| Python       | ≥ 3.10                        | Python bindings and tests                             |

Optional: OpenVINO ≥ 2024.0 (planned depth-estimation head).

### Makefile

Run these targets from this directory. `build` builds and installs the Python
wheel containing the native C++ extension. `build-cpp` builds only the standalone
C++ core library. `test-cpp` installs pinned GoogleTest with Conan before
configuring and running CTest. `test-unit` runs both the C++ suite and the Python
suite; the latter installs the wheel first so the native-extension parity test
exercises the compiled backend. Set `PYTHON` to an environment with pytest and
NumPy installed; the repository test environment can be selected with
`PYTHON=../../tests/.venv/bin/python`.

```bash
make build
make build-cpp
make test-cpp
make test-cpp-coverage
make test-python
make test-unit PYTHON=../../tests/.venv/bin/python
```

Python coverage for these tests is collected by the root
`make run_unit_tests_coverage` target. Native C++ coverage is measured locally
with `test-cpp-coverage`, which enforces 90% line and 50% branch coverage by
default and writes HTML and XML reports under
`build-coverage/coverage/cpp/`. Override the thresholds with
`CPP_COVERAGE_LINE_MIN` and `CPP_COVERAGE_BRANCH_MIN`.

### Benchmarks

Standalone `benchmarks/` scripts from the upstream package are not vendored here.
Expected throughput on a 16-core Intel Core Ultra 7 at Release with oneTBB:

| N detections | Latency | Throughput |
| ------------ | ------- | ---------- |
| 1            | ~4 µs   | 250 k/s    |
| 32           | ~8 µs   | 4 M/s      |
| 128          | ~12 µs  | 10 M/s     |
| 256          | ~18 µs  | 14 M/s     |

## Pipeline fit

This library is the **per-camera projection kernel**. Typical downstream use:

```
2D detector                     3D detector (LiDAR / stereo / monocular-3D DNN)
    └─▶ project_frustum_batch()     └─▶ project_frustum_3d() / from_3d_annotations()
              └──────────────────────────────────┘
                           ← this library →
                    └─▶ transform_to_world[_batch]()
                            └─▶ observation_conditioning   (mesh / FREE_3D)
                                    └─▶ multi-camera fuser / tracker
```

The `mu`, `Sigma`, `ray`, `depth_lo`, `depth_hi`, and `score` fields are the interface
contract with [`observation_conditioning`](../observation_conditioning/), which applies
scene-mesh constraints (or passes FREE_3D detections through) before fusion/tracking.

For algorithm details and deployment notes see [ALGORITHM.md](ALGORITHM.md).
