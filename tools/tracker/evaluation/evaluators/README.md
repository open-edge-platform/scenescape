<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tracker Evaluators

This directory contains evaluator implementations for computing tracking quality metrics in the evaluation pipeline.

## Overview

Each tracker evaluator implements the `TrackerEvaluator` abstract base class (see [../base/tracker_evaluator.py](../base/tracker_evaluator.py)) to:

- Configure which metrics to compute
- Process tracker outputs and ground-truth data
- Compute industry-standard tracking quality metrics
- Export results and optional plots

Evaluators handle metric-library-specific details (TrackEval, py-motmetrics, etc.) while providing a unified interface to the evaluation pipeline.

## Available Evaluators

### TrackEvalEvaluator

**Purpose**: Compute tracking quality metrics using the TrackEval library with custom 3D point tracking support.

**Status**: **FULLY IMPLEMENTED** - Computes real metrics from tracker outputs using TrackEval library with custom MotChallenge3DPoint dataset class.

**Supported Metrics**:

- **HOTA metrics**: HOTA, DetA, AssA, LocA, DetPr, DetRe, AssPr, AssRe
- **CLEAR MOT metrics**: MOTA, MOTP, MT, ML, Frag
- **Identity metrics**: IDF1, IDP, IDR

For full metric list, refer to the TrackEval documentation: https://pypi.org/project/trackeval/.

**Key Features**:

- **3D Point Tracking**: Custom `MotChallenge3DPoint` class extends TrackEval's `MotChallenge2DBox` with:
  - Euclidean distance similarity (instead of IoU)
  - 3D position extraction (x, y, z from translation field)
  - Configurable distance threshold (default: 2.0 meters for 0.5 similarity)
- **Format Conversion**: Automatic conversion from canonical JSON format to MOTChallenge CSV
- **UUID Mapping**: Consistent UUID-to-integer ID mapping for track identity preservation
- **Timestamp Handling**: Frame synchronization via FPS-based timestamp-to-frame conversion

**Usage Example**:

```python
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from evaluators.trackeval_evaluator import TrackEvalEvaluator
from datasets.metric_test_dataset import MetricTestDataset
from harnesses.scene_controller_harness import SceneControllerHarness

# Initialize dataset
dataset = MetricTestDataset("path/to/dataset")
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

# Initialize and run harness
harness = SceneControllerHarness(container_image='scenescape-controller:latest')
harness.set_scene_config(dataset.get_scene_config())
harness.set_custom_config({'tracker_config_path': '/path/to/tracker-config.json'})
tracker_outputs = harness.process_inputs(dataset.get_inputs())

# Initialize evaluator
evaluator = TrackEvalEvaluator()

# Configure metrics
evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])
evaluator.set_output_folder(Path('/path/to/results'))

# Process and evaluate
evaluator.process_tracker_outputs(
    tracker_outputs=tracker_outputs,
    ground_truth=dataset.get_ground_truth()
)

# Get metrics
metrics = evaluator.evaluate_metrics()
print(f"HOTA: {metrics['HOTA']:.3f}")
print(f"MOTA: {metrics['MOTA']:.3f}")
print(f"IDF1: {metrics['IDF1']:.3f}")
```

**Current Limitations**:

- Fixed class name ("pedestrian") for all objects
- Single-sequence evaluation only
- No parallel processing support
- Limited configuration options for TrackEval parameters

**Implementation**: [trackeval_evaluator.py](trackeval_evaluator.py)

**Tests**: See [tests/test_trackeval_evaluator.py](tests/test_trackeval_evaluator.py) for comprehensive test suite with 16 test cases covering configuration, processing, evaluation, and integration workflows.

### DiagnosticEvaluator

**Purpose**: Per-frame location comparison and error analysis between matched output tracks and ground-truth tracks.

**Status**: **FULLY IMPLEMENTED** - Bipartite track matching with per-frame location and distance CSV/plot outputs.

**Supported Metrics**:

- **LOC_T_X**: Per-frame X position of each matched (output, GT) track pair
- **LOC_T_Y**: Per-frame Y position of each matched (output, GT) track pair
- **DIST_T**: Per-frame Euclidean distance error between each matched pair

**Key Features**:

- **Track Matching**: Bipartite assignment (Hungarian algorithm) minimizing mean Euclidean distance over overlapping frames. Requires a minimum of 10 overlapping frames (`MIN_OVERLAP_FRAMES`).
- **Missing Frame Handling**: Frames where only one side (output or GT) has data produce `NaN` in CSV output, preserving full temporal context.
- **CSV Output**: Per-metric CSV files with headers:
  - LOC_T_X / LOC_T_Y: `[frame_id, track_id, gt_id, value_track, value_gt]`
  - DIST_T: `[frame_id, track_id, gt_id, distance]`
- **Plot Output**: One matplotlib figure per metric with all matched pairs overlaid.
- **Summary Scalars**: `evaluate_metrics()` returns `DIST_T_mean`, `LOC_T_X_mae`, `LOC_T_Y_mae`, and `num_matches`.

**Usage Example**:

```python
from evaluators.diagnostic_evaluator import DiagnosticEvaluator
from pathlib import Path

evaluator = DiagnosticEvaluator()
metrics = (evaluator
           .configure_metrics(['LOC_T_X', 'LOC_T_Y', 'DIST_T'])
           .set_output_folder(Path('/path/to/results'))
           .process_tracker_outputs(tracker_outputs, gt_file_path)
           .evaluate_metrics())
print(f"Mean distance: {metrics['DIST_T_mean']:.3f}")
print(f"X MAE: {metrics['LOC_T_X_mae']:.3f}")
print(f"Y MAE: {metrics['LOC_T_Y_mae']:.3f}")
print(f"Matched pairs: {int(metrics['num_matches'])}")
```

**Current Limitations**:

- Uses only X and Y coordinates (Z ignored)
- Single-sequence evaluation only
- No configurable overlap threshold (fixed at 10 frames)

**Implementation**: [diagnostic_evaluator.py](diagnostic_evaluator.py)

**Tests**: See [tests/test_diagnostic_evaluator.py](tests/test_diagnostic_evaluator.py) for unit tests covering track matching, scalar metrics, CSV output, and reset workflows.

### JitterEvaluator

**Purpose**: Evaluate tracker smoothness by measuring positional jitter in tracked object trajectories, and compare it against jitter already present in the ground-truth test data.

**Status**: **FULLY IMPLEMENTED** — Computes RMS jerk and acceleration variance from both tracker outputs and ground-truth tracks using numerical differentiation.

**Supported Metrics**:

| Metric                        | Source         | Description                                                                                                       |
| ----------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------- |
| `rms_jerk`                    | Tracker output | RMS jerk across all tracker output tracks (m/s³)                                                                  |
| `acceleration_variance`       | Tracker output | Variance of acceleration magnitudes across all tracker output tracks (m/s²)²                                      |
| `rms_jerk_gt`                 | Ground truth   | Same as `rms_jerk` computed on ground-truth tracks                                                                |
| `acceleration_variance_gt`    | Ground truth   | Same as `acceleration_variance` computed on ground-truth tracks                                                   |
| `rms_jerk_ratio`              | Tracker / GT   | `rms_jerk` / `rms_jerk_gt` — tracker jitter relative to GT (1.0 = equal)                                          |
| `acceleration_variance_ratio` | Tracker / GT   | `acceleration_variance` / `acceleration_variance_gt` — tracker acceleration variance relative to GT (1.0 = equal) |

Comparing `rms_jerk` with `rms_jerk_gt` shows how much jitter the tracker
adds on top of any jitter already present in the test data.

**Algorithm**:

All metrics are derived by applying three sequential layers of forward finite differences to 3D positions, accounting for variable time steps between frames:

$$v_i = \frac{p_{i+1} - p_i}{\Delta t_i}, \quad a_i = \frac{v_{i+1} - v_i}{\Delta t_{v,i}}, \quad j_i = \frac{a_{i+1} - a_i}{\Delta t_{a,i}}$$

- **rms_jerk / rms_jerk_gt**: $\sqrt{\frac{1}{N}\sum |j_i|^2}$ over all jerk samples from all tracks.
- **acceleration_variance / acceleration_variance_gt**: $\text{Var}(|a_i|)$ over all acceleration magnitude samples from all tracks.
- **rms_jerk_ratio / acceleration_variance_ratio**: tracker metric divided by the corresponding GT metric. Returns 0.0 when the GT denominator is zero. Values >1.0 indicate the tracker adds more jitter than is inherent in the ground truth.

Minimum track length: 3 points for acceleration, 4 points for jerk. Shorter tracks are skipped; if no eligible tracks exist, the metric returns 0.0.

For GT metrics, ground-truth frame numbers are converted to relative timestamps using the FPS derived from the tracker output.

**Key Features**:

- Builds per-track position histories from canonical tracker output format.
- Parses MOTChallenge 3D CSV ground-truth file for GT metric computation.
- Supports variable frame rates — time deltas are computed from actual timestamps.
- Deduplicates frames with identical timestamps (mirrors `TrackEvalEvaluator` behaviour).
- Sorts each track's positions by timestamp before metric computation.
- Saves a plain-text `jitter_results.txt` summary to the configured output folder.

**Usage Example**:

```python
from pathlib import Path
from evaluators.jitter_evaluator import JitterEvaluator

evaluator = JitterEvaluator()
evaluator.configure_metrics(['rms_jerk', 'rms_jerk_gt', 'rms_jerk_ratio',
                             'acceleration_variance', 'acceleration_variance_gt',
                             'acceleration_variance_ratio'])
evaluator.set_output_folder(Path('/path/to/results'))

# Pass ground_truth=None to skip GT metrics
evaluator.process_tracker_outputs(tracker_outputs, ground_truth=dataset.get_ground_truth())
metrics = evaluator.evaluate_metrics()

print(f"RMS Jerk (tracker): {metrics['rms_jerk']:.4f} m/s³")
print(f"RMS Jerk (GT):      {metrics['rms_jerk_gt']:.4f} m/s³")
print(f"RMS Jerk ratio:     {metrics['rms_jerk_ratio']:.4f}  (1.0 = equal jitter)")
```

**Pipeline Configuration**:

```yaml
evaluators:
  - class: evaluators.jitter_evaluator.JitterEvaluator
    config:
      metrics:
        [
          rms_jerk,
          rms_jerk_gt,
          rms_jerk_ratio,
          acceleration_variance,
          acceleration_variance_gt,
          acceleration_variance_ratio,
        ]
```

**Implementation**: [jitter_evaluator.py](jitter_evaluator.py)

**Tests**: See [tests/test_jitter_evaluator.py](tests/test_jitter_evaluator.py).

### CameraAccuracyEvaluator

**Purpose**: Measure the raw position error introduced by each camera's calibration by comparing projected world-coordinate positions against ground-truth positions, without any tracker fusion.

**Status**: **FULLY IMPLEMENTED** — Computes per-camera, per-object distance error and visibility from `CameraProjectionHarness` outputs.

**Supported Metrics**:

| Metric       | Description                                                                                          |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| `DIST_T`     | Per-frame Euclidean distance (m) between projected and ground-truth XY position, averaged per object |
| `VISIBILITY` | Number of frames each camera detects each object (and as % of total GT frames)                       |

**Key Features**:

- **Per-camera, per-object breakdown**: every `(camera, object)` pair gets its own mean error and visibility count.
- **Object ID decoding**: harness encodes IDs as `"{camera_id}:{object_id}"`; this evaluator splits them back.
- **Camera position resolution**: `set_scene_config()` runs `cv2.solvePnP` on each sensor's calibration points to place a star marker on trajectory plots.
- **Camera view direction**: `set_scene_config()` also computes the normalized 2-D world-space viewing direction of each camera (`R^T @ [0, 0, 1]` XY component) and draws an arrow on the trajectory plot.
- **Axis orientation**: when the camera is above the scene centre (`cam_y > mean(gt_y)`), both X and Y axes are flipped (180° rotation) so the camera always appears at the visual bottom with correct left/right chirality.
- **Human-readable CSV output**: `summary_table.csv` uses column names like `"Cam_x1_0 - Mean Error (m)"`.
- **Terminal table**: `format_summary()` renders a 2-row-header table with `|` separators between camera groups.
- **Plots** (per camera):
  - `distance_errors_{cam}.png` — distance error over time.
  - `trajectories_{cam}.png` — projected (solid) vs GT (dashed) XY trajectories, camera position star, view-direction arrow, tight-zoomed with start-point markers.
  - `error_vs_cam_distance_{cam}.png` — mean projection error vs. distance from camera (binned).
- **Visibility bar chart**: `visibility_per_camera.png` comparing per-object visibility across cameras.

**Metrics returned by `evaluate_metrics()`**:

- `n_cameras`, `n_objects` — counts (int)
- `dist_mean_all`, `dist_mean_{cam}`, `dist_mean_{cam}_{obj}` — distance errors (float, metres)
- `visibility_{cam}_{obj}` — frame count (int)
- `visibility_pct_{cam}_{obj}` — visibility percentage (float, 0–100)

**Usage Example**:

```python
from pathlib import Path
from evaluators.camera_accuracy_evaluator import CameraAccuracyEvaluator

evaluator = CameraAccuracyEvaluator()
evaluator.configure_metrics(['DIST_T', 'VISIBILITY'])
evaluator.set_output_folder(Path('/path/to/results'))
evaluator.process_tracker_outputs(harness_outputs, gt_file_path)
results = evaluator.evaluate_metrics()

print(evaluator.format_summary())
print(f"Overall mean error: {results['dist_mean_all']:.3f} m")
```

**Pipeline Configuration**:

```yaml
harness:
  class: harnesses.camera_projection_harness.CameraProjectionHarness
  config:
    container_image: scenescape-controller:latest

evaluators:
  - class: evaluators.camera_accuracy_evaluator.CameraAccuracyEvaluator
    config:
      metrics: [DIST_T, VISIBILITY]
```

See `pipeline_configs/camera_projection_evaluation.yaml` for a ready-to-run example.

**Implementation**: [camera_accuracy_evaluator.py](camera_accuracy_evaluator.py)

**Tests**: See [tests/test_camera_accuracy_evaluator.py](tests/test_camera_accuracy_evaluator.py) — 42 test cases covering configuration, metric computation, CSV/plot outputs, `format_summary()`, `set_scene_config()` (camera positions and view directions), axis orientation, view-direction arrow rendering, edge cases, and reset.

## Adding New Evaluators

To add support for a new metric computation library:

1. **Create evaluator class**: Implement all abstract methods from `TrackerEvaluator` base class (see [../base/tracker_evaluator.py](../base/tracker_evaluator.py))
2. **Integrate metric library**: Wrap the external library (TrackEval, py-motmetrics, etc.) or implement custom code to compute metrics
3. **Handle formats**: Convert canonical tracker outputs and ground-truth to library-specific formats
4. **Support configuration**:
   - `configure_metrics()` - specify which metrics to compute

- `set_output_folder()` - where to save results and plots

5. **Document requirements**: Update this README with supported metrics and configuration options
6. **Create tests**: Add tests validating metric computation and result export

### Implementation Patterns

**Metric computation workflow**:

1. Configure metrics via `configure_metrics(['HOTA', 'MOTA', ...])`
2. Set result output folder via `set_output_folder(Path('/results'))`
3. Process data via `process_tracker_outputs(tracker_outputs, ground_truth)`
4. Compute metrics via `evaluate_metrics()` → returns `Dict[str, float]`
5. Reset state via `reset()` to evaluate another tracker

**Method chaining**:
All configuration methods return `self` for fluent API:

```python
metrics = (evaluator
           .configure_metrics(['HOTA', 'MOTA'])
           .set_output_folder(Path('/results'))
           .process_tracker_outputs(outputs, gt)
           .evaluate_metrics())
```

**Ground-truth format**:
Evaluators receive ground-truth in **MOTChallenge 3D CSV format**: See [Canonical Data Formats](../README.md#canonical-data-formats)

- Provided by dataset's `get_ground_truth()` method

## Design Documentation

See [tracker-evaluation-pipeline.md](../../../../docs/design/tracker-evaluation-pipeline.md) for overall architecture and design decisions.
