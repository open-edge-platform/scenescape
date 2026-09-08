# Design Document: ReID Service API Expansion

- **Author(s)**: Derrick Addo
- **Date**: 2026-09-08
- **Status**: `Proposed`

---

## 1. Overview

This document specifies a set of candidate API additions to `reid-service` once it exists as a
standalone component. Priority and exact shape are open; this is meant to give the team something concrete to react to,
not a committed backlog.

Each item below maps back to either a gap in today's `ReIDDatabase` contract (`reid.py`) or
something the SLP epics ([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221)
— POI Re-ID & Alerting, [Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120)
— Storewide Suspicious Activity) already call for but explicitly leave as future/out-of-scope
work.

## 2. Goals

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
  ships.
- Scope — not yet solve — an informally-raised trajectory-export ask, so a future CCB submission
  starts from an honest breakdown of what's known vs. unknown rather than a guessed estimate.

## 3. Non-Goals

- **Writing to or deleting from the general/tracking gallery via this API.** Its only writer
  remains the controller's internal tracking pipeline, unchanged.
- **Image-to-embedding extraction/inference.** `reid-service`'s job stays storage and search;
  running the ReID model to turn an image into an embedding happens outside it, same as today.
- **Stream Manager's internal video/clip API.** Referenced only where it bounds the trajectory
  discussion; its design is owned by the Stream Manager team.
- **UI implementation** of the 2D-track click-through or any other frontend work — separate
  codebase, out of scope here.
- **Wire-level schema (OpenAPI/proto) for any endpoint below.** This document specifies shape and
  behavior; exact request/response schemas are an implementation-time detail.
- **A final decision on authN/authZ mechanism, or on the DATA_EXTERNAL-reuse-vs-dedicated-topic
  question for correlation.** Both are deliberately left as open questions (Section 9), not
  resolved here.

## 4. Background / Context

### 4.1 What `reid-service` already provides

`reid.py`'s `ReIDDatabase` is already a clean, backend-agnostic abstract contract —
`connect()`, `addEntry()`, `getPersistedAttributes()`, `findMatches()`, `findSchemaMetadata()`,
`ensureSchema()`, `purgeExpired()`, `retentionEnabled()` — implemented identically by both
`VDMSDatabase` and `QdrantDatabase`. Everything in this document is additive to that contract, not
a replacement of it. `addEntry` was designed around the tracking pipeline: every call carries an
`rvid` (motion-tracker ID) and happens as a side effect of a track being observed. Nothing in the
current contract has any notion of "POI," a second gallery, deletion, or per-appearance history —
all of that is new surface area, described section by section below.

### 4.2 Motivating epics

- [Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) — SLP: Person of
  Interest Re-Identification & Alerting. Defines the POI enrollment/matching/alerting use case
  and explicitly leaves POI gallery management (retention, removal criteria) and alert-routing
  business logic out of scope.
- [Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120) — SLP:
  Storewide Suspicious Activity Detection & Multi-Camera Tracking with VLM Recall. Motivates the
  Query API as a first-class endpoint (investigator/VLM-recall tooling) and names
  `Gallery_Size_Active_Persons` / `ReID_Match_Latency_ms` as KPIs with no current data source.

---

## 5. Proposed Design

### 5.1 Design principles (cross-cutting)

Decisions carried across every subsection below, settled in discussion rather than sketched
per-endpoint:

- **Writes are POI-gallery-only.** Insert, update, and delete operations exposed by this API
  apply **only to the POI gallery** — not to the general/tracking gallery. To be unambiguous
  about what that means per operation:
  - **Insert** (5.3, `POST /poi`) — POI gallery only. There is no equivalent "insert a general
    tracking descriptor" endpoint in this API; the general gallery's only writer stays the
    controller's internal tracking pipeline (`UUIDManager` → `addEntry`), unchanged from today.
  - **Update** (5.3, `PATCH /poi/{poi_id}` and appending reference embeddings) — POI gallery
    only. The general gallery has no update concept in this API at all.
  - **Delete** (5.6) — POI gallery only. See that section for why general-gallery deletion is
    explicitly not part of this API, and how compliance/erasure requests against the general
    gallery are handled instead.
  - **Query** (5.2, `findMatches`) — the one operation that reads from *both* galleries.
    Read-only either way; querying the general gallery through this API never writes to it.

  Nothing in the Query API, Deletion API, or Gallery/collection management subsections should be
  read as applying to the general gallery unless explicitly called out — and after this
  subsection, nothing does.
- **POI records are persisted, not just long-TTL.** A POI record isn't "the same as the general
  gallery but with a bigger number" — it's meant to survive indefinitely by design, distinct
  from the general gallery's inherently ephemeral, TTL-bound nature. See 5.9 for what
  "persisted" actually needs to mean beyond disabling TTL.
- **`poi_id` is always server-generated.** Enrollment does not accept a client-supplied ID — the
  service mints the identifier and returns it in the response.

### 5.2 Query API as a first-class endpoint

`findMatches` exists internally today but is only ever called from inside the tracking
pipeline. Exposing it directly over the service API would let investigator tools, a
[VLM-recall service (Epic #120)](https://github.com/intel-retail/storewide-loss-prevention/issues/120),
or a [POI-matching UI (Epic #221)](https://github.com/intel-retail/loss-prevention/issues/221)
query the gallery without routing through the controller at all. Straightforward extension of
existing internals — no new adapter logic needed, just an HTTP/gRPC front door onto `findMatches`
with the same TIER 1 constraints (`reid_constraints.py`) exposed as query parameters.

### 5.3 Explicit POI enrollment endpoint (insert & update — POI gallery only)

**Why it needs its own endpoint, not just `addEntry`.** POI enrollment
([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221)) is a different flow
entirely from live tracking — a security operator manually uploads a reference image or marks a
person in a video clip, with no tracker context at all. Forcing that through `addEntry` means
inventing a synthetic `rvid` and hoping nothing downstream assumes it's real. A dedicated
`POST /poi` endpoint sidesteps that: it accepts one or more precomputed embeddings and enrollment
metadata (`severity`, `notes`, `enrolled_by`), and only *internally* calls the same write path
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
endpoint is expected to already have in hand. Tracked as an open question in Section 9.

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
vs. hard delete via 5.6).

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
  *different* retention policy than the general-gallery writer uses, which is a real (if small)
  adapter change, not just an API wrapper.
- **Query behavior differs by design.** POI matching wants a small `k_neighbors` and a strict
  threshold against a small gallery; general tracking match/no-match logic is tuned differently.
  The Query API (5.2) should be able to target "the POI set" vs. "the general set" explicitly
  rather than inferring it from `object_type` alone.

**Validation.** Reuse what already exists rather than re-inventing it: `prepareReidDict` /
`prepareReidVector` in `reid.py` already validate shape, finiteness, and (optionally)
normalization of an embedding before it's written. The enrollment endpoint should run enrollment
images through the same validation path and reject bad embeddings with the same class of error
the pipeline already uses (`ReidNoValidVectorsError`), rather than defining new validation rules.

### 5.4 POI-to-tracking correlation and alert delivery

**Decision — correlation runs outside the controller, as a standalone daemon.** A separate
process consumes `reid-service` purely as an API client — the same way any other future tool
would (per the investigator/VLM-recall use case in 5.2) — and does the correlation itself,
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
already exists in the codebase:

`moving_object.py` already carries an `embedding_vector` field (base64-encoded) and a
`reid_provenance` field, and `scene_controller.py`'s `publishExternalDetections` already attaches
both (`attach_reid_provenance=True`) and puts them on the MQTT bus at `PubSub.DATA_EXTERNAL` —
this is the existing multi-hierarchy embedding-forwarding mechanism (parent/child scene sharing).
The daemon subscribing to that topic already receives live embeddings today, with no new
`reid-service` capability needed. Two things worth deciding before treating this as the final
wiring, though:

- **It's rate-limited and gated by logic built for a different purpose.**
  `publishExternalDetections` only fires per `scene.external_update_rate` (not every frame), and
  whether an object's embedding gets attached at all is decided by `_hierarchyReidPublishPolicy`
  (`will_enroll` / `withhold` / `passthrough`) — logic that answers "should this scene claim
  write ownership of this embedding," not "should the POI daemon see this object." Subscribing to
  `DATA_EXTERNAL` as-is means POI correlation silently inherits both constraints for reasons
  unrelated to POI matching.
- **It's currently scoped narrowly on purpose — worth not widening it by accident.** Only
  `DATA_EXTERNAL` carries embeddings; the general `DATA_SCENE` topic every other consumer
  subscribes to does not. That's a real, already-working privacy boundary limiting who sees
  embedding data today.

The reuse-vs-dedicated-topic choice is tracked as an open question in Section 9. Once
`{gid: poi_id}` is discovered, that tag should stick for the life of the `gid` (mirroring the
existing sticky-once-true pattern used for `_category_has_embeddings`) rather than re-checking
every subsequent frame for a track that's already tagged.

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
  dedup window governs *how often to notify*, a different question from *whether a match
  occurred*. Suppressing at correlation would throw away the record of every real match;
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

### 5.5 Gallery/collection management API

**What's actually missing today.** Neither `VDMSDatabase` nor `QdrantDatabase` currently exposes
anything like a count or listing call — `findSchemaMetadata` tells you a collection *exists* and
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

### 5.6 Deletion API (POI gallery only)

Doesn't exist in any form today — `ReIDDatabase` has no `deleteEntry`. Scoped to the POI gallery
only, per 5.1. Needed for:

- POI removal (Epic #221 explicitly leaves "removal criteria" out of scope today, but an API
  will be needed once that's decided).
- Demo and test data cleanup for POI entries created during testing.

**General-gallery deletion is explicitly out of scope for this API.** An earlier draft of this
section considered "right-to-erasure / compliance requests against the general gallery" as a use
case, which directly conflicts with the POI-only write-scope principle. Resolving that: this
deletion API does not touch the general gallery. If a compliance/erasure need against the general
gallery ever becomes real, it should be handled separately — for example, by relying on the
general gallery's existing short TTL (24h default) to age the data out on its own, or by a
distinct, explicitly-scoped mechanism decided later.

Proposed shape: delete-by-`poi_id` and delete-by-filter (e.g. by `severity` or enrollment date),
reusing the same constraint structure `reid_constraints.py` already builds for queries.

### 5.7 Runtime TTL / eviction control

`descriptor_ttl_secs` and the purge interval are static env vars fixed at process start today.
Two gaps once 5.3 and 5.5 exist:

- **Per-collection TTL.** POI records are meant to be persisted, not merely long-TTL (5.1) — this
  needs to be settable per collection, not just per process.
- **Pressure-based eviction.** Current bounding is purely time-based, so storage can still grow
  within the TTL window under heavy ingest. Proposed: an eviction mode that deletes oldest-first
  once a collection crosses a configured size/storage cap, independent of age — paired with, not
  replacing, the existing TTL.

### 5.8 Explicit schema/version negotiation endpoint

Today, embedding dimensions are inferred lazily from the first vector written
(`_ensureReIDDimensions` → `ensureSchema`). That's reasonable when the only caller is the
controller, which always writes before it needs to query. Once other tools can call the service
directly (the investigator/VLM-recall use case in 5.2 doesn't necessarily write before it
queries), an explicit "declare dimensions/metric for this collection" call becomes more useful
than relying on implicit inference from whichever caller happens to write first.

### 5.9 POI database persistence

"Persisted" got compressed into a one-line design principle in 5.1 — it's a bigger topic than
that line covers, and it matters more for POI than it does for the general gallery. If the
general gallery loses data, it's not really a loss — the gallery is continuously repopulated by
live tracking. POI is the opposite: there's no automatic recovery. A security operator has to
notice a POI silently isn't being watched for anymore, then manually re-enroll.

**The immediate, concrete answer: a persistent volume.** Attach a Docker volume (or, in
Kubernetes, a `PersistentVolumeClaim`) to wherever the POI collection's backend data lives, so a
container restart, image update, or pod recreation doesn't wipe it. Nothing in `vdms_adapter.py`
or `qdrant_adapter.py` needs to change for this — it's a Compose/Helm deployment decision. This is
the concrete, buildable requirement: **the POI collection's storage must be backed by a
persistent volume**, verified independently of whatever collection/retention API design (5.5,
5.7) gets layered on top of it. This alone covers the most common failure mode and is enough to
treat "persisted" as solved for an initial version.

**What a volume doesn't cover — open follow-on questions, not blockers.** None of these need to
be answered before the volume requirement above ships:

- **Host or disk loss.** A volume protects against the container dying, not the underlying disk
  dying. Whether that residual risk is acceptable is a scoping call worth making deliberately.
- **Write acknowledgment semantics.** A volume says nothing about whether `POST /poi` waits for
  the backend to actually flush before returning success. For the general gallery, a dropped
  write is tolerated as routine (`ReidPartialWriteError` already exists because partial writes
  are normal there). POI enrollment returning "success" for a write that didn't durably land is a
  real problem with no next frame to self-correct it.
- **Backup / export.** A volume protects against container churn, not against someone deleting
  the volume or needing to restore a point-in-time copy. Nothing in `ReIDDatabase` exports data
  today — 5.5's gallery-management API only sketched stats, not a dump.
- **Migration continuity.** Ties back to the VDMS→Qdrant migration motivating the original
  separation work. A volume holds a backend's own on-disk format — it doesn't cross a
  VDMS-to-Qdrant swap by itself. The general gallery doesn't need a migration path; the POI
  gallery does, or every POI has to be re-enrolled by hand. The same export/import capability as
  the backup question above would serve both needs.

### 5.10 Trajectory export API (pre-CCB discussion — not yet an official ask)

Raised informally, not yet a CCB: the ability to export a moving object's full trajectory by
`gid` — every camera it was seen on, in order, until it exits the scene — with frames stitchable
into a video, clickable from the 2D track UI, and exposed via API. This spans three separable
pieces with very different amounts of known scope.

**What's actually being asked, stripped down.** Not the video itself — that's Stream Manager's
job. What ReID needs to produce is the *list of sightings* that tells Stream Manager which
cameras and which time windows to pull footage from.

**The gap, confirmed against the actual code.** The system today only keeps a "latest known
state" per object, not a running diary of every sighting — and critically, the two things a
trajectory needs (location and time) are not even in the part of the object that reaches the ReID
database:

- `moving_object.py` has two genuinely separate things: `self.location` (a list of `Chronoloc`
  entries — point + timestamp + bounding box) and `self.metadata` (a separate dict for arbitrary
  semantic/sensor attributes).
- `UUIDManager`'s write to the ReID database only ever pulls from `self.metadata`, via
  `_extractSemanticMetadata()`. `self.location` is never touched by that path. So today's ReID
  gallery stores the embedding vector plus generic semantic metadata — camera, timestamp, and
  bounding box never make it in.
- One encouraging detail: the camera ID isn't even missing from the codebase —
  `_extractCameraId()` already exists and already extracts it, but today it's wired only to a
  metrics counter (`CameraRegistry.recordEmbeddingObserved`), not to the ReID write. So this
  isn't "invent new tracking data" — it's "connect two things that already exist
  (`_extractCameraId()` and `self.location`'s timestamp/bbox) to a write that already happens."

**Two changes on the ReID-service side, not one:**

1. **Write path:** attach `camera_id` and timestamp (and likely bounding box) to every descriptor
   write, sourced from the two existing-but-unwired pieces above.
2. **Query shape:** a new "give me every appearance for this gid, ordered by time" query —
   different from today's `getPersistedAttributes`, which is deliberately *latest-only*.

**Open questions to settle before sizing this for real:**

- **Retention.** "Entire session until it exits" is fine within the general gallery's existing
  24h TTL if "session" means "currently in-store or just left." If it needs to answer for a
  session from days ago, that's a direct conflict with the general gallery being deliberately
  ephemeral (same tension flagged for POI in 5.9).
- **Granularity.** Camera + timestamp is enough for a time window per camera. If precise frame
  number or bounding box is needed per sighting, that's more data per write.

**The other two-thirds of this ask are unscoped from here:**

- **Stream Manager** — turning a list of (camera, time window) into actual stitched, playable
  video. Nothing in any code reviewed so far touches video, RTSP, clips, or frame storage — this
  is very plausibly the majority of the real cost, and can't be responsibly sized without someone
  who owns that service in the room.
- **UI** — the click-through from a 2D track to a session page. Small in isolation, sequenced
  after both APIs above have a settled contract.

**Recommendation for what actually goes to CCB.** Don't submit one lump number. The ReID-service
piece above is genuinely scopeable (roughly 1–2 sprints for one engineer). Stream Manager is not
yet scopeable at all. Propose the CCB submission itself request a short joint discovery session
with Stream Manager's owner before a total estimate is quoted.

---

## 6. Alternatives Considered

| Alternative | Considered for | Outcome |
| --- | --- | --- |
| Controller-embedded correlation (checking the POI set inside `UUIDManager`'s existing per-frame loop) | POI-to-tracking correlation (5.4) | **Rejected.** Cheapest and lowest-latency, but reintroduces ReID-specific logic into the controller at the exact point separation is trying to remove it from. |
| Reusing `DATA_EXTERNAL` as-is for the correlation daemon's embedding feed | Correlation data source (5.4) | **Open, not yet decided.** Weighed against a second, dedicated publish path decoupled from `_hierarchyReidPublishPolicy`'s unrelated gating. |

## 7. Rollout / Migration Plan

Unlike a phased architectural migration, the sections above don't have a hard dependency order —
each is closer to an independent epic than a sequential phase. That said, a few real sequencing
dependencies exist and are worth respecting:

- **Authentication/authorization (Section 9) should be decided before any write-capable endpoint
  ships** — POI enrollment (5.3) and Deletion (5.6) are the first network-reachable, write-capable
  surfaces this service will have, and retrofitting auth after they're built is worse than
  deciding it first.
- **TTL/eviction control (5.7) depends on POI enrollment (5.3) and Gallery/collection management
  (5.5) existing first** — there's nothing to set a per-collection policy on until POI
  collections exist and are visible.
- **The trajectory export API (5.10) depends on the separation work in
  `reid-service-extraction-proposal.md` being stable**, and on a joint discovery session with
  Stream Manager before any total estimate is quoted — it should not be scheduled ahead of either.

Recommend treating each remaining subsection as its own small, independently schedulable story,
prioritized against whichever SLP epic
([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) or
[Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120)) is closer to
needing it.

## 8. Testing & Monitoring

**Testing.** New adapter capability (per-collection TTL overrides, count/list support in both
backends per 5.5, the new trajectory write/query shape per 5.10) should be tested the same way
the existing `VDMSDatabase`/`QdrantDatabase` adapters already are — unit tests per backend,
exercised through the shared `ReIDDatabase` contract so behavior stays identical across backends.

**Monitoring.** `latency_metrics.py` already establishes the pattern every new metric here should
follow: raw values to an OTel histogram/gauge, not just a REST response for humans to poll.
Specifically:
- `Gallery_Size_Active_Persons` / `POI_Gallery_Size` as OTel gauges tagged by collection/scene
  (5.5), feeding the performance-tools `GalleryExtractor` both SLP epics already name.
- `POI_Match_Latency_ms` tracked independently from the general tracking pipeline's
  `ReID_Match_Latency_ms` (5.4), owned by the correlation daemon rather than `reid-service`
  itself.

## 9. Open Questions

- **Enrollment embedding extraction.** Who runs image → embedding extraction for a one-off POI
  enrollment — a spun-up/torn-down DL Streamer pipeline, or a lightweight synchronous extraction
  API? (5.3)
- **Correlation data feed.** Reuse the existing `DATA_EXTERNAL` MQTT topic as-is for the
  correlation daemon (inheriting its rate limit and unrelated hierarchy write-ownership gating),
  or add a second, dedicated publish path? (5.4)
- **Gallery stats scoping.** Should `/collections/{name}/stats` support a `scene_id` /
  `camera_id` filter for the shared multi-hierarchy database, or is the whole-collection number
  sufficient for v1? (5.5)
- **AuthN/authZ mechanism.** mTLS (reusing the existing VDMS client-cert pattern in
  `reid_env.py`) vs. an API key (as already supported by the Qdrant adapter), or both. Needs
  deciding before POI enrollment/deletion ship — see Section 7.
- **Host/disk loss risk acceptance.** Is protection against container-lifecycle events (a
  persistent volume) sufficient for POI, or does the residual host/disk-loss risk need to be
  explicitly addressed? (5.9)
- **Write acknowledgment semantics for POI enrollment.** Does `POST /poi` need confirmed-write
  semantics stricter than the general gallery's tolerant partial-write behavior? (5.9)
- **Backup/export mechanism.** Is an explicit POI export/backup capability needed beyond the
  persistent volume, and does it double as the VDMS→Qdrant migration mechanism? (5.9)
- **General-gallery compliance/erasure mechanism.** If a right-to-erasure need against the
  general gallery becomes real, is the existing 24h TTL sufficient, or does it need its own
  distinct, explicitly-scoped mechanism outside this API? (5.6)
- **Trajectory retention window.** Does "entire session" mean "currently in-store or just left"
  (fits the existing 24h TTL) or does it need to reach further back — directly conflicting with
  the general gallery's deliberate ephemerality? (5.10)
- **Trajectory data granularity.** Is camera + timestamp sufficient per sighting, or does Stream
  Manager need frame number / bounding box for precise seek and stitch accuracy? (5.10)
- **Stream Manager and UI scope for trajectory export.** Both remain entirely unscoped pending a
  joint discovery session with their respective owners. (5.10)

## 10. References

- [Epic #221 — SLP: Person of Interest Re-Identification & Alerting](https://github.com/intel-retail/loss-prevention/issues/221)
- [Epic #120 — SLP: Storewide Suspicious Activity Detection & Multi-Camera Tracking with VLM Recall](https://github.com/intel-retail/storewide-loss-prevention/issues/120)