<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Run the Radar-Intersection Fusion Demo

- **Time to Complete:** About 30–45 minutes (first image rebuild)

This guide runs the **Radar Intersection** demo: RadarPillars (OpenVINO IR)
detections on `scenescape/data/radar/{id}` fused with OpenVINO camera
`gvadetect` on `scenescape/data/camera/{id}`.

It does **not** use `g3dradarprocess` (raw ADC). Inference is a DLSPS
`user_scripts` path (`radar_publisher.py` + `radarpillars_infer.py`).

## Architecture

| Piece | Role |
| --- | --- |
| `sample_data/radar_intersection/docker-compose.radar-override.yml` | Scene/data/model init + `radar-stream` |
| `radar_publisher.py` | Radar OV infer + camera GStreamer `gvadetect` → MQTT |
| `radarpillars_infer.py` | VIDETEC `(N,5)` → PCD → host VFE/attention + OV BEV/detect |
| `model_installer/FP16/` | Baked RadarPillars OpenVINO IR + preproc weights |
| `RadarIntersection-scene-import.zip` | Scene + camera + first-class radar sensor |

Model: [Fatihbin/radarpillars-vod](https://huggingface.co/Fatihbin/radarpillars-vod)
(Apache-2.0). Domain gap: VoD ego training vs gantry VIDETEC — this demo
proves IR + DLS + SceneScape plumbing; quality may need fine-tuning later.

## Prerequisites

1. Same host requirements as the core demo (`SUPASS`, Docker, secrets).
2. Camera JPEG sequence (optional for radar-only): the V2X-Seq example used by
   the LiDAR demo under
   `sample_data/lidar_intersection/V2X-Seq-SPD-Example/infrastructure-side/image/`.
   Override with `RADAR_CAM_DATASET_DIR` if needed.
3. Manager/Controller images that include first-class radar
   (`DATA_RADAR`, `Radar` sensor). `make demo-radar` rebuilds core images by
   default (`DEMO_REBUILD_IMAGES=true`).

## Run

```bash
SUPASS=<password> make demo-radar
```

Compose starts:

1. `radar-scene-init` — imports **Radar Intersection** (idempotent).
2. `radar-data-init` — synthetic radar `.npy` frames + re-encoded camera JPEGs.
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
| `RADAR_DEVICE` | `CPU` | OpenVINO device for RadarPillars |
| `CAM_DEVICE` | `CPU` | OpenVINO device for `gvadetect` |
| `RADAR_MUTE` / `CAM_MUTE` | `false` | Mute a modality |
| `RADAR_CAM_DATASET_DIR` | LiDAR V2X example tree | Must contain `infrastructure-side/image/` |
| `DEMO_REBUILD_IMAGES` | `true` | Set `false` to skip rebuild when images are current |

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

`radar-stream` logs should show `[radar] frame … objects=N`. Scene view should
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

Smoke-test:

```bash
python3 sample_data/radar_intersection/radarpillars_infer.py \
  # or import RadarPillarsOV and run on a synthetic / VIDETEC frame
```

## Related

- [Add and Use Radar Sensors](./add-and-use-radar-sensors.md)
- [Run the LiDAR-Intersection Fusion Demo](./run-lidar-intersection-demo.md)
