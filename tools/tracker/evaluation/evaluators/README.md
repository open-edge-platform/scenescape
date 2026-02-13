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
dataset.set_cameras(["x1", "x2"]).set_camera_fps(30)

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
