
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Re-ID Service

The Re-ID service is the standalone home for the existing VDMS and Qdrant
adapters. This initial service skeleton exposes a thin gRPC boundary while the
Scene Controller continues to use the compatibility import paths in-process.

## Build

```bash
make reid_service
```

To build all non-core services, including Re-ID:

```bash
make build-all
```

## Run with Compose

Build the image and select one backend override:

```bash
make reid_service

docker compose \
  -f docker-compose.yml \
  -f sample_data/compose/docker-compose.vdms-override.yml \
  up -d reid reid-service
```

The service listens on `REID_SERVICE_PORT` (default `50051`) and connects to
the backend using the existing `REID_*` settings. The current API surface is a
skeleton for health, matching, schema metadata, and manual purge operations.

Controller migration, Tracker stream ingestion, POI management, gallery
statistics, deletion, and trajectory APIs are follow-on work.
