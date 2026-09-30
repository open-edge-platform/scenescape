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
   SUPASS=<password> RADAR_PERCEPTION=radarpillars RADAR_IR_DIR=FP16_ft2 \
     make demo-radar
   ```

Defaults: `DLSTREAMER_SRC=../dlstreamer`, `RADAR_REQUIRE_REAL=true`,
`RADAR_ACCUMULATE_PAST=10` (radarpillars). Re-runs skip Zenodo work when
`VIDETEC-2/.demo_ready` exists.

| Target | Purpose |
| --- | --- |
| `make prepare-radar-data` | VIDETEC download/convert + camera stage only |
| `make prepare-radar-videtec` | Radar + GNSS only |
| `make prepare-radar-camera` | Camera JPEGs only |
| `make build-dlsps-g3d` | Bake local DLSPS from `saratpoluri/dlstreamer` |

## Checked in vs fetched

| In git | First-deploy cache (gitignored) |
| --- | --- |
| Scene ZIP/JSON/PNG, compose, publishers, FT2 / roadside / classical IRs | `VIDETEC-2/` (Zenodo + convert), `camera_demo/` |

Attribution: *VIDETEC-2, Zenodo [17799385](https://zenodo.org/records/17799385), CC BY 4.0*.
