<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Re-ID Service

The Re-ID service packages the existing Re-ID database contract and VDMS and
Qdrant adapters as a standalone deployable service. This extraction keeps
adapter behavior unchanged and adds a backend-neutral gRPC boundary.

## Current Scope

The skeleton provides health, `FindMatches`, `FindSchemaMetadata`, and manual
`PurgeExpired` wrappers. The Controller still uses compatible
`controller.reid*` imports for its in-process path. Tracker MQTT ingestion,
Controller migration, POI APIs, gallery management, and trajectory export are
follow-on work.

## Configuration

The service uses `REID_DATABASE` (`VDMS` or `QDRANT`), `REID_HOSTNAME`,
`REID_PORT`, `REID_USE_TLS`, the existing Re-ID certificate variables, and
`REID_DESCRIPTOR_TTL_SECS`. `REID_SERVICE_PORT` selects the gRPC port and
defaults to `50051`.

The backend remains the Compose service `reid`; the extracted application is
`reid-service` so existing backend overrides continue to work.
