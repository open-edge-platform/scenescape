<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Smart parking as a SceneScape spatial app

The Metro AI Suite
[smart-parking](https://github.com/open-edge-platform/edge-ai-suites/tree/main/metro-ai-suite/metro-vision-ai-app-recipe/smart-parking)
sample is **video analytics only** (DL Streamer detect/classify → MQTT/dashboard). This prompt is
**not** a port of that app. It borrows that sample’s **dataset** and a similar **vehicle VA
pipeline**, then builds a **SceneScape spatial** parking application on top.

Use this when you need a small (~5 MB) downloadable clip to validate the full
`scenescape-setup` + `dlstreamer-coding-agent` path. For a Metro sample that already includes
SceneScape and four distinct views, prefer
[07-smart-intersection-custom-pipeline.md](./07-smart-intersection-custom-pipeline.md).

**Caveat:** this dataset reuses one clip as two cameras (same as the Metro `install.sh` pattern).
That is enough to exercise deploy + spatial regions; it is **not** a good Re-ID demo — keep
`detectionPolicy` (do **not** enable Re-ID / `reidPolicy` by default).

## Prompt

```text
Build a SceneScape spatial analytics app for a parking deck at ~/deployments/smart-parking
(scene name: Parking Deck B) — not a VA-only dashboard clone of Metro smart-parking.

App outcomes (what spatial unlocks vs per-camera VA):
- Stall occupancy and no-parking / fire-lane dwell as scene regions on a deck map (scene-metre
  coordinates), not pixel ROIs redrawn per camera
- Deck utilization / heatmap from regulated scene translations over time
- Color (and other VA attributes) attached to scene-tracked vehicles in map space — where the
  vehicle is and how long it stays in a zone, not only "red car in this frame"
Do not enable Re-ID / reidPolicy for this deploy (detectionPolicy only). The sample reuses one
clip on two cameras; cross-camera identity is out of scope here.

Dataset (download once; reuse as two camera feeds like the sample install.sh):
https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/main/videos/smart_parking_720p_30fps.mp4

Cameras (after download into ~/deployments/smart-parking/videos/):
- cam_entry -> new_video_1.mp4
- cam_aisle -> new_video_2.mp4

VA customization (dlstreamer-coding-agent, then SceneScape merge): detect vehicles with YOLO and
add vehicle color classification (similar to the smart-parking DPS config). Validate against the
downloaded clip. Use detectionPolicy — not reidPolicy.

After DEPLOY COMPLETE: create named stall / no-parking regions on the scene map and point at
scenescape/regulated/scene/<scene_uid> (and region event topics) as the app integration surface.
```

## Expected agent behavior

1. Treats this as a **SceneScape spatial** parking app (`scenescape-setup`), not a Metro VA-only
   recreate. Emphasizes map regions / dwell / regulated scene output as the unlock vs per-camera
   boxes. Does **not** enable Re-ID (`reidPolicy`); persists `detectionPolicy` only.
2. Downloads the dataset URL into `<deploy_dir>/videos/`, creates `new_video_1.mp4` and
   `new_video_2.mp4`, then `deploy_inputs.py write` with `--video-files`,
   `--camera-ids cam_entry cam_aisle`, and a non-empty `--pipeline-customization-prompt`.
3. Follows [dlstreamer-coding-agent](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent)
   through validation → `<deploy_dir>/pipeline-customization/result.json`, then
   `configure_pipeline.py` merge into SceneScape native DPS form.
4. Runs the full orchestrator (bootstrap → calibrate → scene → tracking verification), not a
   VA-only compose stack.
5. Reports `DEPLOY COMPLETE` with `scene_uid` and Post-Task metrics; guides post-deploy stall /
   no-parking regions and MQTT consumers per
   [using-scene-output.md](../references/using-scene-output.md).
