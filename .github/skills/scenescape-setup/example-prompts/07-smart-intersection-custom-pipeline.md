<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Smart intersection as a SceneScape spatial app

The Metro AI Suite
[smart-intersection](https://github.com/open-edge-platform/edge-ai-suites/tree/main/metro-ai-suite/metro-vision-ai-app-recipe/smart-intersection)
sample already combines VA with SceneScape. This prompt builds a **spatial traffic analytics**
app on that sample’s **four-camera dataset** (helm `videosRepo` / `init-videos.sh`:
`1122{east,west,north,south}_h264.ts` from
[edge-ai-resources](https://github.com/open-edge-platform/edge-ai-resources)), with an optional
custom multi-class detect pipeline underneath.

**Note:** each `.ts` is ~300 MB (~1.2 GB total). Prefer
[06-smart-parking-custom-pipeline.md](./06-smart-parking-custom-pipeline.md) (~5 MB) when you only
need a small download to exercise VA→spatial lift; use this prompt for the real four-view
intersection dataset (distinct FOVs — suitable for cross-camera path continuity).

## Prompt

```text
Build a SceneScape spatial traffic analytics app at ~/deployments/smart-intersection
(scene name: Intersection 1122) on the Metro AI Suite smart-intersection four-camera dataset —
not camera-local detect-and-draw alone.

App outcomes (what spatial unlocks vs per-camera VA):
- Per-leg approach volume via tripwires on east/west/north/south approaches (direction counts
  in scene space)
- Crosswalk / conflict-zone occupancy via scene regions (counts, entered/exited, dwell)
- Vehicle ↔ pedestrian proximity in one shared scene-metre frame (two classes, same map)
- Path continuity around the square: follow a scene object ID as it moves through adjacent
  camera FOVs (visibility on the regulated scene topic)
- Optional: queue length on an approach from region counts

Dataset — same videosRepo as the smart-intersection helm chart:
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos

Cameras (download each into ~/deployments/smart-intersection/videos/):
- cam_east  -> 1122east_h264.ts
- cam_west  -> 1122west_h264.ts
- cam_north -> 1122north_h264.ts
- cam_south -> 1122south_h264.ts

Full URLs:
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122east_h264.ts
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122west_h264.ts
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122north_h264.ts
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/1122south_h264.ts

VA customization (dlstreamer-coding-agent, then SceneScape merge): detect vehicles and
pedestrians (multi-class). Validate against one downloaded .ts. Prefer GPU if available,
otherwise CPU. Use detectionPolicy.

After DEPLOY COMPLETE: create named approach tripwires and conflict-zone / crosswalk regions;
use scenescape/regulated/scene/<scene_uid> and region/tripwire event topics as the app
integration surface.
```

## Expected agent behavior

1. Treats this as a **SceneScape spatial traffic** app — tripwires, regions, multi-class scene
   positions, cross-camera path continuity — not “detect cars on four independent feeds.”
2. Downloads all four `.ts` files via the `github.com/.../raw/refs/heads/...` videosRepo URLs
   into `<deploy_dir>/videos/` (LFS-safe form; not blob pages).
3. Calls `deploy_inputs.py write` with `--video-files`,
   `--camera-ids cam_east cam_west cam_north cam_south`, and a non-empty
   `--pipeline-customization-prompt` for multi-class detect (+ device hint).
4. Follows [dlstreamer-coding-agent](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent)
   through validation → `<deploy_dir>/pipeline-customization/result.json`, then
   `configure_pipeline.py` merge.
5. Runs the full orchestrator asynchronously; tracking verification should see objects across
   more than one camera; reports `DEPLOY COMPLETE` with `scene_uid` and Post-Task metrics; points
   at post-deploy regions/tripwires per
   [using-scene-output.md](../references/using-scene-output.md).
