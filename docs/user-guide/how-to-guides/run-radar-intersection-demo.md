<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Run the Radar-Intersection Fusion Demo

- **Time to Complete:** About 20–45 minutes (depends on perception mode)

This guide runs the **Radar Intersection** demo: radar detections on
`scenescape/data/radar/{id}` fused with OpenVINO camera `gvadetect` on
`scenescape/data/camera/{id}`.

## Perception modes (`RADAR_PERCEPTION`)

All modes share one stack:
`g3dlidarparse` → `g3dinference` → `gvametaconvert` → MQTT
(`radar_sensor_contract`). Only the `model-type` and bin layout change.

| Mode | `model-type` | Input bins | When to use |
| --- | --- | --- | --- |
| **`classical`** (default) | `classical` | `frames_bin` (5-float) | Best **sparsity robustness** |
| **`roadside`** | `roadside` | `frames_bin` + OV PointNetSeg | Sparse DNN; VIDETEC CC BY weights |
| **`radarpillars`** | `radarpillars` | `pcd_bin` (7-float) | Pillar / VoD-style DNN |

```bash
SUPASS=<password> make demo-radar                              # classical
SUPASS=<password> RADAR_PERCEPTION=roadside make demo-radar
SUPASS=<password> RADAR_PERCEPTION=radarpillars make demo-radar
```

It does **not** use `g3dradarprocess` (raw ADC).

## Architecture

| Piece | Role |
| --- | --- |
| `docker-compose.radar-override.yml` | Scene/data/model init + `radar-stream` |
| `radar_publisher.py` | Shared GST → FIFO → MQTT for all modes |
| `radar_file_playback.py` | `multifilesrc` / parse / `g3dinference` fragments |
| `model_installer/classical/` | Classical g3dinference JSON config |
| `model_installer/roadside/FP16/` | Roadside OpenVINO IR (VIDETEC-trained) |
| `model_installer/FP16/` | RadarPillars IR |
| `make build-dlsps-g3d` | DLSPS image with `classical`/`roadside`/`radarpillars` runtimes |

Roadside commercial path: see
[`baselines/PROVENANCE.md`](../../../sample_data/radar_intersection/baselines/PROVENANCE.md)
(VIDETEC CC BY 4.0; no RoadsideRadar NC dataset).

## Prerequisites

1. Same host requirements as the core demo (`SUPASS`, Docker, secrets).
2. A local [DLStreamer](https://github.com/open-edge-platform/dlstreamer) checkout
   with generalized `g3dinference` including `classical` / `roadside` runtimes
   (default `../dlstreamer`). Override `DLSTREAMER_SRC=...`.
3. **Real VIDETEC-2 radar frames (recommended)** — see
   [VIDETEC-2 real data](#videtec-2-real-data). Without them,
   `radar-data-init` falls back to synthetic frames (plumbing only).
4. Camera JPEG sequence (optional for radar-only): V2X-Seq example under
   `sample_data/lidar_intersection/V2X-Seq-SPD-Example/infrastructure-side/image/`.
5. Manager/Controller with first-class radar (`DATA_RADAR`).

## VIDETEC-2 real data

[VIDETEC-2](https://zenodo.org/records/17799385) (CC BY 4.0) provides the
gantry FMCW detections used for the DNN acceptance gate. Synthetic bins do
**not** close that gate.

1. Download `Radar_dataset.zip` and `gnss.zip` from the Zenodo record.
2. Extract the HDF5 files and GNSS CSVs under
   `sample_data/radar_intersection/VIDETEC-2/` (git-ignored):

   ```bash
   mkdir -p sample_data/radar_intersection/VIDETEC-2/{download,radar,gnss}
   # place Radar_dataset.zip + gnss.zip into download/, then:
   unzip download/Radar_dataset.zip -d sample_data/radar_intersection/VIDETEC-2/radar
   unzip download/gnss.zip -d sample_data/radar_intersection/VIDETEC-2/gnss
   ```

3. Convert radar **51** (Oct 9 overlap with `rosbag2_2025_10_09-14_43_55`) to
   `(N,5)` frames + VoD 7-float `pcd_bin`, preserving `/frames/timestamp`:

   ```bash
   python3 radar/videtec_hdf5_to_frames.py \
     sample_data/radar_intersection/VIDETEC-2/radar/radar_dataset_51.h5 \
     -o sample_data/radar_intersection/VIDETEC-2/converted/frames
   python3 sample_data/radar_intersection/prepare_radar_demo_data.py \
     -o sample_data/radar_intersection/VIDETEC-2/converted \
     --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames
   ```

4. **Optional densify (C4):** stack ±5 neighbor frames into densified bins for
   `g3dinference` playback (same recipe as offline GNSS peak on 2100–4100).
   Does not change the GStreamer graph — point `RADAR_DATA_PATH` at the output:

   ```bash
   python3 sample_data/radar_intersection/build_accumulated_pcd_bins.py \
     --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
     --accumulate-half-window 5 \
     --start-index 2100 --stop-index 4100 \
     -o sample_data/radar_intersection/VIDETEC-2/converted/pcd_bin_acc5
   # Then set RADAR_RAW_DATASET_DIR / compose path to use pcd_bin_acc5, or:
   # RADAR_DATA_PATH=.../pcd_bin_acc5/%06d.bin RADAR_START_INDEX=2100 RADAR_STOP_INDEX=4100
   ```

5. `radar-data-init` mounts
   `RADAR_RAW_DATASET_DIR` (default
   `./sample_data/radar_intersection/VIDETEC-2/converted`). When `frames/` or
   `pcd_bin/` is present it copies real data into the sample-data volume;
   otherwise it generates synthetic frames. Set `RADAR_REQUIRE_REAL=true` to
   fail closed without the archive.

Attribution when using or redistributing converted frames:

> VIDETEC-2 dataset, Zenodo record [17799385](https://zenodo.org/records/17799385),
> Creative Commons Attribution 4.0 International (CC BY 4.0).

## Run

```bash
# Default: classical (g3dinference model-type=classical)
SUPASS=<password> make demo-radar

# OpenVINO roadside (model-type=roadside; VIDETEC CC BY weights)
SUPASS=<password> RADAR_PERCEPTION=roadside make demo-radar

# RadarPillars (model-type=radarpillars)
SUPASS=<password> RADAR_PERCEPTION=radarpillars make demo-radar
```

`make demo-radar` always runs `build-dlsps-g3d` so all four model-types are in
the plugin. Compose steps:

1. `radar-scene-init` — imports **Radar Intersection** (idempotent).
2. `radar-data-init` — `frames/`, `frames_bin/` (5-float), `pcd_bin/` (7-float).
3. `radar-model-init` — installs config/IR for the selected `RADAR_PERCEPTION`.
4. `radar-stream` — shared GST publish path for radar + camera.

Open the UI and select **Radar Intersection**.

### Radar-only

```bash
CAM_MUTE=true SUPASS=<password> make demo-radar
```

### Force real-data-only init

```bash
RADAR_REQUIRE_REAL=true CAM_MUTE=true SUPASS=<password> make demo-radar
```

## Useful environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `RADAR_PERCEPTION` | `classical` | `classical` \| `roadside` \| `radarpillars` |
| `RADAR_DEVICE` | `CPU` | OpenVINO device for roadside / radarpillars |
| `RADAR_SCORE_THRESHOLD` | mode default (`0` / `0.1`) | Use `≈0.03` for radarpillars on real VIDETEC |
| `RADAR_MODEL_CONFIG` | mode default under `vol-models` | Override g3dinference config JSON |
| `RADAR_DATA_PATH` | `frames_bin` or `pcd_bin` | multifilesrc pattern |
| `DLSTREAMER_SRC` | `../dlstreamer` | Checkout for `build-dlsps-g3d` |
| `DLS_G3D_IMAGE` | `…:2026.2.0-ubuntu24-rc2-g3d` | Baked DLSPS tag |
| `CAM_DEVICE` | `CPU` | OpenVINO device for `gvadetect` |
| `RADAR_MUTE` / `CAM_MUTE` | `false` | Mute a modality |
| `RADAR_RAW_DATASET_DIR` | `./sample_data/radar_intersection/VIDETEC-2/converted` | Host `frames/` / bins |
| `RADAR_START_INDEX` / `RADAR_STOP_INDEX` | `0` / unset | Frame slice |
| `RADAR_REQUIRE_REAL` | `false` | `true` fails if no real VIDETEC inputs |
| `DEMO_REBUILD_IMAGES` | `true` | Set `false` to skip Scenescape image rebuild |

## Verify

```bash
# Confirm data-init used real frames
docker compose -f docker-compose.yml \
  -f sample_data/radar_intersection/docker-compose.radar-override.yml \
  logs radar-data-init | tail -20

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

## GNSS accuracy gate (offline)

After producing per-frame RadarPillars detections JSONL (timestamps aligned with
`frames/index.json`), score against the Oct 9 RTK track:

```bash
python3 sample_data/radar_intersection/eval_radarpillars_gnss.py \
  --index sample_data/radar_intersection/VIDETEC-2/converted/frames/index.json \
  --detections /path/to/detections.jsonl \
  --gnss sample_data/radar_intersection/VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55/*_gps.csv \
  -o sample_data/radar_intersection/VIDETEC-2/gnss_metrics.json
```

Primary metrics are GNSS VRU recall @ 1/2/3 m and matched position error — not
camera-label mAP. Use the published VIDETEC local origin via `--videtec-origin`
(UTM 32N E=695310.500, N=5347376.094; see `videtec_local_origin.json`).

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
