<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build Observation Processor from Source

## Prerequisites

- A working Docker Engine and Docker Compose installation.
- A clone of the SceneScape repository.
- Generated service secrets before deployment. From the repository root, run
  `make init-secrets` if they have not already been created.

## Build the image

From the repository root, build the Observation Processor image:

```bash
make observation_processor
```

This target builds the SceneScape common base image first, then builds the
Observation Processor runtime image. The service Makefile can also build the
image directly with `make -C observation_processor` when the common base image
is already available.

## Run with Docker Compose

Start the Scene Controller and Observation Processor profiles:

```bash
make deploy DEPLOY_PROFILES="controller observation-processor"
```

The service listens on port `50052` inside the Compose network with TLS, using
the network address `observation-processor.scenescape.intel.com`. `make
init-secrets` generates the `scenescape-observation-processor` server
certificate mounted by the Compose profile. The optional profile starts the
gRPC service but does not currently route Scene Controller detections to it.

For deployment credentials, environment variables, and a sample request, see
the [Observation Processor service README](../../../../../observation_processor/README.md).

## Tests

The unit and loopback gRPC tests are in
`tests/sscape_tests/observation_processor/`. After setting up the repository test
environment, run them with the same `PYTHONPATH` the root unit suite uses for
the spatial performance libraries:

```bash
PYTHONPATH="spatial_performance_primitives/frustum_gaussian/python:spatial_performance_primitives${PYTHONPATH:+:$PYTHONPATH}" \
  tests/.venv/bin/python -m pytest tests/sscape_tests/observation_processor -q
```

To run the full Scenescape unit suite (includes this package):

```bash
make run_sscape_unit_suite
```

## Kubernetes

A Helm chart for the Observation Processor has not been created yet. The
service cannot currently be deployed with the Scenescape Kubernetes chart.
