<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Create Scene and Register Cameras via REST API

Scene creation and placeholder camera registration happen automatically when
[`reconstruct_and_finalize.py`](../scripts/reconstruct_and_finalize.py) finalizes the
reconstruction through the manager. The manager then updates those cameras with mapping-service
poses/intrinsics and applies mesh/camera alignment. Use the notes below if you need to inspect or
manually register additional cameras.

## Manually Creating a Scene

To create an empty scene before reconstruction is available:

```bash
curl -sk -X POST https://localhost/api/v1/scene \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "my_scene", "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]}'
```

The `transform` field is a 16-element row-major 4×4 identity matrix (required by the API).
Once reconstruction is done, finalize the mesh with
[`reconstruct_and_finalize.py`](../scripts/reconstruct_and_finalize.py) using `--scene-uid`.

## Scene coordinate convention

World `(0, 0)` is the scene's **bottom-left corner**, not the center. Valid ground-plane
coordinates span `[0, floorWidth] × [0, floorHeight]` in meters, where
`floorWidth = map_image_width_px / scale` and `floorHeight = map_image_height_px / scale`
(`scale` is pixels-per-meter). **Z is up**; the ground plane is at `z = 0`.

Camera `translation` / `rotation` values outside that positive XY range are still valid MQTT
data, but they will not appear in SceneScape's own web UI (the orthographic viewport frames
`bottom = 0` … `top = floorHeight`). A custom consumer that assumes a center origin will look
correct in isolation while the SceneScape UI looks empty or clustered at a corner — that is an
origin mismatch, not a tracker or topic bug.

Axes and camera local frame follow OpenCV / SceneScape convention (right-handed, Z-up scene;
camera identity looks along +Z with image X-right and Y-down). See
`docs/user-guide/how-to-guides/integrate-cameras-and-sensors.md` in the SceneScape repo.

## Camera Registration

`reconstruct_and_finalize.py` creates placeholder cameras before finalization. Manager finalization
requires those cameras to exist so it can update them by `camera_id`. To manually register a camera:

```bash
curl -sk -X POST https://localhost/api/v1/camera \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "camera1",
        "sensor_id": "camera1",
        "scene": "<scene-uid>",
        "transform_type": "quaternion",
        "translation": [x, y, z],
        "rotation": [qx, qy, qz, qw],
        "scale": [1.0, 1.0, 1.0],
        "intrinsics": {"fx": 945.6, "fy": 945.9, "cx": 640.2, "cy": 363.2}
    }'
```

## Notes

- `rotation` is a quaternion in `[x, y, z, w]` order.
- `intrinsics` must be a JSON object with keys `fx`, `fy`, `cx`, `cy` (not a list).
- `transform_type` must be `"quaternion"` when providing translation/rotation/scale.
- If a POST fails with 400 `"sensor_id already exists"`, delete the existing camera first.
  The camera API's path UID **is** the `sensor_id` (and the serializer's read-only `uid`
  field aliases it) — there is no list-all or `?sensor_id=` filter. Use the same string you
  chose at creation (e.g. `camera1` / `uav-1`):

  ```bash
  curl -sk -X DELETE "https://localhost/api/v1/camera/<camera_id>" \
    -H "Authorization: Token $TOKEN"
  ```

  To confirm which cameras a scene already has, `GET /api/v1/scene/<scene_uid>` embeds a
  `cameras` array; each entry's `uid` equals its `sensor_id`. Do not call
  `GET /api/v1/camera` without a UID (returns `"UID is required"`) or with a query filter
  (returns `"Unknown query parameter"`).
- The manager URL from the host is `https://localhost` (TLS required, self-signed cert).
  `web.scenescape.intel.com` is only a Docker network alias for container-to-container calls.
