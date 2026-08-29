<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR 16: Unified External-Source Ingestion Contract for the Scene Controller

- **Author(s)**: Sarat Poluri
- **Date**: 2026-07-21 (publisher-centric binding and scene/service registry target updated
  2026-07-22; remote-child hierarchy export signal updated 2026-08-29)
- **Status**: `Accepted`
- **Related**: [ADR 13 (proposed, PR #1526) — Controller Breakdown into Functionality-Aligned Microservices](https://github.com/open-edge-platform/scenescape/pull/1526/files) (see [Relationship to ADR 13](#relationship-to-adr-13-controller-breakdown-and-known-deviation) below)

## Context

Before this work, `scenescape/external/{scene_id}/{thing_type}` only carried one contract: a
configured **child scene** publishing its own tracked objects, where `{scene_id}` identified the
_sending_ child and the controller looked up that child's statically configured parent scene and
`cameraPose` to transform its objects. There was no way for a **dynamic** external source — a
physical agent (drone, robot, forklift), a UWB/RTLS positioning system, or another positioning
service — to publish observations directly into a scene, because those sources have no
preconfigured static camera pose and are not modeled as child scenes.

We needed a single, versioned contract that:

- Lets dynamic sources publish object observations, expressed in their own local frame, into a
  scene, alongside a pose that lets the controller resolve source-local coordinates into
  scene-local coordinates.
- Preserves the legacy configured-child-scene behavior and aligns dynamic agents with the same
  **publisher-centric** topic rule (publish under own id; consumers bind relationships).
- Does **not** require the Scene Controller to maintain a per-publisher lookup/translation cache
  mapping each source's native ID scheme, coordinate convention, or track-continuity semantics
  into a canonical form. That translation burden belongs on the publishing side (the agent or an
  adapter it runs behind), not on a shared, multi-tenant controller that must scale to many
  concurrent, heterogeneous publishers.
- Reuses the existing tracking, persistent-attribute, sensor, ROI, and analytics pipeline instead
  of building a parallel path for external sources.

An early shipping shape also treated the topic as a **scene inbox** (`{scene_id}` = target scene,
every scene self-subscribes). That conflicts with hierarchy (same path, publisher id) and cannot
grow into proximity-based attachment without forcing every agent to choose a scene. This ADR
records the payload/identity contract, **publisher-centric topics**, and **consumer-side binding**,
including the target architecture in which a discoverable **scene/service registry** (spatial
index) tells the **binder** which scenes to attach — without changing the agent publish path.

## Decision

### Publisher-centric topics and consumer-side binding

Canonical external topic:

```text
scenescape/external/{publisher_id}/{thing_type}
```

- `{publisher_id}` identifies the **sender** (configured child scene uid, agent id, UWB hub id,
  positioning service id, etc.). It never means “ingest into this scene.”
- When the payload includes `source_id`, it **MUST equal** `{publisher_id}`. Mismatches are
  rejected (logged and dropped). Once the topic path is treated as fully authoritative,
  `source_id` may become optional in a later revision; today it remains required by schema and
  must match the path.
- A publisher does not need to know parent or scene topology to publish.

**Relationships are consumer-side bindings**, not destination topics:

```text
(scene_uid, publisher_id) → {
  reason: static_child | spatial | manual,
  transform_policy: child_cameraPose | wgs84_via_scene_trs | trusted_scene_pose,
  retrack: bool,   # hierarchy / future only — see below
  last_seen, expires_at
}
```

- **Static (hierarchy today):** parent lists children → controller/binder applies the configured
  child transform. Hierarchy publishes omit `source_id`. Per-child **`retrack` is configurable**
  on the parent↔child relationship (same as before this ADR).
- **Manual / ops:** operator or API (or `CONTROLLER_EXTERNAL_SOURCE_BINDINGS`) attaches a
  publisher id to a scene without hierarchy rows.
- **Spatial (registry-driven):** a scene/service registry decides membership; the binder updates
  its subscription/ingest list accordingly (see below).

**Retrack for dynamic external sources is not binding-configurable today.**
`_handleExternalSourceObject()` always constructs the sender with `retrack=False` (trusted
identity by default). The `retrack` field on the binding record above is reserved for hierarchy
and for a possible future per-object / object-type opt-out (see Future Work); it is **not** read
for `source_id` publishers in the current implementation.

Agents authenticate to the MQTT broker and publish under their own id. Scene attachment is
always binder-side.

### Co-observation with cameras and scene sensors (live behavior)

External objects and camera-tracked objects are **independent tracks** in the same scene. If a
robot and a scene camera both observe the same physical person, the scene may contain both the
external source’s trusted `id` and a separately assigned camera/ReID `gid`. Both participate in
ROI, tripwire, and sensor-area analytics once ingested. There is **no** fusion or deduplication
between camera and external paths today (see Future Work).

### Scene / service registry (target architecture)

The **registry** is a logically named, network-discoverable service (for example via DNS-SD /
mDNS or site DNS — concrete discovery mechanism is deployment choice). It is aware of multiple
scenes and their geospatial footprints, and uses **spatial indexing** to answer: given a
publisher’s geopose (and policy), which scene(s) should be bound?

Critical split of responsibility:

| Component                                             | Does                                                                                                                                         | Does not                                                                 |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Agent / publisher**                                 | Discovers the fabric (broker and/or registry by logical name); authenticates (same-CA base case); publishes only under `external/{its_id}/…` | Choose a scene topic path; encode scene membership in MQTT destination   |
| **Registry**                                          | Holds scene catalog + spatial index; resolves publisher pose → candidate scene set (overlap, handoff, priority policy)                       | Require the agent to republish to a different topic                      |
| **Binder** (controller today, or dedicated component) | Applies registry (or static/manual) results: upsert/drop bindings; update MQTT subscription / ingest routing                                 | Invent scene topology independently of registry once registry is present |

The registry therefore determines **which scenes the binder should interact with** to keep its
subscription list correct. It does **not** tell the agent “publish to scene X’s inbox.”

Non-normative target flow:

```text
Agent                         Registry                      Binder / Controller
  |-- discover logical name -->|                              |
  |-- auth (same CA) --------->|                              |
  |-- PUB external/{me}/+ (pose+objects) -------------------->|
  |                            |<-- pose / membership query --|
  |                            |-- scene set (spatial index)->|
  |                            |                              |-- update bindings / SUBs
  |-- PUB detections --------------------------------------->|-- ingest into bound scenes
```

**Interim runtime (until registry ships).** The controller **wildcard-subscribes** to
`external/+/+` (hears every publisher that can authenticate to the broker) and attaches `wgs84`
publishers to every geo-calibrated scene (plus optional `CONTROLLER_EXTERNAL_SOURCE_BINDINGS`).
That interim auto-attach is a stand-in for registry spatial resolution, not the long-term
multi-scene policy. Standalone root scenes must not emit hierarchy echoes onto the external
topic (`publishExternalDetections` returns early when `scene.parent` is unset **and** no remote
parent has attached). A remote child is a root on its own broker; when a parent
`ChildSceneController` connects to that broker it retained-publishes
`scenescape/sys/hierarchy/parent/{child_uid}` with `attached` (and `detached` on disconnect),
and the child enables hierarchy `DATA_EXTERNAL` for that scene uid while attached.

**Subscription migration (explicit).** The long-term binder should move from the interim
wildcard to **binding-driven selective subscribe** (only `external/{publisher_id}/+` for
publishers currently bound to local scenes, plus whatever hierarchy still requires). Wildcard
remain acceptable only as a transitional convenience; ACL hardening assumes selective publish
rights on `external/{own_id}/#` and should not depend on every controller instance ingesting the
entire fabric forever.

**Trust-domain base case (same as parent/child scenes today).** Joining a Scenescape fabric
means authenticating to an MQTT broker whose certificates were issued by the **same authority**
the deployment trusts. Stronger isolation, discovery hardening, and ACL options are deferred —
see [Future Work](#future-work) — and are not required for the base case.

### Payload contract: `external_source` disambiguated by `source_id`

Messages on the external topic use the `external_source` schema
(`controller/src/schema/metadata.schema.json`) with nested `external_pose` and
`external_detection` definitions when `source_id` is present. Legacy child hierarchy publishes
(no `source_id`) remain unchanged in payload shape and parent lookup.

### Pose resolution and caching

A new `ExternalSourcePoseCache` (`controller/src/controller/external_source.py`) resolves and
caches the source-to-scene transform, keyed by `(scene.uid, source_id)`, with a default 30 s TTL:

- `reference_frame: wgs84` — a global geopose. Any source may publish it, but it is only
  resolvable when the bound scene has valid four-corner geospatial calibration
  (`Scene.trs_xyz_to_lla`); otherwise the message is rejected with
  `scene_georeference_unavailable` rather than approximated.
- `reference_frame: scene` — a pose already expressed in scene-local coordinates. This is
  privileged and only accepted from `source_id`s listed in
  `CONTROLLER_TRUSTED_POSITIONING_SOURCES`; otherwise rejected with `untrusted_scene_pose`
  (fails closed when unset).
- Messages may omit `pose` to reuse the most recent non-expired cached transform for that
  `(scene_id, source_id)` pair. A message with `pose` and empty `objects` refreshes the cache
  without ingesting observations.

### `objects[*].id` is a required, source-local reference, trusted as global identity by default

Each observation in `objects[]` must include `id`: a string the _source_ uses to correlate that
observation across its own messages (for example, a UWB tag's hardware identifier, or a robot's
local track slot).

An earlier revision of this decision required an operator to explicitly allowlist which
`source_id`s were trusted to have their `id` used as global identity
(`CONTROLLER_TRUSTED_IDENTITY_SOURCES`; superseded, see
[Trusted identity by default, with collision detection](#trusted-identity-by-default-with-collision-detection)
below). That per-source configuration requirement does not scale as the number of external
sources/integrations grows — every new source would need a deployer to explicitly register it
before its identity could be trusted. The current design instead trusts every source's `id`
directly as global identity (`gid`) **by default, with no configuration or registration step**,
protected at runtime by automatic collision detection rather than a pre-configured allowlist.

`id` was schema-optional before this feature's first revision; `MovingObject.__init__`
construction, however, unconditionally read `info['id']`. That contract mismatch only surfaced
once a real external-source payload without `id` was exercised end-to-end (see Consequences), so
the fix makes `id` required in the schema — matching the design intent — instead of adding a
silent UUID-synthesis fallback in `MovingObject`. A UWB system reporting several simultaneously
observed tags in one message is exactly the batched-multi-object case `id` exists for: each
object in the same `objects[]` array must carry a distinct `id`.

### Trusted identity by default, with collision detection

Every external-source object's `id` is trusted directly as global track identity (`gid`) by
default: `_handleExternalSourceObject()` always constructs its `SimpleNamespace` sender with
`retrack=False`, so `Scene.processSceneData()` routes the object through the existing
`already_tracked_objects` merge path (the same mechanism a configured child scene already uses
via its own per-scene `retrack` setting) instead of Scenescape's kinematic tracker/ReID
association. That path sets `gid = oid` the first time an `id` is seen and preserves that `gid`
on every subsequent message reporting the same `id` (`MovingObject.setPrevious()`), with existing
staleness pruning (`MAX_UNRELIABLE_TIME`) still applying once a source stops reporting an `id`.
No new persistence or lifecycle code was needed for this part — it is exactly the mechanism child
scenes already relied on, extended to dynamic external sources.

Trusting every source's `id` completely unconditionally would let two different sources that
happen to report the same `id` value silently merge two distinct physical objects under one
identity. `controller/src/controller/external_source.py::IdentityClaimRegistry` prevents this
without requiring any configuration: each `id` is claimed exclusively per `(scene_uid, category)`.
`_handleExternalSourceObject()` filters `jdata['objects']` through
`IdentityClaimRegistry.claim(scene.uid, detection_type, source_id, obj_id, msg_when)` before
calling `scene.processSceneData()` — an object whose claim attempt fails (a different source
currently holds a live claim on that same `id`) is dropped and logged as a rejection; the
remaining, non-colliding objects in the same message are still ingested normally. A claim expires
after the same TTL pattern used by `ExternalSourcePoseCache` (`DEFAULT_IDENTITY_CLAIM_TTL_SECONDS`),
so a source that stops publishing an `id` does not block a different source from claiming that
same `id` value indefinitely.

This is the direct resolution of the collision risk originally raised as the rationale for
requiring a pre-configured trust allowlist: instead of asking an operator to vouch for a source
ahead of time, the controller now vouches for uniqueness by construction, at message-processing
time, for every source.

**Known, explicit limitation.** Collision detection only protects against two _different_
sources colliding on the same `id` at the same time. It does not, and structurally cannot, detect
a _single_ source reusing one of its own previously-claimed `id`s for a genuinely different
physical object once that earlier claim has gone stale — for example, a robot restarting and
reissuing small integer track-slot numbers that a previous, now-expired claim also used. In that
case the reused `id` is silently accepted as a continuation of the previous object's identity.
This is the same UWB-vs-resettable-counter distinction the design has called out from the start;
it is now addressed through operational guidance (choose a persistent, unique `id` — see the Scene
Controller data-format documentation) rather than through a configuration gate, because a
configuration gate cannot detect a bad `id` scheme either — it can only be told about it in
advance, which is precisely the scaling problem this revision removes.

### Time-chunked tracking buckets external sources by `source_id`

`TimeChunkedIntelLabsTracking.trackObjects()` buckets incoming frames by a `cameraID`/`uid`
attribute read off each object's `camera`/`child` reference, exactly like it already does for
camera detections (`cameraID`) and legacy child scenes (`uid`). The `SimpleNamespace` built for
external sources in `_handleExternalSourceObject()` sets `uid=source_id`. Because external sources
always use `retrack=False`, those MovingObjects are passed in `already_tracked_objects` (not
`objects`); time chunking therefore resolves the bucket id from `already_tracked_objects` when
`objects` is empty, so per-publisher bucketing still applies.

### Camera-parameter cache refresh only applies to camera messages

`CacheManager.refreshScenesForCamParams()` assumes every inbound message is a camera detection
carrying an `id` camera identifier used to refresh cached intrinsics/distortion. External-source
messages carry `source_id`, not a camera `id`, and have no camera parameters to refresh, so
`handleMovingObjectMessage()` now skips this step for `DATA_EXTERNAL` messages.

## Relationship to ADR 13 (Controller Breakdown) and Known Deviation

[ADR 13 (proposed, PR #1526)](https://github.com/open-edge-platform/scenescape/pull/1526/files)
— "Controller Breakdown into Functionality-Aligned Microservices" — describes the target,
fully decomposed architecture: a recursive **Scene Graph** in which every sub-scene (child scene,
camera, SLAM-localized robot/drone, sensor) presents its output through the same interface a scene
exposes to its own external sources — **pose + observations**. This ADR's `external_source`
contract is a direct, present-day instance of exactly that pattern: any dynamic source publishes
`(pose, objects)` through one uniform interface, ahead of the full microservice split. Publisher-
centric topics plus consumer-side binding keep that recursive model without requiring the
publisher to know its parent. Implemented within the still-monolithic Controller rather than as a
separate Positioning/Transform/Persistence service split.

**Known deviation, now mostly addressed — trust is automatic and collision-checked, not yet
object-type-based.** ADR 13 states that identities flowing up the hierarchy "carry global
identities assigned by the shared Re-ID Service. The first global UUID assigned to an identity at
any level in the hierarchy remains stable for that identity throughout the entire hierarchy" and
separately flags, as an explicit open question, that "current retracking causes unnecessary ID
reassignment and mishandles active trackers (e.g., UWB); a decision may need to be object-type-based
rather than scene-based."

This implementation went through two revisions on the way to its current state. It originally
reproduced the ADR 13 problem exactly: `_handleExternalSourceObject()` unconditionally constructed
its source `SimpleNamespace` with `retrack=True`, so every external-source object was always
re-associated by Scenescape's own kinematic tracker/ReID path. A second revision addressed this
at the source level via a `CONTROLLER_TRUSTED_IDENTITY_SOURCES` allowlist, but that traded the
ADR 13 problem for an operational-scaling problem: every source needed explicit pre-configuration
before its identity could be trusted. The current revision (see
[Trusted identity by default, with collision detection](#trusted-identity-by-default-with-collision-detection))
removes that configuration requirement entirely: `retrack` is now always `False` for external
sources, and `IdentityClaimRegistry` provides the safety net that an allowlist previously provided,
without requiring any source to be registered in advance.

This remains a **partial** resolution of ADR 13's open question: trust/collision-checking is
applied per `(scene, category)`, not yet per-object-`category`-_and_-source combination in the
finer-grained sense ADR 13 raises (for example, a source whose `person` observations should be
identity-trusted while its `vehicle` observations from a lower-confidence secondary sensor should
still be retracked by the kinematic tracker). See [Future Work](#future-work) for that remaining
gap. Documented here as a known, intentional scoping decision, not an oversight.

## Alternatives Considered

- **Synthesize a random UUID for `oid` when `id` is omitted (keep `id` schema-optional).**
  Rejected: it would let a source send multiple simultaneous objects in one message with no way
  to disambiguate them (any of which could reasonably omit `id`), and it papers over — rather than
  enforces — the design intent that `id` is the source's own correlation reference and therefore
  required input.
- **Have the Scene Controller maintain a per-publisher ID-mapping/lookup cache** translating each
  source's native ID scheme into a canonical form. Rejected: this was an explicit design
  constraint for this work — the controller must not take on the responsibility of tracking every
  publisher's local ID namespace; that translation belongs in a source-side adapter, not in the
  shared controller.
- **Keep target-scene-in-topic as the long-term model; add a scene-discovery API for agents.**
  Rejected: every publisher must learn topology and re-target topics on handoff; hierarchy and
  dynamic agents stay on different models; proximity logic is duplicated at the edge.
- **Registry that tells the agent which scene topic to publish to.** Rejected: conflates
  discovery with destination addressing and reintroduces scene-inbox semantics. The agreed model
  is registry → **binder subscription updates**, while the agent keeps publishing under its own
  id.
- **Separate topic trees forever** (`external/scene/{id}/…` vs `external/source/{id}/…`).
  Rejected as the sole end state: preserves dual semantics. A temporary alias during migration is
  acceptable.
- **Agent publishes once and binder republishes into scene inboxes.** Rejected as end state:
  binder should drive **subscriptions** into ingest, not rewrite destination topics.
- **Let the source-supplied `id` drive global track continuity by always retracking** (historical
  first revision). Superseded by default trusted identity plus collision detection.

## Consequences

### Positive

- One payload contract for dynamic external sources (pose + objects, trusted `id` with collision
  detection) reused by the existing analytics pipeline.
- One topic rule for children and dynamic agents; publishers need not know parents; multi-scene
  attachment lives in binder policy (eventually registry-driven) without changing agent publish
  paths.
- Removes the structural cause of root-scene self-echo (no scene inbox self-subscribe);
  unattached roots still skip hierarchy `DATA_EXTERNAL`, while remote children export only after
  a retained parent-attach signal on their broker.
- Trust-domain base case matches existing parent/child MQTT (same issuing authority).
- Clear separation: discoverable registry (spatial index) vs binder (subscriptions) vs publisher
  (own-id telemetry) aligns with common service-discovery + geo-directory practice.

### Negative

- Publishers must always include a per-observation `id`, even for the simplest single-point-object
  case; this is a small increase in required payload verbosity versus letting it be inferred.
- Early external-source seams with camera-only code required fixes found mainly by end-to-end
  MQTT tests: schema/`MovingObject` required `id`; camera-parameter cache refresh had to skip
  `DATA_EXTERNAL`; and time-chunked bucketing initially read only `objects[0].camera`, so
  `retrack=False` external batches (passed via `already_tracked_objects` even though
  `uid=source_id` was set) were mis-bucketed under the empty-frame sentinel until
  `TimeChunkedIntelLabsTracking` also resolved ids from `already_tracked_objects`.
- Camera and external observations of the same physical object are not fused: deployers may see
  duplicate tracks and duplicate analytics events until cross-source association lands.
- The trust boundary for `reference_frame: scene` poses depends on
  `CONTROLLER_TRUSTED_POSITIONING_SOURCES` (and a manual binding) being deployed/configured
  correctly; an empty or unset trust list fails closed (trusts nothing).
- Until the registry ships, interim geospatial auto-attach may fan a `wgs84` publisher into every
  geo-calibrated scene (no footprint/handoff policy yet), and the interim **wildcard** subscribe
  means every authenticated publisher on the broker is visible to the controller.
- Registry discovery, spatial-index choice, binder↔registry API, and the move from wildcard to
  selective subscribe remain to be specified and implemented.

## Future Work

Carried forward from the original implementation plan's deferred items, plus binding and
trust-domain follow-ons:

- **Scene/service registry + spatial binder.** Replace interim “attach `wgs84` to all
  geo-calibrated scenes” **and** the interim `external/+/+` wildcard with a discoverable
  registry (logical name on the network; DNS-SD / DNS or equivalent) that maintains a
  multi-scene catalog and spatial index, and drives the binder’s **selective** subscription
  updates (footprint tests, hysteresis, overlap/handoff/priority). Agents continue to publish
  only under their own id; the registry never retargets the MQTT path to a scene inbox. Specify
  binder↔registry API and whether the binder queries the registry or the registry pushes
  membership events.
- **Trust-domain join hardening (discuss with security).** Base case remains: same issuing
  authority as parent/child MQTT today. Stronger guarantees are explicitly out of current
  scope and should be reviewed with a security expert before adoption, including for example:
  - LAN/broker (and registry) discovery subordinate to pinned CA authentication
  - Per-site or per-coalition intermediate CAs (finer than one shared product CA)
  - MQTT ACLs binding client identity to `publish` on `external/{own_id}/#` only
  - Short-lived certs, revocation, device attestation / enrollment
  - Network isolation and explicit cross-domain federation/bridging (never auto-merge trust
    domains)
  - Keeping **trust-domain join** (which broker/fabric) separate from **scene binding** (which
    scenes ingest a publisher — registry + binder)
- **Object-type-aware trusted identity (tracks ADR 13's open "Retracking redesign" question,
  remaining gap after the default-trust-plus-collision-detection revision above).** Trust and
  collision detection are currently applied per `(scene, category)`, not per
  `(source_id, category)` — ADR 13 explicitly raises the finer-grained case (for example, a
  source whose `person` observations should be identity-trusted while its `vehicle` observations
  from a lower-confidence secondary sensor should still be retracked by the kinematic tracker).
  Supporting that would require a per-object opt-out (for example a `trusted: false` flag settable
  per message/object, honored by `_handleExternalSourceObject()` to fall back to the tracker/ReID
  path for just that object) rather than the current all-or-nothing-per-source behavior. Deferred.
- **`IdentityClaimRegistry` does not detect a single source reusing a stale `id` for a new
  physical object.** As documented in
  [Trusted identity by default, with collision detection](#trusted-identity-by-default-with-collision-detection),
  collision detection only catches two different sources colliding on the same live `id`; it
  cannot catch a source reissuing one of its own previously-claimed, now-expired `id`s for a
  genuinely different object (for example, a robot restarting and reusing small integer
  track-slot numbers). This is currently addressed only through operational guidance (choose a
  persistent, unique `id`). A future extension could reduce blast radius further (for example,
  requiring some minimum silence period or an explicit "new object" flag before a stale `id` can
  be reclaimed at all), but this is deferred pending real-world evidence that guidance alone is
  insufficient.
- **Gap: trusted-identity objects are routed through an entirely separate code path instead of
  the shared UUID-manager/ReID pipeline, rather than through the same pipeline with
  provenance-driven nuance.** When retrack is disabled, `Scene.processSceneData()` forks objects
  into `already_tracked_objects`/`mergeAlreadyTrackedObjects()`, which sets `gid = oid` directly
  and never calls `UUIDManager.assignID()`. `reid_state` defaults to `ReidState.PENDING_COLLECTION`
  at construction (`MovingObject.__init__`) and, because `assignID()` is never called for these
  objects, is never resolved to `MATCHED`/`QUERY_NO_MATCH`/`REID_DISABLED` — it stays permanently
  stuck at `PENDING_COLLECTION` for the object's entire lifetime, since `setPrevious()` just
  copies that same unresolved state forward on every subsequent frame. `previous_ids_chain` stays
  empty for the same reason (only `assignID()`'s query path appends to it).
  **`PENDING_COLLECTION` is actively misleading here, not merely incomplete**: it implies an
  embedding-collection/query is in progress and will eventually resolve, which is never true for a
  trusted-identity object — no query will ever be made. Existing `ReidState` values do not cover
  this case either: `REID_DISABLED` means the ReID _subsystem_ is off for every object, not that
  one specific object's identity was externally asserted and doesn't need ReID. Correctly
  representing this state would require a new `ReidState` value (for example `TRUSTED_EXTERNAL` or
  `IDENTITY_ASSERTED`) meaning "identity was asserted by a trusted external source; no ReID query
  applies to this object," distinct from both "query pending" and "ReID disabled system-wide."
  This is a structural gap, not just a reporting omission: the current design treats "trusted
  identity" as a fork at ingestion (two disjoint object pipelines) rather than as one attribute of
  a single pipeline. The eventual direction is to treat all objects — camera-tracked and
  external-source alike — the same way through one object pipeline, with per-object _nuance_
  applied based on provenance/trust (for example: skip the ReID query and don't reassign `gid` for
  a trusted object, but still route it through `UUIDManager`, set the new `ReidState` value, and
  populate `previous_ids_chain` consistently for every object regardless of source). Realizing
  that would require a deliberate, minimal extension to `UUIDManager`/`MovingObject` — a new
  `ReidState` value plus accepting an externally-asserted `gid` as an input rather than only ever
  computing one — instead of the current all-or-nothing retrack-routing
  fork. Deferred.
- **Cross-source association/deduplication.** Fusing or deduplicating observations of the same
  physical object reported by multiple independent external sources (or by an external source and
  a camera) is out of scope; until that lands, co-observed people/vehicles may appear as parallel
  tracks and may each fire ROI/tripwire/sensor analytics. Covariance-aware tracking/ROI
  boundaries and uncertainty-aware volume/collision/occupancy calculations are also deferred.
- **Trusted object-library size lookup.** No default object size is synthesized when `size` is
  omitted; a future trusted-library lookup (for example resolving `category` to a canonical
  bounding size) could reduce how often external sources fall back to point-object-only analytics
  eligibility.
- **Fully enforced MQTT mTLS/ACL policy.** Binding credentials to allowed publisher ids, and
  enforcing externally owned UUID authorization as a separately authorized extension, is reserved
  for the broader security integration (see trust-domain join hardening above) and not implemented
  as part of this contract's base case.
- **Cache interpolation/quality gating.** The pose cache currently permits reuse of any
  non-expired cached transform; pose interpolation and stricter age/quality gating beyond the TTL
  are deferred.

## References

- `controller/src/schema/metadata.schema.json` (`external_source`, `external_pose`,
  `external_detection` definitions)
- `controller/src/controller/external_source.py` (`ExternalSourcePoseCache`,
  `IdentityClaimRegistry`)
- `controller/src/controller/scene_controller.py`
  (`handleMovingObjectMessage`, `_handleExternalSourceObject`, `_handleChildSceneObject`,
  `_scenesForExternalPublisher`, `updateSubscriptions`, `handleHierarchyParentMessage`,
  `_parseTrustedSources`, `_parseExternalSourceBindings`)
- `controller/src/controller/child_scene_controller.py`
  (remote MQTT client; retained `SYS_HIERARCHY_PARENT` attach/detach on the child broker)
- `controller/src/controller/moving_object.py` (`MovingObject.__init__`, `oid`/`gid` distinction)
- `controller/src/controller/ilabs_tracking.py` (`mergeAlreadyTrackedObjects`, the retrack=False
  identity-passthrough path trusted external-source objects always use)
- `controller/src/controller/time_chunking.py` (`TimeChunkedIntelLabsTracking.trackObjects`,
  `_sourceIdForTimeChunking` — buckets `already_tracked_objects` by `uid`/`cameraID`)
- `controller/src/controller/cache_manager.py` (`refreshScenesForCamParams`,
  `cameraParametersChanged`)
- `controller/src/controller/uuid_manager.py` (global ID assignment, ReID)
- `docs/user-guide/microservices/controller/data_formats.md` (external-source contract reference,
  Trusted Identity by Default with Collision Detection, `source_id` self-identification guidance)
- `docs/user-guide/how-to-guides/publish-external-source-adapter.md` (converter/adapter how-to;
  procedure only — links to `data_formats.md` for the contract)
- `.github/skills/external-source-adapter/SKILL.md` (agent checklist for writing converters;
  anti-drift pointers to the how-to and `data_formats.md`)
- `docs/user-guide/microservices/controller/controller.md`
  (`CONTROLLER_TRUSTED_POSITIONING_SOURCES`, `CONTROLLER_EXTERNAL_SOURCE_BINDINGS`,
  remote hierarchy parent-attach signal)
- `docs/user-guide/how-to-guides/build-a-scene/configure-hierarchy-of-scenes.md` (parent/child
  hierarchy; static binding precursor; remote-child attach signal)
- `docs/user-guide/how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md`
  (single-host remote hierarchy + ReID; parent-attach enablement)
- `tests/functional/test_external_source_ingest.py` (MQTT ingest, geo accuracy, pose cache reuse, source_id/topic mismatch, identity collision, untrusted scene pose)
- `tests/functional/test_external_source_analytics.py` (ROI / tripwire with external objects)
- `tests/sscape_tests/schema/test_schema.py`, `tests/sscape_tests/schema/conftest.py`
- `tests/sscape_tests/scenescape/test_external_source.py`
  (`TestIdentityClaimRegistry` collision-detection unit coverage)
- `tests/sscape_tests/scenescape/test_scene_controller.py`
  (`TestSceneControllerHandleExternalSourceObject`, publisher binding / multi-geo fan-out,
  wildcard SUB, mismatch drop, root-hierarchy / parent-attach export gate)
- `tests/sscape_tests/scenescape/test_child_scene_controller.py`
  (retained `SYS_HIERARCHY_PARENT` attach/detach on connect / disconnect / `loopStop`)
- `tests/sscape_tests/scene_pytest/test_time_chunking_child_scene.py`
  (time-chunk bucketing for child/`uid` and already-tracked external sources)
- [ADR 11 — Configurable ReID Similarity Metric and Track Lineage Output](0011-inner-product-reid-state-and-id-lineage.md)
  (the `gid`/UUID lineage machinery that external-source objects also flow through)
- [ADR 13 (proposed, PR #1526) — Controller Breakdown into Functionality-Aligned Microservices](https://github.com/open-edge-platform/scenescape/pull/1526/files)
  (recursive pose+observations hierarchy contract this ADR instantiates; source of the
  "Retracking redesign" open question this ADR documents as a known deviation)
