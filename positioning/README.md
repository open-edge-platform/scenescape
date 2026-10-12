<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Service

Positioning is the deployment boundary for source pose capabilities. The initial
service shell establishes MQTT identity, retained resolver status, liveness, and
deployment wiring. Camera polling and pose resolution are intentionally disabled
until the PTZ runtime phase is added.

Build with `make positioning`; run the service tests with `make -C positioning
test-build` and `docker run --rm intel/scenescape-positioning-test:$(cat version.txt)`.
Service and deployment requirements are in [docs/README.md](docs/README.md).

The runtime is generic: do not add lab camera IPs, usernames, passwords, or
camera-specific calibration to the checked-in configuration. ONVIF credentials
belong in deployment secrets and each camera's calibration belongs in Manager.
