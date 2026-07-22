<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR 14: Unified External-Source Ingestion Contract for the Scene Controller

- **Author(s)**: Sarat Poluri, GitHub Copilot
- **Date**: 2026-07-21
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
  target scene, alongside a pose that lets the controller resolve source-local coordinates into
  scene-local coordinates.
- Preserves the legacy configured-child-scene behavior unchanged.
- Does **not** require the Scene Controller to maintain a per-publisher lookup/translation cache
  mapping each source's native ID scheme, coordinate convention, or track-continuity semantics
  into a canonical form. That translation burden belongs on the publishing side (the agent or an
  adapter it runs behind), not on a shared, multi-tenant controller that must scale to many
  concurrent, heterogeneous publishers.
- Reuses the existing tracking, persistent-attribute, sensor, ROI, and analytics pipeline instead
  of building a parallel path for external sources.

The full implementation plan, decisions, and progress log for this effort are tracked in session
notes; this ADR captures the resulting architecture and the specific correctness issues found
while exercising the contract end-to-end.

## Decision

### Single topic, dual contract, disambiguated by `source_id`

`scenescape/external/{scene_id}/{thing_type}` continues to carry both contracts:

- **Legacy child scene** (no `source_id`): unchanged. `{scene_id}` is the sending child; the
  controller resolves its configured parent and static `cameraPose`.
- **Unified external source** (`source_id` present): `{scene_id}` is the _target_ scene. Messages
  are validated against a new `external_source` schema definition
  (`controller/src/schema/metadata.schema.json`) with nested `external_pose` and
  `external_detection` definitions, rather than reusing/weakening the camera `detector` schema.

### Pose resolution and caching

A new `ExternalSourcePoseCache` (`controller/src/controller/external_source.py`) resolves and
caches the source-to-scene transform, keyed by `(scene.uid, source_id)`, with a default 30 s TTL:

- `reference_frame: wgs84` — a global geopose. Any source may publish it, but it is only
  resolvable when the target scene has valid four-corner geospatial calibration
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
external sources in `_handleExternalSourceObject()` now also sets `uid=source_id` so that
time-chunked buckets are keyed per publishing source, consistent with how child scenes already
key by `uid`.

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
`(pose, objects)` into a target scene through one uniform interface, ahead of the full
microservice split. In that sense this work is aligned with, and a concrete step toward, ADR 13's
target hierarchy contract, implemented within the still-monolithic Controller rather than as a
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
- **Let the source-supplied `id` drive global track continuity directly**, bypassing the internal
  tracker/ReID association for external sources. Rejected: source ID lifecycle semantics are
  heterogeneous and untrusted (resettable local counters vs. permanent hardware IDs); accepting
  them directly as global identity would produce inconsistent re-identification guarantees across
  source types and would reintroduce the exact problem controller-assigned UUIDs were adopted to
  solve.

## Consequences

### Positive

- One documented contract lets any dynamic external source — physical agent, positioning service,
  or new-style child scene — publish into a target scene without the controller special-casing
  publisher types beyond pose-trust and geo-reference checks.
- Global identity assignment stays exclusively inside the controller's existing tracker/ReID path,
  so re-identification guarantees are uniform regardless of what ID scheme (if any) a source's
  hardware or firmware uses.
- Point observations (no `size`) remain eligible for ROI/tripwire/sensor-tagging analytics while
  being excluded from volume/occupancy/collision analytics, matching camera-detection semantics.
- Multiple simultaneous objects from one source (for example several UWB tags in one message) are
  disambiguated safely because `id` is required and per-object.

### Negative

- Publishers must always include a per-observation `id`, even for the simplest single-point-object
  case; this is a small increase in required payload verbosity versus letting it be inferred.
- Three related but independent silent-failure modes existed at the seams between the new
  external-source path and code that previously only had to handle camera detections and legacy
  child scenes: a schema/construction contract mismatch on `id` (`KeyError: 'id'` in
  `MovingObject.__init__`), a camera-only cache-refresh step invoked unconditionally
  (`KeyError: 'id'` in `CacheManager.cameraParametersChanged`), and time-chunked tracking silently
  dropping every external-source frame because its `SimpleNamespace` sender had no `cameraID`/`uid`
  attribute to bucket by. None of these were caught by unit tests in isolation; only a functional
  MQTT test exercising the full ingest path against a live controller surfaced them.
- The trust boundary for `reference_frame: scene` poses depends on
  `CONTROLLER_TRUSTED_POSITIONING_SOURCES` being deployed/configured correctly; an empty or unset
  value fails closed (trusts nothing), which is safe by default but must be understood by
  deployers who intend to use a scene-local positioning service.

## Future Work

Carried forward from the original implementation plan's deferred items, plus documentation gaps
identified while closing out this contract:

- **Done — Publisher/adapter converter-script documentation.** Guide:
  [`docs/user-guide/how-to-guides/publish-external-source-adapter.md`](../user-guide/how-to-guides/publish-external-source-adapter.md);
  agent skill:
  [`.github/skills/external-source-adapter/SKILL.md`](../../.github/skills/external-source-adapter/SKILL.md).
  Both point at the canonical contract in
  `docs/user-guide/microservices/controller/data_formats.md` rather than duplicating field
  tables. Remaining Future Work items below are unchanged.
- **Multi-scene discovery/fan-out.** Scene discovery, boundary arbitration, agent handoff between
  overlapping scenes, and priority rules when a source is in range of more than one scene are all
  deferred; sources choose their target scene explicitly for now.
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
- **Trusted-identity objects currently bypass the shared UUID-manager/ReID path entirely, rather
  than being recorded through it.** When retrack is disabled, `Scene.processSceneData()` routes
  objects through `already_tracked_objects`/`mergeAlreadyTrackedObjects()`, which sets
  `gid = oid` directly and never calls `UUIDManager.assignID()` — so `reid_state` and
  `previous_ids_chain` (ADR 11) are never populated for these objects (there is nothing to
  record, since identity never transitions). If a future need arises to give trusted-identity
  objects the same structured `reid_state`/lineage _reporting_ as tracked objects — without
  actually querying ReID or reassigning `gid` — that would require a deliberate, minimal
  extension to `UUIDManager`/`MovingObject`, not a change to the current retrack routing.
- **Cross-source association/deduplication.** Fusing or deduplicating observations of the same
  physical object reported by multiple independent external sources (or by an external source and
  a camera) is out of scope; covariance-aware tracking/ROI boundaries and uncertainty-aware
  volume/collision/occupancy calculations are deferred.
- **Trusted object-library size lookup.** No default object size is synthesized when `size` is
  omitted; a future trusted-library lookup (for example resolving `category` to a canonical
  bounding size) could reduce how often external sources fall back to point-object-only analytics
  eligibility.
- **Fully enforced MQTT mTLS/ACL policy.** Binding credentials to allowed `source_id`s and target
  scenes, and enforcing externally owned UUID authorization as a separately authorized extension,
  is reserved for the broader security integration and not implemented as part of this contract.
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
  `updateSubscriptions`, `_parseTrustedSources`)
- `controller/src/controller/moving_object.py` (`MovingObject.__init__`, `oid`/`gid` distinction)
- `controller/src/controller/ilabs_tracking.py` (`mergeAlreadyTrackedObjects`, the retrack=False
  identity-passthrough path trusted external-source objects always use)
- `controller/src/controller/time_chunking.py` (`TimeChunkedIntelLabsTracking.trackObjects`)
- `controller/src/controller/cache_manager.py` (`refreshScenesForCamParams`,
  `cameraParametersChanged`)
- `controller/src/controller/uuid_manager.py` (global ID assignment, ReID)
- `docs/user-guide/microservices/controller/data_formats.md` (external-source contract reference,
  Trusted Identity by Default with Collision Detection, `source_id` self-identification guidance)
- `docs/user-guide/how-to-guides/publish-external-source-adapter.md` (converter/adapter how-to;
  procedure only — links to `data_formats.md` for the contract)
- `.github/skills/external-source-adapter/SKILL.md` (agent checklist for writing converters;
  anti-drift pointers to the how-to and `data_formats.md`)
- `docs/user-guide/microservices/controller/controller.md` (`CONTROLLER_TRUSTED_POSITIONING_SOURCES`
  reference and pointer to the no-configuration-required identity trust model)
- `tests/functional/test_external_source_ingest.py` (end-to-end MQTT ingest coverage)
- `tests/sscape_tests/schema/test_schema.py`, `tests/sscape_tests/schema/conftest.py`
- `tests/sscape_tests/scenescape/test_external_source.py`
  (`TestIdentityClaimRegistry` collision-detection unit coverage)
- `tests/sscape_tests/scenescape/test_scene_controller.py`
  (`TestSceneControllerHandleExternalSourceObject` retrack/trust routing coverage)
- [ADR 11 — Configurable ReID Similarity Metric and Track Lineage Output](0011-inner-product-reid-state-and-id-lineage.md)
  (the `gid`/UUID lineage machinery that external-source objects also flow through)
- [ADR 13 (proposed, PR #1526) — Controller Breakdown into Functionality-Aligned Microservices](https://github.com/open-edge-platform/scenescape/pull/1526/files)
  (recursive pose+observations hierarchy contract this ADR instantiates; source of the
  "Retracking redesign" open question this ADR documents as a known deviation)
