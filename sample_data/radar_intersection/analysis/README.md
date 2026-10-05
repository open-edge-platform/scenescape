<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Radar-intersection evaluation harness

Offline tools for scoring radar perception modes against **camera
pseudo-ground-truth** and a **satellite class map**. Evaluation only —
map classes are not applied as product filters.

| Script | Role |
| --- | --- |
| `segment_map.py` | Build road/crosswalk/sidewalk/vegetation raster |
| `detect_camera_frames.py` | OMZ detector over staged camera JPEGs (run in radar-stream) |
| `project_camera_detections.py` | Project boxes to scene + radar-local (needs `scene_common`) |
| `metrics.py` | Recall@3m, map-class split, plausible-on-footpath, vehicle counts |
| `offline_g3d_infer.py` | Frame-indexed GST appsink runner (meta extraction best-effort) |
| `offline_g3d_publish.py` | GST `gvametapublish` runner with `lidar_frame.frame_id` reindexing |

Also usable: `baselines/classical_batch.py` and `baselines/roadside_batch.py`
(exact per-frame indexing, tunable cluster params).

## Quick path (reuse existing dets)

```bash
python3 sample_data/radar_intersection/analysis/segment_map.py \
  --out-npy /tmp/seg_cls.npy --out-overlay /tmp/seg_overlay.jpg

python3 sample_data/radar_intersection/analysis/metrics.py \
  --dets /tmp/det_past4.jsonl \
  --camera-gt /tmp/cam1_proj.json \
  --seg-npy /tmp/seg_cls.npy --name past4
```
