# Design Document: ReID Service — Extraction, API & Capabilities

- **Author(s)**: Derrick Addo, Sarat Poluri
- **Date**: 2026-09-14
- **Status**: `Proposed`
- **Related ADRs**: [ADR 13 — Controller Breakdown into Functionality-Aligned Microservices](../adr/0013-controller-breakdown-microservices.md),
  [ADR 7 — Tracker Service](../adr/0007-tracker-service.md),
  [ADR-10 — ReID Metadata Storage Architecture](../adr/0010-reid-metadata-storage-architecture.md),
  [ADR-11 — Inner-Product ReID State and ID Lineage](../adr/0011-inner-product-reid-state-and-id-lineage.md),
  [ADR 14 — Unified TTL Retention for ReID Descriptor Store Growth](../adr/0014-reid-descriptor-ttl-retention.md),
  [ADR 15 — Hierarchy ReID Provenance and Enrollment Scope](../adr/0015-hierarchy-reid-provenance.md)

---

## 1. Overview

This document is a design proposal — not an ADR — covering `reid-service` end to end: extracting
today's in-process ReID layer into a standalone service (Section 5), and the externally callable
API and capability surface that service exposes once it exists (Section 6).

**ADR 13: Controller Breakdown into Functionality-Aligned Microservices** (`Accepted`,
2026-06-11) is the governing decision for this work. Its end state is **full microservice
separation**: each Controller responsibility moves into a functionality-aligned service, and the
legacy Controller is **retired** once those homes exist and parity/reliability gates pass
(ADR 13 Phase 7 — "monolith retirement"). Tracker (ADR 7) is already out; this document takes
the next Re-ID step — give today's in-process ReID library a durable home outside the Controller
so that responsibility can leave the monolith rather than remain embedded until retirement day.

Within that direction, this proposal aligns with ADR 13's interface guidance for Re-ID's live
tracking loop: **MQTT for the asynchronous, fan-out track-stream ingest** that feeds
`reid-service`'s internal matching/storage. For `reid-service`'s external, synchronous
query/store surface (investigator tooling, VLM-recall, POI enrollment), ADR 13's stated guidance
is **gRPC**, and that's this document's leaning — but MQTT is also mentioned as an option below
rather than settled on exclusively; see Section 5.1 and Open Questions.

ADR 13's target diagram groups Re-ID with broader scene-state persistence in one combined
service block. That does not block this extraction: **ReID's home is `reid-service`**, the same
way MOT's home is the Tracker Service (ADR 7) even though later phases still rearrange neighbors.
Whether operators later co-deploy or merge `reid-service` with a Persistence service is a
deployment/packaging choice that can follow; it is not a prerequisite for Controllers to stop
owning ReID. This document scopes to that extraction (referred to throughout as `reid-service`).

ADR 13's Phase 1 ("Scene State Persistence + shared Re-ID integration") cites **ADR-10
(ReID Metadata Storage Architecture)** and **ADR-11 (Inner-Product ReID State and ID
Lineage)** as covering related territory. Two later ReID ADRs also bound this work: **ADR 14
(Unified TTL Retention)** and **ADR 15 (Hierarchy ReID Provenance and Enrollment Scope)**.
All four are complementary to this document, not substitutes for it:

- **ADR-10** (`Proposed`) decides the 2-tier hybrid search contract — schema-less metadata
  properties plus vector similarity (TIER 1 constraint filtering, then TIER 2 match). That is
  the storage/query semantics `reid-service` inherits; this document does not reopen it.
- **ADR-11** (`Accepted`) decides configurable similarity metric (`COSINE`/`L2`, with
  `COSINE`→VDMS `IP`), explicit `reid_state` on tracks, and `previous_ids_chain` lineage in
  scene output. That is match/output-contract behavior; this document does not reopen it.
- **ADR 14** (`Proposed`) decides the backend-neutral TTL retention contract —
  `descriptor_ttl_secs` / `REID_DESCRIPTOR_TTL_SECS`, `retentionEnabled()`,
  `_applyRetentionProperties()`, `purgeExpired()`, and the controller-side purge timer
  (`REID_PURGE_INTERVAL_SECS`, process-local `_PURGE_OWNER`). Retention is reclaim-only, not an
  identity-validity rule. This document relocates that reclaim schedule into `reid-service`
  (Section 5.1) and later proposes per-collection / pressure-based extensions (Section 6.8)
  without reopening ADR 14's reclaim-only semantics for the general gallery.
- **ADR 15** (`Proposed`) decides hierarchy ReID enroll/query scope — separate
  `quality_features` vs `enrollment_features`, explicit `metadata.reid.provenance` on hierarchy
  output (`quality_vetted`, `will_enroll` / `enrolled`), and publish policy
  (`passthrough` / `withhold` / `will_enroll` via `_hierarchyReidPublishPolicy`), plus
  write-health / write-epoch guards. That policy is why a shared DB does not double-enroll the
  same crop across hierarchy levels. Orchestration that enforces it moves into `reid-service`
  with the extraction (Section 5.1); the POI correlation feed question in Section 6.5 is whether
  to reuse ADR 15's `DATA_EXTERNAL` contract or add a dedicated path.

What this document adds — and what ADR-10 / 11 / 14 / 15 do not cover — is the **deployable
boundary** on the path to Controller retirement: extracting the in-process library into
`reid-service`, owning live ingest off the Tracker MQTT stream, centralizing purge/metrics
ownership (solving ADR 14's cross-process purge duplication), and defining the external
API/capability surface (including POI). The TIER 1 helpers, adapters, retention contract, match
semantics, and hierarchy enroll/query rules move with the extraction; they are not redesigned
here.

The API half (Section 6) covers two things that are easy to conflate but need to be kept
distinct:

- **Baseline surface (Section 6.1):** the endpoints needed just to expose today's in-process
  `ReIDDatabase` contract (`reid.py`) over a network transport at all, for callers other than
  `reid-service` itself — there is currently no HTTP/gRPC front door onto any of it.
- **New capability (Sections 6.2–6.11):** the POI enrollment/matching/alerting flow and related
  gallery-management, deletion, TTL, schema-negotiation, and trajectory-export capabilities the
  SLP epics ([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) — POI
  Re-ID & Alerting, [Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120)
  — Storewide Suspicious Activity) call for but explicitly leave as future/out-of-scope work.

Priority and exact shape within the "new capability" bucket are open; that part is meant to give
the team something concrete to react to, not a committed backlog. The baseline surface is not
optional in the same way — some version of it has to exist for `reid-service` to be a service at
all.

**Ingest vs API.** The live tracking gallery is written by `reid-service` consuming the Tracker
Service's MQTT stream (Section 5). The API in Section 6 exposes no write endpoint for that path;
see Non-Goals and Section 6.1.

## 2. Goals

**Extraction (Section 5):**

- Extract the ReID storage layer out of the controller into a standalone `reid-service`, so its
  lifecycle is centrally owned rather than duplicated per controller process — one step toward
  ADR 13's Controller retirement once every former Controller feature has a service home.
- **One external surface and capability set, independent of backend.** Callers of `reid-service`
  get the same operations and the same semantics whether the store is VDMS, Qdrant, or a later
  adapter. Backend differences stay inside the service (adapters implement the shared
  `ReIDDatabase` contract); they do not fork the external API, success rules, or feature set.
- Give callers other than a controller process a way to reach ReID capability at all.
- Give new ReID capability a home that isn't "inside the controller."
- Centralize purge/retention scheduling and separate ReID's metrics identity from the
  controller's.

**API & capability (Section 6):**

- **Define the baseline transport, not just the extensions.** Since `reid-service` doesn't exist
  yet as a standalone deployable, specify the endpoints needed to expose the existing
  `ReIDDatabase` contract (query, schema metadata) over the network — the foundation everything
  else in Section 6 sits on top of.
- Expose `reid-service`'s existing internal query capability (`findMatches`) as a first-class,
  externally callable API.
- Add a POI enrollment surface (insert, update, delete) that is clearly and permanently scoped to
  a POI gallery, separate from the general tracking gallery.
- Define how a POI match gets correlated with an in-progress tracked identity (`gid`) and turned
  into a delivered alert, without reintroducing ReID-specific logic into the controller.
- Add gallery/collection visibility (size, composition) sufficient to feed the
  `Gallery_Size_Active_Persons` / `POI_Gallery_Size` KPIs the SLP epics already name.
- Make POI records durably persisted, distinct from the general gallery's deliberately ephemeral,
  TTL-bound nature.
- Establish authentication/authorization before any write-capable, network-reachable endpoint
  ships — POI enrollment (6.4) and Deletion (6.7). Trust for Tracker-stream ingest is a separate
  question on its own track; see Section 11.
- **Define the trajectory-export API's contract** (request/response shape and the write-path
  change it depends on), so a future CCB submission starts from an honest breakdown of what's
  known vs. unknown rather than a guessed estimate. Phasing (Section 9) determines when this
  ships, not whether it's specified here.

## 3. Non-Goals

- **Settling final co-deployment with Scene State Persistence.** ADR 13 draws Persistence + Re-ID
  in one block; this document still extracts ReID into `reid-service` as its home. Later
  co-location or merge with Persistence is out of scope here and does not reopen whether ReID
  leaves the Controller.
- **Writing to or deleting from the general/tracking gallery via the API in Section 6.** There is
  no such path — `reid-service` consumes the Tracker Service's MQTT stream directly for the live
  tracking loop, and the API exposes no write endpoint for it at all. Enforced by absence of
  endpoints, not by locking down a restricted writer (Section 6.1).
- **Image-to-embedding extraction/inference.** `reid-service`'s job stays storage and search;
  running the ReID model to turn an image into an embedding happens outside it, same as today.
- **Stream Manager's internal video/clip API.** Referenced only where it bounds the trajectory
  discussion (6.11); owned by the Stream Manager team. Draft:
  [docs/design/stream-manager](https://github.com/open-edge-platform/scenescape/tree/tdorau/stream-manager-api-draft/docs/design/stream-manager).
- **UI implementation** of the 2D-track click-through or any other frontend work — separate
  codebase, out of scope here.
- **Wire-level schema (OpenAPI/proto) for any endpoint below**, including the baseline surface
  and trajectory export. This document specifies shape and behavior; exact request/response
  schemas are an implementation-time detail.
- **A final decision on authN/authZ mechanism, or on the DATA_EXTERNAL-reuse-vs-dedicated-topic
  question for correlation.** Both are deliberately left as open questions (Section 11), not
  resolved here.

## 4. Background / Context

### 4.1 Today: ReID is a library, not a service

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
architecture is addressed in Section 5.1.

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
  depends on the target transport (see Section 5.1).

### 4.2 What's coupled to what

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
  layer today. **Where this orchestration lives after extraction is the central question
  Section 5 addresses.**
- **The layer this document proposes extracting:** `reid.py` (the `ReIDDatabase` ABC and its
  shared helpers — validation, TIER 1 constraint building, schema lifecycle), `vdms_adapter.py`,
  `qdrant_adapter.py`, `reid_registry.py` (backend selection), `reid_env.py` (connection/tuning
  config), `reid_constraints.py`. This is exactly the surface Section 6 assumes already exists as
  a service.

### 4.3 Problems this creates

Three concrete problems exist today because this layer is a library, not a service:

1. **No shared lifecycle across a hierarchy.** Parent/child scene controllers each run their own
   copy of this layer against the same backing store (per ADR 15's hierarchy provenance /
   enrollment-scope design, implemented in `scene_controller.py`'s `publishExternalDetections` /
   `_hierarchyReidPublishPolicy`). Schema creation races, retention/purge scheduling (ADR 14's
   process-local `_PURGE_OWNER` is the within-process half of this), and TIER 1 constraint logic
   are all independently duplicated per process instead of centrally owned.
2. **No way for anything other than a controller process to reach this layer.** Investigator
   tooling, VLM-recall (Epic #120), and POI enrollment/matching (Epic #221) all need to call
   `findMatches` and (for POI) `addEntry`-equivalent writes from outside a controller's Python
   process. Today that's impossible without importing `controller.reid` directly, which means
   running controller-internal code outside the controller.
3. **No place to add capability without touching the controller.** Every capability in Section 6
   (POI gallery, deletion, gallery stats, TTL control, schema negotiation, trajectory export) is
   additive to `ReIDDatabase`'s existing methods, not additive to `UUIDManager`'s orchestration.
   There's currently nowhere to add it that isn't "inside the controller."

### 4.4 What the existing `ReIDDatabase` contract already provides

`reid.py`'s `ReIDDatabase` is already a clean, backend-agnostic abstract contract —
`connect()`, `addEntry()`, `getPersistedAttributes()`, `findMatches()`, `findSchemaMetadata()`,
`ensureSchema()`, `purgeExpired()`, `retentionEnabled()` — implemented identically by both
`VDMSDatabase` and `QdrantDatabase`. Section 6.1 defines how this contract gets exposed as an API
for the first time; everything after that is additive to it. `addEntry` was designed around the
tracking pipeline: every call carries an `rvid` (motion-tracker ID) and happens as a side effect
of a track being observed. Nothing in the current contract has any notion of "POI," a second
gallery, deletion, or per-appearance history — all of that is new surface area, described section
by section below.

### 4.5 Motivating epics

- [Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) — SLP: Person of
  Interest Re-Identification & Alerting. Defines the POI enrollment/matching/alerting use case
  and explicitly leaves POI gallery management (retention, removal criteria) and alert-routing
  business logic out of scope.
- [Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120) — SLP:
  Storewide Suspicious Activity Detection & Multi-Camera Tracking with VLM Recall. Motivates the
  Query API as a first-class endpoint (investigator/VLM-recall tooling) and names
  `Gallery_Size_Active_Persons` / `ReID_Match_Latency_ms` as KPIs with no current data source.

---

## 5. Proposed Design — Part A: Service extraction

### 5.1 Service boundary and transport model

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
  an answer — the orchestration logic in Section 4.2 (feature-gathering, TIER 1 extraction,
  write-health/epoch tracking) moves into `reid-service` alongside the storage layer, because
  that's the service that now owns UUID assignment and lifecycle end to end. That move includes
  ADR 15's enroll/query split (`quality_features` vs `enrollment_features`), provenance-gated
  write authority (`will_enroll` / `enrolled`), and write-health / write-epoch guards — those
  rules are not reinvented here; they relocate with the orchestration. This is a materially
  different shape than "the controller publishes to MQTT and reid-service responds" — it's "the
  upstream Tracker Service publishes a stream, and reid-service's own internal logic decides what
  to do with it," with no cross-service round trip for the live loop at all.
- **`findMatches` and `addEntry`, as external, synchronous-feeling operations, are ADR 13's
  "Re-ID match/store."** Investigator tooling, VLM-recall, and POI enrollment/matching
  (Section 4.3, problems 2–3) need a way to reach `reid-service`'s surface for this. ADR 13's
  stated guidance points at gRPC/REST for this kind of query/response workload, and that's this
  document's leaning — it's a strong, direct match for Section 6's scope, whose Query API, POI
  enrollment, deletion, and gallery management sections are written as an HTTP/gRPC surface.
  **MQTT is also a viable option for this surface and isn't ruled out here** — a request/reply
  pattern over MQTT (correlation ID + reply-to topic) would keep every external interface
  consistent with one transport instead of splitting gRPC for queries and MQTT for streaming. The
  trade-off isn't resolved here: gRPC gives a simpler client contract (a call that returns a
  value) and matches ADR 13's stated guidance directly; MQTT keeps the whole system on one
  message bus and avoids running two transport stacks, at the cost of the client needing to
  handle correlation and timeouts itself. See Open Questions. Section 6.1 reflects this model:
  there is no write endpoint for the live loop, because no caller exists for one.
- **`purgeExpired` is unaffected by this alignment.** ADR 14 already defined the retention
  contract and the controller-side reclaim timer. Independent of the MQTT-vs-gRPC question, this
  document relocates that schedule so `reid-service` owns it entirely:
  `_purgeExpiredDescriptors()` and the per-`UUIDManager` `purge_timer` are removed from the
  controller outright, `reid-service` runs its own internal timer and calls `purgeExpired()` on
  itself, the `_PURGE_OWNER` election lock is deleted entirely, and `REID_PURGE_INTERVAL_SECS`
  (and `REID_DESCRIPTOR_TTL_SECS`) move into `reid-service`'s own config. That also closes the
  cross-process duplicate-reclaim gap ADR 14's Consequences already flagged. Adapter-level
  expiration representation (VDMS `_expiration` vs Qdrant `expires_at`) and reclaim-only
  semantics stay as ADR 14 decided them.

**Consequence for query-performance degradation signaling.** `DEFAULT_MAX_QUERY_TIME`'s
rolling-average measurement (Section 4.1) was built around one blocking call plus one TCP round
trip. Under this model, the live matching loop is _internal to `reid-service`_ — there's no
cross-service call in that loop for a Controller-side circuit breaker to wrap. That Controller
mechanism therefore **retires with the Controller** (Section 8); it is not ported. What remains
is a `reid-service` concern: detect when query performance has degraded and either signal
consumers to stop relying on matches, or — when the cause is gallery growth / data volume —
surface a purge or compaction recommendation. Exact policy is still open (Section 11); it does
not block extraction.

### 5.2 What doesn't change

The wire format between detectors and the Tracker Service, TIER 1 constraint semantics (ADR-10),
similarity-metric / `reid_state` / lineage contracts (ADR-11), general-gallery reclaim-only TTL
semantics (ADR 14), hierarchy provenance and enroll/query scope rules (ADR 15), and the
VDMS/Qdrant backend contract itself (`ReIDDatabase`'s abstract methods) are unaffected by this
alignment — none of them depended on the transport question.

### 5.3 ReID metrics separation

`metrics.py` exports everything today under one OTel resource identity:
`CONTROLLER_SERVICE_NAME = "scene-controller"`. That includes seven ReID-specific instruments —
`scenescape_controller_reid_rolling_avg_match_latency`, `..._rolling_min/max_match_latency`,
`..._match_latency`, `..._current_camera_count`, `..._tracked_object_count`,
`..._total_tracked_object_count` — all populated from `latency_metrics.py`'s
`MatchLatencyTracker`, fed by `UUIDManager.markTrackStart()`/`recordMatchLatency()`.

**`reid-service` owns and sets the match-latency metrics, under its own OTel resource identity.**
Because live matching is internal to `reid-service` (Section 5.1), it can time its own
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

**Camera/tracked-object-count metrics leave the Controller before Phase 7 retirement; they are
not kept as a Controller exception.** `record_reid_current_camera_count`,
`record_reid_tracked_object_count`, and `record_reid_total_tracked_object_count` are derived from
`CameraRegistry`/`TrackedObjectRegistry` — today, controller-side state. Match-latency instruments
move with `reid-service` (above) because live matching lives there. Registry-derived counts follow
whichever service owns those registries after disaggregation (not assumed to be `reid-service`
unless those registries land there). Exact SERVICE_NAME / owner is an implementation detail of
the phase that extracts those registries; what this document settles is that they must not remain
Controller-only through retirement.

### 5.4 Tracker stream contract (live ingest + trajectory fields)

This section owns what the Tracker Service's MQTT track-stream must carry into `reid-service`.
Section 6.11 defines the external read surface that depends on this contract (notably
`GET /trajectories/{gid}`); it does not redefine the ingest path.

**Baseline for live matching/writing — Tracker stream audit (current code).** `reid-service`
performs matching and storage by consuming the Tracker stream directly (Section 5.1). Against
today's Tracker Service (`tracker/`):

- **Embeddings can pass through, but are not a first-class track field.** Camera detections may
  carry `metadata` (schema allows detector-defined keys such as `reid`); Tracker stores that as
  `Detection::metadata_json`, preserves it through transform/MOT
  (`TrackingWorker::convert_tracks`), and re-emits it on
  `scenescape/data/scene/{scene_id}/{category}` via `TrackPublisher::serialize`. Unit tests cover
  `metadata.reid.embedding_vector` passthrough. There is no dedicated embedding field on `Track`,
  no requirement that detectors populate `metadata.reid`, and multi-camera metadata fusion is
  confidence / last-write-wins — so embedding presence for live matching is **best-effort
  passthrough**, not a guaranteed contract.
- **Gaps for the trajectory ingest fields in this section:** published `Track` objects do **not**
  carry `camera_id` or a per-object sighting `timestamp`. Message-level `timestamp` exists on the
  scene envelope; world-space `translation` / `size` exist on the object. `scene-data.schema.json`
  optionally allows `visibility` (camera IDs) and `camera_bounds`, but `TrackPublisher` does not
  emit them today. Closing those gaps is Tracker (or upstream) work before `reid-service` can
  persist a sighting diary off the stream alone — logged as an open question in Section 11.
  Pixel bounding box is **not** required for the Stream Manager integration path (Section 6.11).

**Additional fields for trajectory persistence.** Trajectory export needs an ordered diary of
sightings, not only the latest known state. Today that diary is not what reaches the ReID store,
and the two things a trajectory needs (location and time) are not even in the part of the object
that reaches the ReID database:

- `moving_object.py` has two genuinely separate things: `self.location` (a list of `Chronoloc`
  entries — point + timestamp + bounding box) and `self.metadata` (a separate dict for arbitrary
  semantic/sensor attributes).
- `UUIDManager`'s write to the ReID database only ever pulls from `self.metadata`, via
  `_extractSemanticMetadata()`. `self.location` is never touched by that path. So today's ReID
  gallery stores the embedding vector plus generic semantic metadata — camera and timestamp never
  make it in.
- One encouraging detail: the camera ID isn't even missing from the codebase —
  `_extractCameraId()` already exists and already extracts it, but today it's wired only to a
  metrics counter (`CameraRegistry.recordEmbeddingObserved`), not to the ReID write. So this
  isn't "invent new tracking data" — it's "connect two things that already exist
  (`_extractCameraId()` and `self.location`'s timestamp) to a write that already happens."

**Required ingest change:** the Tracker stream payload that `reid-service` consumes must include
`camera_id` and per-sighting `timestamp`, alongside the existing embedding and semantic metadata
— sourced from `_extractCameraId()` and `self.location`'s `Chronoloc` entries respectively.
`reid-service` persists those fields on each descriptor write. Bounding box is not required for
Stream Manager retrieval (Section 6.11). This is a change to what the Tracker Service's stream
carries and what `reid-service` persists from it, not a new endpoint — there is still no external
write endpoint for this path; it is entirely stream-driven. Retention trade-offs for how far back
trajectory queries can reach are covered in Section 6.11, not here.

---

## 6. Proposed Design — Part B: External API & capability surface

Everything in this section assumes the service defined in Section 5 exists: ReID extracted into
`reid-service`, live ingest via the Tracker Service's MQTT stream with matching/writing handled
internally, and purge scheduling owned by the service. There is no existing `reid-service`
deployment today, and none of the endpoints below exist in any network-reachable form. `reid.py`'s
`ReIDDatabase` contract is real and stable, but it has only ever been called **in-process** by the
controller. This section is the first place an externally callable transport (HTTP/gRPC, or MQTT
request/reply per the open question in Section 5.1) gets defined for the parts of it meant for
callers other than `reid-service` itself — both for the existing contract (6.1) and for the new
POI-driven capability (6.2 onward). The general/tracking gallery's write path is explicitly _not_
part of that externally callable transport — see 6.1.

### 6.1 Baseline service API surface

Before any POI-specific capability can exist, `reid-service` needs _some_ network-reachable
version of the contract it already has in-process — for callers other than `reid-service` itself.
This is the part of the design that Section 6.2 onward assumes already exists; it's specified
explicitly rather than left implicit, since — unlike the POI work — there is no existing
deployment to point to as "already covers this."

**The general/tracking gallery's write path is not part of this baseline surface — it has no
endpoint at all.** Per Section 5.1, `reid-service` doesn't get written to over an API for the live
tracking loop; it consumes the Tracker Service's MQTT track-stream directly and performs matching
and writing internally, as part of its own stream processing. There is no controller (or anything
else) calling a write endpoint for this path, so there's nothing here to lock down to a specific
caller — the access question that mattered under the earlier client/RPC design doesn't apply. The
Non-Goal in Section 3 still holds (this API does not let arbitrary callers write to the general
gallery); it's just enforced by there being no such endpoint, rather than by restricting one.

**Proposed baseline endpoints** — the externally callable surface, each a thin transport wrapper
around the corresponding `ReIDDatabase` method, with no behavior change from today's in-process
semantics:

- **Read: mirrors `findMatches`.** Covered in full in 6.3 (Query API), since exposing this to
  callers _beyond_ the live tracking loop — investigator tooling, VLM recall, POI matching — is
  itself one of this document's goals, not just a transport detail. Whether this rides on
  gRPC/REST or MQTT request/reply is the open question raised in Section 5.1 — not settled here.
- **Read: mirrors `findSchemaMetadata`.** Lets a caller confirm a collection's existence,
  dimensions, and similarity metric before querying — needed once external callers exist, since
  they can't assume the schema the way the internal stream-consumption path can.
- **Admin (optional, internal use): mirrors `purgeExpired`.** `reid-service` schedules its own
  purges internally per Section 5.1 — this endpoint isn't required for that to work. It exists
  only as an optional operational hook (manual trigger during incident response,
  liveness/maintenance tooling), not a load-bearing part of the design.
- **Health/readiness.** Standard for any deployable service — not present in the in-process
  contract at all, since "is `reid.py` reachable" was never a meaningful question before now.

**Why this matters for everything downstream.** Sections 6.2–6.11 describe new capability in
terms of "the API" as though a baseline already exists. It doesn't yet. Building this baseline is
what turns `reid-service` from "a module the controller imports" into an actual service other
things can call — the POI/gallery/trajectory work is what that service does once it exists, not
what makes it exist in the first place. Note that this baseline is entirely about the externally
callable surface; the live tracking loop's own data path (Tracker Service → MQTT →
`reid-service`) isn't part of "the API" in the sense this section uses that term at all.

### 6.2 Design principles (cross-cutting)

Decisions carried across every subsection below, settled in discussion rather than sketched
per-endpoint:

- **Backend-independent external contract.** The API in this section is one surface: the same
  endpoints, request/response shapes, and success/failure rules for every backend. Where an
  adapter lacks a primitive the contract needs (for example a count), the service implements that
  capability on top of the adapter so callers do not branch on VDMS vs Qdrant. Which backend is
  deployed is an operator concern, not part of the caller contract.
- **Writes are POI-gallery-only — the general gallery has no writer in this API at all.** Per
  6.1, the general/tracking gallery is written to by `reid-service` consuming the Tracker
  Service's MQTT stream directly, not by any endpoint in this API. All insert, update, and delete
  operations this API exposes — everything in 6.4 (POI enrollment) and 6.7 (deletion) — apply
  **only to the POI gallery**. To be unambiguous about what that means per operation:
  - **Insert** (6.4, `POST /poi`) — POI gallery only. There is no "insert a general tracking
    descriptor" endpoint in this API at all; that path is `reid-service`'s own internal stream
    consumption, not something this API exposes.
  - **Update** (6.4, `PATCH /poi/{poi_id}` and appending reference embeddings) — POI gallery
    only. The general gallery has no update concept in this API at all.
  - **Delete** (6.7) — POI gallery only. See that section for why general-gallery deletion is
    explicitly not part of this API; general-gallery aging uses the existing 24h TTL for now.
  - **Query** (6.3, `findMatches`) — the one operation that reads from _both_ galleries.
    Read-only either way; querying the general gallery through this API never writes to it.

  Nothing in the Query API, Deletion API, or Gallery/collection management subsections should be
  read as applying to the general gallery unless explicitly called out — and after this
  subsection, nothing does.

- **POI records are persisted, not just long-TTL.** A POI record isn't "the same as the general
  gallery but with a bigger number" — it's meant to survive indefinitely by design, distinct
  from the general gallery's inherently ephemeral, TTL-bound nature. See 6.10 for what
  "persisted" actually needs to mean beyond disabling TTL.
- **`poi_id` is always server-generated.** Enrollment does not accept a client-supplied ID — the
  service mints the identifier and returns it in the response.

### 6.3 Query API as a first-class endpoint

`findMatches` exists internally today but is only ever called from inside the tracking
pipeline. Exposing it directly over the service API (building on the baseline transport in 6.1)
would let investigator tools, a
[VLM-recall service (Epic #120)](https://github.com/intel-retail/storewide-loss-prevention/issues/120),
or a [POI-matching UI (Epic #221)](https://github.com/intel-retail/loss-prevention/issues/221)
query the gallery without routing through the controller at all. Straightforward extension of
existing internals — no new adapter logic needed, just an HTTP/gRPC front door onto `findMatches`
with the same TIER 1 constraints (`reid_constraints.py`) exposed as query parameters.

### 6.4 Explicit POI enrollment endpoint (insert & update — POI gallery only)

**Why it needs its own endpoint, not just `addEntry`.** POI enrollment
([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221)) is a different flow
entirely from live tracking — a security operator manually uploads a reference image or marks a
person in a video clip, with no tracker context at all. Forcing that through `addEntry` means
inventing a synthetic `rvid` and hoping nothing downstream assumes it's real. A dedicated
`POST /poi` endpoint sidesteps that: it accepts one or more precomputed embeddings and enrollment
metadata (`severity`, `notes`, `enrolled_by`), and only _internally_ calls the same write path
`addEntry` already uses. Per the design principles above, the caller does not supply a `poi_id` —
the service generates one and returns it in the response; the caller addresses that POI in later
calls (`PATCH`, delete) using the ID the service gave back.

**Important scoping note:** the service should accept precomputed embedding vectors, not raw
images. Image → embedding extraction (running the ReID model) stays outside `reid-service`, same
as it does today — the service's job is storage and search, not inference. This keeps the
service's dependency footprint (and GPU/NPU requirements) unchanged from today.

**Open question — who actually runs that extraction for enrollment images?** For the live
tracking pipeline this is a non-issue: DL Streamer pipelines are already running continuously per
camera. Enrollment is different — it's a one-off, infrequent event, not a continuous stream. Two
options, with different operational cost:

- Bring up a DL Streamer pipeline container just to process the one enrollment frame, then tear
  it down — reuses the exact same extraction path as live tracking, but pipeline
  startup/teardown overhead for a single frame is a lot of machinery for one image.
- A lightweight synchronous embedding-extraction API (either exposed by DL Streamer directly, if
  feasible, or a small dedicated helper service) that takes one image and returns one embedding
  — much less overhead, but is a second extraction code path to keep in sync with the live
  pipeline.

This needs an answer before `POST /poi` can be built, since it determines what the caller of that
endpoint is expected to already have in hand. Tracked as an open question in Section 11.

**Reference images and updates.**
[Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) expects 1–5 reference
images per POI. `addEntry` already accepts a list of `reid_vectors` in one call, so
batch-enrolling multiple reference embeddings for one POI needs no new adapter capability — the
enrollment endpoint just needs to accept a list. What's missing is the **update** story:

- Adding a new reference image to an already-enrolled POI later (e.g., a better-quality capture)
  should be additive, not a full re-enrollment.
- Updating metadata only — severity, notes, active/inactive status — shouldn't require
  re-embedding or re-writing vectors at all.

Proposed split: `POST /poi/{poi_id}/embeddings` (append a reference embedding) vs.
`PATCH /poi/{poi_id}` (metadata-only update). This also gives a clean point to implement the
"removal criteria" workflow Epic #221 explicitly punts on today (soft-disable via `PATCH` status
vs. hard delete via 6.7).

**Write acknowledgment.** Enrollment and embedding-append writes are all-or-nothing at the API
layer (Section 6.10): success only when every vector in that call is accepted; no half-enrolled
`poi_id`.

**Isolation from the general tracking gallery.**
[Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) calls out a "two-tier
gallery" — a small, manually-curated POI gallery (tens to low thousands) searched with tight
confidence thresholds, separate from the large, continuously-growing general tracking gallery.
That argues for POI enrollments landing in their own `set_name`/collection rather than sharing the
general gallery's namespace. Two consequences worth deciding now:

- **Retention differs by design.** The general gallery's TTL (`descriptor_ttl_secs`, default
  24h) exists specifically so it doesn't grow unbounded. A POI gallery almost certainly wants a
  much longer TTL, or none. Today's adapters apply one TTL per adapter instance at construction
  time (`_applyRetentionProperties`); the enrollment endpoint needs a way to write with a
  _different_ retention policy than the general-gallery writer uses, which is a real (if small)
  adapter change, not just an API wrapper.
- **Query behavior differs by design.** POI matching wants a small `k_neighbors` and a strict
  threshold against a small gallery; general tracking match/no-match logic is tuned differently.
  The Query API (6.3) should be able to target "the POI set" vs. "the general set" explicitly
  rather than inferring it from `object_type` alone.

**Validation.** Reuse what already exists rather than re-inventing it: `prepareReidDict` /
`prepareReidVector` in `reid.py` already validate shape, finiteness, and (optionally)
normalization of an embedding before it's written. The enrollment endpoint should run enrollment
images through the same validation path and reject bad embeddings with the same class of error
the pipeline already uses (`ReidNoValidVectorsError`), rather than defining new validation rules.

### 6.5 POI-to-tracking correlation and alert delivery

**Decision — correlation runs outside the controller, as a standalone daemon.** A separate
process consumes `reid-service` purely as an API client — the same way any other future tool
would (per the investigator/VLM-recall use case in 6.3) — and does the correlation itself,
entirely decoupled from the controller.

This was weighed against embedding the check directly in `UUIDManager`'s existing per-frame loop
(cheapest to build, lowest latency, since the live embedding is already sitting right there when
`gid` gets assigned via `querySimilarity()` → `findMatches()`). That's rejected specifically
because it would pull new POI-aware logic back into the controller at the exact moment we're
separating ReID out of it — keeping ReID concerns (including POI, which is a ReID concept) out of
the controller is the actual point of this whole body of work, so the daemon approach is the one
consistent with it even though it costs a bit of latency and a small amount of new plumbing.

**What the daemon correlates against.** The daemon doesn't have a live per-frame embedding the
way the controller does. This turns out not to be a blocker, because the mechanism to feed it
already exists in the codebase — and is governed by **ADR 15**:

`moving_object.py` already carries an `embedding_vector` field (base64-encoded) and a
`reid_provenance` field, and `scene_controller.py`'s `publishExternalDetections` already attaches
both (`attach_reid_provenance=True`) and puts them on the MQTT bus at `PubSub.DATA_EXTERNAL` —
ADR 15's hierarchy embedding-forwarding contract (parent/child scene sharing). The daemon
subscribing to that topic already receives live embeddings today, with no new `reid-service`
capability needed. Two things worth deciding before treating this as the final wiring, though:

- **It's rate-limited and gated by logic built for a different purpose (ADR 15).**
  `publishExternalDetections` only fires per `scene.external_update_rate` (not every frame), and
  whether an object's embedding gets attached at all is decided by `_hierarchyReidPublishPolicy`
  (`will_enroll` / `withhold` / `passthrough`) — logic that answers "should this scene claim
  write ownership of this embedding," not "should the POI daemon see this object." Subscribing to
  `DATA_EXTERNAL` as-is means POI correlation silently inherits ADR 15's publish constraints for
  reasons unrelated to POI matching.
- **It's currently scoped narrowly on purpose — worth not widening it by accident.** Only
  `DATA_EXTERNAL` carries embeddings; the general `DATA_SCENE` topic every other consumer
  subscribes to does not. That's a real, already-working privacy boundary limiting who sees
  embedding data today (ADR 15 attaches provenance only to hierarchy output for the same reason).

The reuse-vs-dedicated-topic choice is therefore whether ADR 15's hierarchy contract is a fit
feed for POI correlation, or whether a dedicated path is needed — tracked as an open question in
Section 11. Once `{gid: poi_id}` is discovered, that tag should stick for the life of the `gid`
(mirroring the existing sticky-once-true pattern used for `_category_has_embeddings`) rather
than re-checking every subsequent frame for a track that's already tagged.

**Correlation publishes an event; it does not deliver an alert.** `scene_controller.py` already
has an MQTT event bus for exactly this kind of fact-of-occurrence broadcasting — tracking events
go out on `PubSub.EVENT` topics, and `child_scene_controller.py`'s `republishEvents` already
forwards a child scene's events up to the parent. The daemon should publish a `poi_match` event
onto that bus, using the payload shape already sketched in
[Epic #221](https://github.com/intel-retail/loss-prevention/issues/221)'s POI Match Alert schema
(`poi_id`, `camera_id`, confidence, bbox, timestamp) — getting the existing hierarchy propagation
for free when the match happens in a child scene. This is the one place the daemon needs write
access back into the existing MQTT bus rather than being a pure `reid-service` consumer.

Actual alert **delivery** should still be a separate downstream consumer, not the same code path
as correlation:

- Epic #221's alert delivery target (3 seconds from match) is generous relative to how quickly
  the daemon needs to move on to the next correlation check. Blocking the daemon on network I/O
  to a security terminal for every match risks it falling behind on new matches for no benefit.
- Epic #221 wants alerts deliverable to more than one kind of destination (local terminal, REST
  endpoint, message queue) — an integration/fan-out concern that shouldn't require touching
  correlation code every time a new delivery target is added.
- **Alert deduplication belongs at the delivery layer, not the correlation layer.** The 5-minute
  dedup window governs _how often to notify_, a different question from _whether a match
  occurred_. Suppressing at correlation would throw away the record of every real match;
  suppressing at delivery keeps a full match history for investigation while still controlling
  notification noise.

**Delivery method options.** Epic #221 scopes delivery to "a local security terminal or API
endpoint," explicitly leaving third-party notification-system integration out of scope. Within
that boundary, there are three plausible transports, not mutually exclusive:

- **MQTT (reuse the existing bus).** Cheapest option — the `poi_match` event is already on
  `PubSub.EVENT`; a local security terminal or on-prem dashboard could subscribe directly, the
  same way `child_scene_controller.py` already subscribes to tracking/event topics.
- **REST callback (webhook push).** The alert consumer POSTs to a configured URL per Epic #221's
  "API endpoint" delivery target. Better fit for an external security system that isn't already
  an MQTT subscriber; needs retry/backoff handling MQTT's pub/sub model gets for free.
- **Message queue.** Epic #221's acceptance criteria explicitly names this as an option alongside
  REST. Best fit for enterprise integrations wanting durable, replayable delivery.

Recommend supporting MQTT plus a configurable REST webhook as the initial pair, with
message-queue delivery as an additive option once a concrete integration needs it.

**Latency metric separation.** Epic #221's own performance-tools section already names
`POI_Match_Latency_ms` as a distinct KPI from the general tracking pipeline's
`ReID_Match_Latency_ms` — meant to be tracked separately, not folded into one number. The daemon
becomes the natural owner of `POI_Match_Latency_ms`: it should tag its own query latency
independently (e.g. `gallery=poi`) rather than relying on `reid-service` to know which downstream
KPI a given query's latency feeds into — `reid-service` itself should only report generic
per-query latency, staying agnostic to POI as a concept.

**Where this lives.** The dedup window, retry logic, and multi-transport fan-out above are enough
independent logic that alert delivery is worth treating as owned by the same daemon that performs
correlation, rather than a second standalone component. That daemon is also the natural place to
expose the "Alert API" Epic #221 calls for.

### 6.6 Gallery/collection management API

**What's actually missing today.** Neither `VDMSDatabase` nor `QdrantDatabase` currently exposes
anything like a count or listing call — `findSchemaMetadata` tells you a collection _exists_ and
its dimensions/metric, not how many entries are in it. This means the KPIs the SLP epics already
name — `Gallery_Size_Active_Persons`, `POI_Gallery_Size` — have no data source today. This is new
adapter work in both backends, not just an API wrapper: VDMS has no direct "count" primitive
comparable to Qdrant's `client.count()` / collection info.

**Proposed endpoints:**

- `GET /collections` — list known collections/sets with dimensions, similarity metric, backend,
  and retention policy.
- `GET /collections/{name}/stats` — size and composition of one collection.

**The "size" question needs a real answer, not just a number.** A raw vector count is the wrong
metric for `Gallery_Size_Active_Persons`. Both galleries can have multiple descriptors per
person — POI enrollment intentionally stores 1–5 reference images per POI, and the general
gallery accumulates additional embeddings per UUID over time. "Active persons" means **distinct
UUID count**, not row count. The stats endpoint should report both explicitly (`vector_count` and
`distinct_object_count`).

**Scoping stats to the multi-hierarchy world.** Per the multi-hierarchy sharing design (all
scenes in a hierarchy share one ReID database), "gallery size" for a shared database isn't
necessarily one number a partner cares about. Worth deciding whether `/collections/{name}/stats`
supports a `scene_id` or `camera_id` filter, or whether that breakdown is explicitly out of scope
for v1.

**Admin operations.** Today, collection creation is entirely implicit — `ensureSchema` lazily
creates the schema on the first write. That's fine for the general gallery, which keeps its
existing internally-managed lifecycle unchanged. The ambiguity is on the POI side: once more than
one POI-type collection can exist, implicit creation gets ambiguous. Proposed: an explicit
`POST /collections` (name, dimensions, metric, retention policy) scoped to POI-type collections,
leaving the general gallery's lazy self-managed creation exactly as it is today.

**Feeding existing observability, not just a new REST surface.** `latency_metrics.py` already
establishes the pattern this should follow: raw values go to an OTel histogram/gauge for
dashboards, not just a REST response for humans to poll. Gallery size should be exported the same
way (`Gallery_Size_Active_Persons` as an OTel gauge tagged by collection/scene) so the
performance-tools `GalleryExtractor` mentioned in both SLP epics has something to actually read
during gallery-scaling benchmarks.

### 6.7 Deletion API (POI gallery only)

Doesn't exist in any form today — `ReIDDatabase` has no `deleteEntry`. Scoped to the POI gallery
only, per 6.2. Needed for:

- POI removal (Epic #221 explicitly leaves "removal criteria" out of scope today, but an API
  will be needed once that's decided).
- Demo and test data cleanup for POI entries created during testing.

**General-gallery deletion is explicitly out of scope for this API.** An earlier draft of this
section considered "right-to-erasure / compliance requests against the general gallery" as a use
case, which directly conflicts with the POI-only write-scope principle. Resolving that: this
deletion API does not touch the general gallery. **Settled for now:** rely on the general
gallery's existing short TTL (24h default via ADR 14 / `REID_DESCRIPTOR_TTL_SECS`) to age
descriptors out. Additional purge / compaction mechanisms (including any explicit
compliance-erasure path beyond TTL) may be added to `reid-service` later; they are not part of
this API surface and do not block extraction or the POI deletion endpoint.

Proposed shape: delete-by-`poi_id` and delete-by-filter (e.g. by `severity` or enrollment date),
reusing the same constraint structure `reid_constraints.py` already builds for queries.

### 6.8 Runtime TTL / eviction control

**ADR 14** already established the general-gallery retention contract this section builds on:
`descriptor_ttl_secs` / `REID_DESCRIPTOR_TTL_SECS` (default 24h; `0` disables),
`REID_PURGE_INTERVAL_SECS`, reclaim-only purge (descriptors stay searchable until physically
removed), and adapter-private expiration representation. Those knobs are static env vars fixed
at process start today; Section 5.1 moves the reclaim schedule into `reid-service` without
changing that contract for the general gallery.

Two gaps once 6.4 and 6.6 exist:

- **Per-collection TTL.** POI records are meant to be persisted, not merely long-TTL (6.2) — this
  needs to be settable per collection, not just per process. That is an additive extension of
  ADR 14's single-TTL-per-adapter model, not a replacement of reclaim-only semantics for the
  general gallery.
- **Pressure-based eviction.** ADR 14 already noted TTL is not a hard memory limit — storage can
  still grow within the window under heavy ingest. Proposed: an eviction mode that deletes
  oldest-first once a collection crosses a configured size/storage cap, independent of age —
  paired with, not replacing, ADR 14's TTL. (ADR 14 listed capacity-based eviction as an
  alternative deferred beyond that ADR's scope; this section is where that follow-on lands.)

### 6.9 Explicit schema/version negotiation endpoint

Today, embedding dimensions are inferred lazily from the first vector written
(`_ensureReIDDimensions` → `ensureSchema`). That's reasonable when the only caller is the
controller, which always writes before it needs to query. Once other tools can call the service
directly (the investigator/VLM-recall use case in 6.3 doesn't necessarily write before it
queries), an explicit "declare dimensions/metric for this collection" call becomes more useful
than relying on implicit inference from whichever caller happens to write first.

### 6.10 POI database persistence

"Persisted" got compressed into a one-line design principle in 6.2 — it's a bigger topic than
that line covers, and it matters more for POI than it does for the general gallery. If the
general gallery loses data, it's not really a loss — the gallery is continuously repopulated by
live tracking. POI is the opposite: there's no automatic recovery. A security operator has to
notice a POI silently isn't being watched for anymore, then manually re-enroll.

**Settled shipping bar: persistent volume, not production disk HA.** This work ships a step
above reference level, not production-grade durability. Attach a Docker volume (or, in
Kubernetes, a `PersistentVolumeClaim`) to wherever the POI collection's backend data lives, so a
container restart, image update, or pod recreation doesn't wipe it. Nothing in `vdms_adapter.py`
or `qdrant_adapter.py` needs to change for this — it's a Compose/Helm deployment decision. The
concrete requirement: **the POI collection's storage must be backed by a persistent volume**,
verified independently of whatever collection/retention API design (6.6, 6.8) gets layered on
top of it.

**Host / disk loss is explicitly out of scope.** A volume protects against container-lifecycle
events, not underlying host or disk failure. That residual risk is accepted for this bar; no
replication, RAID, or multi-AZ durability work is in scope here.

**Settled — POI write acknowledgment (API contract, not disk fsync).** A volume does not define
when `POST /poi` may return success. For the general gallery, dropped or partial writes are
tolerated (`ReidPartialWriteError` exists because the live loop self-corrects on later frames).
POI has no such recovery path. **`POST /poi` (and POI embedding appends) are all-or-nothing:**
success only if every vector in that enrollment write is accepted by the backend; otherwise the
call fails and no usable `poi_id` is returned for a half-written enrollment. This is stricter
than general-gallery partial-write tolerance at the **API** layer. It does not require
production-grade fsync/quorum semantics. How each adapter confirms the write stays internal
(Qdrant `upsert(..., wait=True)`; VDMS per-descriptor status). Callers see one outcome either
way: full success or failure — consistent with the backend-independent contract in Section 2 and
6.2.

**Settled — no backup/export or live migration API in this bar.** A volume does not protect
against volume deletion or provide a portable dump. Nothing in `ReIDDatabase` exports data today,
and this design does not add a dump/import endpoint. **POI recovery after volume loss, or after a
VDMS→Qdrant (or other) backend swap, is manual re-enrollment.** A future read-only export (that
could also serve offline migration) may be scheduled as a separate epic; it is not required for
extraction, PV-backed POI, or `POST /poi`.

### 6.11 Trajectory export API

The ability to export a moving object's full trajectory by `gid` — every camera it was seen on, in
order, until it exits the scene — with frames stitchable into a video, clickable from the 2D track
UI, and exposed via API. Originally raised informally; specified here as an actual API contract
rather than left as an open discussion, per review feedback that phasing (Section 9) should decide
_when_ this ships, not whether its shape gets defined now. This spans three separable pieces with
very different amounts of known scope; only the `reid-service` piece is owned by this document.

**What's actually being asked, stripped down.** Not the video itself — that's Stream Manager's
job. What ReID needs to produce is the _list of sightings_ that tells a caller which cameras and
which time windows to pull footage from.

**Ingest prerequisite.** Persisting a sighting diary — `camera_id` and per-sighting `timestamp` on
each general-gallery write — is specified in Section 5.4 (Tracker stream contract), including the
gap analysis against today's code. This section does not redefine that write path; there is no
write endpoint for it (6.1).

**Defined API contract.**

- **New read endpoint:** `GET /trajectories/{gid}` — returns the ordered list of sightings for a
  `gid`: one entry per descriptor write, each with `camera_id` and `timestamp`, ordered
  chronologically. This is a different query shape from today's `getPersistedAttributes`, which
  is deliberately _latest-only_; it's a new method on the `ReIDDatabase` contract, not a
  reinterpretation of an existing one.

**Settled — sighting granularity vs Stream Manager.** Against the Stream Manager draft
([docs/design/stream-manager](https://github.com/open-edge-platform/scenescape/tree/tdorau/stream-manager-api-draft/docs/design/stream-manager)):

| Concern                                                                                                                                              | Owner               | Contract                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Ordered sighting diary (`camera_id`, `timestamp`)                                                                                                    | `reid-service`      | `GET /trajectories/{gid}`                                                                                                 |
| Attach / buffer camera streams; event-triggered multi-stream recording; list records                                                                 | Stream Manager      | `/v1/streams`, `/v1/records/start\|stop`, `GET /v1/records`                                                               |
| Retrieve a frame or clip                                                                                                                             | Stream Manager      | `GET /v1/records/{id}/frame?stream-id&timestamp` (nearest frame); `GET /v1/records/{id}/clip?stream-id&timestamp-start&…` |
| Map `camera_id` ↔ SM `stream_id` / Sensor Manager `sensor_id`; decide when to record vs query existing records; present / stitch multi-camera clips | Business logic / UI | Outside both service APIs                                                                                                 |

Stream Manager seeks and clips by **RFC 3339 timestamps** on NTP-synced streams. Its retrieval
APIs take `stream-id` + time (or time range); they do **not** accept frame numbers or bounding
boxes. Therefore **camera + timestamp is the required ReID sighting contract** for Stream Manager
integration. Pixel bbox and frame number are not required for that path (optional later for UI
overlays only — not a Stream Manager dependency, and not required on the Tracker ingest fields in
Section 5.4).

SM returns **per-stream** frames/clips, not a single already-stitched multi-camera video.
Cross-camera presentation remains UI / business-logic work.

**Settled — retention.** Trajectory sightings live in the general gallery, so they age out with
the same ADR 14 TTL (`descriptor_ttl_secs` / `REID_DESCRIPTOR_TTL_SECS`, default 24h).
`GET /trajectories/{gid}` can only return what is still stored: after purge, older sessions are
gone — there is no separate longer-lived trajectory archive in this design. "Entire session until
it exits" therefore means a session that still fits inside that window (currently in-store or
recently left). Extending beyond 24h would require changing general-gallery retention (or a
dedicated store), which is out of scope here.

**Recommendation for what actually goes to CCB.** Don't submit one lump number. The
`reid-service` piece (stream fields per Section 5.4 plus `GET /trajectories/{gid}` here) is
genuinely scopeable (roughly 1–2 sprints for one engineer) and is now specified rather than left
as an open discussion. Stream Manager's retrieval surface is drafted; remaining cost is
integration (id mapping, record lifecycle vs query, multi-clip UI) — schedule that as a separate
story after a short joint check with Stream Manager's owner, not as an unbounded discovery.

---

## 7. Alternatives Considered

**Extraction (Section 5):**

| Alternative                                                                                                                                                                        | Why it doesn't fit as well as the proposed design                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Leave the layer in-process, add POI/gallery/etc. capability as new controller-internal methods, and only expose a thin HTTP facade in front of the controller for external callers | Doesn't solve the cross-hierarchy duplicate-lifecycle problem (Section 4.3, #1), and ties every new ReID capability to a controller release instead of a `reid-service` release.                                                                                          |
| Extract only the VDMS/Qdrant adapters, keep `ReIDDatabase`'s validation/constraint-building logic in the controller                                                                | Splits one coherent contract across a network boundary for no benefit — `reid_constraints.py`'s TIER 1 logic and `reid.py`'s vector validation are meaningless without the adapter they feed, and duplicating them controller-side defeats the point of a shared service. |
| Controller holds a client object and calls `reid-service` directly via synchronous RPC                                                                                             | Ties the controller to the service's availability through a client reference it holds directly.                                                                                                                                                                           |

**API & capability (Section 6):**

| Alternative                                                                                           | Considered for                    | Outcome                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Controller-embedded correlation (checking the POI set inside `UUIDManager`'s existing per-frame loop) | POI-to-tracking correlation (6.5) | **Rejected.** Cheapest and lowest-latency, but reintroduces ReID-specific logic into the controller at the exact point separation is trying to remove it from. |
| Reusing ADR 15's `DATA_EXTERNAL` hierarchy contract as-is for the correlation daemon's embedding feed | Correlation data source (6.5)     | **Open, not yet decided.** Weighed against a second, dedicated publish path decoupled from ADR 15's `_hierarchyReidPublishPolicy` write-ownership gating.      |

## 8. Consequences

- **The Controller-side query-latency circuit breaker retires with the Controller.**
  `DEFAULT_MAX_QUERY_TIME` protected a caller (UUIDManager in-process) from a slow callee. Under
  this design there is no such cross-boundary call in the live loop — matching is internal to
  `reid-service` — so the old mechanism is not ported. Replacement intent (Section 11): detect
  degraded query performance so consumers can stop using matches, and when the cause is data
  volume, recommend purge or compaction. Policy details remain a follow-on; they do not justify
  keeping ReID in the Controller.
- **Tracker scene-track output is not yet sufficient for trajectory persistence.** Embeddings may
  ride in passthrough `metadata.reid`, but `camera_id` and per-sighting timestamp are missing from
  published tracks today (Section 5.4 / Section 11). Bounding box is not required for Stream
  Manager retrieval (Section 6.11).
- **POI durability stops at a persistent volume.** Host/disk-loss residual risk is accepted for
  this shipping bar (Section 6.10); general-gallery aging stays on the existing 24h TTL until
  later purge/compaction work (Section 6.7). POI enrollment is all-or-nothing at the API layer;
  there is no backup/export or automated backend-migration path — recovery is re-enrollment.

## 9. Rollout / Migration Plan

**Extraction follows ADR 13's phased pattern.** Ship `reid-service` behind feature flags, dual-run
with the legacy Controller ReID path until parity/reliability gates pass, then remove the
in-Controller library path so Controllers no longer own ReID — the same shape as Tracker
extraction (Phase 0) and ADR 13's general "legacy Controller role shrinks until Phase 7
retirement" plan. ReID-specific cutover checklist (env migration for
`REID_DESCRIPTOR_TTL_SECS` / purge interval, hierarchy write-health handoff, metrics cutover) is
implementation detail for that phase, not an open architectural question.

For the API work in Section 6: unlike a phased architectural migration, those subsections don't
have a hard dependency order — each is closer to an independent epic than a sequential phase.
That said, a few real sequencing dependencies exist and are worth respecting:

- **The baseline service API (6.1) has to exist before anything else in Section 6 can ship** —
  it's the transport every other subsection assumes.
- **Authentication/authorization (Section 11) should be decided before any write-capable endpoint
  ships** — POI enrollment (6.4) and Deletion (6.7) are the write-capable endpoints this API
  exposes, and retrofitting auth after they're built is worse than deciding it first. The
  general/tracking gallery's write path isn't an endpoint this applies to, but its own trust
  boundary — `reid-service`'s MQTT subscription to the Tracker Service — needs the equivalent
  scrutiny on its own track (Section 11).
- **TTL/eviction control (6.8) depends on POI enrollment (6.4) and Gallery/collection management
  (6.6) existing first** — there's nothing to set a per-collection policy on until POI
  collections exist and are visible.
- **The trajectory export API (6.11) depends on the Tracker stream contract in Section 5.4 being
  stable** (`camera_id` + per-sighting `timestamp` on published tracks). Stream Manager's
  timestamp-based frame/clip APIs are already drafted; schedule integration (id mapping, record
  lifecycle, multi-clip UI) after that contract is stable — not ahead of Tracker field work. Its
  API contract is defined now (6.11); this dependency governs timing, not definition.

Recommend treating each remaining subsection as its own small, independently schedulable story,
prioritized against whichever SLP epic
([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) or
[Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120)) is closer to
needing it.

## 10. Testing & Monitoring

**Testing.** New adapter capability (per-collection TTL overrides, count/list support in both
backends per 6.6, the new trajectory query shape per 6.11 and the stream-field persistence it
depends on per Section 5.4) should be tested the same way the existing
`VDMSDatabase`/`QdrantDatabase` adapters already are — unit tests per backend, exercised through
the shared `ReIDDatabase` contract so behavior stays identical across backends. The baseline API
(6.1) should additionally get contract/integration tests at the transport layer, since it's the
first place any of this is network-reachable at all.

**Monitoring.** `latency_metrics.py` already establishes the pattern every new metric here should
follow: raw values to an OTel histogram/gauge, not just a REST response for humans to poll.
Specifically:

- `Gallery_Size_Active_Persons` / `POI_Gallery_Size` as OTel gauges tagged by collection/scene
  (6.6), feeding the performance-tools `GalleryExtractor` both SLP epics already name.
- `POI_Match_Latency_ms` tracked independently from the general tracking pipeline's
  `ReID_Match_Latency_ms` (6.5), owned by the correlation daemon rather than `reid-service`
  itself.

## 11. Open Questions

**Extraction (Section 5):**

- **Transport for `reid-service`'s external query/store surface: gRPC or MQTT.** Section 5.1
  leans gRPC/REST, following ADR 13's stated guidance and matching Section 6's HTTP/gRPC scope,
  but doesn't settle it — an MQTT request/reply pattern (correlation ID + reply-to topic) is a
  live alternative that would keep every `reid-service` interface on one transport instead of
  splitting gRPC for queries and MQTT for streaming. Not decided here.
- **Query-performance degradation signaling (replaces the retired Controller circuit breaker).**
  Intent: detect when `reid-service` query performance has degraded so consuming services can
  stop using match results; and when the likely cause is gallery / data volume, surface a
  suggestion to purge or compact (building on ADR 14 reclaim). Exact signals, thresholds,
  consumer-facing contract (e.g. health/ready vs explicit degrade event), and purge/compaction
  recommendation shape are still to be designed — they do not block extraction.
- **Tracker stream gaps for live matching and trajectory (verified against current Tracker code).**
  Reviewed `tracker/` (`Detection` / `Track`, `message_handler`, `TrackingWorker`,
  `TrackPublisher`, `camera-data.schema.json`, `scene-data.schema.json`):
  - **Embeddings:** optional passthrough only — if a detector puts `metadata.reid` (including
    `embedding_vector`) on the camera message, Tracker can preserve and republish it on the
    scene track topic. Not a required field; multi-camera metadata fusion may overwrite by
    confidence / last-write-wins. **Gap:** no first-class, guaranteed embedding-on-track
    contract for `reid-service` live matching.
  - **`camera_id`:** known on input batches (`DetectionBatch.camera_id`) but **not** written onto
    published `Track` objects. Schema allows optional `visibility` / `camera_bounds`; publisher
    does not emit them. **Gap** for trajectory persistence (Section 5.4).
  - **Per-sighting timestamp:** only the scene-envelope `timestamp` is published, not a
    per-object sighting time. **Gap** for an ordered diary of sightings.
  - **Bounding box:** input has `bounding_box_px`; output has world `translation` / `size` only.
    **Not required** for Stream Manager retrieval (Section 6.11); optional later for UI overlays
    only.
    Closing the `camera_id` and per-sighting-timestamp gaps is Tracker (or detector) contract
    work before `reid-service` can rely on the MQTT stream alone for matching + trajectory
    writes.
- **Trust boundary for `reid-service`'s MQTT subscription to the Tracker Service.** Since the
  general/tracking gallery has no write endpoint (6.1) — `reid-service` gets that data by
  subscribing to the Tracker Service's MQTT stream directly — what secures that subscription
  (broker-level ACLs, topic-level auth, network policy, or a combination)? This is a different
  question from the endpoint authN/authZ decision below, since there's no endpoint here to
  authenticate a caller against.

**API & capability (Section 6):**

- **Enrollment embedding extraction.** Who runs image → embedding extraction for a one-off POI
  enrollment — a spun-up/torn-down DL Streamer pipeline, or a lightweight synchronous extraction
  API? (6.4)
- **Correlation data feed.** Reuse ADR 15's `DATA_EXTERNAL` hierarchy contract as-is for the
  correlation daemon (inheriting its rate limit and `will_enroll` / withhold / passthrough
  write-ownership gating), or add a second, dedicated publish path? (6.5)
- **Gallery stats scoping.** Should `/collections/{name}/stats` support a `scene_id` /
  `camera_id` filter for the shared multi-hierarchy database, or is the whole-collection number
  sufficient for v1? (6.6)
- **authN/authZ mechanism** for the write-capable endpoints (6.4, 6.7) — deliberately left open
  (Section 3), but must be decided before either ships (Section 9).

**Settled (kept here for traceability):**

- **Host/disk loss (6.10).** Persistent volume only; residual host/disk-loss risk accepted.
  Shipping bar is a step above reference, not production disk HA.
- **POI write acknowledgment (6.10 / 6.4).** All-or-nothing enrollment at the API layer: success
  only if every vector in the write is accepted; stricter than general-gallery partial-write
  tolerance. Not fsync/quorum durability.
- **Backup/export / backend migration (6.10).** No export or live-migration API in this bar;
  volume loss or VDMS→Qdrant swap → manual POI re-enrollment. Optional future dump epic.
- **General-gallery compliance/erasure (6.7).** Existing 24h TTL is the mechanism for now;
  additional purge/compaction (or an explicit erasure path) may be added to `reid-service` later.
- **Trajectory sighting granularity (6.11).** Camera + timestamp is sufficient. Stream Manager
  retrieves by `stream-id` + RFC 3339 time (nearest frame / clip range); frame number and bbox
  are not part of that contract. Multi-camera stitch/presentation stays in business logic / UI.
- **Trajectory retention (6.11).** Same as general-gallery TTL (24h default). The API cannot
  return sightings already purged; no separate longer-lived trajectory archive.

## 12. References

- **ADR 13 — Controller Breakdown into Functionality-Aligned Microservices** (`Accepted`,
  2026-06-11) — full microservice separation and eventual Controller retirement (Phase 7); source
  of the gRPC/MQTT interface guidance this document aligns with. This design is one extraction
  step toward that retirement.
- **ADR 7 — Tracker Service** (`Accepted`) — the already-completed extraction whose MQTT track
  stream `reid-service` consumes.
- **ADR-10 (ReID Metadata Storage Architecture)** (`Proposed`) — 2-tier hybrid search and
  schema-less metadata; the storage/query semantics `reid-service` inherits (see Overview).
- **ADR-11 (Inner-Product ReID State and ID Lineage)** (`Accepted`) — similarity-metric
  configuration, `reid_state`, and `previous_ids_chain`; the match/output contract
  `reid-service` inherits (see Overview).
- **ADR 14 (Unified TTL Retention for ReID Descriptor Store Growth)** (`Proposed`) —
  backend-neutral TTL / `purgeExpired` contract relocated into `reid-service` (Section 5.1) and
  extended for per-collection / pressure-based control (Section 6.8).
- **ADR 15 (Hierarchy ReID Provenance and Enrollment Scope)** (`Proposed`) — hierarchy
  enroll/query split, provenance wire contract, and publish policy; orchestration moves with
  extraction (Section 5.1), and bounds the POI correlation feed choice (Section 6.5).
- [Epic #221 — SLP: Person of Interest Re-Identification & Alerting](https://github.com/intel-retail/loss-prevention/issues/221)
- [Epic #120 — SLP: Storewide Suspicious Activity Detection & Multi-Camera Tracking with VLM Recall](https://github.com/intel-retail/storewide-loss-prevention/issues/120)
- [Stream Manager design draft](https://github.com/open-edge-platform/scenescape/tree/tdorau/stream-manager-api-draft/docs/design/stream-manager)
  (`tdorau/stream-manager-api-draft`) — event-based buffering, timestamp-aligned recording, and
  frame/clip retrieval that bounds Section 6.11.
