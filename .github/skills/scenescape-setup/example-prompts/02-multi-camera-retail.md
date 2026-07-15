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

1. Validates `len(streams) == len(camera_ids)` (3 == 3) and that camera IDs are unique before
   proceeding.
2. Calibration phase produces one calibration JPEG per camera ID.
3. Tracking verification (step 13) confirms tracked objects are observed across more than one
   camera, not just a single feed.
