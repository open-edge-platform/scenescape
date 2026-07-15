<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Multi-camera retail deployment

## Prompt

```text
Deploy SceneScape in ~/deployments/retail-demo with three RTSP cameras and scene name
'Retail Demo':
- cam1: rtsp://192.168.1.10:8554/cam1
- cam2: rtsp://192.168.1.11:8554/cam2
- cam3: rtsp://192.168.1.12:8554/cam3
```

## Expected agent behavior

1. All Step 1 fields (`deploy_dir`, `streams`, `camera_ids`, `scene_name`) are explicit in the
   prompt — no clarifying questions needed.
2. Validates `len(streams) == len(camera_ids)` (3 == 3) and that camera IDs are unique before
   proceeding.
3. Persists `deploy-inputs.json`, then launches the orchestrator in an async terminal and polls
   for completion rather than blocking.
4. Calibration phase produces one calibration JPEG per camera ID.
5. Tracking verification (step 13) confirms tracked objects are observed across more than one
   camera, not just a single feed.
6. Reports `DEPLOY COMPLETE` with `scene_uid` and the Post-Task deployment metrics breakdown in
   the same response.
