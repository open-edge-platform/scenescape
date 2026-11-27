<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Rolling Terrain Dataset

One person moving on a non-planar (rolling) surface, seen by two cameras, consumed by
[`RollingTerrainDataset`](../../../../tools/tracker/evaluation/datasets/rolling_terrain_dataset.py)
in the tracker evaluation pipeline. The ground height (z) varies along the path, so tracking
needs probabilistic (Mahalanobis) association and the observation processor in `full` mode
(scene mesh).

## Contents

- `scene_config.json` — scene and per-camera configuration (explicit intrinsics and extrinsics, `map: scene.glb`)
- `scene.glb` — scene mesh (world coordinates, Z-up, no mesh pose)
- `cam_front_left.json`, `cam_back_right.json` — per-camera object detections (JSONL, one frame per line)
- `gtLoc.json` — ground-truth object locations per frame

685 frames over about 52 s; timestamps are irregular (58–196 ms apart, about 13 Hz on average) and shared by both cameras.
