<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Build Re-ID Service from Source

Build the common image and standalone Re-ID image from the repository root:

```bash
make reid
```

The service is also included by `make build-all`. It is intentionally excluded
from `build-core` because the default Controller profile still uses the legacy
in-process ReID path.

Start it with a backend override after building:

```bash
docker compose \
  -f docker-compose.yml \
  -f sample_data/compose/compose.vdms-override.yml \
  up -d reid reid-service
```

Use `sample_data/compose/compose.qdrant-override.yml` instead when selecting Qdrant. The service listens on
`REID_SERVICE_PORT` (default `50051`) and uses the existing `REID_*` backend and
TLS configuration.

To keep Controller hierarchy publishing but delegate ReID matching and writes
to the service, set `CONTROLLER_REID_MODE=service` and start both the Controller
and ReID service profiles as shown in the [service configuration](../reid-service.md#configuration).
