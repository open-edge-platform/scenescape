<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Tracker Evaluation Pipeline

A pluggable framework for evaluating multi-camera 3D tracking systems using industry-standard datasets, metrics, and evaluation toolkits.

## Overview

This pipeline implements the [Tracker Evaluation Pipeline Design](../../../docs/design/tracker-evaluation-pipeline.md) and supports the [Tracking Evaluation Strategy (ADR 9)](../../../docs/adr/0009-tracking-evaluation.md).

### Architecture

The pipeline consists of three core components:

1. **Tracking Dataset**: Provides scene configuration, input detections, and ground-truth
2. **Tracker Harness**: Executes the tracking system on input data
3. **Tracker Evaluator**: Computes tracking quality metrics

These components communicate using canonical data formats defined by JSON schemas in `tracker/schema/`.

## Quick Start

### Installation

```bash
cd tools/tracker/evaluation
pip install -r requirements.txt
```

### Usage

Create a YAML configuration file (see `examples/` directory):

```yaml
dataset:
  class: datasets.metric_test_dataset.MetricTestDataset
  config:
    data_path: /path/to/test_data

harness:
  class: harnesses.scene_controller_harness.SceneControllerHarness
  config:
    tracker_config: /path/to/tracker-config.json

evaluator:
  class: evaluators.trackeval_evaluator.TrackEvalEvaluator
  config:
    metrics: [HOTA, MOTA, IDF1]
    result_folder: /path/to/results
```

Run the pipeline:

```bash
python -m evaluation.pipeline_engine config.yaml
```

## Directory Structure

```
evaluation/
├── base/                 # Abstract base classes (component interfaces)
├── datasets/             # Dataset implementations
├── harnesses/            # Tracker harness implementations
├── evaluators/           # Evaluator implementations
├── utils/                # Shared utilities
└── examples/             # Example configurations
```

## Extending the Pipeline

### Adding a New Dataset

1. Create a new file in `datasets/` (e.g., `wildtrack_dataset.py`)
2. Implement the `TrackingDataset` ABC from `base/tracking_dataset.py`
3. Convert dataset-specific formats to canonical formats

### Adding a New Harness

1. Create a new file in `harnesses/` (e.g., `standalone_tracker_harness.py`)
2. Implement the `TrackerHarness` ABC from `base/tracker_harness.py`

### Adding a New Evaluator

1. Create a new file in `evaluators/` (e.g., `custom_evaluator.py`)
2. Implement the `TrackerEvaluator` ABC from `base/tracker_evaluator.py`

## Canonical Data Formats

The pipeline uses standardized data formats defined by JSON schemas to enable interoperability between components. All implementations must conform to these canonical formats.

### Scene Configuration Format

**Schema**: `tracker/schema/scene.schema.json`

**Purpose**: Describes scene and camera setup including camera intrinsics and extrinsics.

**Structure**:
```json
{
  "uid": "scene-unique-id",
  "name": "Scene_Name",
  "cameras": [
    {
      "uid": "camera-unique-id",
      "name": "Camera_Name",
      "intrinsics": {
        "fx": 964.24,
        "fy": 964.63,
        "cx": 400.0,
        "cy": 300.0
      },
      "distortion": {
        "k1": 0.0,
        "k2": 0.0
      }
    }
  ]
}
```

### Input Detection Format

**Schema**: `tracker/schema/camera-data.schema.json`

**Purpose**: Object detections from individual cameras (tracker input).

**Structure**:
```json
{
  "timestamp": 1234567890.123,
  "id": "camera-unique-id",
  "objects": [
    {
      "id": 1,
      "label": "person",
      "bbox2d": [x_min, y_min, x_max, y_max],
      "confidence": 0.95
    }
  ]
}
```

### Tracker Output Format

**Schema**: `tracker/schema/scene-data.schema.json`

**Purpose**: 3D tracking results from the tracker (evaluator input).

**Structure**: See schema file for complete specification.

### Ground Truth Format (MOTChallenge 3D CSV)

**Purpose**: Ground-truth tracks for evaluation (evaluator reference data).

**Format**: MOTChallenge 3D CSV with 8 columns:

| Column | Name       | Description                    | Type  |
|--------|------------|--------------------------------|-------|
| 1      | frame      | Frame number (1-indexed)       | int   |
| 2      | id         | Object/track ID                | int   |
| 3      | x          | 3D position X coordinate       | float |
| 4      | y          | 3D position Y coordinate       | float |
| 5      | z          | 3D position Z coordinate       | float |
| 6      | conf       | Confidence/detection score     | float |
| 7      | class      | Object class (1 for person)    | int   |
| 8      | visibility | Visibility flag (1 = visible)  | int   |

**Example**:
```csv
1,1,5.2,3.1,0.0,1.0,1,1
1,2,7.8,4.5,0.0,1.0,1,1
2,1,5.3,3.2,0.0,1.0,1,1
```

**Notes**:
- Frame numbers are 1-indexed (not 0-indexed)
- Default class value is 1 (person) per TrackEval convention
- Visibility 1 indicates fully visible object

## References

- [Design Document](../../../docs/design/tracker-evaluation-pipeline.md)
- [ADR 9: Tracking Evaluation Strategy](../../../docs/adr/0009-tracking-evaluation.md)
- [TrackEval Toolkit](https://github.com/JonathonLuiten/TrackEval)
