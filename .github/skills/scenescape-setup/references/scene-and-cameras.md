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
- If a POST fails with 400 "sensor_id already exists", delete the old camera first:
  `curl -sk -X DELETE https://localhost/api/v1/camera/<uid> -H "Authorization: Token $TOKEN"`
- The manager URL from the host is `https://localhost` (TLS required, self-signed cert).
  `web.scenescape.intel.com` is only a Docker network alias for container-to-container calls.
