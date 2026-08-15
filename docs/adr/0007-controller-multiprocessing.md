# ADR 7: Controller Multiprocessing

- **Author(s)**: [Mohammed Sufiyan Saqib](https://github.com/mohammed-saqib), [Sarat Poluri](https://github.com/saratpoluri)
- **Date**: 2026-05-12
- **Status**: `Accepted`
- **Supersedes**: N/A (replaces draft titled “Controller Multiprocessing and Scene-Aware Time Chunking”; scene-aware chunking and related camera-count resolution are deferred — see Alternatives Considered)

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

Tracker time-chunking remains the existing timer-only design from ADR 3 (`time_chunking_enabled` / `time_chunking_interval_milliseconds`). Items deferred from earlier drafts of this ADR are listed under Alternatives Considered.

### Interaction with tracker time-chunking

Controller ingress overwrite/admission and tracker time-chunking are **intentionally stacked**, not alternatives:

| Layer | Where | What is kept / dropped |
| --- | --- | --- |
| Controller ingress | Before scene worker / tracker | Latest detection per camera; in-flight cap can refuse work under overload |
| Time-chunking | Tracker path (optional) | Latest frame per camera+category per interval; busy tracker can drop a whole chunk |

Neither layer replaces the other. Time-chunking does not disable controller freshest-frame behavior. Product-facing knobs for the tracker layer live in `tracker-config.json` (see tracker how-to). Controller admission and async-publish limits remain implementation settings, not user-guide configuration.

## Alternatives Considered

- Keep single-threaded callback-thread pipeline: rejected due to head-of-line blocking.
- Global worker pool without scene affinity: rejected due to poorer isolation and harder fairness reasoning.

### Deferred (not in this ADR’s accepted scope)

- **Scene-aware / hybrid time-chunking** in the tracker path: group frames by `(category, scene_id, camera_id)`, dispatch complete scenes on an event-driven path, and use a timer fallback for partial scenes with fixed-rate monotonic scheduling. Deferred — not implemented on this branch; adds scheduling complexity beyond the multiprocessing goal. Existing timer-only time-chunking (ADR 3) is retained.
- **Cache-safe camera count resolution** (former Decision #3): resolve expected cameras per scene via cache fast-lookups only (no HTTP on the hot path) so complete-scene dispatch knows when a scene is “full.” Deferred with scene-aware time-chunking — it has no consumer without that path. Revisit only if scene-aware chunking is revived.

## Consequences

### Positive

- Better throughput isolation between scenes.
- Freshest-frame processing under bursty camera inputs via per-camera overwrite buffering.
- Crash recovery scoped to the affected scene worker.
- MQTT callback path stays short; heavy work runs in scene workers.

### Negative

- Higher implementation complexity (worker lifecycle and coordination).
- Additional memory/process overhead due to per-scene executors.
- Stacked freshness layers (controller ingress plus optional time-chunking) can drop more intermediate frames than either alone; operators should tune camera FPS and time-chunking interval using the tracker how-to before enabling object batching.

## References

- [ADR 3: Scaling Controller Performance](0003-scaling-controller-performance.md)
- Tracker configuration: `controller/docs/user-guide/How-to-configure-tracker.md`
