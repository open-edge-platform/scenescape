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

**Purpose**: Execute tracker inside Scenescape scene controller Docker container.

**Mode**: **Synchronous batch processing** - processes all inputs and returns outputs.

**Key Features**:

- Runs tracker in isolated Docker container
- Accepts raw scene configuration format (not canonical)
- Supports all scene controller tracker configurations

**Prerequisites**:

- Docker installed and running
- Scene controller image available (e.g., `intel/scenescape-controller:2026.0.0-dev`)
- Tracker configuration file

**Configuration**:

```python
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from harnesses.scene_controller_harness import SceneControllerHarness
from datasets.unity_dataset import UnityDataset

# Initialize dataset
dataset = UnityDataset("path/to/dataset")
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

# Initialize harness with container image
harness = SceneControllerHarness(container_image='intel/scenescape-controller:2026.0.0-dev')

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

**Scenescape API Usage**:

The `run_tracker.py` script executes inside the container and calls the following Scenescape modules:

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
- Scenescape controller image available (e.g., `intel/scenescape-controller:2026.1.0-dev`)

**Configuration**:

```python
from harnesses.camera_projection_harness import CameraProjectionHarness
from datasets.unity_dataset import UnityDataset

dataset = UnityDataset("path/to/dataset")
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

harness = CameraProjectionHarness(container_image="intel/scenescape-controller:2026.1.0-dev")
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

### BlackBoxHarness

**Purpose**: Black-box end-to-end tracker evaluation over live MQTT messages without any dependency on internal Scenescape Python APIs.

**Mode**: **Synchronous batch processing** — processes all inputs and returns outputs.

**Key Features**:

- Starts an `eclipse-mosquitto` broker container and the tracker container on an isolated Docker network (`black_box_harness_{run_id}`); both containers and the network are removed after the run.
- Publishes each input frame to `scenescape/data/camera/{camera_id}` and collects tracker outputs from `scenescape/data/scene/{scene_id}/+`.
- Publishes input frames paced by wall-clock delays derived from the data timestamps, reproducing the original capture cadence. `maxlag`/`max_lag_s=1e15` only suppresses lag-rejection in the tracker — it does **not** replace pacing, which is required for the time-chunk scheduler to fire at the correct rate.
- Persists `inputs.json` and `outputs.json` to the output folder when `set_output_folder()` is called, creating the directory automatically if it does not exist.
- Copies the source tracker configuration file into a `config/` subfolder of the output folder (for both container types), preserving the original filename, so each run records the config it was given. For the Tracker Service container the effective `config.json` is derived from this file by the harness (injecting MQTT/Manager endpoints, `max_lag_s=1e15`, and optional OTLP/metrics settings), so the copy captures the source configuration rather than the fully-resolved runtime config.
- Supports both **Controller** (`intel/scenescape-controller`) and **Tracker Service** (`intel/scenescape-tracker`) container types, set explicitly via the required `container_type` config key.
- Runs a **Mock Manager REST API** (`mock_manager.py`) on the Docker host so both container types can load scene configuration without a real Manager deployment.

**Prerequisites**:

- Docker installed and running
- `eclipse-mosquitto` image available (or override `broker_image`)
- Tracker container image available (e.g., `intel/scenescape-controller:2026.1.0-dev` or `intel/scenescape-tracker:2026.1.0-dev`)
- `paho-mqtt>=1.6.1` installed (included in `requirements.txt`)

**Configuration**:

```python
from harnesses.black_box_harness import BlackBoxHarness
from datasets.unity_dataset import UnityDataset

dataset = UnityDataset("path/to/dataset")
dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)

harness = BlackBoxHarness(container_image="intel/scenescape-controller:2026.1.0-dev")
harness.set_scene_config(dataset.get_scene_config())
harness.set_custom_config({
    "tracker_config_path": "/path/to/tracker-config.json",
    "container_type": "controller",  # required: "controller" or "tracker"
    "broker_image": "eclipse-mosquitto:2.0.22",
    # Optional overrides:
    # "drain_timeout": 5.0,            # Seconds to wait after last frame
    # "scene_id": "my-scene-uid",      # Override UID from scene config
    # Optional observability (capture OTLP metrics via an OTEL Collector sidecar):
    # "enable_metrics": True,
    # "metrics_collector_image": "otel/opentelemetry-collector-contrib:0.155.0",
})

outputs = list(harness.process_inputs(dataset.get_inputs()))
```

**`set_custom_config()` keys**:

| Key                   | Required | Default | Description                                                          |
| --------------------- | -------- | ------- | -------------------------------------------------------------------- |
| `tracker_config_path` | Yes      | —       | Path to tracker config JSON, mounted into the tracker container      |
| `broker_image`        | Yes      | —       | Docker image for the MQTT broker (e.g. `"eclipse-mosquitto:2.0.22"`) |
| `container_type`      | Yes      | —       | `"controller"` or `"tracker"`                                        |

| `drain_timeout` | No | `5.0` | Seconds to wait for remaining tracker outputs after the last frame |
| `scene_id` | No | derived from scene config `uid` | Override the MQTT topic scene ID |
| `startup_wait_s` | No | `2.0` | Seconds to wait after container starts before publishing frames |
| `enable_metrics` | No | `false` | Run an OTEL Collector sidecar to capture tracker/controller OTLP metrics |
| `metrics_collector_image` | When `enable_metrics` | — | OTEL Collector image (e.g. `"otel/opentelemetry-collector-contrib:0.155.0"`) |
| `metrics_export_interval_s` | No | `2` | Metrics export interval in seconds |
| `metrics_otlp_port` | No | `4317` | OTLP/gRPC port the collector listens on |

**Observability (optional)**:

When `enable_metrics` is set, the harness starts an OpenTelemetry Collector container on the
run's Docker network. The tracker/controller container is configured to push its OTLP/gRPC
metrics to the collector, which writes them to a file via the `file` exporter. After the run
the harness aggregates the captured metrics and writes `metrics_summary.txt` to the output
folder with, per metric:

- **Latency histograms** (e.g. `tracker.mqtt.latency`, `scenescape_controller_mqtt_handler_duration`): `count`, `avg`, `min`, `max`. Median is omitted because only bucketed counts are exported.
- **Counters** (e.g. `tracker.mqtt.messages`): cumulative `total` plus the per-export delta `avg` / `min` / `max` / `median`.
- **Gauges** (e.g. `tracker.tracks.active`): `avg` / `min` / `max` / `median` over all observed values.

After writing the summary, the harness verifies how many frames were dropped (summing the
`scenescape_controller_mqtt_messages_dropped` and `tracker.mqtt.dropped` counters), prints the
count and ratio, and emits a `WARNING` when the dropped-to-output-frame ratio exceeds 1%.
The aggregated values are also available programmatically via
`metrics_recorder.collect_metric_values()` and `metrics_recorder.check_dropped_frames()`.

Enabling metrics adds a few seconds to each run so the controller's periodic export and the
tracker's shutdown flush are captured before teardown. The collector image is pulled on first
use.

**MQTT Topics**:

- Input (publish): `scenescape/data/camera/{camera_id}`
- Output (subscribe): `scenescape/data/scene/{scene_id}/+`

**Mock Manager REST API**:

Both container types call a Manager REST API to load scene configuration on startup.
The harness starts `mock_manager.py` as a thread on the Docker host and registers it via
`--add-host` so containers can reach it at `http://<manager_hostname>:8888/api/v1`.

Endpoints served:

| Method | Path                   | Description                                                  |
| ------ | ---------------------- | ------------------------------------------------------------ |
| POST   | `/api/v1/auth`         | Returns `{"token": "mock"}` — accepts any credentials        |
| GET    | `/api/v1/scenes`       | Returns the full scene with cameras and computed extrinsics  |
| GET    | `/api/v1/scenes/child` | Returns `{"results": []}` (no child scenes)                  |
| GET    | `/api/v1/assets`       | Returns `{"results": []}` (no assets)                        |
| GET    | `/api/v1/camera/<uid>` | Returns per-camera data including calibration and extrinsics |
| POST   | `/api/v1/camera/<uid>` | Accepts calibration updates (no-op — not persisted)          |

Camera extrinsics (`translation`, `rotation`, `scale`) are computed from the dataset's
`camera points` / `map points` using the same logic as production:
`PointCorrespondenceTransform._calculatePoseMat()` in `scene_common/transform.py`,
including distortion coefficients, coplanarity check, and `_poseMatToPose()` scale extraction.

**Tracker Service auth file**:

The Tracker Service reads a JSON auth file at startup (path set via `scenes.manager.auth_path`
in its config). The file must contain `"user"` and `"password"` fields
(validated by `api_scene_loader.cpp`). The harness writes `{"user": "harness", "password": "harness"}`.

**Implementation**: [black_box_harness/](black_box_harness/)

**Files**:

- **black_box_harness.py**: Main harness implementation — Docker orchestration, MQTT publishing/collecting, timestamp pacing
- **mock_manager.py**: Minimal Manager REST API server — extrinsics computation, scene/camera endpoints
- **metrics_recorder.py**: Parses OTEL Collector output, writes `metrics_summary.txt`, and exposes `collect_metric_values()` / `check_dropped_frames()`
- `__init__.py`: Module initialisation

**Tests**:

- [tests/test_black_box_harness.py](tests/test_black_box_harness.py) — 56 test cases covering initialisation, config validation, timestamp pacing, wall-clock frame pacing (time-chunk scheduler correctness), full orchestration flow (Docker and paho fully mocked), `outputs.json` persistence to new nested directories, and Tracker Service auth file `user`/`password` fields.
- [tests/test_mock_manager.py](tests/test_mock_manager.py) — 42 test cases covering `_distortion_to_array()` (None/list/dict inputs, 14-key mapping), coplanarity helpers, `_pose_mat_to_extrinsics()` (identity, translation, scale, JSON serialization), `_compute_extrinsics()` (happy path, insufficient points, 2-D map points, distortion dict), `_build_rest_scene()` structure and JSON serializability, and all HTTP endpoints via a real ephemeral HTTPServer.

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
