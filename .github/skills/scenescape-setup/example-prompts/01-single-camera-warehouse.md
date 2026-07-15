<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example — Single-camera warehouse deployment

## Prompt

```text
Deploy SceneScape in ~/deployments/warehouse-demo with one RTSP camera (cam1) and scene name
'Warehouse Demo'. Camera stream: rtsp://192.168.1.10:8554/cam1.
```

## Expected agent behavior

1. All Step 1 fields (`deploy_dir`, `streams`, `camera_ids`, `scene_name`) are explicit in the
   prompt — no clarifying questions needed.
2. Persist `deploy-inputs.json`, then launch the orchestrator in an async terminal.
3. Poll for completion rather than blocking; report `DEPLOY COMPLETE` with `scene_uid` and the
   Post-Task deployment metrics breakdown in the same response.
