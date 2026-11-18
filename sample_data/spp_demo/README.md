<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SPP Demo: Tracking on Non-Planar Terrain with the Observation Processor

> **⚠️ Experimental.** Uses experimental tracking options that may change between releases.

This demo tracks a person walking over rolling terrain (non-planar motion) with the Tracker
service and the experimental Observation Processor service (spatial performance primitives), in the
`Rolling-terrain` scene: a synthetic person that a person detection model does not detect.
[Detection replay](../../tools/detection_replay/README.md) plays the videos with the detections
recorded when rendering them instead, and publishes them like a detection-only pipeline. The videos
are trimmed so that they loop without a jump in the person's position. The videos already show the
recorded boxes; the published Live View frames redraw them.

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
2. starts the Rolling-terrain detection replay
   ([`compose.rolling-terrain-video.yml`](compose.rolling-terrain-video.yml)) for cameras
   `rt-cam1_front_left` and `rt-cam2_back_right`, from the videos and per-frame detections in
   [`Rolling-terrain`](Rolling-terrain);
3. uploads the `Rolling-terrain` scene with its mesh and the [object library](object-library.json).

Stop it with `make demo-close`.

## Verify

- The Tracker service uses the observation processor:

  ```bash
  docker compose logs tracker | grep -i "observation processor"
  ```

  It logs `Experimental observation processor enabled`. Failed calls are logged as warnings
  (`Observation processor call failed ...; using local processing`).

- The cameras show Live View frames with the recorded boxes redrawn.

- Open the scene in the web UI: the track follows the terrain in height.
