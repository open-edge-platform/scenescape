# Design Document: ReID Service — API & Capability Design

- **Author(s)**: Derrick Addo
- **Date**: 2026-09-08
- **Status**: `Proposed`

---

## 1. Overview

This document specifies the API and capability surface of `reid-service` as a standalone
component. It builds directly on the **ReID Service Extraction proposal**
([`reid-service-extraction.md`](./reid-service-extraction.md)) — the design that pulls ReID out of the controller into
its own service — and picks up where that proposal leaves off: it establishes *that* ReID becomes
a separate service (and, per its alignment with **ADR 13**, how it gets its data — the Tracker
Service's MQTT track-stream, consumed directly, with matching/writing handled internally); this
document defines *what that service's externally-callable API looks like*, end to end. That
includes two things that are easy to conflate but need to be kept distinct:

- **Baseline surface (Section 5.1):** the endpoints needed just to expose today's in-process
  `ReIDDatabase` contract (`reid.py`) over a network transport at all, for callers other than
  `reid-service` itself — there is currently no HTTP/gRPC front door onto any of it.
- **New capability (Sections 5.2–5.11):** the POI enrollment/matching/alerting flow and related
  gallery-management, deletion, TTL, schema-negotiation, and trajectory-export capabilities the
  SLP epics ([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) — POI
  Re-ID & Alerting, [Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120)
  — Storewide Suspicious Activity) call for but explicitly leave as future/out-of-scope work.

Priority and exact shape within the "new capability" bucket are open; that part is meant to give
the team something concrete to react to, not a committed backlog. The baseline surface is not
optional in the same way — some version of it has to exist for `reid-service` to be a service at
all.

## 2. Goals

- **Define the baseline transport, not just the extensions.** Since `reid-service` doesn't exist
  yet as a standalone deployable, specify the endpoints needed to expose the existing
  `ReIDDatabase` contract (query, write, schema metadata) over the network — the foundation
  everything else in this document sits on top of.
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
  ships — POI enrollment (5.4) and Deletion (5.7) are the write-capable endpoints this applies
  to. The general/tracking gallery's write path (5.1) isn't an endpoint in this API at all, but
  the trust boundary on *its* input — `reid-service`'s MQTT subscription to the Tracker Service's
  stream — deserves the same scrutiny; see Section 9.
- **Define the trajectory-export API's contract** (request/response shape and the write-path
  change it depends on), so a future CCB submission starts from an honest breakdown of what's
  known vs. unknown rather than a guessed estimate. Phasing (Section 7) determines when this
  ships, not whether it's specified here.

## 3. Non-Goals

- **Writing to or deleting from the general/tracking gallery via this API.** There is no such
  path — see 5.1: `reid-service` consumes the Tracker Service's MQTT stream directly for the live
  tracking loop, and this API exposes no write endpoint for it at all.
- **Image-to-embedding extraction/inference.** `reid-service`'s job stays storage and search;
  running the ReID model to turn an image into an embedding happens outside it, same as today.
- **Stream Manager's internal video/clip API.** Referenced only where it bounds the trajectory
  discussion (5.11); its design is owned by the Stream Manager team.
- **UI implementation** of the 2D-track click-through or any other frontend work — separate
  codebase, out of scope here.
- **Wire-level schema (OpenAPI/proto) for any endpoint below**, including the baseline surface
  and trajectory export. This document specifies shape and behavior; exact request/response
  schemas are an implementation-time detail.
- **A final decision on authN/authZ mechanism, or on the DATA_EXTERNAL-reuse-vs-dedicated-topic
  question for correlation.** Both are deliberately left as open questions (Section 9), not
  resolved here.

## 4. Background / Context

### 4.0 Relationship to the ReID Service Extraction proposal

The **ReID Service Extraction proposal** ([`reid-service-extraction.md`](./reid-service-extraction.md)) decided that
ReID logic — currently living inside the controller — becomes its own standalone service,
`reid-service`, and, aligning with **ADR 13 (Controller Breakdown into Functionality-Aligned
Microservices, `Accepted`)**, that `reid-service` gets its live tracking data by consuming the
Tracker Service's MQTT stream directly rather than being called by a controller. That decision is
a prerequisite for everything below: there is no existing `reid-service` deployment today, and
none of the endpoints in this document exist in any network-reachable form. `reid.py`'s
`ReIDDatabase` contract is real and stable, but it has only ever been called **in-process** by the
controller. This document is the first place an externally-callable transport (HTTP/gRPC) gets
defined for the parts of it meant for callers other than `reid-service` itself — both for the
existing contract (5.1) and for the new POI-driven capability (5.2 onward). The general/tracking
gallery's write path is explicitly *not* part of that externally-callable transport — see 5.1.

### 4.1 What `reid-service` already provides

`reid.py`'s `ReIDDatabase` is already a clean, backend-agnostic abstract contract —
`connect()`, `addEntry()`, `getPersistedAttributes()`, `findMatches()`, `findSchemaMetadata()`,
`ensureSchema()`, `purgeExpired()`, `retentionEnabled()` — implemented identically by both
`VDMSDatabase` and `QdrantDatabase`. Section 5.1 below defines how this contract gets exposed as
an API for the first time; everything after that is additive to it. `addEntry` was designed
around the tracking pipeline: every call carries an `rvid` (motion-tracker ID) and happens as a
side effect of a track being observed. Nothing in the current contract has any notion of "POI," a
second gallery, deletion, or per-appearance history — all of that is new surface area, described
section by section below.

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

### 5.1 Baseline service API surface

Before any POI-specific capability can exist, `reid-service` needs *some* network-reachable
version of the contract it already has in-process — for callers other than `reid-service` itself.
This is the part of the design that Section 5.2 onward assumes already exists; it's specified
explicitly here rather than left implicit, since — unlike the POI work — there is no existing
deployment to point to as "already covers this."

**The general/tracking gallery's write path is not part of this baseline surface — it has no
endpoint at all.** Per the ReID Service Extraction proposal's current design (aligned with
ADR 13), `reid-service` doesn't get written to over an API for the live tracking loop; it consumes
the Tracker Service's MQTT track-stream directly and performs matching and writing internally, as
part of its own stream processing. There is no controller (or anything else) calling a write
endpoint for this path, so there's nothing here to lock down to a specific caller — the access
question that mattered under the earlier client/RPC design doesn't apply. Non-Goal in Section 3
still holds (this API does not let arbitrary callers write to the general gallery); it's just
enforced by there being no such endpoint, rather than by restricting one.

**Proposed baseline endpoints** — the externally-callable surface, each a thin transport wrapper
around the corresponding `ReIDDatabase` method, with no behavior change from today's in-process
semantics:

- **Read: mirrors `findMatches`.** Covered in full in 5.3 (Query API), since exposing this to
  callers *beyond* the live tracking loop — investigator tooling, VLM recall, POI matching — is
  itself one of this document's goals, not just a transport detail. Whether this rides on gRPC/REST
  or MQTT request/reply is an open question inherited from the extraction proposal — not settled
  here (see Section 9).
- **Read: mirrors `findSchemaMetadata`.** Lets a caller confirm a collection's existence,
  dimensions, and similarity metric before querying — needed once external callers exist, since
  they can't assume the schema the way the internal stream-consumption path can.
- **Admin (optional, internal use): mirrors `purgeExpired`.** `reid-service` schedules its own
  purges internally per the extraction proposal — this endpoint isn't required for that to work.
  It exists only as an optional operational hook (manual trigger during incident response,
  liveness/maintenance tooling), not a load-bearing part of the design.
- **Health/readiness.** Standard for any deployable service — not present in the in-process
  contract at all, since "is `reid.py` reachable" was never a meaningful question before now.

**Why this matters for everything downstream.** Sections 5.2–5.11 describe new capability in
terms of "the API" as though a baseline already exists. It doesn't yet. Building this baseline is
what turns `reid-service` from "a module the controller imports" into an actual service other
things can call — the POI/gallery/trajectory work is what that service does once it exists, not
what makes it exist in the first place. Note that this baseline is entirely about the
externally-callable surface; the live tracking loop's own data path (Tracker Service → MQTT →
`reid-service`) isn't part of "the API" in the sense this document uses that term at all.

### 5.2 Design principles (cross-cutting)

Decisions carried across every subsection below, settled in discussion rather than sketched
per-endpoint:

- **Writes are POI-gallery-only — the general gallery has no writer in this API at all.** Per
  5.1, the general/tracking gallery is written to by `reid-service` consuming the Tracker
  Service's MQTT stream directly, not by any endpoint in this API. All insert, update, and delete
  operations this API exposes — everything in 5.4 (POI enrollment) and 5.7 (deletion) — apply
  **only to the POI gallery**. To be unambiguous about what that means per operation:
  - **Insert** (5.4, `POST /poi`) — POI gallery only. There is no "insert a general tracking
    descriptor" endpoint in this API at all; that path is `reid-service`'s own internal stream
    consumption, not something this API exposes.
  - **Update** (5.4, `PATCH /poi/{poi_id}` and appending reference embeddings) — POI gallery
    only. The general gallery has no update concept in this API at all.
  - **Delete** (5.7) — POI gallery only. See that section for why general-gallery deletion is
    explicitly not part of this API, and how compliance/erasure requests against the general
    gallery are handled instead.
  - **Query** (5.3, `findMatches`) — the one operation that reads from _both_ galleries.
    Read-only either way; querying the general gallery through this API never writes to it.

  Nothing in the Query API, Deletion API, or Gallery/collection management subsections should be
  read as applying to the general gallery unless explicitly called out — and after this
  subsection, nothing does.

- **POI records are persisted, not just long-TTL.** A POI record isn't "the same as the general
  gallery but with a bigger number" — it's meant to survive indefinitely by design, distinct
  from the general gallery's inherently ephemeral, TTL-bound nature. See 5.10 for what
  "persisted" actually needs to mean beyond disabling TTL.
- **`poi_id` is always server-generated.** Enrollment does not accept a client-supplied ID — the
  service mints the identifier and returns it in the response.

### 5.3 Query API as a first-class endpoint

`findMatches` exists internally today but is only ever called from inside the tracking
pipeline. Exposing it directly over the service API (building on the baseline transport in 5.1)
would let investigator tools, a
[VLM-recall service (Epic #120)](https://github.com/intel-retail/storewide-loss-prevention/issues/120),
or a [POI-matching UI (Epic #221)](https://github.com/intel-retail/loss-prevention/issues/221)
query the gallery without routing through the controller at all. Straightforward extension of
existing internals — no new adapter logic needed, just an HTTP/gRPC front door onto `findMatches`
with the same TIER 1 constraints (`reid_constraints.py`) exposed as query parameters.

### 5.4 Explicit POI enrollment endpoint (insert & update — POI gallery only)

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
vs. hard delete via 5.7).

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
  The Query API (5.3) should be able to target "the POI set" vs. "the general set" explicitly
  rather than inferring it from `object_type` alone.

**Validation.** Reuse what already exists rather than re-inventing it: `prepareReidDict` /
`prepareReidVector` in `reid.py` already validate shape, finiteness, and (optionally)
normalization of an embedding before it's written. The enrollment endpoint should run enrollment
images through the same validation path and reject bad embeddings with the same class of error
the pipeline already uses (`ReidNoValidVectorsError`), rather than defining new validation rules.

### 5.5 POI-to-tracking correlation and alert delivery

**Decision — correlation runs outside the controller, as a standalone daemon.** A separate
process consumes `reid-service` purely as an API client — the same way any other future tool
would (per the investigator/VLM-recall use case in 5.3) — and does the correlation itself,
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

### 5.6 Gallery/collection management API

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

### 5.7 Deletion API (POI gallery only)

Doesn't exist in any form today — `ReIDDatabase` has no `deleteEntry`. Scoped to the POI gallery
only, per 5.2. Needed for:

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

### 5.8 Runtime TTL / eviction control

`descriptor_ttl_secs` and the purge interval are static env vars fixed at process start today.
Two gaps once 5.4 and 5.6 exist:

- **Per-collection TTL.** POI records are meant to be persisted, not merely long-TTL (5.2) — this
  needs to be settable per collection, not just per process.
- **Pressure-based eviction.** Current bounding is purely time-based, so storage can still grow
  within the TTL window under heavy ingest. Proposed: an eviction mode that deletes oldest-first
  once a collection crosses a configured size/storage cap, independent of age — paired with, not
  replacing, the existing TTL.

### 5.9 Explicit schema/version negotiation endpoint

Today, embedding dimensions are inferred lazily from the first vector written
(`_ensureReIDDimensions` → `ensureSchema`). That's reasonable when the only caller is the
controller, which always writes before it needs to query. Once other tools can call the service
directly (the investigator/VLM-recall use case in 5.3 doesn't necessarily write before it
queries), an explicit "declare dimensions/metric for this collection" call becomes more useful
than relying on implicit inference from whichever caller happens to write first.

### 5.10 POI database persistence

"Persisted" got compressed into a one-line design principle in 5.2 — it's a bigger topic than
that line covers, and it matters more for POI than it does for the general gallery. If the
general gallery loses data, it's not really a loss — the gallery is continuously repopulated by
live tracking. POI is the opposite: there's no automatic recovery. A security operator has to
notice a POI silently isn't being watched for anymore, then manually re-enroll.

**The immediate, concrete answer: a persistent volume.** Attach a Docker volume (or, in
Kubernetes, a `PersistentVolumeClaim`) to wherever the POI collection's backend data lives, so a
container restart, image update, or pod recreation doesn't wipe it. Nothing in `vdms_adapter.py`
or `qdrant_adapter.py` needs to change for this — it's a Compose/Helm deployment decision. This is
the concrete, buildable requirement: **the POI collection's storage must be backed by a
persistent volume**, verified independently of whatever collection/retention API design (5.6,
5.8) gets layered on top of it. This alone covers the most common failure mode and is enough to
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
  today — 5.6's gallery-management API only sketched stats, not a dump.
- **Migration continuity.** Ties back to the VDMS→Qdrant migration motivating the original
  separation work ([`reid-service-extraction.md`](./reid-service-extraction.md)). A volume holds a backend's own on-disk
  format — it doesn't cross a VDMS-to-Qdrant swap by itself. The general gallery doesn't need a
  migration path; the POI gallery does, or every POI has to be re-enrolled by hand. The same
  export/import capability as the backup question above would serve both needs.

### 5.11 Trajectory export API

The ability to export a moving object's full trajectory by `gid` — every camera it was seen on, in
order, until it exits the scene — with frames stitchable into a video, clickable from the 2D track
UI, and exposed via API. Originally raised informally; specified here as an actual API contract
rather than left as an open discussion, per review feedback that phasing (Section 7) should decide
*when* this ships, not whether its shape gets defined now. This spans three separable pieces with
very different amounts of known scope; only the first is `reid-service`'s to own.

**What's actually being asked, stripped down.** Not the video itself — that's Stream Manager's
job. What ReID needs to produce is the _list of sightings_ that tells Stream Manager which
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

**Defined API contract.**

- **Write-path change:** the general/tracking gallery's write path — `reid-service` consuming the
  Tracker Service's MQTT stream directly, per 5.1 — additionally needs `camera_id`, `timestamp`,
  and (pending the granularity decision below) `bounding_box` in the incoming stream payload,
  alongside the existing embedding and semantic metadata, sourced from `_extractCameraId()` and
  `self.location`'s `Chronoloc` entries respectively. This is a change to what the Tracker
  Service's stream carries and what `reid-service` persists from it, not a new endpoint — there
  is no write endpoint for this path at all (5.1).
- **New read endpoint:** `GET /trajectories/{gid}` — returns the ordered list of sightings for a
  `gid`: one entry per descriptor write, each with `camera_id`, `timestamp`, and bounding box,
  ordered chronologically. This is a different query shape from today's `getPersistedAttributes`,
  which is deliberately _latest-only_; it's a new method on the `ReIDDatabase` contract, not a
  reinterpretation of an existing one.

**Open questions to settle before sizing this for real:**

- **Retention.** "Entire session until it exits" is fine within the general gallery's existing
  24h TTL if "session" means "currently in-store or just left." If it needs to answer for a
  session from days ago, that's a direct conflict with the general gallery being deliberately
  ephemeral (same tension flagged for POI in 5.10).
- **Granularity.** Camera + timestamp is enough for a time window per camera. If precise frame
  number or bounding box is needed per sighting, that's more data per write.

**The other two-thirds of this ask remain unscoped from here, deliberately:**

- **Stream Manager** — turning a list of (camera, time window) into actual stitched, playable
  video. Nothing in any code reviewed so far touches video, RTSP, clips, or frame storage — this
  is very plausibly the majority of the real cost, and can't be responsibly sized without someone
  who owns that service in the room.
- **UI** — the click-through from a 2D track to a session page. Small in isolation, sequenced
  after both APIs above have a settled contract.

**Recommendation for what actually goes to CCB.** Don't submit one lump number. The `reid-service`
piece above is genuinely scopeable (roughly 1–2 sprints for one engineer) and is now specified
above rather than left as an open discussion. Stream Manager is not yet scopeable at all. Propose
the CCB submission itself request a short joint discovery session with Stream Manager's owner
before a total estimate is quoted.

---

## 6. Alternatives Considered

| Alternative                                                                                           | Considered for                    | Outcome                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Controller-embedded correlation (checking the POI set inside `UUIDManager`'s existing per-frame loop) | POI-to-tracking correlation (5.5) | **Rejected.** Cheapest and lowest-latency, but reintroduces ReID-specific logic into the controller at the exact point separation is trying to remove it from. |
| Reusing `DATA_EXTERNAL` as-is for the correlation daemon's embedding feed                             | Correlation data source (5.5)     | **Open, not yet decided.** Weighed against a second, dedicated publish path decoupled from `_hierarchyReidPublishPolicy`'s unrelated gating.                   |

## 7. Rollout / Migration Plan

Unlike a phased architectural migration, the sections above don't have a hard dependency order —
each is closer to an independent epic than a sequential phase. That said, a few real sequencing
dependencies exist and are worth respecting:

- **The baseline service API (5.1) has to exist before anything else in this document can ship**
  — it's the transport every other section assumes.
- **Authentication/authorization (Section 9) should be decided before any write-capable endpoint
  ships** — POI enrollment (5.4) and Deletion (5.7) are the write-capable endpoints this API
  exposes, and retrofitting auth after they're built is worse than deciding it first. The
  general/tracking gallery's write path (5.1) isn't an endpoint this applies to, but its own trust
  boundary — `reid-service`'s MQTT subscription to the Tracker Service — needs the equivalent
  scrutiny on its own track (Section 9).
- **TTL/eviction control (5.8) depends on POI enrollment (5.4) and Gallery/collection management
  (5.6) existing first** — there's nothing to set a per-collection policy on until POI
  collections exist and are visible.
- **The trajectory export API (5.11) depends on the design in
  [`reid-service-extraction.md`](./reid-service-extraction.md) being stable**, and on a joint discovery session with
  Stream Manager before any total estimate is quoted — it should not be scheduled ahead of either.
  Its API contract is defined now (5.11); this dependency governs timing, not definition.

Recommend treating each remaining subsection as its own small, independently schedulable story,
prioritized against whichever SLP epic
([Epic #221](https://github.com/intel-retail/loss-prevention/issues/221) or
[Epic #120](https://github.com/intel-retail/storewide-loss-prevention/issues/120)) is closer to
needing it.

## 8. Testing & Monitoring

**Testing.** New adapter capability (per-collection TTL overrides, count/list support in both
backends per 5.6, the new trajectory write/query shape per 5.11) should be tested the same way
the existing `VDMSDatabase`/`QdrantDatabase` adapters already are — unit tests per backend,
exercised through the shared `ReIDDatabase` contract so behavior stays identical across backends.
The baseline API (5.1) should additionally get contract/integration tests at the transport layer,
since it's the first place any of this is network-reachable at all.

**Monitoring.** `latency_metrics.py` already establishes the pattern every new metric here should
follow: raw values to an OTel histogram/gauge, not just a REST response for humans to poll.
Specifically:

- `Gallery_Size_Active_Persons` / `POI_Gallery_Size` as OTel gauges tagged by collection/scene
  (5.6), feeding the performance-tools `GalleryExtractor` both SLP epics already name.
- `POI_Match_Latency_ms` tracked independently from the general tracking pipeline's
  `ReID_Match_Latency_ms` (5.5), owned by the correlation daemon rather than `reid-service`
  itself.

## 9. Open Questions

- **Enrollment embedding extraction.** Who runs image → embedding extraction for a one-off POI
  enrollment — a spun-up/torn-down DL Streamer pipeline, or a lightweight synchronous extraction
  API? (5.4)
- **Correlation data feed.** Reuse the existing `DATA_EXTERNAL` MQTT topic as-is for the
  correlation daemon (inheriting its rate limit and unrelated hierarchy write-ownership gating),
  or add a second, dedicated publish path? (5.5)
- **Gallery stats scoping.** Should `/collections/{name}/stats` support a `scene_id` /
  `camera_id` filter for the shared multi-hierarchy database, or is the whole-collection number
  sufficient for v1? (5.6)
- **Host/disk loss risk acceptance.** Is protection against container-lifecycle events (a
  persistent volume) sufficient for POI, or does the residual host/disk-loss risk need to be
  explicitly addressed? (5.10)
- **Write acknowledgment semantics for POI enrollment.** Does `POST /poi` need confirmed-write
  semantics stricter than the general gallery's tolerant partial-write behavior? (5.10)
- **Backup/export mechanism.** Is an explicit POI export/backup capability needed beyond the
  persistent volume, and does it double as the VDMS→Qdrant migration mechanism? (5.10)
- **General-gallery compliance/erasure mechanism.** If a right-to-erasure need against the
  general gallery becomes real, is the existing 24h TTL sufficient, or does it need its own
  distinct, explicitly-scoped mechanism outside this API? (5.7)
- **Trajectory retention window.** Does "entire session" mean "currently in-store or just left"
  (fits the existing 24h TTL) or does it need to reach further back — directly conflicting with
  the general gallery's deliberate ephemerality? (5.11)
- **Trajectory data granularity.** Is camera + timestamp sufficient per sighting, or does Stream
  Manager need frame number / bounding box for precise seek and stitch accuracy? (5.11)
- **Trust boundary for `reid-service`'s MQTT subscription to the Tracker Service.** Since the
  general/tracking gallery has no write endpoint (5.1) — `reid-service` gets that data by
  subscribing to the Tracker Service's MQTT stream directly — what secures that subscription
  (broker-level ACLs, topic-level auth, network policy, or a combination)? This is a different
  question from the endpoint authN/authZ decision above, since there's no endpoint here to
  authenticate a caller against.
- **Transport for the Query API (5.3): gRPC/REST or MQTT request/reply.** Inherited from the
  extraction proposal — gRPC/REST is the current leaning (and what this document assumes
  throughout), but MQTT hasn't been ruled out. Not decided here; see
  [`reid-service-extraction.md`](./reid-service-extraction.md).

## 10. References

- **ReID Service Extraction proposal** ([`reid-service-extraction.md`](./reid-service-extraction.md)) — the design this
  document builds on; also the source of the ADR 13 alignment referenced throughout.
- **ADR 13 — Controller Breakdown into Functionality-Aligned Microservices** (`Accepted`) — the
  accepted architectural decision that the extraction proposal aligns with.
- [Epic #221 — SLP: Person of Interest Re-Identification & Alerting](https://github.com/intel-retail/loss-prevention/issues/221)
- [Epic #120 — SLP: Storewide Suspicious Activity Detection & Multi-Camera Tracking with VLM Recall](https://github.com/intel-retail/storewide-loss-prevention/issues/120)