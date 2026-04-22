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
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

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

### CameraProjectionHarness

**Purpose**: Project per-camera bounding-box detections to world coordinates and return results in canonical Tracker Output Format, **bypassing the full tracking pipeline**. This isolates the position error introduced by each camera's calibration.

**Mode**: **Synchronous batch processing** — processes all inputs and returns outputs.

**Key Features**:

- Runs `run_projection.py` inside a `scenescape-controller` Docker container (which already has `scene_common`, OpenCV, and open3d).
- Accepts standard scene configuration format (same as `dataset.get_scene_config()`).
- Projects bounding-box bottom-centre `(centre_x, bottom_y)` to world XY plane via `CameraPose.cameraPointToWorldPoint()`.
- Encodes output object IDs as `"{camera_id}:{object_id}"` so `CameraAccuracyEvaluator` can split them back into camera and object parts.
- Optionally persists `inputs.json` and `outputs.json` artefacts to the configured output folder.

**Prerequisites**:

- Docker installed and running
- SceneScape controller image available (e.g., `scenescape-controller:2026.1.0-dev`)

**Configuration**:

```python
from harnesses.camera_projection_harness import CameraProjectionHarness
from datasets.metric_test_dataset import MetricTestDataset

dataset = MetricTestDataset("path/to/dataset")
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

harness = CameraProjectionHarness(container_image="scenescape-controller:2026.1.0-dev")
harness.set_scene_config(dataset.get_scene_config())

outputs = list(harness.process_inputs(dataset.get_inputs()))
```

**Optional custom config keys** (pass via `set_custom_config()`):

- `container_image`: override the Docker image at runtime.
- `object_classes`: list of per-category projection settings. Each entry is a dict with:
  - `name` (str, required): category name (case-insensitive).
  - `shift_type` (int, optional, default `1`): `1` = TYPE_1 (bottom-centre), `2` = TYPE_2 (perspective-corrected point using `CameraPose.projectBounds()`).
  - `x_size` / `y_size` (float, optional, default `0.0`): physical object dimensions in metres used to push the projected point `mean([x_size, y_size]) / 2` metres away from the camera, matching `MovingObject.mapObjectDetectionToWorld()`.

  Example (also valid as YAML `harness.config.object_classes`):

  ```python
  harness.set_custom_config({
      "object_classes": [
          {"name": "person", "shift_type": 1, "x_size": 0.5, "y_size": 0.5},
          {"name": "vehicle", "shift_type": 2, "x_size": 2.0, "y_size": 4.0},
      ]
  })
  ```

  Categories not listed fall back to TYPE_1 with no size offset. The list is serialised to `params.json` and passed into the container for `run_projection.py` to read.

**Output Object ID format**: `"{camera_id}:{object_id}"` (e.g., `"Cam_x1_0:2"`).

**Implementation**: [camera_projection_harness/](camera_projection_harness/)

**Files**:

- **camera_projection_harness.py**: Main harness implementation
- **run_projection.py**: Script executed inside the container to apply `CameraPose` projection
- `__init__.py`: Module initialisation

**Tests**:

- [tests/test_camera_projection_harness.py](tests/test_camera_projection_harness.py) — 23 test cases covering initialisation, scene/custom config validation (including `object_classes`), output folder, `process_inputs()` success/failure paths, reset, and helper methods.
- [tests/test_run_projection.py](tests/test_run_projection.py) — 7 test cases covering `_build_class_map` (run without Docker). The size-offset step uses `scene_common.geometry.Line` directly so has no custom math to unit-test.

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
