<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Re-ID Service

The Re-ID service is the standalone home for the existing VDMS and Qdrant
adapters. The service exposes a backend-neutral gRPC boundary while the
Scene Controller continues to use the compatibility import paths in-process.

VDMS queries use a five-second socket timeout. A query exception or incomplete
response disconnects the client before releasing the query lock, discarding
pending replies. Normal queries and readiness probes share a rate-limited
reconnect path (at most one attempt every five seconds), so in-process Controller
callers recover without polling readiness. Failed queries are not automatically
replayed: a timed-out write may already have been applied by the backend.

## Build

```bash
make reid
```

To build all non-core services, including Re-ID:

```bash
make build-all
```

## Run with Compose

Build the image and select one backend override:

```bash
make reid

docker compose \
  -f docker-compose.yml \
  -f sample_data/compose/docker-compose.vdms-override.yml \
  up -d reid reid-service
```

The service listens on `REID_SERVICE_PORT` (default `50051`) and connects to
the backend using the existing `REID_*` settings. The baseline API declares
`Health` (including backend readiness), `FindMatches`, `FindSchemaMetadata`,
`PurgeExpired`, `IngestStats`, and the authorized `CreateCollection`,
`EnrollPoi`, and `AppendPoiEmbeddings` operations. POI enrollment uses
precomputed vectors and records writer attribution; metadata management,
deletion, and collection statistics remain follow-on work. See the
[wire contract and Python client example](../docs/user-guide/microservices/reid-service/reid-service.md#baseline-grpc-contract)
for request/response shapes, validation, and status codes.

Tracker scene streams are currently ingested over MQTT, not gRPC. Controller
migration, POI metadata management, gallery statistics, deletion, and trajectory
APIs are follow-on work.
