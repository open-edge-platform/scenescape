<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Roadside baseline — commercial-safe provenance

## Short answer

**Yes — roadside weights must be trained without the RoadsideRadar dataset**
(CC BY-NC-SA 4.0, non-commercial). The SceneScape roadside path does that by
training only on **VIDETEC-2** (CC BY 4.0) with GNSS weak labels.

We do **not** load INFRA-3DRC / RoadsideRadar weights or labels.

## What is Apache-2.0 / commercially usable

| Asset | License | Role |
| --- | --- | --- |
| `baselines/roadside_seg.py` (and train/infer scripts) | Apache-2.0 | Compact reimplementation; paper-inspired method only |
| Checkpoint `roadside_videtec_ccby.pt` | Weights from VIDETEC training; code Apache-2.0 | Production candidate |
| VIDETEC-2 frames + GNSS | [CC BY 4.0](https://zenodo.org/records/17799385) | Train + eval (attribution required) |

## What is excluded (license sidestep)

| Asset | License | Status |
| --- | --- | --- |
| RoadsideRadar / INFRA-3DRC dataset | CC BY-NC-SA 4.0 | **Not used** for train or eval |
| Upstream `roadside-radar-seg` pretrained weights | n/a (none shipped; their *code* is Apache-2.0) | **Not used** |

Upstream code at https://github.com/bhanderisavan/roadside-radar-seg is
Apache-2.0 and may be used under those terms; their **dataset** must not be
used for commercial training. SceneScape sidesteps that by using VIDETEC only.

## Canonical checkpoint

```text
sample_data/radar_intersection/VIDETEC-2/phase1_baselines/roadside_videtec_ccby.pt
```

`meta` inside the `.pt` records `train_data`, `train_data_license`, and
`excludes_datasets`.

## Retrain

```bash
~/mainline/RadarPillar/.venv/bin/python \
  sample_data/radar_intersection/baselines/train_roadside_weak.py \
  --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
  --index sample_data/radar_intersection/VIDETEC-2/converted/frames/index.json \
  --gnss sample_data/radar_intersection/VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55/*_gps.csv \
  --sensor sample_data/radar_intersection/VIDETEC-2/converted/frames/sensor.json \
  --train-start 500 --train-end 9000 \
  --exclude-start 2100 --exclude-end 4100 \
  --stride 2 --accumulate-half-window 5 --epochs 40 --device cuda \
  -o sample_data/radar_intersection/VIDETEC-2/phase1_baselines/roadside_videtec_ccby.pt
```

Attribution when redistributing models or demos that used VIDETEC:
*VIDETEC-2, Zenodo 17799385, CC BY 4.0*.
