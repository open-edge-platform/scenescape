<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SPP Demo: Tracking on Stairs with the Observation Processor

> **⚠️ Experimental.** Uses experimental tracking options that may change between releases.

This demo tracks people walking on stairs (non-planar motion) with the Tracker service and the
experimental Observation Processor service (spatial performance primitives), in two scenes:

- `Stairs`: recorded videos; DL Streamer Pipeline Server detects people with a person detection
  model.
- `Stairs-synthetic`: a rendered room with stairs and a synthetic person, which a person detection
  model does not detect. [Detection replay](../../tools/detection_replay/README.md) plays the
  videos with the detections recorded when rendering them instead, and publishes them like a
  detection-only pipeline. The videos already show the recorded boxes; the published Live View
  frames redraw them.

The Observation
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
3. starts the Stairs-synthetic detection replay
   ([`compose.stairs-synthetic-video.yml`](compose.stairs-synthetic-video.yml)) for cameras
   `cam1_front_left` and `cam2_back_right`, from the videos and per-frame detections in
   [`Stairs-synthetic`](Stairs-synthetic);
4. uploads the `Stairs` and `Stairs-synthetic` scenes with their meshes and the
   [object library](object-library.json).

Stop it with `make demo-close`.

## Verify

- The Tracker service uses the observation processor:

  ```bash
  docker compose logs tracker | grep -i "observation processor"
  ```

  It logs `Experimental observation processor enabled`. Failed calls are logged as warnings
  (`Observation processor call failed ...; using local processing`).

- The `Stairs-synthetic` cameras show Live View frames with the recorded boxes redrawn.

- Open the `Stairs` or `Stairs-synthetic` scene in the web UI: tracks on the stairs follow the
  steps in height.
