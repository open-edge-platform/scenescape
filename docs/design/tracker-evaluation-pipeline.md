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

1. Extensibility (support for specific datasets, trackers etc.) is accomplished by implementing Components' Base Classe interfaces in Python language
2. Composability: components in the pipeline can be plugged-in and used together by exposing well-defined interfaces that enable to integrate them in the pipeline
3. Encapsulation and decoupling:
  - Components are decoupled. Each component owns and encapsulates logic and data needed to accomplish its task, e.g. harness may use internally docker compose and broker to run the tracker, dataset may use HuggingFace Dataset library, but those are implementation details hidden from the pipeline user
  - Data is exchanged in canonical formats
  - Conversions that must be supported by the component implementations:
    - dataset scene and camera configuration to canonical format - part of Tracking Dataset implementation
    - dataset object detection inputs to canonical format - part of Tracking Dataset implementation
    - dataset ground-truth to Tracker Evaluator input track format - part of Tracking Dataset implementation
    - track canonical format to Tracker Evaluator input track format - part of Tracker Evaluator implementation
4. In future discoverability interface will be implemented in each component (e.g. what modes of operation are supported)

## Evaluation pipeline:

TODO: make this diagram in Mermaid

DATASET ---scene and cameras configuration--> HARNESS
DATASET ---inputs--> HARNESS ---tracker outputs----> EVALUATOR
DATASET ---ground-truth---> EVALUATOR
EVALUTOR ----metrics---> EVALUTION RESULTS

## Standard data formats:

- Scene and camera configuration canonical format (defined by JSON schema) - TO BE DEFINED
- Input object detection canonical format (defined by JSON schema) - SceneScape camera detection format
- Output track canonical format (defined by JSON schema) - SceneScape track format
- Tracker Evaluator input track format (MOTChallenge CSV format is assumed in Phase 1)

## Modes of operation:

Default mode (the only one supported in Phase 1):
- Offline (Batch) - default: whole data sequence is processed at once by each component and stored as a complete list in memory or filesystem

Future modes:
- Streaming - for large datasets: data is streamed between components (only part of data sequence is kept in storage while running the evaluation pipeline)
- Real-time - for benchmarking in production or time-based tracker algorithms (e.g. time-chunking)

Note: a harness / dataset may support only a subset of models

## Pipeline configurability:

- Declarative: user declares desired pipeline state: components implementation, mode of operation, configuration for each component in YAML file
- User declares components implementation to be used as a path to Python class implementing base component interface, which is a single entry-point for using the component
- Mode of operation
- Dataset configuration
  - Choice of scene
  - Choice of cameras for the scene
  - Choice of time range for the input sequences
- Harness
  - Tracker specific configuration
- Evaluator
  - Set of metrics

## Minimal Interfaces of Component Classes (as of Phase 1)

### Tracking Dataset

Implementation of the component class must implement the following functions.

- SetScene
  - argument: scene
  - returns: self
  - on error: raises exception
- SetCameras
  - argument: list of camera IDs
  - returns: self
  - on error: raises exception
- SetTimeRange
  - argument: start, end timestamp
  - returns: self
  - on error: raises exception
- GetInputs
  - argument: camera (optional)
  - returns: iterative list of inputs in canonical format
  - on error: raises exception
- GetGroundTruthInputs
  - argument: none
  - returns: iterative list of inputs in Tracker Evaluator input track format
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
  - arguments: list of metrics to be evaluated
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

## Open Questions

- whether to use SimpleNamespaces, class inheritance or other Python mechanisms to accomplish the goals
