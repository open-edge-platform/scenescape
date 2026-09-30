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
| `RadarIntersection.json` + scene-import ZIP | Portable scene (map + sensor poses) |
| `radar_scene_init.py` | Import ZIP + sync sensors from JSON |
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
4. Camera JPEG sequence for fusion (default `CAM_MUTE=false`):
   - **Default:** `make demo-radar` runs `prepare-radar-camera`, which downloads
     VIDETEC-2 `runs_vru.tar.gz` from Zenodo (cached under gitignored
     `VIDETEC-2/download/`), extracts Oct‑9 `run_0` / `s110_o_cam_8`, and stages
     time-aligned JPEGs under gitignored
     `sample_data/radar_intersection/camera_demo/`. **No camera dataset files
     are committed to the repo.** Requires converted radar
     `VIDETEC-2/converted/frames/index.json` (step 3 below). Defaults:
     `RADAR_CAM_DATASET_DIR=./sample_data/radar_intersection/camera_demo`,
     `CAM_START_INDEX=3270`, `CAM_STOP_INDEX=4100`.
   - Skip staging: `CAM_MUTE=true`, or `SKIP_RADAR_CAMERA_STAGE=true`, or point
     `RADAR_CAM_DATASET_DIR` at another tree (e.g. V2X-Seq under
     `sample_data/lidar_intersection/V2X-Seq-SPD-Example` with
     `CAM_START_INDEX=10699` `CAM_STOP_INDEX=10949`).
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

4. **Preferred densify (live-ready):** single-frame `pcd_bin` + GST
   `accumulate-past` (causal ring in `g3dinference`). For radarpillars,
   `make demo-radar` defaults `RADAR_ACCUMULATE_PAST=10` (≈ offline ±5 span
   without future frames). No prebuilt densified bins required.

   Optional offline non-causal bins (legacy / A–B vs causal):

   ```bash
   python3 sample_data/radar_intersection/build_accumulated_pcd_bins.py \
     --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
     --accumulate-half-window 5 \
     --start-index 2100 --stop-index 4100 \
     -o sample_data/radar_intersection/VIDETEC-2/converted/pcd_bin_acc5
   # RADAR_PCD_SUBDIR=pcd_bin_acc5 RADAR_ACCUMULATE_PAST=0  # pre-densified
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

## Scene configuration (portable)

**Source of truth** for the demo scene is committed under
`sample_data/radar_intersection/`:

| Artifact | Role |
| --- | --- |
| `RadarIntersection.json` | Map scale / LLA corners + **all** camera and radar poses |
| `RadarIntersection.png` | Mapbox satellite (host file) |
| `RadarIntersection-scene-import.zip` | Fresh-machine import (JSON + map) |
| `radar_scene_init.py` | Imports the ZIP if needed, then **re-syncs** every sensor from the JSON |
| `pack_radar_scene_import.py` | Rebuilds the ZIP after JSON/map edits |
| `videtec_map_calibration.json` / `radar_pose_gnss_fit.json` | Provenance for how poses were derived |

On any machine, `make demo-radar` runs `radar-scene-init`, which:

1. Imports **Radar Intersection** from the ZIP if the scene is missing
   (e.g. after `make demo-close` wiped volumes).
2. Creates/updates the eight cameras and two radars from
   `RadarIntersection.json` so UI calibrations do not have to be repeated.

Default sensors: `radar-cam1` plus s110 n/w/s and s120 o/n/w/s; radars
`intersection-radar1` (dataset 51) and `intersection-radar2` (dataset 52,
time-aligned `3098–3928` ↔ radar1 `3270–4100`).

After you change poses in the UI (or edit the JSON), lock them for other
hosts:

```bash
# Prefer exporting from a known-good live DB into RadarIntersection.json,
# then:
python3 sample_data/radar_intersection/pack_radar_scene_import.py
# commit RadarIntersection.json + RadarIntersection-scene-import.zip
# (+ calibration provenance JSON if you updated fits)
```

To refresh Mapbox imagery only (requires a Mapbox token, **not** stored in
git):

```bash
export MAPBOX_API_KEY=<token>
python3 sample_data/radar_intersection/fetch_videtec_mapbox_map.py
python3 sample_data/radar_intersection/pack_radar_scene_import.py
```

Radar1 pose is GNSS XY/yaw fit (`radar_pose_gnss_fit.json`); radar2 is the
dataset-local ENU offset from radar1 with opposite yaw. Camera poses are
UI / PnP calibrations stored in the JSON — see
`videtec_map_calibration.json`.


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

1. `radar-scene-init` — imports **Radar Intersection** if missing, then
   syncs every camera/radar pose from `RadarIntersection.json`.
2. `radar-data-init` — `frames/`, `frames_bin/` (5-float), `pcd_bin/` /
   `radar2/pcd_bin` (7-float), and per-camera JPEGs.
3. `radar-model-init` — installs config/IR for the selected `RADAR_PERCEPTION`.
4. `radar-stream` — shared GST publish path for radars + cameras. Detections
   stay sensor-local; Controller applies the JSON poses.

Open the UI and select **Radar Intersection**. Default fusion publishes
both radars and all eight cameras (see `CAM_SENSOR_IDS` /
`RADAR_SENSOR_IDS`). Select any `radar-cam*` pane for live video;
`getimage` is answered per camera id.

Example (FT2 + **causal densify** + time-aligned VIDETEC camera fusion).
Camera staging is automatic on `make demo-radar` when `CAM_MUTE` is false
(first run downloads ~4 GiB `runs_vru` once into `VIDETEC-2/download/`):

```bash
SUPASS=<password> RADAR_PERCEPTION=radarpillars RADAR_REQUIRE_REAL=true \
  RADAR_IR_DIR=FP16_ft2 RADAR_ACCUMULATE_PAST=10 \
  RADAR_START_INDEX=3270 RADAR_STOP_INDEX=4100 RADAR_SCORE_THRESHOLD=0.1 \
  make demo-radar
```

(`RADAR_ACCUMULATE_PAST=10` is the radarpillars Makefile default; single-frame
`pcd_bin` is staged. Set `RADAR_ACCUMULATE_PAST=0` + `RADAR_PCD_SUBDIR=pcd_bin_acc5`
for the older pre-densified playback path.)

Open **Radar Intersection**, select any **radar-cam*** pane, and
confirm map tracks update while camera detections publish on
`scenescape/data/camera/{id}`. The staged slice covers frames
**3270–4100** (~15:01–15:02 CEST; see `camera_demo/ALIGN.json` after staging).
Use **`RADAR_SCORE_THRESHOLD=0.1`** (radarpillars default) so person count stays
near the single GNSS VRU; `0.03` floods the map with clutter.

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
| `RADAR_DEVICE` | `CPU` | OpenVINO device for roadside / radarpillars (`GPU` needs host `/dev/dri`; compose passes it through like the LiDAR demo) |
| `RADAR_SCORE_THRESHOLD` | mode default (`0` / `0.1`) | Radarpillars: use **`0.1`** (~1 person on densify slice); `0.03` is clutter |
| `RADAR_MODEL_CONFIG` | mode default under `vol-models` | Override g3dinference config JSON |
| `RADAR_DATA_PATH` | `frames_bin` or `pcd_bin` | multifilesrc pattern |
| `DLSTREAMER_SRC` | `../dlstreamer` | Checkout for `build-dlsps-g3d` |
| `DLS_G3D_IMAGE` | `…:2026.2.0-ubuntu24-rc2-g3d` | Baked DLSPS tag |
| `CAM_DEVICE` | `CPU` | OpenVINO device for `gvadetect` |
| `RADAR_MUTE` / `CAM_MUTE` | `false` | Mute a modality |
| `RADAR_CAM_DATASET_DIR` | `./sample_data/radar_intersection/camera_demo` | Host tree with per-id JPEG dirs (auto-staged; gitignored) |
| `CAM_SENSOR_IDS` | eight `radar-cam*` ids | Comma list; each needs `{CAM_DATA_ROOT}/{id}/%06d.jpg` |
| `CAM_START_INDEX` / `CAM_STOP_INDEX` | `3270` / `4100` | JPEG sequence slice (`%06d.jpg`) |
| `SKIP_RADAR_CAMERA_STAGE` | `false` | `true` skips Zenodo download / `camera_demo` staging |
| `RADAR_RAW_DATASET_DIR` | `…/VIDETEC-2/converted` | Host radar1 `frames/` / bins |
| `RADAR2_RAW_DATASET_DIR` | `…/VIDETEC-2/converted_r52` | Host radar2 densified bins |
| `RADAR_SENSOR_IDS` | `intersection-radar1,intersection-radar2` | Comma list of radar MQTT ids |
| `RADAR_DATA_PATHS` / `RADAR_INDEX_RANGES` | see compose | Per-radar bin path and start-stop |
| `RADAR_START_INDEX` / `RADAR_STOP_INDEX` | `3270` / `4100` | Default radar1 slice (overridden per-id via `RADAR_INDEX_RANGES`) |
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

# Camera detections (TLS on 1883 — prefer probing from radar-stream with paho+CA)
docker compose -f docker-compose.yml \
  -f sample_data/radar_intersection/docker-compose.radar-override.yml \
  logs radar-stream | grep -E '\[camera\]|\[radar\]' | tail -20

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
