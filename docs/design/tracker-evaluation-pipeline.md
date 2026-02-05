# Tracker Evaluation Pipeline

The goal of this document is to explain how the [tracking evaluation strategy](../adr/0009-tracking-evaluation.md) is going to be realized.

## Design goals

- Enable user to evaluate different tracker implementations using state-of-the-art industry-standard datasets and evaluation toolkits with minimal effort.
- Enable easy automation of evaluation and consuming metrics, including feedback loops for model training in future
- Enable quick adoption of new datasets
- Enable performance optimizations for huge datasets
- Enable extensibility

## List of base component classes:

1. Tracking Dataset - data that consist of:
   - static scene and cameras configuration
   - inputs: videos and / or sequences of object detections from multiple cameras
   - ground-truth: sequences of each object location
   - optionally additional context data and metadata
2. Tracker Harness - executes a process that:
   - consumes:
     - scene and camera configuration from dataset in canonical format
     - input videos or object detections from dataset in canonical format
     - specific configuration dependent on tracker type (e.g. tracker configuration, models used in video pipelines)
   - produces:
     - tracker outputs (tracks) in canonical format
3. Tracker Evaluator (e.g. wrapped TrackEval) - executes a process that:
   - consumes:
     - tracker output from Tracker Harness
     - ground-truth from Tracking Dataset
   - produces:
     - metrics & plots evaluating tracker performance

## Extensibility and flexibility requirements (Plug-in architecture):

1. Extensibility (support for specific datasets, trackers etc.) is accomplished by implementing Components' Base Class interfaces in Python language
2. Composability: components in the pipeline can be plugged-in and used together by exposing well-defined interfaces that enable to integrate them in the pipeline
3. Encapsulation and decoupling:
   - Components are decoupled. Each component owns and encapsulates the logic and data needed to accomplish its task, e.g. harness may internally use docker compose and broker to run the tracker, dataset may use HuggingFace Dataset library, but these are implementation details hidden from the pipeline user
   - Data is exchanged in canonical formats
   - Conversions that must be supported by the component implementations:
     - dataset scene and camera configuration to canonical format - part of Tracking Dataset implementation
     - dataset object detection inputs to canonical format - part of Tracking Dataset implementation
     - dataset ground-truth to Tracker Evaluator input track format - part of Tracking Dataset implementation
     - track canonical format to Tracker Evaluator input track format - part of Tracker Evaluator implementation
4. In future discoverability interface will be implemented in each component (e.g. what modes of operation are supported)

## Evaluation pipeline:

```mermaid
flowchart LR
    Dataset[Tracking Dataset]
    Harness[Tracker Harness]
    Evaluator[Tracker Evaluator]
    Results[Evaluation Results]

    Dataset -->|scene & cameras config| Harness
    Dataset -->|inputs| Harness
    Harness -->|tracker outputs| Evaluator
    Dataset -->|ground-truth| Evaluator
    Evaluator -->|metrics| Results
```

## Standard data formats:

- Scene and camera configuration canonical format. Defined by JSON schema: tracker/schema/scene.schema.json
- Input object detection canonical format. Defined by JSON schema: tracker/schema/camera-data.schema.json
- Output track canonical format. Defined by JSON schema: tracker/schema/scene-data.schema.json
- Tracker Evaluator input track format (MOTChallenge CSV format is assumed in Phase 1)

### Format Conversion Utilities

Dataset implementations use format conversion utilities to transform data between canonical JSON formats and evaluator input formats. The utilities provide:

- **JSON→JSON conversion**: Pointer-based mapping (RFC 6901) for schema transformations with **strict validation** (all fields must exist)
- **JSON→CSV conversion**: Column mapping with **lenient validation** (missing fields become null/NaN)
- **CSV→DataFrame reading**: Dask-based CSV parsing for efficiency

**Libraries used**:
- `python-rapidjson`: Fast JSON serialization/deserialization
- `jsonpointer`: RFC 6901 JSON pointer support for nested field access
- `dask`: Efficient CSV reading and writing, especially for large datasets

**Validation behavior**:
- Schema transformations (JSON→JSON): Strict - raises exception on missing fields
- Data export (JSON→CSV): Lenient - sets missing fields to null to handle incomplete tracker outputs

### Tracker Evaluator Input Track Format (MOTChallenge 3D CSV)

The canonical CSV format for ground-truth and tracker output data follows the MOTChallenge 3D format.

**Format**: Comma-separated values, one detection per line, no header row.

**Column specification**:

| Column | Name       | Type  | Description                                      |
|--------|------------|-------|--------------------------------------------------|
| 1      | frame      | int   | Frame number (1-indexed)                         |
| 2      | id         | int   | Object/track ID (-1 for detections without ID)   |
| 3      | x          | float | 3D position X coordinate (meters, world frame)   |
| 4      | y          | float | 3D position Y coordinate (meters, world frame)   |
| 5      | z          | float | 3D position Z coordinate (meters, world frame)   |
| 6      | conf       | float | Confidence score (0-1, or 0 if not available)    |
| 7      | class      | int   | Object class ID (1=pedestrian, 2=vehicle, etc.)  |
| 8      | visibility | int   | Visibility flag (1=visible, 0=occluded)          |

**Example**:
```csv
1,1,12.35,4.21,1.70,1.0,1,1
2,1,12.40,4.25,1.70,1.0,1,1
3,1,12.48,4.32,1.70,1.0,1,1
1,2,5.10,8.30,1.65,0.95,1,1
2,2,5.12,8.35,1.65,0.98,1,1
```

**Notes**:
- Frame numbers are 1-indexed (first frame = 1)
- Object IDs must be consistent across frames for the same tracked object
- World coordinates (x, y, z) are in meters in the scene's coordinate system
- For ground-plane constrained tracking, z is typically 0 or a fixed height
- Confidence and visibility may be set to default values (1.0 and 1) if not available

## Modes of operation:

Default mode (the only one supported in Phase 1):
- Offline (Batch) - default: whole data sequence is processed at once by each component and stored as a complete list in memory or filesystem

Future modes:
- Streaming - for large datasets: data is streamed between components (only part of data sequence is kept in storage while running the evaluation pipeline)
- Real-time - for benchmarking in production or time-based tracker algorithms (e.g. time-chunking)

Notes:
1. A specific harness / dataset implementation may support only a subset of models
2. For now it is assumed that Tracker Evaluator supports only offline mode.

## Pipeline configurability:

1. Declarative: user declares desired pipeline state: components implementation, mode of operation, configuration for each component in YAML file
2. User declares components implementation to be used as a path to Python class implementing base component interface, which is a single entry-point for using the component
3. Mode of operation
4. Dataset configuration
   - Choice of scene
   - Choice of cameras for the scene
   - Choice of time range for the input sequences
5. Harness configuration
   - Tracker specific configuration, e.g. tracker container image and tag
6. Evaluator
   - Set of metrics

## Minimal Interfaces of Component Classes (as of Phase 1)

### Tracking Dataset

Implementation of the component class must implement the following functions.

- SetScene
  - argument: scene (optional)
  - returns: self
  - on error: raises exception
- SetCameras
  - argument: list of camera IDs (optional)
  - returns: self
  - on error: raises exception
- SetTimeRange
  - argument: start, end timestamp (optional)
  - returns: self
  - on error: raises exception
- SetCameraFps
  - argument: camera_fps (float)
  - returns: self
  - on error: raises exception
- SetCustomConfig
  - argument: config (dict)
  - returns: self
  - on error: raises exception
- GetInputs
  - argument: camera (optional)
  - returns: iterative list of inputs in canonical format
  - on error: raises exception
- GetGroundTruth
  - argument: none
  - returns: path to ground truth file in Tracker Evaluator input track format (e.g., MOTChallenge CSV)
  - on error: raises exception
- Reset: resets state to initial
  - argument: none
  - returns: self

Future extensions of the interface will be driven by the need of adopting specific datasets and tracking algorithms, e.g. the interface could support division into training and validation sets.

### Tracker Harness

Implementation of the component class must implement the following functions.

- SetCustomConfig
  - argument: custom dict
  - returns: self
  - on error: raises exception
- SetCallbackOutputsReady
  - argument: callback function that will be executed when outputs are ready
    - argument: iterative list of tracker outputs in canonical format
    - returns: nothing
  - returns: self
- SetCallbackOnFailure
  - argument: callback function that will be executed when failure occurs
    - argument: timestamp, error string
    - returns: nothing
- ProcessInputs
  - argument: iterative list of inputs in canonical format
  - returns: self
  - on error: raises exception
- Reset: resets state to initial
  - argument: none
  - returns: self

Future extensions of the interface will be driven by the need of evaluating specific implementations, e.g. black-box tests of production service vs experimental tracker implementation.

### Tracker Evaluator

Implementation of the component class must implement the following functions.

- ConfigureMetrics
  - argument: list of metrics to be evaluated
  - returns: self
  - on error: raises exception
- SetResultFolder
  - arguments: path to folder where results are to be stored
  - returns: self
- ProcessTrackerOutputs
  - arguments:
    - iterative list of tracker outputs in canonical format
    - iterative list of inputs in Tracker Evaluator input track format
  - returns: self
  - on error: raises exception
- EvaluateMetrics
  - arguments: none
  - returns: dict { <metric name>: <metric value> }
- Reset: resets state to initial
  - argument: none
  - returns: self

## Tracker Evaluation Pipeline Engine Module

The highest level component in the design is the Pipeline Engine module, which implements PipelineEngine class.

The module should also contain short main() function that will run if the module is executed as a Python script.
The only argument for the script should be the path to configuration file.

PipelineEngine class exposes the following methods:

### LoadConfiguration

The only argument for the function should be the path to configuration file.

What is does:
  1. Loads and parses a single YAML configuration file
  2. Imports Dataset, Harness and Evaluator modules from paths provided in the configuration file.
  3. Creates instances of the imported Component Classes.
  4. Configures each of the instances with the component parameters provided in the configuration file.
  5. Performs capability discovery for each of the component instances, if necessary for proper pipeline configuration.

Raises exception on error.

### Run

Runs the tracker on the dataset.
No input arguments.
Raises exception on error.

### Evaluate

Evaluates metrics based on the dataset ground-truth.
No input arguments.
Raises exception on error.
Returns: dict { <metric name>: <metric value> }

## Open Questions

### Component Implementation Approach

**Question**: Whether to use SimpleNamespaces, class inheritance or other Python mechanisms to implement component interfaces.

**Decision**: Use **Abstract Base Classes (ABC)** with inheritance.

**Justification**:

- **Type safety**: ABC enforces interface contracts at instantiation time, preventing runtime errors from missing method implementations
- **IDE support**: Provides better autocomplete, type checking, and refactoring capabilities
- **Self-documenting**: Abstract methods clearly define the contract that implementations must fulfill
- **Consistency**: Aligns with existing SceneScape codebase patterns (e.g., modules in `scene_common`)
- **Extensibility**: Allows adding default implementations and shared utility methods in base classes
- **Best practice**: Industry-standard approach for plugin architectures in Python

**Implementation pattern**:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class TrackingDataset(ABC):
  """Base class for tracking dataset implementations."""

  @abstractmethod
  def set_scene(self, scene: Optional[str] = None) -> 'TrackingDataset':
    """Set the scene to use from the dataset.

    Args:
      scene: Scene identifier (optional)

    Returns:
      Self for method chaining

    Raises:
      Exception on error
    """
    pass
```
