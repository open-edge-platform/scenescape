<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Deploy Scenescape on Docker

This guide deploys a clean Scenescape instance with Docker Compose: an empty scene database, without the bundled demo video sources or preloaded demo scenes. To run the demo instead, see [Deploy the Demo](./deploy-demo.md).

- **Time to Complete:** 15-30 minutes

## Prerequisites

- Verify you meet the [System Requirements](../../get-started/system-requirements.md), including Docker.
- A checkout of the Scenescape repository (see [Get Scenescape](../../get-started/installation.md#step-1-get-scenescape)).
- Container images available: see [Prepare Container Images](./prepare-images.md).

## Deploy

Before deploying for the first time, set the `SUPASS` environment variable to the super user password for logging into Scenescape. This should be different from your system user's password:

```bash
export SUPASS=<password>
```

Then, from the repository root:

```bash
# Build images from source:
make build-core docker-compose.yml .env deploy

# If you already ran `make init-secrets install-models` per Prepare Container Images (prebuilt path), use instead:
make docker-compose.yml .env deploy
```

The targets run in order:

- `build-core` generates secrets, builds the core service images, and installs the default models. Skip this and use the prebuilt-image command above if you prepared prebuilt images instead (see [Prepare Container Images](./prepare-images.md)).
- `docker-compose.yml` creates the Compose configuration from the repository's example configuration.
- `.env` creates the Compose environment file from the generated secrets.
- `deploy` starts the `controller` profile and requires `SUPASS` for the initial administrator account.

This starts the Scenescape core: the web application, database, broker, NTP server, Scene Controller, Analytics, and Auto Camera Calibration. It does not start the separate demo video-source stack, and it does not upload any demo scenes.

Verify the containers are running:

```bash
docker compose --profile controller ps
```

## Verify a Successful Deployment

If you are running remotely, connect using `https://<ip_address>` or `https://<hostname>`, using the correct IP address or hostname of the remote Scenescape system. If accessing on a local system, use `https://localhost`. If you see a certificate warning, click the prompts to continue to the site. For example, in Chrome click "Advanced" and then "Proceed to &lt;ip_address> (unsafe)".

> **Note:** These certificate warnings are expected due to the use of a self-signed certificate for initial deployment purposes. This certificate is generated at deploy time and is unique to the instance.

Sign in as `admin` with the password assigned to `SUPASS`.

The scene list is empty. Import or create your own scene and configure its cameras and analytics inputs before expecting detections or tracks; see [Build a Scene](../build-a-scene/index.md).

## Docker Compose Profiles

Scenescape uses [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/) to organize services into logical groups. When starting or stopping services, you must specify the same profile(s) used during deployment.

The following profiles are available:

| Profile             | Description                                                                             |
| ------------------- | --------------------------------------------------------------------------------------- |
| `controller`        | Scene Controller (tracking) + Analytics service. Used by this guide and `make demo`.    |
| `mapping`           | Enables mapping service.                                                                |
| `cluster-analytics` | Enables cluster-analytics service.                                                      |
| `tracker`           | Tracker service + Analytics service (no Scene Controller). Used by `make demo-tracker`. |

> **ReID backends:** For raw Compose, add exactly one of `sample_data/compose/docker-compose.vdms-override.yml` or `sample_data/compose/docker-compose.qdrant-override.yml`. Both overrides provide the same logical `reid` service, shared host `reid.scenescape.intel.com`, port `55555`, TLS settings, and certificates. See [Selecting the ReID Vector Database Backend](../../other-topics/how-to-enable-reidentification.md#selecting-the-reid-vector-database-backend).

Profiles can be specified on the command line with `--profile`:

```console
docker compose --profile controller up -d
```

Multiple profiles can be combined:

```console
docker compose --profile controller --profile mapping up -d
```

Alternatively, profiles can be set via the `COMPOSE_PROFILES` environment variable:

```console
export COMPOSE_PROFILES=controller
docker compose up -d
```

For multiple profiles, use a comma-separated list:

```console
export COMPOSE_PROFILES=controller,mapping
docker compose up -d
```

For more details, see the [Docker Compose profiles documentation](https://docs.docker.com/compose/how-tos/profiles/) and the [COMPOSE_PROFILES environment variable reference](https://docs.docker.com/compose/how-tos/environment-variables/envvars/#compose_profiles).

> **Note:** The `--profile` flags used with `docker compose down` must match those used when starting the services. Otherwise, containers started under a specific profile will remain running.

## Stopping and Starting

To stop the containers, use the following command in the project directory (see [Docker Compose Profiles](#docker-compose-profiles) for details on choosing profiles):

```console
docker compose --profile controller down --remove-orphans
```

To start again after the first time:

```console
docker compose --profile controller up -d
```
