<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example Configurations

This directory contains example YAML configuration files for the tracker evaluation pipeline.

## Available Examples

- `metric_test_evaluation.yaml` - Evaluation using the system metric test dataset (to be added)

## Configuration File Structure

```yaml
# Dataset configuration
dataset:
  class: <python.module.path.ClassName>  # e.g., datasets.metric_test_dataset.MetricTestDataset
  config:
    # Dataset-specific configuration parameters
    key: value

# Harness configuration
harness:
  class: <python.module.path.ClassName>  # e.g., harnesses.scene_controller_harness.SceneControllerHarness
  config:
    # Harness-specific configuration parameters
    key: value

# Evaluator configuration
evaluator:
  class: <python.module.path.ClassName>  # e.g., evaluators.trackeval_evaluator.TrackEvalEvaluator
  config:
    # Evaluator-specific configuration parameters
    metrics: [HOTA, MOTA, IDF1]
    result_folder: /path/to/results
```

## Usage

```bash
python -m evaluation.pipeline_engine examples/metric_test_evaluation.yaml
```
