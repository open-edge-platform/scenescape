<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Multi-camera retail deployment

## Prompt

```text
Deploy SceneScape in ~/deployments/retail-demo with scene name 'Retail Demo'. I don't have
live RTSP cameras — use these two recorded videos as the camera feeds instead:
- cam1: https://github.com/open-edge-platform/scenescape/blob/main/sample_data/demo_scenes/Queuing/video/qcam1.mp4
- cam2: https://github.com/open-edge-platform/scenescape/blob/main/sample_data/demo_scenes/Queuing/video/qcam2.mp4
```

## Expected agent behavior

1. All Step 1 fields (`deploy_dir`, `scene_name`, and the two video sources mapped to
   `camera_ids`) are explicit in the prompt — no clarifying questions needed.
2. Converts each GitHub blob URL to its raw download URL (e.g.
   `https://raw.githubusercontent.com/open-edge-platform/scenescape/main/sample_data/demo_scenes/Queuing/video/qcam1.mp4`)
   and downloads both videos autonomously (e.g. via `curl`/`wget`) into a local directory —
   never asks the user to supply the files or a live RTSP address.
3. Recognizes there are no live RTSP cameras and calls `deploy_inputs.py write` with
   `--video-files` (or `--video-dir` if both files were downloaded into one folder) instead of
   `--streams`, per [video-file-input.md](../references/video-file-input.md).
4. Reads back the synthesized `rtsp://mediaserver:8554/<camera_id>` streams via
   `deploy_inputs.py read` and passes those — not the original video file paths — to the
   orchestrator's `--streams`/`--camera-ids` flags.
5. Validates that `camera_ids` are unique before proceeding.
6. Persists `deploy-inputs.json`, then launches the orchestrator in an async terminal and polls
   for completion rather than blocking.
7. Calibration phase produces one calibration JPEG per camera ID.
8. Tracking verification (step 13) confirms tracked objects are observed across more than one
   camera, not just a single feed.
9. Reports `DEPLOY COMPLETE` with `scene_uid` and the Post-Task deployment metrics breakdown in
   the same response.
