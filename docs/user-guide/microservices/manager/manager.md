<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/scenescape/tree/main/manager">
     GitHub project
  </a>
</div>
hide_directive-->

# Manager Service

The Manager service is the Django-based web UI and REST API gateway for Intel® SceneScape.
It provides configuration and metadata management for scenes, cameras, sensors, and users.

## Overview

The Manager service handles user-facing configuration workflows and persistent metadata storage.
It exposes REST APIs for scene management and serves the web UI used to configure SceneScape.

Key responsibilities:

- Web UI for scene and camera management
- REST API for configuration and integration workflows
- Authentication and authorization
- Metadata persistence in PostgreSQL (no video/object trajectory storage)

To deploy the manager service, refer to [Get Started](./get-started.md).
To build it independently, refer to [Build from Source](./get-started/build-from-source.md).

## Architecture

The service is implemented as a Django application with:

- API endpoints under `manager/src/django/api/`
- models and business logic under `manager/src/django/scenescape/`
- templates and static UI assets under `manager/src/templates/` and `manager/src/static/`

The Manager service communicates with Scene Controller through authenticated REST calls and stores
configuration metadata in PostgreSQL.

## Configuration

Typical runtime configuration includes:

| Configuration Item   | Location/Variable                            | Purpose                                                                     |
| -------------------- | -------------------------------------------- | --------------------------------------------------------------------------- |
| Django secret key    | `SECRET_KEY`                                 | Protects Django cryptographic operations and session integrity.             |
| Database credentials | Generated secrets (`manager/secrets/django`) | Authenticates Manager service access to PostgreSQL metadata storage.        |
| TLS certificates     | `manager/secrets/certs/`                     | Enables TLS-secured service-to-service and user-facing communication.       |
| Service auth tokens  | `manager/secrets/*.auth`                     | Provides service account credentials for internal authentication workflows. |

For shared platform setup steps (host prerequisites, repository setup, secrets initialization,
and full-stack deployment), use the canonical [Getting Started](../../get-started.md) guide.

## Supporting Resources

- [Get Started](./get-started.md)
- [Build from Source](./get-started/build-from-source.md)
- [API Reference](./api-reference.md)
- [Platform Getting Started](../../get-started.md)
- [Using Intel® SceneScape](../../using-intel-scenescape/index.md)

<!--hide_directive
:::{toctree}
:hidden:

get-started.md
api-reference.md

:::
hide_directive-->
