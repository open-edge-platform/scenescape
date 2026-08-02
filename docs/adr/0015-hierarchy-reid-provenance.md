<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 14: Hierarchy ReID Provenance and Enrollment Scope

- **Author(s)**: Sarat Poluri, Derrick Addo
- **Date**: 2026-07-30
- **Status**: `Proposed`
- **Related**: [ADR 10](./0010-reid-metadata-storage-architecture.md),
  [ADR 11](./0011-inner-product-reid-state-and-id-lineage.md)

## TLDR

This decision makes ReID usable in a multi-scene hierarchy without allowing
the same camera crop to be enrolled repeatedly at every hierarchy level.
Embeddings forwarded between scenes carry explicit provenance. A receiving
scene may use a vetted forwarded embedding to **query** the shared ReID
database. With Retrack and parent ReID it may also **write** that embedding:
sole enrollment on query-no-match (e.g. children without ReID), and cluster
**enhancement** after rematch. When a ReID-enabled child stamps `will_enroll` / `enrolled`, the parent still
queries but skips writes so the same crop is not enrolled under a second UUID
while the child flushes. ReID children withhold **local** hierarchy embeddings until
their vector schema is ready **and** at least one database write has succeeded,
so parents neither race-enroll early frames nor honor a write claim the child
cannot fulfill; inherited vetted embeddings still relay. If child writes later
fail, hierarchy publish drops to passthrough and the child stops enrolling so
the parent can sole-enroll without a dual-writer race.

The policy for using a child's already-resolved global ID when a parent
retracks the child remains open. Until that policy is decided, a retracking
parent continues to resolve its own identity rather than adopting the child's
ID.

## Context

A scene hierarchy has two modes for child objects:

- With `retrack` disabled, the parent treats the child's object as already
  tracked and preserves the child-assigned ID.
- With `retrack` enabled, the parent feeds child detections into its own
  tracker. This is necessary so observations from multiple child scenes and
  cameras local to the parent can merge into one parent-level track.

Re-tracking discards the child ID as the authoritative parent identity, but it
does not eliminate the need for visual identity evidence. Forwarded embeddings
allow the parent to query the shared ReID database when it has not yet observed
the object through a local camera.

Only the scene that owns the source camera has the original pixel-space
bounding box. Once an object is forwarded, it is represented in scene/world
coordinates and the receiving parent cannot independently evaluate the quality
of the image crop that produced its embedding.

Scenes in a hierarchy share one ReID database, so each embedding must be
attributable to exactly one scene. Earlier approaches failed in two ways:

1. Removing hierarchy embeddings left a retracking parent without visual
   evidence for child-only tracks and cross-scene identity resolution.
2. Treating every embedding without a pixel bounding box as implicitly vetted
   allowed unverified embeddings to be queried and enrolled. In a shared
   database, parents could then enroll the same crop again under a different
   parent-level ID, fragmenting one physical identity.

## Decision

### 1. Separate ReID query evidence from database enrollment

`UUIDManager` maintains two feature collections:

- `quality_features`: embeddings that may be used for an identity query;
- `enrollment_features`: embeddings this scene is authorized to add to the
  shared ReID database.

An observation is **enrollable at gather time** only when this scene has a
pixel-space bounding box whose area is greater than `minimum_bbox_area`.

An observation is **queryable** when either:

- it is enrollable locally; or
- it has no local pixel bounding box and carries explicit, vetted provenance
  from an upstream scene.

A local crop that fails the area threshold cannot be rescued by a provenance
claim. Forwarded embeddings that are queryable may also be written when this
scene runs ReID on retracked children:

- **No match** — sole enrollment under the parent-assigned UUID (parent-only /
  passthrough when no upstream scene wrote the crop).
- **Match** — rematch that UUID and **enhance** its embedding cluster with the
  vetted forwarded vectors (same idea as accumulating more camera views).

Exact rematch skips only query vectors whose **per-vector** score against the
matched UUID is exact (from the query that just ran — no extra lookup). Vectors
with no score against the matched UUID (absent from the neighbor list) are also
skipped so they cannot pollute another identity's cluster. Local camera crops
are always kept, and near-duplicate views from the same query window still
enhance the cluster. When per-vector scores are unavailable, fall back to
aggregate exact → locals only. In-memory and within-batch exact vector dedupe
remains cheap.

`isEnrollableObservation` remains the local-bbox gate; `mayContributeEnrollmentEmbedding`
covers local crops and vetted forwarded crops for database writes, except when
upstream provenance claims `will_enroll` or `enrolled`.

The default minimum area is shared from `reid_constants.py`, and the quality
gate remains exclusive: `area > minimum_bbox_area`.

### 2. Carry explicit embedding provenance on hierarchy output

Embeddings published on the external scene-hierarchy topic carry a
`metadata.reid.provenance` object:

```json
{
  "origin_scene_id": "<scene UUID>",
  "origin_camera_id": "<camera ID or null>",
  "quality_vetted": true,
  "will_enroll": true,
  "enrolled": true
}
```

The current validity contract requires:

- `quality_vetted` to be exactly `true`; and
- a non-empty `origin_scene_id`.

`origin_camera_id` is retained when known for diagnostics and future policy,
but it is not currently required for trust.

`will_enroll` / `enrolled` are optional **write-authority** claims, stronger than
`quality_vetted` alone: a parent that sees either flag may still **query** with
the embedding but must not **write** it (no sole enrollment on miss, no enhance
on match). Within the existing child-scene MQTT trust model these flags are as
spoofable as other provenance fields; a forged `will_enroll` can suppress parent
enrollment (an enrollment DoS) even when the publisher never writes the DB.

Publishing policy for a ReID-enabled scene:

- **Schema ready + write intent + at least one successful write** — forward
  local vetted crops with `will_enroll: true`. Also set `enrolled: true` when
  the track already has a database id or pending enrollment vectors. Until the
  first successful `addEntry`, hierarchy publish stays in withhold even when the
  schema is ready so parents are not asked to skip writes before the child has
  proven it can enroll.
- **Write intent but schema not ready** (TLS client certs present, or
  `REID_USE_TLS=false` for non-mTLS ReID) — **withhold local**
  `metadata.reid` from hierarchy output until the schema is ready. Already-vetted
  **inherited** embeddings still forward so multi-hop relays keep working. This
  prevents the parent from sole-enrolling early local frames and avoids claiming
  `will_enroll` when the child cannot yet enroll.
- **No write intent** (typical parent-only children: TLS default on, no ReID
  client certs) — forward vetted crops without `will_enroll` so the parent may
  sole-enroll.
- **Write path unhealthy** — after a failed ReID database write (including soft
  backend errors), hierarchy publish drops to passthrough (no `will_enroll`) and
  the child stops local enrollment writes for the process lifetime so the parent
  sole-enrolls without a dual-writer race. In-flight flushes submitted before
  the failure are dropped via a write-epoch guard held across the enrollment
  write. Empty/invalid vector batches raise without sticky-clearing write-health;
  if they occur before the first confirmed write, hierarchy publish uses
  passthrough so a parent can sole-enroll instead of forever withholding.
  Cancelled pool futures leave write-health unchanged.

Relays preserve inherited provenance (including write-authority flags) rather
than re-attributing the embedding. Controllers without ReID write intent leave
the flags unset so parent-only passthrough enrollment still works.

`REID_USE_TLS=false` is treated as an explicit non-mTLS ReID deployment choice
and implies write intent even when hostname/database env vars use built-in
defaults. Parent-only / passthrough children should keep the TLS default.

The scene that first has a qualifying pixel bounding box stamps the
provenance. Relaying scenes preserve the original provenance rather than
re-attributing the embedding to themselves. This keeps the source of a crop
stable across multiple hierarchy hops.

If the publishing scene has neither a qualifying local pixel bounding box nor
already-vetted provenance, it withholds the complete `metadata.reid` payload
from hierarchy output.

Only hierarchy output opts into provenance attachment. Existing scene,
regulated, region, and event outputs retain their current ReID serialization
behavior.

### 3. Enforce provenance at message trust boundaries

Provenance received on a camera/detector topic is removed before constructing
moving objects. A detector is evaluated using the pixel bounding box it
provides and cannot claim that another scene already vetted its crop.

Forwarded embeddings are accepted only under `metadata.reid`, where provenance
travels with the embedding. A top-level `reid` field on child-scene input is
discarded.

`MovingObject` decodes provenance into a separate `reid_provenance` attribute.
Provenance describes the origin and permitted use of an embedding; it is not
part of the embedding or model metadata itself.

For `retrack` disabled children, the parent removes the forwarded embedding
because the child identity is accepted directly and the parent does not call
its UUID manager for that object.

For `retrack` enabled children, the parent preserves the embedding and its
provenance so the parent's UUID manager can query, sole-enroll on no-match, and
enhance a rematched UUID's cluster with further vetted forwarded vectors.

## Alternatives Considered

### Keep ReID scene-local

Do not forward embeddings and let each scene resolve identity independently.

This was rejected for `retrack` enabled hierarchies because a parent would
have no visual evidence for child-only tracks and could not use ReID to bridge
spatial or temporal gaps after geometric tracking.

### Infer vetting from a missing pixel bounding box

Gate embeddings at the child and assume that every bbox-less embedding
received by a parent was already vetted.

This was implemented as an intermediate branch design and rejected. The
absence of a bounding box is not evidence of prior validation, and this model
did not distinguish query use from enrollment. It could therefore duplicate a
crop in the shared database under identities created at multiple hierarchy
levels.

### Reconstruct quality from a metric-space footprint

Use the world/metric object footprint as a proxy after the source pixel
bounding box has been lost.

This was tried and removed. Metric footprint is not equivalent to image crop
quality and can vary with calibration, projection, object-size assumptions,
and viewing geometry. Quality is decided once in the scene that owns the
source pixels.

### Allow vetted forwarded embeddings to be enrolled by parents unconditionally

Always writing forwarded crops at the parent would give forwarded-only tracks a
database contribution, but would also double-enroll whenever a child (or peer)
had already written the same crop. Rejected in favor of **query first**: enroll
forwarded features only on no-match with an empty local enrollment set.

### Re-attribute provenance at every hierarchy hop

This would identify the latest relay instead of the camera-owning origin and
would prevent operators from determining who evaluated the crop. Original
provenance is preserved instead.

### Attach provenance to every controller output

This would expand more wire contracts than required. Provenance is attached
only to the external hierarchy output because that is the boundary where a
different scene must decide whether an embedding can be trusted.

### Adopt the child's resolved global ID when retracking

Using the child's ID as the parent identity would avoid provisional
mismatches, but it conflicts with the reason for retracking: observations from
multiple children and the parent's own cameras must merge into one parent-level
track. One child's ID cannot be treated as authoritative before that merge.
This option remains open as a possible future identity hint rather than as a
direct assignment.

## Consequences

### Positive

- A `retrack` enabled parent can query ReID with vetted child observations.
- Each crop is enrolled at most once under the query-first rule: child enrolls
  when it has ReID; otherwise the parent may enroll on no-match.
- Missing pixel bounding boxes are no longer treated as implicit evidence of
  quality.
- Provenance remains attributable across multiple hierarchy hops.
- Detector messages cannot use claimed provenance to bypass the local crop
  quality gate.

### Negative

- The hierarchy wire payload gains a `metadata.reid.provenance` object.
- Trust currently depends on a provenance claim from the child-scene topic;
  the claim is not yet authenticated against the configured child and camera
  hierarchy beyond the existing MQTT sender lookup. A forged `will_enroll` /
  `enrolled` flag is write-authority and can block parent enrollment.
- If a child with ReID enrolls after the parent already no-match-enrolled the
  same crop, the shared DB can hold two UUIDs until operators align flush
  timing or prefer children-on-shared-DB when both levels have ReID.
  **Mitigation:** ReID-enabled children withhold **local** hierarchy reid until
  schema ready **and** the first successful write (inherited vetted embeddings
  still relay), then stamp `will_enroll` (and `enrolled` once the track owns a
  write) so the parent skips promotion even on a query miss; rematch proceeds
  once the child row is visible. If child database writes fail (including soft
  backend errors that previously only logged), hierarchy publish clears
  `will_enroll` (passthrough) so the parent can sole-enroll; write-health stays
  cleared for the process lifetime and the child stops local enrollment writes
  so it does not keep writing while the parent sole-enrolls. Empty/invalid
  vector batches do not sticky-clear write-health; before the first confirmed
  write they use passthrough instead of forever withholding.
- The same minimum-area rule is evaluated in both publishing and receiving
  code paths. Configuration differences between scenes can produce different
  local acceptance standards.

### Compatibility and migration

- Existing detector messages do not need to provide provenance.
- Existing non-hierarchy controller outputs are unchanged by provenance.
- Hierarchy consumers that preserve extensible metadata can ignore the new
  field.
- Parents running this design require children to send explicit provenance
  before bbox-less embeddings are accepted for ReID queries. Mixed-version
  deployments may therefore lose hierarchy ReID evidence rather than
  implicitly trusting it.
- No vector database schema migration is required because provenance is used
  in controller message handling and is not stored as a ReID vector property.

## Open Questions

### How should a retracking parent use the child's resolved global ID?

The child already publishes its resolved global ID as the object `id`. A
`retrack` enabled parent currently treats that value as a child detection ID,
creates its own parent track, and resolves identity through its own UUID
manager. It does not use the child ID as an identity hint.

This preserves the parent's ability to merge observations from multiple
children and its own cameras, but creates several unresolved behaviors:

- The parent can emit a provisional ID that differs from the child even when
  the child already matched a durable database identity.
- The child's database entry might not be available until its track is
  inactive, so the parent cannot immediately rediscover that identity through
  a database query.
- A forwarded-only parent track may enroll on no-match so the parent UUID can
  remain durable after the track expires; if the child already enrolled,
  rematch recovers that identity without a second write.

Options for a future decision include:

1. Keep the current behavior and use the shared database as the only identity
   convergence mechanism.
2. Seed a new parent track with the child ID as a provisional identity, while
   allowing a later parent query to replace it and record the transition in
   `previous_ids_chain`.
3. Use the child ID only as a tie-breaker or prior inside parent-level identity
   resolution.
4. Adopt a child ID only when it represents a successful ReID match, not a
   child-local provisional ID.

### How should two live parent tracks share one ReID database identity?

`UUIDManager.updateActiveDict` refuses to assign a database gid that is already
held by another **live** track (collision → treat as no-match and mint a new
provisional id). That protects `unique_detection_count` and avoids duplicate
live holders of one durable UUID, but it blocks **concurrent** cross-child
convergence: two remote children publishing the same embedding at the same time
keep two parent IDs even when both would match the same enrolled UUID.

**Current verified behavior (follow-up scope):** identity continuity across
children is asserted **sequentially** — child A enrolls and rematches at the
parent, its parent track leaves `active_ids`, then child B rematches to the
same database UUID (`tests/functional/test_hierarchy_reid_db_scope.py`,
NEX-T21928). Simultaneous two-child merge is not covered.

Options for a future decision include:

1. Keep collision-as-no-match and document sequential rematch (plus geometric
   tracker merge when world poses coincide) as the supported convergence paths.
2. Allow multiple live tracks to share a matched database gid, and define how
   regulated output / `unique_detection_count` / `previous_ids_chain` behave.
3. Prefer tracker-level association of concurrent child detections into one
   track before ReID assignment, so a single track owns the matched gid.
4. When a second live track matches an occupied gid, retarget or merge into the
   existing holder instead of minting a new provisional id.

Until one of these is chosen, do not treat “both children live → one parent ID
via ReID alone” as a guaranteed product contract.

### How should conflicting identity hints be resolved?

A parent track can merge observations from multiple children and local
cameras. Those observations can disagree about:

- child-resolved global IDs;
- ReID state and similarity;
- database query results; and
- whether the same database ID is already held by another live parent track.

The system needs a deterministic arbitration policy. Candidate policies
include child-authoritative, parent-authoritative, similarity-based,
source-trust-weighted, or delayed resolution until evidence converges. The
policy must also define how conflicts appear in `previous_ids_chain`, logs,
and `unique_detection_count`.

### How strongly should hierarchy provenance be validated?

The current contract validates the shape and vetting flag but does not verify
that `origin_scene_id` and `origin_camera_id` belong to the authenticated
sender's configured descendant hierarchy. Questions include:

- Should every hierarchy message be schema-validated like camera messages?
- Should the parent verify the full origin path against cached scene links?
- Should provenance include a hop path, freshness timestamp, or maximum age?
- Should `origin_camera_id` be mandatory?

### How should fused observations retain provenance?

A parent track may fuse embeddings from several children and local cameras,
but each serialized object currently carries at most one provenance object per
embedding payload. Future designs may need per-embedding provenance,
provenance sets, or an audit trail.

### How should ReID model and threshold compatibility be enforced?

Embedding dimensions are checked, but `model_name` is not used to prevent
different ReID models from sharing a vector collection. Scenes can also use
different `minimum_bbox_area` values. A future decision should define whether
hierarchy links require matching model identifiers and quality thresholds or
whether those differences are intentional source-local policy.

## Verification

The ReID design is covered by:

- forwarding tests for the minimum-area boundary, missing or invalid
  provenance, origin stamping, and multi-hop preservation;
- UUID-manager tests proving that forwarded embeddings are queryable, enrolled
  on no-match, used to enhance a matched UUID's cluster, skipped for writes when
  `will_enroll`/`enrolled` is set, and that per-vector exact/absent scores
  control rematch enhancement;
- scene-controller tests for hierarchy publish policy (passthrough / withhold /
  will_enroll), including write-intent / TLS vs non-TLS gating, schema withhold,
  and `publishExternalDetections` wiring of `will_enroll_reid` / `withhold_reid`
  / `reid_enrolled_fn` (confirmed write, unhealthy, and empty-batch before
  confirm);
- detections-builder tests for withhold that still forwards inherited vetted
  reid (multi-hop unit coverage; live multi-hop hierarchies remain out of the
  functional matrix);
- UUID-manager tests for sticky write-health, write-confirmed, empty-batch
  passthrough signaling, locked write-epoch guards, and stopping child
  enrollment when unhealthy; and
- moving-object and scene-controller tests for provenance decoding and
  hierarchy publishing.

End-to-end ReID assertions for a live multi-controller remote hierarchy are in
`tests/functional/test_hierarchy_reid_db_scope.py`. Supported layouts include
shared ReID on parent and children (NEX-T21928) and parent-only ReID with
passthrough children (NEX-T21930). Other profiles act as guards that unsupported
mixes do not falsely merge or double-enroll. Cross-child identity is covered via
**sequential** rematch; concurrent two-child merge via ReID alone remains an
[open question](#how-should-two-live-parent-tracks-share-one-reid-database-identity).
Single-controller hierarchy enrollment and wire `will_enroll` after a confirmed
child write are covered by `tests/functional/test_hierarchy_reid_enrollment.py`
(NEX-T21925–21927). Write-failure → parent sole-enroll recovery is covered at
unit level (sticky write-health / epoch / enrollment stop); live fault injection
is not part of the functional matrix.
Product docs: unrelated scenes may share **or** use separate ReID DBs; under one
parent, avoid split backends when unifying identity; parent-only ReID with
children as embedding passthrough enrolls on query-no-match—see
[ReID across controllers](../user-guide/how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md#reid-across-controllers-what-is-supported).

## References

- [Extended ReID](../user-guide/microservices/controller/Extended-ReID.md)
- [Create and Manage a Scene Hierarchy](../user-guide/how-to-guides/build-a-scene/configure-hierarchy-of-scenes.md)
- [Deploy Multiple Controllers on One Host](../user-guide/how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md)
- [Enable Re-identification](../user-guide/other-topics/how-to-enable-reidentification.md)
- `controller/src/controller/detections_builder.py`
- `controller/src/controller/moving_object.py`
- `controller/src/controller/reid_constants.py`
- `controller/src/controller/scene.py`
- `controller/src/controller/scene_controller.py`
- `controller/src/controller/uuid_manager.py`
