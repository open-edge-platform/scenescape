# ADR 7: Controller Multiprocessing and Scene-Aware Time Chunking

- **Author(s)**: [Mohammed Sufiyan Saqib](https://github.com/mohammed-saqib), [Sarat Poluri](https://github.com/saratpoluri)
- **Date**: 2026-05-12
- **Status**: `Proposed`

## Context

Controller throughput and reliability degrade when all work is performed on the MQTT callback thread. Under multi-camera load this causes:

- callback-thread blocking (tracking/HTTP/publish),
- stale frame backlog,
- weak isolation when a tracker worker crashes,
- inefficient batching when camera frames from different scenes are mixed.

Time-chunking already provides batching. Controller-level queueing and scheduling must avoid redundant buffering behavior while preserving freshness and fairness across scenes.

## Decision

We will use:

1. **Per-scene multiprocessing in `SceneController`**
   - route each scene to a dedicated `ProcessPoolExecutor(max_workers=1)`,
   - keep only the latest frame per camera (overwrite semantics),
   - apply admission control with an in-flight semaphore,
   - automatically recreate broken worker pools.

2. **Scene-aware time-chunking in tracker path**
   - group frames by `(category, scene_id, camera_id)`,
   - dispatch complete scenes immediately (event-driven path),
   - dispatch partial scenes by timeout fallback (timer path),
   - use fixed-rate monotonic scheduling.

3. **Cache-safe camera count resolution**
   - resolve expected cameras per scene via cache fast-lookups only (no HTTP on hot path).

## Alternatives Considered

- Keep single-threaded callback-thread pipeline: rejected due to head-of-line blocking.
- Global worker pool without scene affinity: rejected due to poorer isolation and harder fairness reasoning.
- Timer-only time chunking: rejected because complete scenes wait unnecessarily.
- Event-only time chunking: rejected because partial scenes can starve.

## Consequences

### Positive

- Better throughput isolation between scenes.
- Freshest-frame processing under bursty camera inputs.
- Explicit partial-scene timeout prevents starvation for any scene.
- Crash recovery scoped to the affected scene worker.

### Negative

- Higher implementation complexity (worker lifecycle and coordination).
- Additional memory/process overhead due to per-scene executors.
- More tuning surface (in-flight limits, chunk interval, timeout).
