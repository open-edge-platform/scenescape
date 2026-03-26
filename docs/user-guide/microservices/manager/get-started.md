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

From repository root:

```bash
docker compose up -d manager
```

Check service status:

```bash
docker compose ps manager
docker compose logs manager -f
```

Stop service:

```bash
docker compose stop manager
```

## Access points

- Web UI: `https://<host-or-ip>/`
- REST API base path: `https://<host-or-ip>/api/v1/`

For API discovery, refer to [API Reference](./api-reference.md).

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source.md

:::
hide_directive-->
