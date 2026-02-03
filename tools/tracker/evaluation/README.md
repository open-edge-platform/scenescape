<!--
SPDX-FileCopyrightText: (C) 2025 Intel Corporation
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

- **Scene configuration**: `tracker/schema/scene.schema.json`
- **Input detections**: `tracker/schema/camera-data.schema.json`
- **Tracker outputs**: `tracker/schema/scene-data.schema.json`

## References

- [Design Document](../../../docs/design/tracker-evaluation-pipeline.md)
- [ADR 9: Tracking Evaluation Strategy](../../../docs/adr/0009-tracking-evaluation.md)
- [TrackEval Toolkit](https://github.com/JonathonLuiten/TrackEval)
