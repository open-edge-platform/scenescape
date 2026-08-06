<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Smart intersection (custom pipeline + downloadable dataset)

The Metro AI Suite
[smart-intersection](https://github.com/open-edge-platform/edge-ai-suites/tree/main/metro-ai-suite/metro-vision-ai-app-recipe/smart-intersection)
sample already combines VA with SceneScape. This prompt validates `scenescape-setup` against that
sample’s **four-camera dataset** (helm `videosRepo` / `init-videos.sh`:
`1122{east,west,north,south}_h264.ts` from
[edge-ai-resources](https://github.com/open-edge-platform/edge-ai-resources)), with an optional
custom multi-class detect pipeline.

**Note:** each `.ts` is ~300 MB (~1.2 GB total). Prefer
[06-smart-parking-custom-pipeline.md](./06-smart-parking-custom-pipeline.md) (~5 MB) when you only
need a small download to exercise VA→SceneScape spatial lift; use this prompt for the real
four-view intersection dataset.

## Prompt

```text
Deploy SceneScape for a smart intersection at ~/deployments/smart-intersection.
Scene name: Intersection 1122.

I don't have live RTSP cameras. Download the Metro AI Suite smart-intersection sample videos
from the same videosRepo the helm chart uses:

Base URL:
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos

Files / camera IDs:
- cam_east  -> 1122east_h264.ts
- cam_west  -> 1122west_h264.ts
- cam_north -> 1122north_h264.ts
- cam_south -> 1122south_h264.ts

Full download URLs (one per camera):
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122east_h264.ts
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122west_h264.ts
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122north_h264.ts
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122south_h264.ts

Customize the vision pipeline before SceneScape merge: detect vehicles and pedestrians for
traffic analytics (multi-class detection). Validate via dlstreamer-coding-agent against one of
the downloaded .ts files, then merge into SceneScape. Prefer GPU if available, otherwise CPU.
Use detectionPolicy. Default scene reconstruction map is fine.
```

## Expected agent behavior

1. All Step 1 fields (`deploy_dir`, `scene_name`, four camera IDs, four dataset URLs, and a
   non-empty customization request) are explicit — no clarifying questions needed for those.
2. Downloads each `.ts` with `curl -L` (or equivalent) from the `github.com/.../raw/refs/heads/...`
   URLs into `<deploy_dir>/videos/` — **not** `raw.githubusercontent.com` alone for these files
   (they are Git LFS assets; the helm `videosRepo` form resolves the real payload). Never asks
   the user to supply the files.
3. Calls `deploy_inputs.py write` with `--video-files` pointing at the four local `.ts` paths,
   `--camera-ids cam_east cam_west cam_north cam_south`, and
   `--pipeline-customization-prompt` for multi-class vehicle/pedestrian detection (+ device hint).
4. Because the customization prompt is non-empty: loads and follows
   [dlstreamer-coding-agent](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent),
   validates against a downloaded intersection clip, and writes
   `<deploy_dir>/pipeline-customization/result.json` with `validation.ran_successfully: true`
   before bootstrap step 6 can succeed.
5. Continues the SceneScape orchestrator; `configure_pipeline.py` merges/normalizes into DPS +
   SceneScape native plugins.
6. Launches `deploy_scenescape.sh` asynchronously; tracking verification should observe objects
   across more than one of the four cameras; reports `DEPLOY COMPLETE` with `scene_uid` and
   Post-Task metrics.
