# Tracker Evaluation Pipeline

The goal of this document is to explain how the [tracking evaluation strategy](../adr/0009-tracking-evaluation.md) is going to be realized.

List of base component classes:
- Tracking Dataset - data that consist of:
  - static scene and cameras configuration
  - inputs: videos and / or sequences of object detections from multiple cameras
  - ground-truth: sequences of each object location in time
  - additional context data and metadata
- Tracker Harness - an executable that:
  - consumes:
    - scene and camera configuration from dataset in canonical format
    - input videos or object detections from dataset
  - produces:
    - tracker outputs (tracks)
- Tracker Evaluator (e.g. wrapped TrackEval) - an executable that:
  - consumes:
    - tracker output from Tracker Harness
    - ground-truth from Tracking Dataset
  - produces:
    - list of metrics evaluating tracker performance

Evaluation pipeline:

DATASET ---scene and cameras configuration--> HARNESS
DATASET ---inputs--> HARNESS ---tracker outputs----> EVALUATOR
DATASET ---ground-truth---> EVALUATOR
EVALUTOR ----metrics---> RESULT

Standard data formats:
- Scene and camera configuration canonical format (defined by JSON schema) - TO BE DEFINED
- Input object detection canonical format (defined by JSON schema) - SceneScape camera detection format
- Output track canonical format (defined by JSON schema) - SceneScape track format
- Tracker Evaluator input track format (MOTChallenge CSV format assumed)

Modes of operation:
- Offline (batch) - default: whole data sequence is processed at once by each component
- Offline (streaming) - for large datasets: data is streamed between components (only part of data sequence is kept in storage while running the evaluation pipeline)
- Online (real-time) - for benchmarking in production or time-based tracker algorithms (e.g. time-chunking)

Extensibility and flexibility requirements (plug-in architecture):
- Tracking Dataset must support conversions:
  - of scene and camera configuration to canonical format
  - of object detection inputs to canonical format
  - ground-truth to Tracker Evaluator input track format
- Tracker Harness must support conversion of tracker outputs to Tracker Evaluator input track format
- Tracker Harness is not aware of

Pipeline configurability
- Dataset
  - Choice of cameras
  - Choice of time range
