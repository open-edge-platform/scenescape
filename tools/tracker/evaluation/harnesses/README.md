<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tracker Harnesses

This directory contains harness implementations for executing tracking systems in the evaluation pipeline.

## Overview

Each tracker harness implements the `TrackerHarness` abstract base class (see [../base/tracker_harness.py](../base/tracker_harness.py)) to:

- Configure and execute a tracking system
- Feed input detections to the tracker
- Collect and return tracker outputs

Harnesses handle tracker-specific deployment details (containers, processes, API calls) while providing a unified interface to the evaluation pipeline.

## Available Harnesses

### SceneControllerHarness

**Purpose**: Execute tracker inside SceneScape scene controller Docker container.

**Mode**: **Batch processing only** - all inputs must be provided in a single `process_inputs()` call.

**Key Features**:
- Runs tracker in isolated Docker container
- Uses python-on-whales for container management
- Accepts raw scene configuration format (not canonical)
- Supports all scene controller tracker configurations

**Prerequisites**:
- Docker installed and running
- Scene controller image available (e.g., `scenescape-controller:2026.0.0-dev`)
- Tracker configuration file

**Configuration**:
```python
from harnesses.scene_controller_harness import SceneControllerHarness
from datasets.metric_test_dataset import MetricTestDataset

# Initialize harness
harness = SceneControllerHarness()

# Configure
harness.set_scene_config(dataset.get_scene_config_raw())  # Raw format!
harness.set_custom_config({
    'container_image': 'scenescape-controller:2026.0.0-dev',
    'tracker_config_path': '/path/to/tracker-config.json'
})

# Set callback for outputs
def handle_outputs(outputs):
    for output in outputs:
        print(output)

harness.set_callback_outputs_ready(handle_outputs)

# Process inputs (batch mode)
harness.process_inputs(dataset.get_inputs())
```

**Important Notes**:
- `set_scene_config()` expects **raw dataset format**, not canonical format
- For MetricTestDataset, use `get_scene_config_raw()` instead of `get_scene_config()`
- All inputs are processed in a single container execution
- Container is automatically removed after execution

**Implementation**: [scene_controller_harness.py](scene_controller_harness.py)

## Adding New Harnesses

To add support for a new tracker deployment method:

1. **Create harness class**: Implement all abstract methods from `TrackerHarness` base class (see [../base/tracker_harness.py](../base/tracker_harness.py))
2. **Handle configuration**: Implement `set_scene_config()` and `set_custom_config()` for your tracker's needs
3. **Implement execution**: In `process_inputs()`, execute tracker and collect outputs
4. **Add callbacks**: Call `_callback_outputs_ready` with results or `_callback_on_failure` on errors
5. **Document requirements**: Update this README with prerequisites and configuration examples
6. **Create tests**: Add tests validating harness behavior

### Harness Implementation Patterns

**Batch processing** (like SceneControllerHarness):
- Consume all inputs in `process_inputs()`
- Execute tracker on complete input set
- Call callback once with all outputs

**Streaming processing** (for future harnesses):
- Accept inputs incrementally
- Call callback as outputs become available
- Support partial result collection

## Design Documentation

See [tracker-evaluation-pipeline.md](../../../../docs/design/tracker-evaluation-pipeline.md) for overall architecture and design decisions.
