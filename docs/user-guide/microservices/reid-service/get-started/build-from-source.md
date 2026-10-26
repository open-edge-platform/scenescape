<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Build Re-ID Service from Source

Build the common image and standalone Re-ID image from the repository root:

```bash
make reid_service
```

The service is also included by `make build-all`. It is intentionally excluded
from `build-core` while the Controller continues to own the live in-process
Re-ID path.

Start it with a backend override after building:

```bash
docker compose \
  -f docker-compose.yml \
  -f sample_data/compose/docker-compose.vdms-override.yml \
  up -d reid reid-service
```

Use the Qdrant override instead when selecting Qdrant. The service listens on
`REID_SERVICE_PORT` (default `50051`) and uses the existing `REID_*` backend and
TLS configuration.
