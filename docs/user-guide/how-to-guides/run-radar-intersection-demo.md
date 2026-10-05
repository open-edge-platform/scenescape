<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Run the Radar-Intersection Fusion Demo

- **Time to Complete:** About 20–45 minutes (depends on perception mode)

This guide runs the **Radar Intersection** demo: radar detections on
`scenescape/data/radar/{id}` fused with OpenVINO camera `gvadetect`
(OMZ [`person-vehicle-bike-detection-crossroad-1016`](https://docs.openvino.ai/2024/omz_models_model_person_vehicle_bike_detection_crossroad_1016.html))
on four s110 cameras (`scenescape/data/camera/{id}`).

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
| `runtime/radar_scene_init.py` | Import ZIP + sync sensors from JSON |
| `runtime/radar_publisher.py` | Shared GST → FIFO → MQTT for all modes |
| `runtime/radar_file_playback.py` | `multifilesrc` / parse / `g3dinference` fragments |
| `prepare/` | First-deploy VIDETEC download/convert + camera stage |
| `model_installer/classical/` | Classical g3dinference JSON config |
| `model_installer/roadside/FP16/` | Roadside OpenVINO IR (VIDETEC-trained) |
| `model_installer/FP16/` / `FP16_ft2/` | RadarPillars IR |
| `make build-dlsps-g3d` | Bake DLSPS from [saratpoluri/dlstreamer](https://github.com/saratpoluri/dlstreamer) (`classical`/`roadside`/`radarpillars`) |

Roadside commercial path: see
[`baselines/PROVENANCE.md`](../../../sample_data/radar_intersection/baselines/PROVENANCE.md)
(VIDETEC CC BY 4.0; no RoadsideRadar NC dataset).

## Prerequisites

1. Same host requirements as the core demo (`SUPASS`, Docker, secrets).
2. Clone and build against **[saratpoluri/dlstreamer](https://github.com/saratpoluri/dlstreamer)**
   (generalized `g3dinference` with `classical` / `roadside` / `radarpillars`).
   Stock [open-edge-platform/dlstreamer](https://github.com/open-edge-platform/dlstreamer)
   does **not** include these runtimes yet.

   ```bash
   # sibling of the scenescape checkout (matches default DLSTREAMER_SRC)
   git clone https://github.com/saratpoluri/dlstreamer.git ../dlstreamer
   # optional: DLSTREAMER_SRC=/path/to/saratpoluri/dlstreamer
   ```

   `make demo-radar` / `make build-dlsps-g3d` bake that tree into the local
   `-g3d` DLSPS image.
3. Network access on **first** `make demo-radar` to download VIDETEC-2 from
   [Zenodo 17799385](https://zenodo.org/records/17799385) (CC BY 4.0)
   — radar HDF5 (~1.9 GiB), GNSS (~4 MiB), and optionally cameras
   (`runs_vru` ~4 GiB). Cached under gitignored `VIDETEC-2/` /
   `camera_demo/`. Re-runs are idempotent.
4. Manager/Controller with first-class radar (`DATA_RADAR`).

## First deploy (automated)

Scene definitions, FT2 / roadside / classical model IRs, and compose
pipelines are **in git**. VIDETEC bytes are **not**; `make demo-radar`
fetches and converts them on first run:

```bash
# One shot: bake g3d image + download/convert VIDETEC + stage cameras + start
SUPASS=<password> RADAR_PERCEPTION=radarpillars RADAR_IR_DIR=FP16_ft2 \
  make demo-radar
```

`demo-radar` depends on `prepare-radar-data` =

| Target | Script | Produces (gitignored) |
| --- | --- | --- |
| `prepare-radar-videtec` | `prepare/prepare_videtec_demo_data.py` | `VIDETEC-2/download/`, `radar/`, `gnss/`, `converted/` (dataset 51), `converted_r52/` (dataset 52) |
| `prepare-radar-camera` | `prepare/stage_videtec_camera_demo.py` | `camera_demo/{radar-cam*}/` JPEGs |

Defaults: `RADAR_REQUIRE_REAL=true` (fail if prep skipped / incomplete),
`RADAR_ACCUMULATE_PAST=10` for radarpillars. Skip pieces with
`SKIP_RADAR_VIDETEC_PREP=true`, `SKIP_RADAR_CAMERA_STAGE=true`, or
`CAM_MUTE=true`. Synthetic-only plumbing:
`SKIP_RADAR_VIDETEC_PREP=true RADAR_REQUIRE_REAL=false`.

The radar demo does not start the stock Retail / Queuing sample pipelines
(`mediaserver`, `retail-*`, `queuing-*`) or `autocalibration` — they are gated
behind the `sample-scenes` compose profile — and `radar-scene-init` deletes the Retail and
Queuing scenes from the database to save memory. Keep them with
`RADAR_PRUNE_OTHER_SCENES=false` and `--profile sample-scenes`.

Manual / CI refresh:

```bash
make prepare-radar-data          # radar+GNSS+cameras
make prepare-radar-videtec       # radar+GNSS only
python3 sample_data/radar_intersection/prepare/prepare_videtec_demo_data.py --check-only
```

## VIDETEC-2 real data

[VIDETEC-2](https://zenodo.org/records/17799385) (CC BY 4.0) is the
acceptance dataset. Prefer the automated path above. Manual equivalent:

1. Archives land in `sample_data/radar_intersection/VIDETEC-2/download/`
   (`Radar_dataset.zip`, `gnss.zip`, `runs_vru.tar.gz`).
2. `prepare/prepare_videtec_demo_data.py` extracts HDF5s and converts both radars:

   - radar **51** → `VIDETEC-2/converted/{frames,frames_bin,pcd_bin}/`
   - radar **52** → `VIDETEC-2/converted_r52/...` (time-aligned
     `3098–3928` ↔ radar1 `3270–4100`)

3. **Preferred densify (live):** single-frame `pcd_bin` + GST
   `accumulate-past` (`RADAR_ACCUMULATE_PAST=10` by default for
   radarpillars). No prebuilt densified bins required.

   Optional offline non-causal bins (legacy / A–B vs causal):

   ```bash
   python3 sample_data/radar_intersection/prepare/build_accumulated_pcd_bins.py \
     --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
     --accumulate-half-window 5 \
     --start-index 2100 --stop-index 4100 \
     -o sample_data/radar_intersection/VIDETEC-2/converted/pcd_bin_acc5
   # RADAR_PCD_SUBDIR=pcd_bin_acc5 RADAR_ACCUMULATE_PAST=0
   ```

4. `radar-data-init` mounts `RADAR_RAW_DATASET_DIR` /
   `RADAR2_RAW_DATASET_DIR` (defaults under `VIDETEC-2/converted*`) and
   copies into the sample-data volume.

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
2. Creates/updates the four s110 cameras and two radars from
   `RadarIntersection.json` so UI calibrations do not have to be repeated.

Default live pair for cam↔radar compare: `radar-cam1` (s110_o anchor) +
`intersection-radar1` (dataset 51). Restore the four s110 cameras / two radars via
`CAM_SENSOR_IDS` / `RADAR_SENSOR_IDS` (s110 o/n/w/s; radar2
time-aligned `3098–3928` ↔ radar1 `3270–4100`).

After you change poses in the UI (or edit the JSON), lock them for other
hosts:

```bash
# Prefer exporting from a known-good live DB into RadarIntersection.json,
# then:
python3 sample_data/radar_intersection/scene/pack_radar_scene_import.py
# commit RadarIntersection.json + RadarIntersection-scene-import.zip
# (+ calibration provenance JSON if you updated fits)
```

To refresh Mapbox imagery only (requires a Mapbox token, **not** stored in
git):

```bash
export MAPBOX_API_KEY=<token>
python3 sample_data/radar_intersection/scene/fetch_videtec_mapbox_map.py
python3 sample_data/radar_intersection/scene/pack_radar_scene_import.py
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
   `radar2/frames_bin` + `radar2/pcd_bin`, and per-camera JPEGs.
3. `radar-model-init` — installs config/IR for the selected `RADAR_PERCEPTION`.
4. `radar-stream` — shared GST publish path for radars + cameras. Detections
   stay sensor-local; Controller applies the JSON poses.

Open the UI and select **Radar Intersection**. Default fusion publishes
both radars and all four s110 cameras (see `CAM_SENSOR_IDS` /
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
| `DLSTREAMER_SRC` | `../dlstreamer` | [saratpoluri/dlstreamer](https://github.com/saratpoluri/dlstreamer) checkout for `build-dlsps-g3d` |
| `DLS_G3D_IMAGE` | `…:2026.2.0-ubuntu24-rc2-g3d` | Baked DLSPS tag |
| `CAM_DEVICE` | `GPU` | OpenVINO device for camera `gvadetect` |
| `CAM_MODEL` | `…/omz/person-vehicle-bike-detection-crossroad-1016/FP32/….xml` | OMZ crossroad detector |
| `CAM_MODEL_PROC` | `…/model-proc/person-vehicle-bike-detection-crossroad-1016.json` | vehicle / person / cyclist |
| `CAM_SCORE_THRESHOLD` | `0.6` | Global `gvadetect` score threshold |
| `CAM_PERSON_MIN_SCORE` | `0.75` | Extra person score floor (cuts sign/grass FPs) |
| `CAM_PERSON_MIN_HEIGHT_PX` | `100` | Drop tiny person boxes |
| `CAM_PERSON_MIN_ASPECT` | `1.2` | Require height/width ≥ this for person |
| `CAM_MODEL_INSTANCE_ID` | _(empty)_ | Optional shared `gvadetect` instance id (can stall 8-cam preroll) |
| `CAM_SENSOR_IDS` | `radar-cam1` | Default: s110_o anchor cam overlapping radar1; restore full 8-cam list for multi-view |
| `RADAR_SENSOR_IDS` | `intersection-radar1` | Default: dataset-51 radar only (paired with radar-cam1) |
| `RADAR_MUTE` / `CAM_MUTE` | `false` | Mute a modality |
| `RADAR_CAM_DATASET_DIR` | `./sample_data/radar_intersection/camera_demo` | Host tree with per-id JPEG dirs (auto-staged; gitignored) |
| `CAM_START_INDEX` / `CAM_STOP_INDEX` | `3270` / `4100` | JPEG sequence slice (`%06d.jpg`) |
| `SKIP_RADAR_CAMERA_STAGE` | `false` | `true` skips Zenodo download / `camera_demo` staging |
| `SKIP_RADAR_VIDETEC_PREP` | `false` | Skip Zenodo radar/GNSS download+convert |
| `RADAR_RAW_DATASET_DIR` | `…/VIDETEC-2/converted` | Host radar1 `frames/` / bins |
| `RADAR2_RAW_DATASET_DIR` | `…/VIDETEC-2/converted_r52` | Host radar2 densified bins |
| `RADAR_DATA_PATHS` / `RADAR_INDEX_RANGES` | empty / index ranges | Per-radar path override (default: mode `frames_bin` or `pcd_bin` + `radar2/…`) |
| `RADAR_START_INDEX` / `RADAR_STOP_INDEX` | `3270` / `4100` | Default radar1 slice (overridden per-id via `RADAR_INDEX_RANGES`) |
| `RADAR_REQUIRE_REAL` | `true` (via Makefile) | Fail if no real VIDETEC inputs |
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

Radar detections carry `"source": "radar"`. Camera detections are tagged
`"source": "camera"` by the `source=camera` property on
`sscape_post_inference_data_publish`, so tracks keep the originating sensor and
the scene view labels marks `R` / `C`. The property defaults to empty, so stock
pipelines publish unchanged payloads.

## GNSS accuracy gate (offline)

After producing per-frame RadarPillars detections JSONL (timestamps aligned with
`frames/index.json`), score against the Oct 9 RTK track:

```bash
python3 sample_data/radar_intersection/radarpillars/eval_radarpillars_gnss.py \
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
python3 sample_data/radar_intersection/radarpillars/export_radarpillars_ov.py \
  --ckpt sample_data/radar_intersection/weights/radarpillar_vod_best_map52.56.pth \
  -o sample_data/radar_intersection/model_installer/FP16
```

Optional offline Python smoke (not used by the demo path):

```bash
python3 sample_data/radar_intersection/radarpillars/radarpillars_infer.py
```

## Related

- [Add and Use Radar Sensors](./add-and-use-radar-sensors.md)
- [Run the LiDAR-Intersection Fusion Demo](./run-lidar-intersection-demo.md)
