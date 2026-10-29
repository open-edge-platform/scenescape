<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Basketball demo

Stairs-style single-scene demo for evaluating **3D basketball tracking** (frustum
Gaussian → observation conditioning → probabilistic tracker) against monocular
metric depth (Depth Anything V2).

## Contents

| Path | Purpose |
|------|---------|
| `video/cam{1,2}.mp4` | Concatenated set-1 + set-2 clips (1280×720 @ 15 fps, ~78 s) |
| `Basketball.zip` | Scene import (placeholder floor map; cameras `bball-cam1` / `bball-cam2`, uncalibrated) |
| `basketball-config.json` | DL Streamer GPU pipelines (`gvadetect` + YOLO-World person/basketball) |
| `compose.basketball-video.yml` | Private mediaserver + ffmpeg loopers + DL Streamer (`/dev/dri`) |
| `models/yolov8s-worldv2-person-basketball/` | OpenVINO **FP16** IR + `yolo_v8` model-proc |
| `object-library.json` | Person + basketball Asset3D priors (FREE_3D; no `project_to_map`) |

**Not included:** Retail / Queuing scenes or pipelines. No CPU detection sidecar.

## Start

```bash
SUPASS=<password> make demo-basketball
```

This brings up core SceneScape **plus the mapping profile** (needed to build the
map and calibrate cameras), imports only the Basketball scene, and starts the
Basketball video source. It does **not** start Retail/Queuing mediaserver or
pipelines.

Stop with `make demo-close`.

### GPU inference (both cameras in sync)

`basketball-config.json` runs **both** cameras through DL Streamer with:

- `decodebin3` → `video/x-raw(memory:VAMemory)` (VA decode)
- `gvadetect device=GPU pre-process-backend=va-surface-sharing`
- shared `model-instance-id=bball-yoloworld` + `batch-size=2` so both streams
  hit the same OpenVINO FP16 YOLO-World instance at a common rate

`compose.basketball-video.yml` mounts `/dev/dri` into `basketball-video`. After
changing the config or model, recreate that service:

```bash
SCENESCAPE_NETWORK=$(docker network ls --format '{{.Name}}' | grep -E '_scenescape$' | head -1) \
  docker compose --project-directory . -f sample_data/demo_scenes/Basketball/compose.basketball-video.yml \
  up -d --force-recreate basketball-video
```

Confirm GPU is in use (look for `GPU` / `va-surface-sharing` / no long CPU
inference stalls):

```bash
docker logs scenescape-basketball-video-1 2>&1 | tail -50
```

## Map + calibration (required once)

The shipped zip uses a placeholder floor PNG and approximate intrinsics — there
are no extrinsics. After `demo-basketball` is up:

1. Open the Basketball scene in the UI (3D).
2. Set calibration type to **Markerless** if not already.
3. Capture frames from `bball-cam1` / `bball-cam2` (or use the mapping-service
   reconstruction flow) to generate the mesh and auto-calibrate poses.
4. Confirm the scene controller is subscribed to
   `scenescape/data/camera/bball-cam{1,2}`.

Observation conditioning is gated on scene name `Basketball` (same allow-list
path as Stairs).

## Regenerate YOLO-World FP16 IR (optional)

No OpenVINO YOLO-World FP16 IR is published on Hugging Face for this use case.
Convert Ultralytics → OpenVINO FP16 locally (corporate proxy for weight download):

```bash
bash sample_data/demo_scenes/Basketball/models/prepare_yolo_world.sh
```

That writes FP16 `.xml`/`.bin` plus `yolo-world-person-basketball.json`
(`converter: yolo_v8`, labels `person,basketball`) under
`models/yolov8s-worldv2-person-basketball/`, which `gvadetect device=GPU` already
references.

## Frustum vs DA-V2 depth compare

```bash
PYTHONPATH=scene_common/src tests/.venv/bin/python tmp_bball_dav2_compare.py \
  --out tmp_zverify_out/bball_depth_dynamics.json
```

## DA-V2 comparison

Reuse the Stairs offline method (`tmp_zverify_mono_depth_compare.py`): same
detector BBs → frustum `depth_est` vs Depth-Anything-V2-Metric-Indoor median in
the BB core → world Z via camera pose.
