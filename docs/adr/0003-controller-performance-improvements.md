# ADR 3: Controller Performance Improvements (Parent ADR)

- **Author(s)**: [Tomasz Dorau, ...](https://github.com/tdorauintc)
- **Date**: 2025-10-10
- **Status**: `Proposed`

## Context

SceneScape's requirement for the next releases is to support real-time tracking of 100-300 objects with 4 cameras at 15 FPS each. The short-term requirement is tracking up to 100 objects of 1 category (people). The long-term requirement is to track 300 objects across multiple categories.

Performance test results show that these requirements cannot be met with the current controller implementation, hence performance optimizations are necessary.

This ADR aggregates and summarizes all architectural decisions to improve controller performance at a high level. Each specific decision is discussed in a separate child ADR document.

## Decision

We decided to take several independent approaches that address the problem:

- Short term:
    1. Use time-chunking (ADR TBD)
- Long term:
    1. Spatial indexing to determine which detections are independent of each other and which actually need to be handled together (ADR TBD)
    2. Rewrite controller code in C++

## Alternatives Considered

1. Batch the camera inference results into a single message.
   - Pros: TBD
   - Cons:
     - It is difficult to implement when the FPS of the cameras differs.
     - It is difficult when using camera + lidar + radar.
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

- Benefit 1
- Benefit 2

### Negative

- Drawback 1
- Drawback 2

## References

- Related design doc link
