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
scene may use a vetted forwarded embedding to query the shared ReID database,
but only the scene that owns the source camera may enroll that embedding.

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

An observation is **enrollable** only when this scene has a pixel-space
bounding box whose area is greater than `minimum_bbox_area`.

An observation is **queryable** when either:

- it is enrollable locally; or
- it has no local pixel bounding box and carries explicit, vetted provenance
  from an upstream scene.

A local crop that fails the area threshold cannot be rescued by a provenance
claim. Forwarded embeddings may be queryable but are never enrollable by the
receiving scene. Pending database entries and post-match feature accumulation
therefore contain only `enrollment_features`. A forwarded-only parent track
does not submit an empty database insertion.

The default minimum area is shared from `reid_constants.py`, and the quality
gate remains exclusive: `area > minimum_bbox_area`.

### 2. Carry explicit embedding provenance on hierarchy output

Embeddings published on the external scene-hierarchy topic carry a
`metadata.reid.provenance` object:

```json
{
  "origin_scene_id": "<scene UUID>",
  "origin_camera_id": "<camera ID or null>",
  "quality_vetted": true
}
```

The current validity contract requires:

- `quality_vetted` to be exactly `true`; and
- a non-empty `origin_scene_id`.

`origin_camera_id` is retained when known for diagnostics and future policy,
but it is not currently required for trust.

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
provenance so the parent's UUID manager can use it as query evidence while
preventing parent-side enrollment.

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

### Allow vetted forwarded embeddings to be enrolled by parents

This would give forwarded-only parent tracks a database contribution, but it
would also let multiple hierarchy levels enroll the same crop and would make
the receiving parent write on behalf of an upstream producer. It is rejected
for the current design.

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
- Each source camera crop has one scene responsible for database enrollment.
- Missing pixel bounding boxes are no longer treated as implicit evidence of
  quality.
- Provenance remains attributable across multiple hierarchy hops.
- Detector messages cannot use claimed provenance to bypass the local crop
  quality gate.

### Negative

- The hierarchy wire payload gains a `metadata.reid.provenance` object.
- Trust currently depends on a provenance claim from the child-scene topic;
  the claim is not yet authenticated against the configured child and camera
  hierarchy beyond the existing MQTT sender lookup.
- A forwarded-only parent track contributes no embeddings to the database.
  Its parent-level ID may therefore be non-durable after the track expires.
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
- A forwarded-only parent track is not enrolled and may not recover the same
  parent identity after it expires.

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
- UUID-manager tests proving that forwarded embeddings are queryable but not
  enrollable;
- scene tests proving that camera-provided provenance and top-level child
  `reid` fields are discarded; and
- moving-object and scene-controller tests for provenance decoding and
  hierarchy publishing.

End-to-end ReID assertions for a live multi-controller remote hierarchy are in
`tests/functional/test_hierarchy_reid_db_scope.py` (shared / children-only /
parent-only / partial / split DB profiles).

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
