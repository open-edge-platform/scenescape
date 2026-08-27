<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ReID Capacity Eviction Policies

## Status

Future extension. This document records a possible design; it does not describe
current behavior.

Current time-based retention is documented in
[ADR-0014](../../docs/adr/0014-reid-descriptor-ttl-retention.md).

## Motivation

The current ReID retention model uses a descriptor TTL and a periodic reclaim
cycle. It provides a coarse bound based on ingest rate and time, but it can
discard valid, older identities even when the vector store has ample capacity.
It also cannot react to an unusually high ingest rate within the TTL window.

A capacity-based extension should preserve as much long-term ReID value as
possible while preventing descriptor growth from compromising service
robustness.

## Goals

- Apply the same controller-facing capacity contract to VDMS and Qdrant.
- Keep backend-specific counting, vector retrieval, and deletion inside the
  adapters.
- Let operators choose between oldest-first eviction and centroid compaction.
- Reuse the existing process-wide, five-minute reclaim worker.
- Keep TTL retention usable independently or together with capacity eviction.
- Avoid eviction work on the add or match hot paths.

## Non-goals

- React directly to container RSS, node pressure, or Kubernetes eviction
  signals in the first version.
- Guarantee byte-exact memory usage across vector databases.
- Migrate or backfill descriptors written before capacity metadata is added.
- Coordinate eviction across multiple controller replicas in the first
  version.

## Pressure Signal

Use physical descriptor count as the initial capacity signal. It is available
to both backends, is stable enough for operator configuration, and avoids
backend- and deployment-specific memory telemetry.

Actual memory use still depends on vector dimensions, indexes, payload size,
and backend implementation. A later version may add an optional byte estimate
without changing the eviction-policy interface.

## Proposed Configuration

```text
REID_MAX_DESCRIPTORS=0
REID_EVICTION_POLICY=oldest
```

- `REID_MAX_DESCRIPTORS`: Maximum desired physical descriptor count. `0`
  disables capacity eviction.
- `REID_EVICTION_POLICY`: `oldest` or `centroid`.

Use an internal low watermark of 85% of `REID_MAX_DESCRIPTORS`. When the high
watermark is reached, reclaim in one batch down to the low watermark. Do not
expose the low-watermark ratio until operational evidence shows that it needs
operator tuning.

## Shared Adapter Contract

Extend `ReIDDatabase` with backend-neutral operations:

```python
def countDescriptors(self):
  """Return the physical descriptor count, or None when unavailable."""

def evictToCapacity(self, target_count, policy):
  """Reclaim descriptors until target_count is reached when possible."""
```

The exact query, ordering, point identifiers, and deletion commands remain
private to each adapter.

Every new descriptor also needs a backend-neutral numeric `inserted_at`
timestamp. Unlike the previously removed `added_at` field, this property has a
defined consumer: deterministic oldest-first eviction. Both backends should
index it when capacity eviction is enabled.

## Reclaim Cycle

The process-wide reclaim owner runs every five minutes:

1. Run the existing TTL `purgeExpired()` operation.
2. If capacity eviction is disabled, stop.
3. Read the current physical descriptor count.
4. If count is below `REID_MAX_DESCRIPTORS`, stop.
5. Call `evictToCapacity()` with the 85% low-watermark target and selected
   policy.
6. Record count before/after, duration, policy, and failures in logs and
   metrics.

Reclaim must not overlap. A cycle starts only after the previous cycle has
completed.

## Policy: `oldest`

Delete descriptors globally in ascending `inserted_at` order until the target
count is reached.

Properties:

- Provides a hard descriptor-count bound.
- Is straightforward to reason about and test.
- Can remove every descriptor belonging to an old identity.
- Does not modify the descriptors that remain.

Backend outline:

- Qdrant: ordered scroll with payload and point IDs, followed by batched point
  deletion.
- VDMS: find descriptors ordered or constrained by `inserted_at`, followed by
  `DeleteDescriptor` using IDs or timestamp batches supported by VDMS.

The VDMS query shape and stable descriptor identifier must be verified against
the deployed VDMS version before implementation.

## Policy: `centroid`

Prefer identities with multiple descriptors. Replace a selected identity's
source descriptors with one representative centroid:

1. Read vectors and payloads for one UUID.
2. Compute their arithmetic mean.
3. Normalize the result when required by the active similarity metric.
4. Carry forward the newest descriptor's semantic metadata and the latest
   persisted attributes.
5. Insert the replacement before deleting source descriptors.
6. Mark the replacement as compacted so it is not repeatedly averaged without
   new source descriptors.

Properties:

- Preserves a searchable representation of more identities.
- Reclaims repeated observations before deleting complete identities.
- Changes nearest-neighbor behavior because a centroid may not represent
  multiple appearance modes.
- Requires vector reads and substantially more work than oldest-first deletion.
- Cannot guarantee a hard bound once every UUID has only one descriptor.

To preserve the robustness guarantee, the initial implementation should fall
back to oldest-first deletion if centroid compaction cannot reach the target.
The fallback must be explicit in user documentation and metrics.

## Correctness and Failure Handling

- Insert a centroid replacement before deleting its source descriptors.
- Use an operation marker or deterministic replacement identifier so retries
  do not create unbounded duplicate centroids.
- Treat partial deletion as retryable and recount before the next batch.
- Never block `addEntry()`, `findMatches()`, or `getPersistedAttributes()` on a
  reclaim cycle.
- Existing descriptors without `inserted_at` require an explicit policy:
  ignore them, rebuild the collection, or delete them through an
  operator-controlled migration.
- Multiple controller replicas can still run competing process-wide workers.
  Production enablement in replicated deployments requires a distributed
  lease or a backend-atomic ownership mechanism.

## Metrics

Add at least:

- Current descriptor count.
- Configured maximum and low watermark.
- Reclaim cycle duration.
- Number deleted by TTL.
- Number deleted by oldest-first eviction.
- Number of source descriptors compacted and centroids created.
- Number removed by centroid fallback.
- Reclaim failures and partial retries.

## Test Plan

### Shared contract tests

- Capacity disabled when maximum is `0`.
- No eviction below the high watermark.
- Reclaim reaches the low watermark.
- TTL purge runs before capacity eviction.
- Only one reclaim cycle runs at a time.
- Failures do not affect add or match operations.

### Oldest policy

- Deletes globally oldest descriptors first.
- Handles equal timestamps deterministically.
- Preserves newer descriptors.
- Works in multiple batches.

### Centroid policy

- Produces the expected normalized centroid.
- Preserves UUID and selected payload metadata.
- Preserves latest persisted attributes.
- Inserts replacement before deleting sources.
- Is idempotent after a partial failure.
- Falls back to oldest-first when compaction cannot reach target.

### Backend integration

- Run the same behavioral suite against VDMS and Qdrant.
- Verify physical counts before and after reclaim.
- Verify remaining identities are still matchable.
- Measure Qdrant tombstone/optimizer lag separately from logical point count.

## Delivery Phases

1. Add configuration parsing, `inserted_at`, counting, metrics, and oldest-first
   eviction for both adapters.
2. Validate descriptor-count thresholds under representative ingest.
3. Add centroid compaction behind the policy selector.
4. Add distributed reclaim ownership before enabling capacity eviction in
   multi-replica controller deployments.
5. Reassess whether TTL remains necessary once capacity eviction has sufficient
   production evidence.

## Open Decisions

- Exact default for `REID_MAX_DESCRIPTORS`; it should remain disabled until
  memory measurements establish a safe value.
- Whether centroid input should include all descriptors for a UUID or retain a
  small number of recent raw descriptors alongside the centroid.
- How semantic metadata conflicts are resolved during centroid creation.
- How descriptors lacking `inserted_at` are migrated.
- Which distributed lease mechanism is appropriate for replicated
  deployments.
