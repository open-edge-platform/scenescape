<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Run the Radar-Intersection Fusion Demo

- **Time to Complete:** About 30–45 minutes (first image rebuild)

This guide runs the **Radar Intersection** demo: RadarPillars detections via
DLStreamer `g3dinference model-type=radarpillars` on
`scenescape/data/radar/{id}`, fused with OpenVINO camera `gvadetect` on
`scenescape/data/camera/{id}`.

It does **not** use `g3dradarprocess` (raw ADC). Inference runs in GStreamer
(same shape as the LiDAR PointPillars demo).

## Architecture

| Piece | Role |
| --- | --- |
| `sample_data/radar_intersection/docker-compose.radar-override.yml` | Scene/data/model init + `radar-stream` |
| `radar_publisher.py` | Combined GStreamer pipeline → MQTT |
| `radar_file_playback.py` | `multifilesrc` / `g3dlidarparse point-features=7` / `g3dinference` fragments |
| `model_installer/FP16/` | Baked RadarPillars OpenVINO IR + RPW1 preproc weights |
| `RadarIntersection-scene-import.zip` | Scene + camera + first-class radar sensor |
| `make build-dlsps-g3d` | Local DLSPS image with generalized `g3dinference` |

Model: [Fatihbin/radarpillars-vod](https://huggingface.co/Fatihbin/radarpillars-vod)
(Apache-2.0). Domain gap: VoD ego training vs gantry VIDETEC — this demo
proves IR + DLS + SceneScape plumbing; quality may need fine-tuning later.

## Prerequisites

1. Same host requirements as the core demo (`SUPASS`, Docker, secrets).
2. A local [DLStreamer](https://github.com/open-edge-platform/dlstreamer) checkout
   with the generalized `g3dinference` branch (default path
   `../dlstreamer` next to this repo). Override with `DLSTREAMER_SRC=...`.
3. Camera JPEG sequence (optional for radar-only): the V2X-Seq example used by
   the LiDAR demo under
   `sample_data/lidar_intersection/V2X-Seq-SPD-Example/infrastructure-side/image/`.
   Override with `RADAR_CAM_DATASET_DIR` if needed.
4. Manager/Controller images that include first-class radar
   (`DATA_RADAR`, `Radar` sensor). `make demo-radar` rebuilds core images by
   default (`DEMO_REBUILD_IMAGES=true`).

## Run

```bash
SUPASS=<password> make demo-radar
```

`make demo-radar` first runs `build-dlsps-g3d` (rebuilds `libgst3delements.so`
inside the stock DLSPS container and tags
`intel/dlstreamer-pipeline-server:2026.2.0-ubuntu24-rc2-g3d`), then starts
compose:

1. `radar-scene-init` — imports **Radar Intersection** (idempotent).
2. `radar-data-init` — synthetic radar `.bin` PCD + optional camera JPEGs.
3. `radar-model-init` — copies RadarPillars IR into `vol-models`.
4. `radar-stream` — publishes radar + camera detections.

Open the UI and select **Radar Intersection**.

### Radar-only

```bash
CAM_MUTE=true SUPASS=<password> make demo-radar
```

### Fusion (default)

Leave `CAM_MUTE` / `RADAR_MUTE` unset (or `false`). Both modalities publish.

## Useful environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `DLSTREAMER_SRC` | `../dlstreamer` | Checkout used by `build-dlsps-g3d` |
| `DLS_G3D_IMAGE` | `…:2026.2.0-ubuntu24-rc2-g3d` | Baked DLSPS tag |
| `RADAR_DEVICE` | `CPU` | OpenVINO device for RadarPillars |
| `RADAR_SCORE_THRESHOLD` | `0.1` | `g3dinference` score filter |
| `CAM_DEVICE` | `CPU` | OpenVINO device for `gvadetect` |
| `RADAR_MUTE` / `CAM_MUTE` | `false` | Mute a modality |
| `RADAR_CAM_DATASET_DIR` | LiDAR V2X example tree | Must contain `infrastructure-side/image/` |
| `DEMO_REBUILD_IMAGES` | `true` | Set `false` to skip Scenescape image rebuild |

## Verify

```bash
# Radar detections
docker compose -f docker-compose.yml \
  -f sample_data/radar_intersection/docker-compose.radar-override.yml \
  exec -T broker mosquitto_sub -h localhost -t 'scenescape/data/radar/#' -C 3 -v

# Camera detections
docker compose -f docker-compose.yml \
  -f sample_data/radar_intersection/docker-compose.radar-override.yml \
  exec -T broker mosquitto_sub -h localhost -t 'scenescape/data/camera/radar-cam1' -C 3 -v

# Regulated scene (tracks)
docker compose -f docker-compose.yml \
  -f sample_data/radar_intersection/docker-compose.radar-override.yml \
  exec -T broker mosquitto_sub -h localhost -t 'scenescape/regulated/scene/#' -C 5 -v
```

`radar-stream` logs should show `[radar] frames=… objects=N`. Scene view should
show tracks with radar-only, then both sources when camera is unmuted.

## Stop

```bash
make demo-close
```

## Regenerating the OpenVINO IR

Host Python with `torch` + `openvino` + HF checkpoint:

```bash
python3 sample_data/radar_intersection/export_radarpillars_ov.py \
  --ckpt sample_data/radar_intersection/weights/radarpillar_vod_best_map52.56.pth \
  -o sample_data/radar_intersection/model_installer/FP16
```

Optional offline Python smoke (not used by the demo path):

```bash
python3 sample_data/radar_intersection/radarpillars_infer.py
```

## Related

- [Add and Use Radar Sensors](./add-and-use-radar-sensors.md)
- [Run the LiDAR-Intersection Fusion Demo](./run-lidar-intersection-demo.md)
