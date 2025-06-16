```text
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.
# See the LICENSE file in the root of this repository for details.
```
- [PERF/SYS/SSCAPE: Stability System Tests](#perfsyssscape-stability-system-tests)
  - [Test suite requirements mapping](#test-suite-requirements-mapping)
  - [Test suite prerequisites](#test-suite-prerequisites)
  - [PERF/SYS/SSCAPE/01: Verify Re-ID Functions Without Performance Degradation Over Time](#perfsyssscape01-verify-re-id-functions-without-performance-degradation-over-time)
    - [Test summary](#test-summary)
    - [Test requirements mapping](#test-requirements-mapping)
    - [Test Prerequisites](#test-prerequisites)
    - [Test steps](#test-steps)
  - [PERF/SYS/SSCAPE/01: Scene Performance Full](#perfsyssscape01-scene-performance-full)
    - [Test summary](#test-summary-1)
    - [Test requirements mapping](#test-requirements-mapping-1)
    - [Test Prerequisites](#test-prerequisites-1)
    - [Test steps](#test-steps-1)

# PERF/SYS/SSCAPE: Stability System Tests

```Performance```

Performance aims to validate the system's ability to maintain consistent performance and reliability over extended periods of operation, specifically during continuous video playback and real-time person reidentification. 

## Test suite requirements mapping

- [FAREQ-469](https://jira.devtools.intel.com/browse/FAREQ-469)
- [FAREQ-339](https://jira.devtools.intel.com/browse/FAREQ-339)
- [FAREQ-91](https://jira.devtools.intel.com/browse/FAREQ-91)

## Test suite prerequisites

- Successful Deployment of Scenescape
- Check all services are up and running

## PERF/SYS/SSCAPE/01: Verify Re-ID Functions Without Performance Degradation Over Time

### Test summary

- Verify that re-ID works without performance degradation over time

### Test requirements mapping

- [FAREQ-469](https://jira.devtools.intel.com/browse/FAREQ-469)
- [FAREQ-339](https://jira.devtools.intel.com/browse/FAREQ-339)

### Test Prerequisites

1. All services are up and running.

### Test steps

1. Start scenescape with vdms and re-ID enabled in queueing scene
1. Uncomment out vdms container
1. Add +reid to camerachain
1. Verify that re-identification works properly (only 3 unique ids detected, can verify through mqtt)
1. Verify `unique_detection_count` field under data/scene/person/Queuing/person
1. Validate that performance remains constant even after running for 3+ hours
1. Start scenescape in default state (No vdms container or reid)
1. Validate that performance remains constant

## PERF/SYS/SSCAPE/01: Scene Performance Full

### Test summary

- TODO

### Test requirements mapping

- [FAREQ-91](https://jira.devtools.intel.com/browse/FAREQ-91)

### Test Prerequisites

1. All services are up and running.

### Test steps

 - TODO

> Expected output:

```
$ make -C tests scene-performance-full
# Output will be added later
```
