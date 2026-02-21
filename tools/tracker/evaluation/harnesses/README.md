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

**Mode**: **Synchronous batch processing** - processes all inputs and returns outputs.

**Key Features**:

- Runs tracker in isolated Docker container
- Accepts raw scene configuration format (not canonical)
- Supports all scene controller tracker configurations

**Prerequisites**:

- Docker installed and running
- Scene controller image available (e.g., `scenescape-controller:2026.0.0-dev`)
- Tracker configuration file

**Configuration**:

```python
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from harnesses.scene_controller_harness import SceneControllerHarness
from datasets.metric_test_dataset import MetricTestDataset

# Initialize dataset
dataset = MetricTestDataset("path/to/dataset")
dataset.set_cameras(["x1", "x2"]).set_camera_fps(30)

# Initialize harness with container image
harness = SceneControllerHarness(container_image='scenescape-controller:2026.0.0-dev')

# Configure harness
harness.set_scene_config(dataset.get_scene_config())  # Dataset-specific format
harness.set_custom_config({
    'tracker_config_path': '/path/to/tracker-config.json'
})

# Process inputs synchronously - returns outputs
outputs = harness.process_inputs(dataset.get_inputs())

# Use outputs
for output in outputs:
    print(output)
```

**Important Notes**:

- Constructor requires scene controller Docker image
- `set_scene_config()` accepts scene configuration in dataset-specific format (from `dataset.get_scene_config()`)
- `set_custom_config()` only requires `tracker_config_path` - path to tracker configuration JSON file
- All inputs are processed in a single container execution
- Container is automatically removed after execution

**Implementation**: [scene_controller_harness/](scene_controller_harness/)

**Files**:

- **scene_controller_harness.py**: Main harness implementation
- **run_tracker.py**: Script executed inside the container to run the tracker
- \***\*init**.py\*\*: Module initialization

**SceneScape API Usage**:

The `run_tracker.py` script executes inside the container and calls the following SceneScape modules:

_From `scene_common`:_

- `scene_common.scenescape.SceneLoader`: Load scene configuration from JSON
- `scene_common.camera.Camera`: Create camera objects with intrinsics and extrinsics
- `scene_common.geometry.Region`: Create region objects for spatial zones
- `scene_common.geometry.Tripwire`: Create tripwire objects for crossing detection

_From `controller`:_

- `controller.scene.Scene`: Core scene and tracker management
  - `Scene.__init__()`: Initialize scene with tracker configuration parameters
  - `scene.processCameraData()`: Feed detection data to tracker
  - `scene.tracker.currentObjects()`: Get current tracked objects by category
  - `scene.tracker.join()`: Finalize tracker processing
  - `scene.cameras`, `scene.regions`, `scene.tripwires`: Scene entity collections
  - `scene.areCoordinatesInPixels()`, `scene.mapPixelsToMetric()`: Coordinate system utilities
- `controller.detections_builder.buildDetectionsList`: Format tracked objects into detection lists

The tracker runs with configurable timing modes:

- **Time chunking enabled**: Processes detections at configured FPS rate with synchronized output
- **Time chunking disabled**: Processes detections with fixed 25ms intervals to speed up execution

## Adding New Harnesses

To add support for a new tracker deployment method:

1. **Create harness class**: Implement all abstract methods from `TrackerHarness` base class (see [../base/tracker_harness.py](../base/tracker_harness.py))
2. **Handle configuration**: Implement `set_scene_config()` and `set_custom_config()` for your tracker's needs
3. **Implement execution**: `process_inputs()` - synchronous mode: execute tracker and return outputs
4. **Document requirements**: Update this README with prerequisites and configuration examples
5. **Create tests**: Add tests validating harness behavior

### Implementation Patterns

**Synchronous batch processing** (required):

- Method: `process_inputs(inputs) -> Iterator[outputs]`
- Consume all inputs and execute tracker on complete input set
- Return all outputs as iterator
- Use for batch processing, testing, simple evaluation pipelines

## Design Documentation

See [tracker-evaluation-pipeline.md](../../../../docs/design/tracker-evaluation-pipeline.md) for overall architecture and design decisions.
