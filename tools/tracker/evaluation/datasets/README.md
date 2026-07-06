<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tracking Datasets

This directory contains dataset adapter implementations for the tracker evaluation pipeline.

## Overview

Each dataset adapter implements the `TrackingDataset` abstract base class (see [../base/tracking_dataset.py](../base/tracking_dataset.py)) to provide:

- Scene and camera configuration in Scenescape canonical format
- Input data (object detections) from configured cameras, sorted by timestamp
- Ground-truth object locations for evaluation

Dataset adapters convert dataset-specific formats to Scenescape canonical formats as defined in the tracker schemas.

**Important**: When `get_inputs()` returns data from multiple cameras, frames must be sorted by timestamp in chronological order to properly simulate real-time tracking scenarios.

## Available Datasets

### MetricTestDataset

**Purpose**: Adapter for `tests/system/metric/unity_dataset` dataset used in acceptance tests.

**Key Features**:
- Single scene: `Unity`
- Two cameras: `Cam_x1_0`, `Cam_x2_0`
- Multiple FPS options: 1, 10, 30 (separate JSON files per FPS)
- Ground truth in MOTChallenge 3D CSV format (see [Canonical Data Formats](../README.md#canonical-data-formats))

**Usage Example**:
```python
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from datasets.metric_test_dataset import MetricTestDataset

dataset = MetricTestDataset("../../../tests/system/metric/unity_dataset")

# Configure dataset
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

# Get scene configuration
scene_config = dataset.get_scene_config()

# Get camera inputs
for camera_input in dataset.get_inputs("Cam_x1_0"):
    # Process detection data
    pass

# Get ground truth
gt_path = dataset.get_ground_truth()
```

**Documentation**: See [MetricTestDataset docstring](metric_test_dataset.py) for detailed API documentation.

**Tests**: See [tests/test_metric_test_dataset.py](tests/test_metric_test_dataset.py) for comprehensive test suite.

### WildtrackDataset

**Purpose**: Adapter for the [WILDTRACK](https://arxiv.org/pdf/1707.09299.pdf) multi-camera person dataset, using preprocessed artifacts stored under `tests/system/metric/wildtrack_dataset`.

**Key Features**:
- Single scene: `Wildtrack`
- Seven cameras: `cam0`–`cam6` (mapping `cam0=CVLab1`, `cam1=CVLab2`, `cam2=CVLab3`, `cam3=CVLab4`, `cam4=IDIAP1`, `cam5=IDIAP2`, `cam6=IDIAP3`)
- Single FPS option: 2 (native annotation rate; 400 annotated frames)
- Explicit camera intrinsics and extrinsics (converted from the dataset calibration files) in the scene configuration
- Ground truth in MOTChallenge 3D CSV format (see [Canonical Data Formats](../README.md#canonical-data-formats))

**Preprocessing**: The canonical artifacts are generated from the raw dataset with the
`datasets.wildtrack.preprocess` module. See [wildtrack/preprocess.py](wildtrack/preprocess.py).

**Usage Example**:
```python
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from datasets.wildtrack_dataset import WildtrackDataset

dataset = WildtrackDataset("../../../tests/system/metric/wildtrack_dataset")

# Configure dataset (cameras selectable by index 0-6)
dataset.set_cameras([0, 1, 2, 3, 4, 5, 6]).set_camera_fps(2)

# Get scene configuration
scene_config = dataset.get_scene_config()

# Get camera inputs
for camera_input in dataset.get_inputs("cam0"):
    # Process detection data
    pass

# Get ground truth
gt_path = dataset.get_ground_truth()
```

**Documentation**: See [WildtrackDataset docstring](wildtrack_dataset.py) for detailed API documentation.

**Tests**: See [tests/test_wildtrack_dataset.py](tests/test_wildtrack_dataset.py) for the test suite.

**Citation**: WILDTRACK is a third-party dataset that is adopted and used in this tracker evaluation. Source paper:

> "The WILDTRACK Multi-Camera Person Dataset." T. Chavdarova et al.
> https://arxiv.org/pdf/1707.09299.pdf

## Adding New Datasets

To add support for a new dataset:

1. **Create adapter class**: Implement all abstract methods from `TrackingDataset` base class (see [../base/tracking_dataset.py](../base/tracking_dataset.py))
2. **Format conversion**: Convert dataset-specific formats to Scenescape canonical formats (see [Canonical Data Formats](../README.md#canonical-data-formats))
3. **Create tests**: Add comprehensive tests validating format conversion and schema compliance
4. **Update documentation**: Add entry to this README with usage example and key features

## Design Documentation

See [tracker-evaluation-pipeline.md](../../../../docs/design/tracker-evaluation-pipeline.md) for overall architecture and design decisions.
