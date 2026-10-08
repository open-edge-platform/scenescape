<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Radar Intersection demo

Self-contained SceneScape fusion demo: VIDETEC-2 radars + cameras on
`scenescape/data/radar/{id}` and `scenescape/data/camera/{id}`, with portable
scene poses in `RadarIntersection.json`.

**Full guide:**
[Run the Radar-Intersection Fusion Demo](../../docs/user-guide/how-to-guides/run-radar-intersection-demo.md)

## Reproduce on a fresh machine

1. Clone Scenescape (this tree) and the **g3dinference** DLStreamer fork as a
   sibling:

   ```bash
   git clone <scenescape-url> scenescape
   git clone https://github.com/saratpoluri/dlstreamer.git dlstreamer
   cd scenescape
   ```

2. Set `SUPASS` (and other core demo secrets) as for any Scenescape demo.

3. First deploy (downloads VIDETEC-2 from Zenodo, converts radar 51/52, stages
   cameras, bakes the `-g3d` DLSPS image, starts the stack):

   ```bash
   SUPASS=<password> make demo-radar
   ```

Defaults: `RADAR_PERCEPTION=radarpillars` (FT2 IR), `RADAR_ACCUMULATE_PAST=4`,
`RADAR_SCORE_THRESHOLD=0.1`, `DLSTREAMER_SRC=../dlstreamer`,
`RADAR_REQUIRE_REAL=true`. Re-runs skip Zenodo work when
`VIDETEC-2/.demo_ready` exists. Override with
`RADAR_PERCEPTION=classical|roadside` when needed.

## Perception methods

| Mode | In one sentence |
| --- | --- |
| **`radarpillars`** (default) | Pillar/BEV DNN (FT2 OV IR) on densified `pcd_bin`; best person recall |
| **`classical`** | No NN — Doppler + spatial cluster/track on `frames_bin` |
| **`roadside`** | PointNet point labels + class-aware clustering on `frames_bin` |

Full explanations (algorithm, gates, IR paths):
[Run the Radar-Intersection Fusion Demo — Perception modes](../../docs/user-guide/how-to-guides/run-radar-intersection-demo.md#perception-modes-radar_perception).

| Target | Purpose |
| --- | --- |
| `make prepare-radar-data` | VIDETEC download/convert + camera stage only |
| `make prepare-radar-videtec` | Radar + GNSS only |
| `make prepare-radar-camera` | Camera JPEGs only |
| `make build-dlsps-g3d` | Bake local DLSPS from `saratpoluri/dlstreamer` |

## Script layout

| Folder | Contents |
| --- | --- |
| `runtime/` | Live GST/MQTT publisher, scene init (`demo-radar` compose) |
| `prepare/` | Zenodo download, HDF5→bins convert, camera staging |
| `radarpillars/` | Offline OV infer / export / eval / profile |
| `roadside/` | Roadside OV export + sparse publish loop |
| `scene/` | Scene ZIP pack, Mapbox map, GNSS pose fit |
| `baselines/` | Phase-1 classical/roadside comparison |
| `finetune/` | RadarPillars gantry fine-tune tooling (`RADARPILLAR_ROOT`; see finetune/README) |
| `weights/` | Shipped FT2 ep11 `.pth` for further fine-tune only (demo uses OV IRs) |
| `model_installer/` | Shipped classical / roadside / FT2 IRs |

## Checked in vs fetched

| In git | First-deploy cache (gitignored) |
| --- | --- |
| Scene ZIP/JSON/PNG, compose, publishers, FT2 / roadside / classical IRs | `VIDETEC-2/` (Zenodo + convert), `camera_demo/` |

Attribution: *VIDETEC-2, Zenodo [17799385](https://zenodo.org/records/17799385), CC BY 4.0*.
