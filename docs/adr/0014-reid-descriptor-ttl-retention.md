<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR 14: Unified TTL Retention for ReID Descriptor Store Growth

- **Author(s)**: Sarat Poluri, Derrick Addo
- **Date**: 2026-07-30
- **Status**: `Proposed`
- **Related**: [ADR-0010](./0010-reid-metadata-storage-architecture.md)

## Context

On `main`, ReID descriptors are retained indefinitely by both supported vector
database adapters. Descriptor count therefore grows with continued ingestion,
which can increase memory use and eventually reduce controller robustness.

The databases provide different expiration capabilities:

- VDMS understands a native `_expiration` duration and supports
  `DeleteExpired`.
- Qdrant has no native TTL and requires the client to record an expiration
  timestamp and issue a filtered delete.

Implementing retention only in one adapter would leave different operational
behavior and configuration for the same ReID interface. The branch therefore
needs a backend-neutral retention contract while allowing each adapter to use
its native storage operations.

TTL is used here as a coarse storage-growth control, not as an identity
validity rule. Older descriptors remain useful ReID data; deleting them trades
long-term re-identification history for bounded retention and robustness.

## Decision

This branch introduces a shared, controller-driven TTL retention model for all
ReID adapters.

### ReID adapter contract

`ReIDDatabase` gains:

- `descriptor_ttl_secs`, resolved from `REID_DESCRIPTOR_TTL_SECS`.
- `retentionEnabled()` to determine whether finite retention is active.
- `_applyRetentionProperties()` for adapters to attach backend-native
  expiration metadata during `addEntry()`.
- `purgeExpired()` for adapters to reclaim expired descriptors.

The common interface defines when retention applies and when reclaim is
requested. Expiration representation and delete operations remain private to
the adapter.

### Backend implementations

- **VDMS** writes `_expiration` as a TTL duration in seconds and implements
  `purgeExpired()` with `DeleteExpired`.
- **Qdrant** writes an absolute `expires_at` payload value, creates its payload
  index when retention is enabled, and implements `purgeExpired()` with a
  filtered point deletion.

Retention is reclaim-only. Neither adapter filters matching or persisted
attribute lookup by expiration. A descriptor remains searchable until a purge
cycle physically removes it, giving an effective residence time between the
configured TTL and TTL plus one purge interval.

### Reclaim scheduling

`UUIDManager` adds a background purge timer with a default interval of five
minutes (`REID_PURGE_INTERVAL_SECS=300`).

Because a controller process creates multiple `UUIDManager` instances that
share one ReID store, only one manager may own the purge timer in a process.
Ownership is acquired when `connectDatabase()` initiates the database
connection and released during shutdown. Reclaim is submitted to the existing
executor and does not run on the add or match hot paths.

### Configuration and deployment

This branch adds strict parsing for:

- `REID_DESCRIPTOR_TTL_SECS`, default `86400`; `0` disables retention.
- `REID_PURGE_INTERVAL_SECS`, default `300`.

The Helm chart exposes corresponding `reid.descriptorTtlSecs` and
`reid.purgeIntervalSecs` values and maps them to the scene-controller
environment. An explicit TTL value of `0` is preserved.

## Alternatives Considered

- **Continue retaining descriptors indefinitely** — Preserves all historical
  ReID data but does not address growth under sustained ingestion.
- **Use only backend-native expiration** — Simpler for VDMS, but Qdrant has no
  equivalent and would remain unbounded.
- **Filter expired descriptors during queries** — Gives a strict identity
  validity deadline, but TTL in this change is intended only for physical
  storage reclamation.
- **Reclaim during add or match operations** — Avoids a timer but introduces
  variable delete cost into latency-sensitive paths.
- **Capacity-based eviction** — Can react directly to descriptor count or
  memory pressure, but requires separate eviction policies and backend support
  beyond this branch.

## Consequences

### Positive

- VDMS and Qdrant receive the same configurable retention interface.
- Sustained ingestion retains a bounded time horizon instead of all future
  descriptors.
- Backend-specific expiration details do not leak into deployment
  configuration.
- Reclaim is asynchronous and does not add work to normal ReID queries.
- TTL can be disabled without changing adapters or deployment topology.

### Negative

- Purged descriptors can no longer contribute to long-horizon
  re-identification.
- TTL does not provide a hard memory limit; high ingest can still consume
  substantial memory within the retention window.
- Descriptors created before this branch lack expiration metadata and are not
  reclaimed automatically.
- The purge owner is process-local. Multiple controller replicas may each
  issue idempotent reclaim requests against the shared store.
- Qdrant may retain deleted-point tombstones until segment optimization, so
  physical memory release can lag logical deletion.

## References

- User guide: [Storage Bounding](../user-guide/other-topics/how-to-enable-reidentification.md#storage-bounding)
- Related ADR: [ADR-0010 Extended Reidentification Architecture](./0010-reid-metadata-storage-architecture.md)
