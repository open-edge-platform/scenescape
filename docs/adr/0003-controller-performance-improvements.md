# ADR 3: Controller Performance Improvements (Parent ADR)

- **Author(s)**: [Sarat Poluri](), [Jozef Daniecki](), [Tomasz Dorau](https://github.com/tdorauintc), [Lukasz Talarczyk]()
- **Date**: 2025-10-10
- **Status**: `Proposed`

## Context

SceneScape's requirement for the next releases is to support real-time tracking of 100-300 objects with 4 cameras at 15 FPS each. The short-term requirement is tracking up to 100 objects of 1 category (people). The long-term requirement is to track at least 300 objects across multiple categories.

Performance test results show that these requirements cannot be met with the current controller implementation, hence performance optimizations are necessary to address the current bottlenecks.

This ADR aggregates and summarizes architectural decisions to improve controller performance at a high level. Specific decisions are discussed in separate child ADR documents that are referenced at the end of this document.

## Decision

We decided to take several independent approaches that address the problem:

- Short term approach that addresses multiple-camera bottleneck:
    1. Use time-chunking: the tracker is run at a specific rate and all detections from its time window are gathered and handled together in the tracker.
- Long term approaches that address the bottlenecks of high object count and multiple object categories:
    1. Spatial indexing to determine which detections are independent of each other and which actually need to be handled together.
    2. Rewrite controller code in C++.

## Alternatives Considered

1. Batch the camera inference results into a single message.
   - Pros:
     - If it was handled entirely at VA then it would not impose any overhead on the controller.
     - Detections from all cameras are handled together in a single call to the tracker.
   - Cons:
     - It is difficult to implement with multiple cameras running at different FPS.
     - It is difficult when using multiple sensor types, e.g. camera + lidar + radar.
     - The aggregation of metadata across pipelines is not supported by the current visual analytics pipeline framework.
2. Scene controller applying back pressure on inferencing.
   - Pros: TBD
   - Cons: TBD
3. Frame prioritization - A frame that is dense with information should take precedence over a frame where nothing is happening.
   - Pros: TBD
   - Cons: TBD
4. Leverage per-camera tracking information to lighten the load on the controller. Instead of pure object detection, use a detection+tracker model and leverage that information in the controller.
   - Pros: TBD
   - Cons: TBD

## Consequences

### Positive

- Time chunking addresses use cases where the cumulative FPS increases with multiple cameras by processing detections aggregated from multiple sensors in a single call to tracker at a lower rate.
- Time chunking can bring immediate performance improvements for multiple cameras in predict and update steps of Kalman Filter estimators w/o need to change the tracker implementation or adjustments in the data ingestion from sensors / cameras.
- Leveraging spatial indexing can help to avoid unnecessary processing for large scenes multiple non-overlapping cameras in both controller front-end and tracking.
- Rewriting the controller code in C++ will enable true parallelism (which is blocked by GIL in Python) for multiple object categories and maximize efficiency while minimizing overhead from language boundaries.

### Negative

- Time chunking may introduce some latency and potential for missed frames, which can be controlled by the user through configurability to optimize for their specific requirements.
- Enabling spatial indexing requires adding camera visibility awareness in the tracker which may introduce some overhead for smaller scenes with overlapping cameras.
- Maintaining controller code in C++ will require specific expertise in the team and make it more difficult to ramp up for new team members than with Python implementation.

## References

Child ADR documents:
- Time chunking ADR [link TBD].
- Spatial indexing ADR [link TBD].
