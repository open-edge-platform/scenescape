<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Service

The Positioning service is the deployment boundary for source pose capabilities.
The current service shell establishes MQTT identity, retained resolver status,
liveness, and deployment wiring. Camera polling and pose resolution remain disabled
until the PTZ runtime is implemented.

## Documentation

- [Overview and Operations](../docs/user-guide/microservices/positioning/operations.md): Service shell, camera onboarding, deployment, and rollback details.
- [User Guide](../docs/user-guide/microservices/positioning/positioning.md): Service behavior, configuration, and deployment guidance.

## Quick Start

From the repository root, build the service image and create its broker identity and
client certificate:

```sh
make positioning
make init-secrets
```

Start the service through the test Compose profile or the Helm chart. Both mount the
CA, client certificate, private key, and auth file read-only.

## Testing

Run the repository unit suite:

```sh
make run_unit_tests
```

Build and run the service test image:

```sh
make -C positioning test-build
docker run --rm intel/scenescape-positioning-test:$(cat version.txt)
```

The runtime is generic: do not add lab camera IPs, usernames, passwords, or
camera-specific calibration to checked-in configuration. ONVIF credentials belong
in deployment secrets, and each camera's calibration belongs in Manager.
