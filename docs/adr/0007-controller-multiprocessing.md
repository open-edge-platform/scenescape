# ADR 7: Controller Multiprocessing

- **Author(s)**: [Mohammed Sufiyan Saqib](https://github.com/mohammed-saqib), [Sarat Poluri](https://github.com/saratpoluri)
- **Date**: 2026-05-12
- **Status**: `Accepted`
- **Supersedes**: N/A (replaces draft titled “Controller Multiprocessing and Scene-Aware Time Chunking”; scene-aware chunking is out of scope for this decision)

## Context

Controller throughput and reliability degrade when all work is performed on the MQTT callback thread. Under multi-camera load this causes:

- callback-thread blocking (tracking/HTTP/publish)
- stale frame backlog
- weak isolation when a tracker worker crashes

Existing timer-based time-chunking ([ADR 3](0003-scaling-controller-performance.md)) already batches detections in the tracker path. This ADR covers controller-level process isolation and admission control so the MQTT callback stays light and scenes do not share a single worker fate.

## Decision

We will use **per-scene multiprocessing in `SceneController`**:

- route each scene to a dedicated `ProcessPoolExecutor(max_workers=1)`,
- keep only the latest frame per camera (overwrite semantics),
- apply admission control with an in-flight semaphore,
- automatically recreate broken worker pools.

**Out of scope for this ADR:** scene-aware time-chunking (grouping by `(category, scene_id, camera_id)`, event-driven complete-scene dispatch, hybrid timer fallback, and cache-based expected-camera-count resolution for that path). Tracker time-chunking remains the existing timer-only design from ADR 3 (`time_chunking_enabled` / `time_chunking_interval_milliseconds`).

## Alternatives Considered

- Keep single-threaded callback-thread pipeline: rejected due to head-of-line blocking.
- Global worker pool without scene affinity: rejected due to poorer isolation and harder fairness reasoning.
- Scene-aware / hybrid time-chunking in the tracker path: deferred — not implemented on this branch; adds scheduling and cache-lookup complexity beyond the multiprocessing goal. Existing timer-only time-chunking is retained.

## Consequences

### Positive

- Better throughput isolation between scenes.
- Freshest-frame processing under bursty camera inputs via per-camera overwrite buffering.
- Crash recovery scoped to the affected scene worker.
- MQTT callback path stays short; heavy work runs in scene workers.

### Negative

- Higher implementation complexity (worker lifecycle and coordination).
- Additional memory/process overhead due to per-scene executors.
- More tuning surface (`CONTROLLER_MAX_WORKERS`, `CONTROLLER_MAX_INFLIGHT`, async publish queue settings).
- When time-chunking is also enabled, controller overwrite buffering and tracker time-chunk buffering both drop intermediate frames; operators must understand both layers.

## References

- [ADR 3: Scaling Controller Performance](0003-scaling-controller-performance.md)
- Tracker configuration: `controller/docs/user-guide/How-to-configure-tracker.md`
