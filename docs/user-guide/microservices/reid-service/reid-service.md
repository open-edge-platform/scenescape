<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Re-ID Service

The Re-ID service packages the existing Re-ID database contract and VDMS and
Qdrant adapters as a standalone deployable service. This extraction keeps
adapter behavior unchanged and adds a backend-neutral gRPC boundary.

## Current Scope

The service provides health, `FindMatches`, `FindSchemaMetadata`, manual
`PurgeExpired`, and `IngestStats` wrappers alongside Tracker MQTT ingestion.
The Controller still uses compatible `controller.reid*` imports for its
in-process path. Controller retirement, POI APIs, gallery management, and
trajectory export are follow-on work.

## Identity State and Counting

The service publishes identity state and completed decisions on
`scenescape/data/reid/{scene_id}/{category}`. Messages retain `track_id`, `gid`,
`matched`, and `similarity`, and include `reid_state` and `unique_id_count`.
The four states preserve Controller behavior:

- `pending_collection`: gathering features or waiting for a query result.
- `matched`: an accepted match has assigned the gid.
- `query_no_match`: a query completed without an accepted match, including live-gid collisions.
- `reid_disabled`: matching is disabled; tracks retain their local identity.

`matched: false` alone does not indicate a completed no-match decision. Consumers
must inspect `reid_state`. Analytics preserves these states in regulated and
region output, and marks undecided Tracker objects as `pending_collection`.

The cumulative counter is owned by each scene/category matcher and resets when
the service restarts. It increments when a track is first registered without a
usable embedding or while ReID is disabled, and when a query has no accepted
match. A later no-match after an initially missing embedding increments it again,
as in the Controller. A no-match result after a track leaves also increments it.
It is not current occupancy or a count derived from terminal states.

`IngestStats` exposes per-matcher `unique_id_counts` and their aggregate in
`counters.unique_id_count`. Analytics forwards the applicable matcher count as
the existing `unique_detection_count` field in regulated scene messages.

## Configuration

The service uses `REID_DATABASE` (`VDMS` or `QDRANT`), `REID_HOSTNAME`,
`REID_PORT`, `REID_USE_TLS`, the existing Re-ID certificate variables, and
`REID_DESCRIPTOR_TTL_SECS`. `REID_SERVICE_PORT` selects the gRPC port and
defaults to `50051`.

The backend remains the Compose service `reid`; the extracted application is
`reid-service` so existing backend overrides continue to work.

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source

:::
hide_directive-->
