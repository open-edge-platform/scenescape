# ADR 3: Scaling Controller Performance to 300 Objects

- **Author(s)**: [Sarat Poluri](https://github.com/saratpoluri), [Tomasz Dorau](https://github.com/tdorauintc), [Józef Daniecki](https://github.com/jdanieck), [Łukasz Talarczyk](https://github.com/ltalarcz)
- **Date**: 2025-10-13
- **Status**: `Accepted`

## Context

SceneScape's requirement for the next releases is to support real-time tracking of 100-300 objects with 4 cameras at 15 FPS each. The short-term requirement is tracking up to 100 objects of 1 category (people). The long-term requirement is to track at least 300 objects across multiple categories.

Performance test results show that these requirements cannot be met with the current controller implementation, hence performance optimizations are necessary to address the current bottlenecks.

This ADR aggregates and summarizes architectural decisions to improve controller performance at a high level. Specific decisions are discussed in separate design documents that are referenced at the end of this document.

## Decision

We decided to take several independent approaches that address the problem:

- **Short-term approach** that addresses multiple-camera bottleneck:
  1. Use **time-chunking**: the tracker runs at a specific rate and processes detections from different cameras within its time window in one chunk. If multiple frames from a single camera fall within the time window then only the latest frame is included in the chunk.

- **Long-term approaches** that address the bottlenecks of high object count and multiple object categories:
  1. **Spatial indexing** to determine which detections are independent of each other and which actually need to be handled together.
  2. Rewrite controller code in C++.

## Alternatives Considered

1. **Batch the camera inference results into a single message.**
   - Pros:
     - If handled entirely at VA (Visual Analytics), it would not impose any overhead on the controller.
     - Detections from all cameras are handled together in a single call to the tracker.
   - Cons:
     - Difficult to implement with multiple cameras running at different FPS.
     - Difficult when using multiple sensor types, e.g., camera + lidar + radar.
     - The aggregation of metadata across pipelines is not supported by the current visual analytics pipeline framework.

2. **Scene controller applying back pressure on inferencing.**
   - Pros: None identified.
   - Cons:
     - Increased complexity due to additional interactions and coupling with VA pipeline service.
     - Lack of significant advantages over existing solution with dropping frames in controller.

3. **Frame prioritization** - A frame that is dense with information should take precedence over a frame where nothing is happening.
   - Pros: Can reduce some load on controller and is relatively easy to implement.
   - Cons: Low ROI since it does not address the critical bottlenecks.

4. **Leverage per-camera tracking information** to lighten the load on the controller. Instead of pure object detection, use a detection+tracker model and leverage that information in the controller.
   - Pros: The responsibility for doing the actual tracking is taken off from the controller, which performs only the fusion and maintenance of the tracks.
   - Cons: Time needed for path-finding and implementing new methods.

## Consequences

### Positive

- Time chunking addresses use cases where the cumulative FPS increases with multiple cameras by processing detections aggregated from multiple sensors in a single call to the tracker at a lower rate.
- Time chunking can bring immediate performance improvements for multiple cameras in predict and update steps of Kalman Filter estimators without the need to change the tracker implementation or make adjustments in the data ingestion from sensors/cameras.
- Leveraging spatial indexing can help avoid unnecessary processing for large scenes with multiple non-overlapping cameras in both controller front-end and tracking.
- Rewriting the controller code in C++ will enable true parallelism (which is blocked by GIL in Python) for multiple object categories and maximize efficiency while minimizing overhead from language boundaries.

### Negative

- Time chunking may introduce some latency and potential for missed frames, which can be controlled by the user through configuration to optimize for their specific requirements.
- Enabling spatial indexing requires adding camera visibility awareness in the tracker, which may introduce some overhead for smaller scenes with overlapping cameras.
- Maintaining controller code in C++ will require specific expertise in the team and make it more difficult to onboard new team members compared to Python implementation.

## References

**Design specification documents:**

- Time chunking design document [link TBD]
- Spatial indexing design document [link TBD]
