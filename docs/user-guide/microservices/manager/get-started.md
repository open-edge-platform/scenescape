<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Get Started with Manager Service

Use [Getting Started with Intel® SceneScape](../../get-started.md) for shared host and platform
setup. This page only covers manager-specific startup and verification.

## Build manager image

To build only the manager image from source, see [Build from Source](./get-started/build-from-source.md).

## Run the service using Docker Compose

<!-- AGENT: PREREQ - Run `make init-secrets` if not already completed. -->

From repository root:

<!-- AGENT: RUN - Start manager service. -->

```bash
docker compose up -d manager
```

**Expected output:** Manager container starts in detached mode and appears as `Up` in compose status.

<!-- AGENT: VERIFY - Run health checks to confirm service is running. -->

Check service status:

```bash
docker compose ps manager
docker compose logs manager -f
```

<!-- AGENT: VERIFY - Status should be `Up` with no startup errors in logs. -->

**Expected output:** Status column shows "Up", and startup logs show no errors

<!-- AGENT: RUN - Stop service for cleanup. -->

Stop service:

```bash
docker compose stop manager
```

**Expected output:** Manager container stops and is no longer running.

## Access points

<!-- AGENT: ACCESS - Manager Web UI and REST API endpoints. -->

- Web UI: `https://<host-or-ip>/`
- REST API base path: `https://<host-or-ip>/api/v1/`

For API discovery, refer to [API Reference](./api-reference.md).

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source.md

:::
hide_directive-->
