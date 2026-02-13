<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tracking Datasets

This directory contains dataset adapter implementations for the tracker evaluation pipeline.

## Overview

Each dataset adapter implements the `TrackingDataset` abstract base class (see [../base/tracking_dataset.py](../base/tracking_dataset.py)) to provide:

- Scene and camera configuration in SceneScape canonical format
- Input data (object detections) from configured cameras, sorted by timestamp
- Ground-truth object locations for evaluation

Dataset adapters convert dataset-specific formats to SceneScape canonical formats as defined in the tracker schemas.

**Important**: When `get_inputs()` returns data from multiple cameras, frames must be sorted by timestamp in chronological order to properly simulate real-time tracking scenarios.

## Available Datasets

### MetricTestDataset

**Purpose**: Adapter for `tests/system/metric/dataset` dataset used in acceptance tests.

**Key Features**:
- Single scene: `Retail_Demo`
- Two cameras: `x1`, `x2` (Cam_x1_0, Cam_x2_0)
- Multiple FPS options: 1, 10, 30 (separate JSON files per FPS)
- Ground truth in MOTChallenge 3D CSV format (see [Canonical Data Formats](../README.md#canonical-data-formats))

**Usage Example**:
```python
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from datasets.metric_test_dataset import MetricTestDataset

dataset = MetricTestDataset("../../../tests/system/metric/dataset")

# Configure dataset
dataset.set_cameras(["x1", "x2"]).set_camera_fps(30)

# Get scene configuration
scene_config = dataset.get_scene_config()

# Get camera inputs
for camera_input in dataset.get_inputs("x1"):
    # Process detection data
    pass

# Get ground truth
gt_path = dataset.get_ground_truth()
```

**Documentation**: See [MetricTestDataset docstring](metric_test_dataset.py) for detailed API documentation.

**Tests**: See [tests/test_metric_test_dataset.py](tests/test_metric_test_dataset.py) for comprehensive test suite.

## Adding New Datasets

To add support for a new dataset:

1. **Create adapter class**: Implement all abstract methods from `TrackingDataset` base class (see [../base/tracking_dataset.py](../base/tracking_dataset.py))
2. **Format conversion**: Convert dataset-specific formats to SceneScape canonical formats (see [Canonical Data Formats](../README.md#canonical-data-formats))
3. **Create tests**: Add comprehensive tests validating format conversion and schema compliance
4. **Update documentation**: Add entry to this README with usage example and key features

## Design Documentation

See [tracker-evaluation-pipeline.md](../../../../docs/design/tracker-evaluation-pipeline.md) for overall architecture and design decisions.
