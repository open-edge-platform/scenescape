<!--
SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Security malformed data test

Verifies that the scene controller rejects malformed sensor (camera) data.

## Description

The test publishes detector messages onto the MQTT camera input topic and
checks what the controller forwards to the scene output topic. Each case runs
in isolation: one camera publishes for a short window while the test counts the
scene updates produced.

The controller must forward a message only when it both passes schema
validation and originates from a registered camera. Specifically:

- **Positive control** — a registered camera (`camera1`) sending valid data
  produces scene updates.
- **Schema-invalid messages** — produce no scene updates:
  - missing timestamp
  - confidence of zero or negative
  - negative bounding-box width
  - negative bounding-box height
  - negative detection id
  - non-string sender id
  - detection missing its category
  - detection missing bounding box / geometry
  - rotation quaternion component out of range
- **Unknown sender** — a valid payload from an unregistered camera (`camera4`)
  produces no scene updates.
- **Canary** — a freshly registered camera (`sensor10`) sending valid data
  produces scene updates, confirming the database and registration path are
  healthy (guards against false passes).

Known cameras other than `camera1` are registered at runtime over the REST API,
so no custom database fixture is required.

## How to run

```
pytest tests/security/malformed_data/test_malformed_data.py
```

The test brings up the full stack via the shared pytest fixtures and reports a
single pass/fail result for test id `NEX-T10423`.
