<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Smart parking as a SceneScape spatial app

The Metro AI Suite
[smart-parking](https://github.com/open-edge-platform/edge-ai-suites/tree/main/metro-ai-suite/metro-vision-ai-app-recipe/smart-parking)
sample is **video analytics only** (DL Streamer detect/classify → MQTT/dashboard). This prompt is
**not** a port of that app. It borrows that sample’s **dataset** and a similar **vehicle VA
pipeline**, then deploys them as a **SceneScape multi-camera spatial** application (scene map,
cross-camera tracks, regions for stall / no-parking logic).

Use this when you need a small (~5 MB) downloadable clip to validate the full
`scenescape-setup` + `dlstreamer-coding-agent` path. For a Metro sample that already includes
SceneScape, prefer
[07-smart-intersection-custom-pipeline.md](./07-smart-intersection-custom-pipeline.md).

## Prompt

```text
Build a SceneScape spatial analytics app for a parking deck at ~/deployments/smart-parking
(scene name: Parking Deck B) — not a VA-only dashboard clone.

Borrow the Metro AI Suite smart-parking sample's video and a similar vehicle pipeline, then
add SceneScape scene tracking on top:

Dataset (download once; reuse as two camera feeds like the sample install.sh):
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/smart_parking_720p_30fps.mp4

Cameras (after download into ~/deployments/smart-parking/videos/):
- cam_entry -> new_video_1.mp4
- cam_aisle -> new_video_2.mp4

VA customization (dlstreamer-coding-agent, then SceneScape merge): detect vehicles with YOLO and
add vehicle color classification (similar to the smart-parking DPS config). Validate against the
downloaded clip. Use detectionPolicy.

Spatial app goals after DEPLOY COMPLETE (SceneScape, not the Metro VA sample):
- Reconstruct / use a scene map of the deck
- Track vehicles across cam_entry and cam_aisle with stable scene-level IDs where possible
- Support stall occupancy / no-parking via scene regions or tripwires on that map (configure
  after deploy if needed; do not stop at per-camera bounding boxes alone)
```

## Expected agent behavior

1. Treats this as a **SceneScape spatial** deploy (`scenescape-setup`), not a standalone DL
   Streamer / Metro smart-parking recreate. Dataset + pipeline customization come from the Metro
   VA sample; scene map / cross-camera tracking / regions are SceneScape.
2. Downloads the dataset URL into `<deploy_dir>/videos/`, creates `new_video_1.mp4` and
   `new_video_2.mp4`, then `deploy_inputs.py write` with `--video-files`,
   `--camera-ids cam_entry cam_aisle`, and a non-empty `--pipeline-customization-prompt`.
3. Follows [dlstreamer-coding-agent](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent)
   through validation → `<deploy_dir>/pipeline-customization/result.json`, then
   `configure_pipeline.py` merge into SceneScape native DPS form.
4. Runs the full orchestrator (bootstrap → calibrate → scene → tracking verification), not a
   VA-only compose stack.
5. Reports `DEPLOY COMPLETE` with `scene_uid` and Post-Task metrics; notes that stall /
   no-parking regions can be wired on the scene map after deploy (see
   [using-scene-output.md](../references/using-scene-output.md)).
