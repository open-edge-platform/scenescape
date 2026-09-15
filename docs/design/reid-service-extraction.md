# Design Document: ReID Service Extraction

- **Author(s)**: Derrick Addo
- **Date**: 2026-09-14
- **Status**: `Proposed`

This document is a design proposal, the same kind of document as
[`reid-api-expansion.md`](./reid-api-expansion.md) — not an
ADR in its own right. **ADR 13: Controller Breakdown into Functionality-Aligned Microservices**
(`Accepted`, 2026-06-11) is the accepted architectural decision that governs the broader
controller breakdown, and this proposal aligns with its interface guidance for Re-ID's live
tracking loop: **MQTT for the asynchronous, fan-out track-stream ingest** that feeds
`reid-service`'s internal matching/storage. For `reid-service`'s external, synchronous
query/store surface (investigator tooling, VLM-recall, POI enrollment), ADR 13's stated guidance
is **gRPC**, and that's this document's leaning — but MQTT is also mentioned as an option below
rather than settled on exclusively; see Section 3 and Open Questions.

ADR 13 groups Re-ID together with broader scene-state persistence into a single combined service.
This document intentionally does not get into that broader scope or how Re-ID fits inside it —
it scopes strictly to the Re-ID extraction described below, referred to throughout as
`reid-service`, and leaves how that maps onto ADR 13's fuller service boundaries for a separate
discussion.

One gap worth flagging up front: ADR 13's Phase 1 ("Scene State Persistence + shared Re-ID
integration") explicitly cites **ADR-10 (ReID Metadata Storage Architecture)** and **ADR-11
(Inner-Product ReID State and ID Lineage)** as already covering this territory. Neither was
available while drafting this proposal. It should be checked against both before being
finalized — parts of it may be redundant with, or in conflict with, decisions already made there.

---

## 1. Context

Today, "ReID" is not a service — it's a library (`controller.reid`, `controller.reid_registry`,
`controller.reid_env`, `controller.reid_constraints`, `controller.vdms_adapter` /
`controller.qdrant_adapter`) that every controller process imports and instantiates in-process.
Concretely, in `uuid_manager.py`:

```python
self.reid_database = create_reid_database(database, dimensions=None)
```

`UUIDManager.__init__` runs this once per instance — and there is one `UUIDManager` per tracked
**category** (person, vehicle, etc.) within a single controller process, per `Tracking.__init__`
in `tracking.py`. So a single controller process for a single scene can hold several independent
`ReIDDatabase` adapter objects, each opening its own connection to the backing VDMS or Qdrant
container (`vdms_adapter.VDMSDatabase.connect()` / `qdrant_adapter.QdrantDatabase.connect()`, both
over TCP to a configured `REID_HOSTNAME`/`REID_PORT`).

It's worth being precise about what's already networked and what isn't:

- **VDMS/Qdrant themselves are already separate, network-reachable containers.** The adapters
  talk to them over TCP today — this isn't an in-process database.
- **The `ReIDDatabase` abstraction, adapter logic, schema/retention lifecycle, and TIER 1
  constraint-building are not.** All of that runs as a Python library inside each controller
  process. There is no standalone `reid-service` — no separate deployable that owns this layer,
  and no network boundary between the controller's tracking logic and the code that decides _how_
  to query or write the backing store.

Every call into this layer happens in-process, from exactly three call sites, all in
`uuid_manager.py`:

| Method         | Call site                                                          | Trigger                                                                                                       |
| -------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `findMatches`  | `sendSimilarityQuery()` → `self.reid_database.findMatches(...)`    | A track has gathered enough quality visual features (`assignID()` → `pool.submit(self.querySimilarity, ...)`) |
| `addEntry`     | `_writeReidEntry()` → `self.reid_database.addEntry(...)`           | A track goes inactive and its accumulated features flush (`_addNewFeaturesToDatabase()`)                      |
| `purgeExpired` | `_purgeExpiredDescriptors()` → `self.reid_database.purgeExpired()` | A per-process timer, owned by exactly one `UUIDManager` via a module-level `_PURGE_OWNER` lock                |

This table describes today's code as-is; how each of these three call sites maps onto the target
architecture is addressed in Section 3.

Two details about that table matter regardless of the transport decision:

- **The `_PURGE_OWNER` lock is a process-local workaround for a problem extraction solves
  structurally.** Multiple `UUIDManager`s in one process share one backing store, so the code
  elects a single purge owner _within that process_ to avoid duplicate `DeleteExpired`/filter-delete
  calls. It does nothing about duplicate purge scheduling _across_ processes — every controller
  process (one per scene, including every child scene in a hierarchy) still runs its own elected
  owner against the same shared store today.
- **Query latency is on a tight, already-enforced budget.** `sendSimilarityQuery(sscape_object,
max_query_time=DEFAULT_MAX_QUERY_TIME)` (`DEFAULT_MAX_QUERY_TIME = 4` seconds) tracks rolling
  average query time and disables ReID entirely if it drifts past that budget. Today that budget
  covers one in-process Python call plus one TCP round-trip to VDMS/Qdrant. What replaces it
  depends on the target transport (see Section 3).

### 1.1 What's coupled to what

- **Stays inherently tied to whatever ingests detector output, regardless of extraction:**
  `moving_object.py`'s `decodeReIDEmbeddingVector` / `serializeReIDPayload` — decoding the
  embedding a detector sends over MQTT into a numpy array (and back) is about the wire format with
  detectors, not about ReID storage.
- **Orchestration logic that decides _when_ to query/write, currently living in `UUIDManager`:**
  gathering quality visual features (`gatherQualityVisualFeatures`,
  `haveSufficientVisualFeatures`), TIER 1 metadata extraction (`_extractSemanticMetadata`),
  hierarchy write-health/epoch tracking (`reid_write_healthy`, `reid_write_confirmed`,
  `reid_write_epoch`, `ReidWriteSupersededError`), and the query-latency circuit breaker above.
  None of this is ReID-storage logic — it's orchestration that happens to call into the storage
  layer today. **Where this orchestration lives after extraction is the central question this
  document addresses** — see Section 3.
- **The layer this document proposes extracting:** `reid.py` (the `ReIDDatabase` ABC and its
  shared helpers — validation, TIER 1 constraint building, schema lifecycle), `vdms_adapter.py`,
  `qdrant_adapter.py`, `reid_registry.py` (backend selection), `reid_env.py` (connection/tuning
  config), `reid_constraints.py`. This is exactly the surface [`reid-api-expansion.md`](./reid-api-expansion.md) (the API
  Expansion doc) assumes already exists as a service.

## 2. Problem

Three concrete problems exist today because this layer is a library, not a service:

1. **No shared lifecycle across a hierarchy.** Parent/child scene controllers each run their own
   copy of this layer against the same backing store (per the multi-hierarchy embedding-forwarding
   design in `scene_controller.py`'s `publishExternalDetections` /
   `_hierarchyReidPublishPolicy`). Schema creation races, retention/purge scheduling, and TIER 1
   constraint logic are all independently duplicated per process instead of centrally owned.
2. **No way for anything other than a controller process to reach this layer.** Investigator
   tooling, VLM-recall (Epic #120), and POI enrollment/matching (Epic #221) all need to call
   `findMatches` and (for POI) `addEntry`-equivalent writes from outside a controller's Python
   process. Today that's impossible without importing `controller.reid` directly, which means
   running controller-internal code outside the controller.
3. **No place to add capability without touching the controller.** Every capability in the API
   Expansion doc (POI gallery, deletion, gallery stats, TTL control, schema negotiation,
   trajectory export) is additive to `ReIDDatabase`'s existing methods, not additive to
   `UUIDManager`'s orchestration. There's currently nowhere to add it that isn't "inside the
   controller."

## 3. Proposed Design

Extract `reid.py`, `vdms_adapter.py`, `qdrant_adapter.py`, `reid_registry.py`, `reid_env.py`, and
`reid_constraints.py` into a standalone `reid-service`. The transport model below follows ADR 13's
explicit interface guidance.

**ADR 13's stated split:** _"gRPC for synchronous, latency-sensitive, query/response paths
(positioning lookups, projection, Re-ID match/store). MQTT for asynchronous, fan-out streaming
(observations, scene tracks, regulated output, events)."_

**How that maps onto today's three call sites:**

- **Live matching/writing during tracking is not a cross-service call at all.** Per ADR 13's
  target architecture, the Tracker Service (already extracted, ADR 7) streams track updates over
  MQTT — that's the "track stream ingest" half. `reid-service` performs matching and storage
  against its own vector store _as part of consuming that stream, internally, in its own
  process_. There is no separate "controller" entity publishing a match request and waiting for
  an answer — the orchestration logic in Section 1.1 (feature-gathering, TIER 1 extraction,
  write-health/epoch tracking) moves into `reid-service` alongside the storage layer, because
  that's the service that now owns UUID assignment and lifecycle end to end. This is a materially
  different shape than "the controller publishes to MQTT and reid-service responds" — it's "the
  upstream Tracker Service publishes a stream, and reid-service's own internal logic decides what
  to do with it," with no cross-service round trip for the live loop at all.
- **`findMatches` and `addEntry`, as external, synchronous-feeling operations, are ADR 13's
  "Re-ID match/store."** Investigator tooling, VLM-recall, and POI enrollment/matching (Section 2,
  problems 2–3) need a way to reach `reid-service`'s surface for this. ADR 13's stated guidance
  points at gRPC/REST for this kind of query/response workload, and that's this document's
  leaning — it's a strong, direct match for [`reid-api-expansion.md`](./reid-api-expansion.md)'s existing scope, whose Query
  API, POI enrollment, deletion, and gallery management sections were already written as an
  HTTP/gRPC surface, so that doc needs comparatively little rework from this alignment (see
  Consequences). **MQTT is also a viable option for this surface and isn't ruled out here** — a
  request/reply pattern over MQTT (correlation ID + reply-to topic) would keep every external
  interface consistent with one transport instead of splitting gRPC for queries and MQTT for
  streaming. The trade-off isn't resolved here: gRPC gives a simpler client contract (a call that
  returns a value) and matches ADR 13's stated guidance directly; MQTT keeps the whole system on
  one message bus and avoids running two transport stacks, at the cost of the client needing to
  handle correlation and timeouts itself. See Open Questions.
  What does need rework regardless of which transport is picked is [`reid-api-expansion.md`](./reid-api-expansion.md)'s
  Section 5.1, which described a controller-restricted _write_ endpoint assuming a "controller"
  calls it — there is no such caller under this model; the write path for the live loop is
  `reid-service` consuming the Tracker's MQTT stream, not an endpoint anyone calls.
- **`purgeExpired` is unaffected by this alignment.** It was already decided, independent of the
  MQTT-vs-gRPC question, that `reid-service` owns purge scheduling entirely:
  `_purgeExpiredDescriptors()` and the per-`UUIDManager` `purge_timer` are removed from the
  controller outright, `reid-service` runs its own internal timer and calls `purgeExpired()` on
  itself, the `_PURGE_OWNER` election lock is deleted entirely, and `REID_PURGE_INTERVAL_SECS`
  moves into `reid-service`'s own config. Nothing about ADR 13 changes this.

**Consequence for the query-latency circuit breaker.** `DEFAULT_MAX_QUERY_TIME`'s
rolling-average measurement (Section 1) was built around one blocking call plus one TCP round
trip. Under this model, the live matching loop is _internal to `reid-service`_ — there's no
cross-service call in that loop for a circuit breaker to wrap in the first place. Whatever
analogous safeguard is needed (e.g., `reid-service` deciding to skip a match attempt if its own
backend query is running slow) is `reid-service`'s own internal concern, not a controller-side
mechanism. This needs its own design, not a straightforward port of `sendSimilarityQuery`'s logic
— tracked as an open question.

### 3.1 What doesn't change

The wire format between detectors and the Tracker Service, TIER 1 constraint semantics, and the
VDMS/Qdrant backend contract itself (`ReIDDatabase`'s abstract methods) are unaffected by this
alignment — none of them depended on the transport question.

### 3.2 ReID metrics separation

`metrics.py` exports everything today under one OTel resource identity:
`CONTROLLER_SERVICE_NAME = "scene-controller"`. That includes seven ReID-specific instruments —
`scenescape_controller_reid_rolling_avg_match_latency`, `..._rolling_min/max_match_latency`,
`..._match_latency`, `..._current_camera_count`, `..._tracked_object_count`,
`..._total_tracked_object_count` — all populated from `latency_metrics.py`'s
`MatchLatencyTracker`, fed by `UUIDManager.markTrackStart()`/`recordMatchLatency()`.

**`reid-service` owns and sets the match-latency metrics, under its own OTel resource identity.**
Because live matching is internal to `reid-service` (Section 3), it can time its own
start-to-decision window entirely within its own process — there is no cross-service timestamp
handoff to design here. `reid-service` knows when it first received a given track's stream data
and when it reached a decision, both as purely internal facts.

`scenescape_controller_reid_rolling_avg_match_latency`, `..._rolling_min/max_match_latency`, and
`..._match_latency` — and their underlying code — move out of the controller's `metrics.py`
entirely and into `reid-service`'s own metrics module, exported under its own `SERVICE_NAME`
(e.g. `"reid-service"`; exact value not decided here). `reid-service` also needs a new instrument
for its own backend query/write duration against VDMS/Qdrant, distinct from the end-to-end
match-latency figure, for the same reason as before: without it, there's no way to tell "the
backend is slow" from "something upstream of the backend call is slow."

**Camera/tracked-object-count metrics are a genuinely open question, not a settled exception.**
`record_reid_current_camera_count`, `record_reid_tracked_object_count`, and
`record_reid_total_tracked_object_count` are derived from `CameraRegistry`/`TrackedObjectRegistry`
— today, controller-side state. ADR 13's phased plan retires the legacy Controller entirely by
its final phase. Which service owns camera/tracked-object registries in the target architecture
isn't addressed by this document. These metrics' ownership is deferred to Open Questions rather
than asserted here.

## 4. Consequences

- **The query-latency circuit breaker has no obvious new home yet.** `DEFAULT_MAX_QUERY_TIME`
  doesn't port cleanly to "`reid-service` protecting itself from its own slow backend calls" —
  that's a different failure mode (self-protection) than the original (protecting a caller from a
  slow callee). Needs its own design, not assumed to be solved by this document.

## 5. Alternatives Considered

| Alternative                                                                                                                                                                        | Why it doesn't fit as well as the proposed design                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Leave the layer in-process, add POI/gallery/etc. capability as new controller-internal methods, and only expose a thin HTTP facade in front of the controller for external callers | Doesn't solve the cross-hierarchy duplicate-lifecycle problem (Section 2, #1), and ties every new ReID capability to a controller release instead of a `reid-service` release.                                                                                            |
| Extract only the VDMS/Qdrant adapters, keep `ReIDDatabase`'s validation/constraint-building logic in the controller                                                                | Splits one coherent contract across a network boundary for no benefit — `reid_constraints.py`'s TIER 1 logic and `reid.py`'s vector validation are meaningless without the adapter they feed, and duplicating them controller-side defeats the point of a shared service. |
| Controller holds a client object and calls `reid-service` directly via synchronous RPC                                                                                             | Ties the controller to the service's availability through a client reference it holds directly.                                                                                                                                                                           |

## 6. Open Questions

- **Transport for `reid-service`'s external query/store surface: gRPC or MQTT.** Section 3 leans
  gRPC/REST, following ADR 13's stated guidance and matching [`reid-api-expansion.md`](./reid-api-expansion.md)'s existing
  HTTP/gRPC scope, but doesn't settle it — an MQTT request/reply pattern (correlation ID +
  reply-to topic) is a live alternative that would keep every `reid-service` interface on one
  transport instead of splitting gRPC for queries and MQTT for streaming. Not decided here.
- **How `reid-service` as scoped here maps onto ADR 13's broader service boundaries.** This
  document deliberately does not address how Re-ID relates to the rest of what ADR 13 groups
  together with it — that's an explicit non-goal of this pass, tracked here as a question for a
  separate discussion rather than answered.
- **What replaces the query-latency circuit breaker for `reid-service`'s own self-protection?**
  Flagged in Section 3 and Section 4 — not solved here.
- **Ownership of camera/tracked-object-count metrics under ADR 13's target architecture.** Section
  3.2 raises this without an answer — these are controller-derived today, and the controller is
  slated for retirement by ADR 13's Phase 7.
- **Does the Tracker Service's track-update stream already carry embeddings/features today, or
  does that need to be added for `reid-service` to do internal matching directly off the MQTT
  stream?** Not verified in this pass — this document only reviewed the pre-Tracker-extraction
  controller code (`ilabs_tracking.py`, `tracking.py`), not the Tracker Service's current
  output contract.
- **Rollout mechanism.** Not addressed here; needs its own plan once the questions above are
  settled.

## 7. References

- **ADR 13 — Controller Breakdown into Functionality-Aligned Microservices** (`Accepted`,
  2026-06-11) — source of the gRPC/MQTT interface guidance this document aligns with.
- **ADR-10 (ReID Metadata Storage Architecture)** and **ADR-11 (Inner-Product ReID State and ID
  Lineage)** — cited by ADR 13 as already covering related territory; not available for this
  alignment pass, needed before this document is finalized.
- [`reid-api-expansion.md`](./reid-api-expansion.md) — the API & capability design that depends on this document. Its Query
  API, POI enrollment, deletion, and gallery-management sections are largely consistent with
  ADR 13's gRPC/REST guidance already; its Section 5.1 (baseline write surface) needs a rewrite
  per Section 4 above.
