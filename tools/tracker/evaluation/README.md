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

### Prerequisites

**System requirements**:

- Docker installed and running on the host machine
- SceneScape scene controller container image available locally (e.g., `scenescape-controller:2026.0.0-dev`)

To verify Docker is available:

```bash
docker --version
docker images | grep scenescape-controller
```

### Installation

```bash
cd tools/tracker/evaluation
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

Create a YAML configuration file (see `pipeline_configs/` directory):

```yaml
pipeline:
  output:
    path: /tmp/tracker-evaluation # Base output directory

dataset:
  class: datasets.metric_test_dataset.MetricTestDataset
  config:
    data_path: /path/to/dataset
    cameras: [x1, x2]
    camera_fps: 30

harness:
  class: harnesses.scene_controller_harness.SceneControllerHarness
  config:
    container_image: scenescape-controller:latest
    tracker_config_path: /path/to/tracker-config.json

evaluators:
  - class: evaluators.trackeval_evaluator.TrackEvalEvaluator
    config:
      metrics: [HOTA, MOTA, IDF1]
```

Run the pipeline:

```bash
python -m pipeline_engine config.yaml
```

**Output Structure**: Each pipeline run creates a unique timestamped directory:

```
<pipeline.output.path>/
  └── <run-ID>/                        # Format: YYYYMMDD_HHMMSS
      ├── dataset/                     # Dataset-specific caches or exports
      ├── harness/                     # Harness logs or artifacts
      └── evaluators/
          └── <evaluator-key>/         # One folder per evaluator
```

The `<evaluator-key>` is the evaluator class name (e.g., `TrackEvalEvaluator`). When two evaluators
share the same class name, an index suffix is appended to keep keys unique
(e.g., `TrackEvalEvaluator_0/`, `TrackEvalEvaluator_1/`).

**Multiple evaluators**: The `evaluators` list accepts any number of entries. Each evaluator runs
against the same tracker outputs independently.

## Directory Structure

```
evaluation/
├── base/                 # Abstract base classes (component interfaces)
├── datasets/             # Dataset implementations
├── harnesses/            # Tracker harness implementations
├── evaluators/           # Evaluator implementations
├── utils/                # Shared utilities
└── pipeline_configs/     # Pipeline configurations
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

### Input Detection Format

**Schema**: `tracker/schema/camera-data.schema.json`

**Purpose**: Object detections from individual cameras (tracker input).

### Tracker Output Format

**Schema**: `tracker/schema/scene-data.schema.json`

**Purpose**: 3D tracking results from the tracker (evaluator input).

### Ground Truth Format (MOTChallenge 3D CSV)

**Purpose**: Ground-truth tracks for evaluation (evaluator reference data).

**Format**: MOTChallenge 3D CSV with 8 columns:

| Column | Name       | Description                   | Type  |
| ------ | ---------- | ----------------------------- | ----- |
| 1      | frame      | Frame number (1-indexed)      | int   |
| 2      | id         | Object/track ID               | int   |
| 3      | x          | 3D position X coordinate      | float |
| 4      | y          | 3D position Y coordinate      | float |
| 5      | z          | 3D position Z coordinate      | float |
| 6      | conf       | Confidence/detection score    | float |
| 7      | class      | Object class (1 for person)   | int   |
| 8      | visibility | Visibility flag (1 = visible) | int   |

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

## Limitations

- **TrackEval timestamp deduplication**: TrackEval requires unique frame indices while the production tracker can emit multiple frames with identical timestamps when time-chunking is disabled. To bridge this mismatch, [evaluators/trackeval_evaluator.py](evaluators/trackeval_evaluator.py) filters duplicate timestamps inside `TrackEvalEvaluator.process_tracker_outputs()` and keeps only the first frame per timestamp before metrics are computed. This prevents TrackEval from double-counting frames until tracker-side chunking aligns with TrackEval's expectations. The impact on metrics is not significant, since frames with duplicated timestamps in most cases contain almost the same object coordinates.

## Testing

### Test Organization

The evaluation pipeline has comprehensive test coverage:

- **Unit Tests**: Fast tests without external dependencies, located in component-specific test directories
  - `datasets/tests/test_*.py`: Datasets unit tests
  - `harnesses/tests/test_*.py`: Harnesses unit tests
  - `tests/test_format_converters.py`: Format converter unit tests

- **Integration Tests**: Tests requiring Docker and real components, located in `tests/`
  - `tests/test_scene_controller_harness_integration.py`: End-to-end harness tests with container

### Running Tests

**Simple test runner** (recommended):

```bash
cd tools/tracker/evaluation

# Run all tests (including integration tests)
./run_tests.sh

# Run only unit tests (fast, no Docker required)
./run_tests.sh unit

# Run only integration tests (requires Docker)
./run_tests.sh integration
```

**Using pytest directly**:

**Run all tests** (including integration tests):

```bash
cd tools/tracker/evaluation
pytest . -v
```

**Run only unit tests** (fast, no Docker required):

```bash
pytest . -v -m "not integration"
```

**Run only integration tests** (requires Docker):

```bash
pytest . -v -m integration
```

**Run tests from a specific directory**:

```bash
pytest tests/ -v                     # Integration tests
pytest datasets/tests/ -v            # Dataset unit tests
pytest harnesses/tests/ -v           # Harness unit tests
pytest evaluators/tests/ -v           # Evaluators unit tests
```

**Run tests from a specific file**:

```bash
pytest harnesses/tests/test_scene_controller_harness.py -v
```

**Run a specific test**:

```bash
pytest harnesses/tests/test_scene_controller_harness.py::TestSceneControllerHarness::test_initialization -v
```

### Prerequisites for Integration Tests

Integration tests require:

- Docker installed and running
- SceneScape controller container image available (e.g., `scenescape-controller:latest`)

Verify Docker setup:

```bash
docker --version
docker images | grep scenescape-controller
```

### Expected Test Results

Some integration tests may be marked as `xfail` (expected to fail) to document known issues or format mismatches that are planned to be fixed in future work.
