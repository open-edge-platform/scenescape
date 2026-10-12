<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Tests

The service test image runs the broker-independent status contract tests and the
Paho TLS configuration checks:

```sh
make -C positioning test-build
docker run --rm intel/scenescape-positioning-test:$(cat version.txt)
```

The root `make run_unit_tests` target also runs this Python test directory. The
TLS-specific tests are skipped when Paho MQTT is not installed in the host test
environment; the test image installs the pinned runtime dependency.
