<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Test Image

The service test image runs the broker-independent status contract tests from
`tests/sscape_tests/positioning/` and the Paho TLS configuration checks:

```sh
make -C positioning test-build
docker run --rm intel/scenescape-positioning-test:$(cat version.txt)
```

The root `make run_unit_tests` target collects these tests with the rest of the
`tests/sscape_tests/` suite. The TLS-specific tests are skipped when Paho MQTT is
not installed in the host test environment; the test image installs the pinned
runtime dependency.
