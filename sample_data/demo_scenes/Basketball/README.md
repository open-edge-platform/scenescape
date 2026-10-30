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
| `basketball-config.json` | DL Streamer GPU pipelines (`gvadetect` + TrackNet ball fill) |
| `compose.basketball-video.yml` | Private mediaserver + ffmpeg loopers + DL Streamer (`/dev/dri`) |
| `models/yolov8s-coco-person-basketball/` | OpenVINO **FP16** COCO IR + model-proc |
| `object-library.json` | Person + basketball Asset3D priors (FREE_3D; no `project_to_map`) |

**Not included:** Retail / Queuing scenes or pipelines. Detector is closed-set
COCO YOLO (not YOLO-World).

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
- shared `model-instance-id=bball-yolococo` + `batch-size=2`
- COCO YOLOv8s FP16; model-proc renames class 32 (`sports ball`) → `basketball`
  so `detection_labels=person,basketball` and the object library match

`compose.basketball-video.yml` mounts `/dev/dri` and host GIDs `video=44` /
`render=992`. After changing the config or model, recreate:

```bash
make basketball-video-source-down && make basketball-video-source-up
```

Safe GPU check (avoid `intel_gpu_top` / Mission Center on this host):

```bash
docker exec scenescape-basketball-video-1 python3 -c \
  'from openvino import Core; print(Core().available_devices)'
docker exec scenescape-basketball-video-1 \
  curl -s http://localhost:8080/pipelines/status
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

## Detector models

- **Deployed default:** closed-set COCO YOLOv8s FP16 (`models/yolov8s-coco-person-basketball/`).
  Rebuild IR: `bash sample_data/demo_scenes/Basketball/models/prepare_yolo_coco.sh`
- **Fine-tune (recommended for ball quality):** see
  [`models/finetune/README.md`](models/finetune/README.md) — sample frames,
  teacher-label, train 2-class YOLOv8s, export FP16, swap into
  `basketball-config.json`.

Keep `gvadetect` threshold around **0.25**; lowering it for the ball hurt
person precision without fixing ball quality on COCO sports-ball.

### TrackNet bounce fill

Fast bounces still drop YOLO boxes. `sscape_tracknet_ball` runs a 3-frame
heatmap model and, on misses, publishes a **fixed-size** square box (last YOLO
ball diameter) at the TrackNet peak — size is never inflated by tracking.

```bash
bash sample_data/demo_scenes/Basketball/models/tracknet/train_and_export.sh
make basketball-video-source-down && make basketball-video-source-up
```

See [`models/tracknet/README.md`](models/tracknet/README.md).

## Frustum vs DA-V2 depth compare

```bash
PYTHONPATH=scene_common/src tests/.venv/bin/python tmp_bball_dav2_compare.py \
  --out tmp_zverify_out/bball_depth_dynamics.json
```
