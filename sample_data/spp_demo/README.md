<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SPP Demo: Tracking on Stairs with the Observation Processor

> **⚠️ Experimental.** Uses experimental tracking options that may change between releases.

This demo tracks people walking on stairs (non-planar motion) with the Tracker service and the
experimental Observation Processor service (spatial performance primitives). The Observation
Processor projects each pixel box with a frustum Gaussian and conditions it on the scene mesh
(amodal reasoning); the Tracker service tracks the returned 3D position with its measurement noise
covariance. See
[Experimental Observation Processor](../../docs/user-guide/microservices/controller/how-to-configure-tracker.md#experimental-observation-processor).

## Run

```bash
SUPASS='<choose-a-strong-admin-password>' make demo-spp
```

`make demo-spp` builds the core, Tracker, ReID and Observation Processor images (skip with
`DEMO_REBUILD_IMAGES=false`), then:

1. starts the default stack (`docker-compose.yml`) with the `tracker` and `observation-processor`
   profiles and the [`compose.spp-demo.yml`](compose.spp-demo.yml) overlay, which turns on the
   Tracker service's experimental observation processor;
2. starts the Stairs video source ([`compose.stairs-video.yml`](compose.stairs-video.yml),
   pipelines in [`stairs-config.json`](stairs-config.json)) for cameras `stair-cam-1` and
   `stair-cam-2`;
3. uploads the `Stairs` scene with its mesh and the [object library](object-library.json).

Stop it with `make demo-close`.

## Verify

- The Tracker service uses the observation processor:

  ```bash
  docker compose logs tracker | grep -i "observation processor"
  ```

  It logs `Experimental observation processor enabled`. Failed calls are logged as warnings
  (`Observation processor call failed ...; using local processing`).

- Open the `Stairs` scene in the web UI: tracks on the stairs follow the steps in height.
