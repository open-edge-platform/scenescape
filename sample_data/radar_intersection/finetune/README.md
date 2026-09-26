<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# RadarPillars fine-tune on VIDETEC-2 (gantry)

SceneScape demo / MQTT work is **deferred** until GNSS **VRU** recall improves.
This directory prepares a weak-label training set and documents fine-tuning
from the VoD checkpoint ([fthbng77/RadarPillar](https://github.com/fthbng77/RadarPillar),
HF `Fatihbin/radarpillars-vod`).

**Status:** FT4 fixes associated-set training by **freezing PillarAttention**
(nan-grad source). Best **eval window** is **2100–4100** (not 3000–5000).
Single-frame FT2 ep11 → **18.5%** VRU@3m there; with **±5-frame** gantry-static
accumulate → **51.4%** (associable subset ≥92–99%). Demo MQTT still deferred;
next is wire accumulate into the runtime path and/or FT5 train-on-densified.

## Why fine-tune

Baseline VoD-ego weights on real VIDETEC (calibrated UTM origin, stride-5):

- **PyTorch** ckpt: 8 dets / 401 frames; all-class @ 3 m ≈ **0.5%**; VRU FOV @ 3 m **0%**
- **OV** IR: all-class @ 3 m ≈ **16%** is mostly low-score `vehicle` clutter; VRU FOV @ 3 m ≈ **0.5%**
- Score threshold 0.1 → empty; 0.03 → weak boxes
- Many GNSS samples sit **outside** VoD forward `point_cloud_range`; elevation
  outliers drive Z far outside VoD anchors
- Synthetic VoD-like clouds: PyTorch↔OV matched tops agree (~0.6 m) — not an
  OV-only export failure

## 1. Build the dataset

```bash
python3 sample_data/radar_intersection/finetune/build_videtec_dataset.py \
  --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
  --gnss sample_data/radar_intersection/VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55/*_gps.csv \
  --sensor sample_data/radar_intersection/VIDETEC-2/converted/frames/sensor.json \
  --vru-class Pedestrian \
  --max-abs-elev-deg 20 \
  --pc-range -20 -40 -5 60 40 3 \
  -o sample_data/radar_intersection/VIDETEC-2/finetune_ds
```

Outputs KITTI-like `training/{velodyne,label_2,calib}` + `ImageSets/{train,val}.txt`
with one GNSS pseudo-box per kept frame (radar-local).

## 2. Fine-tune (RadarPillar / OpenPCDet)

```bash
git clone https://github.com/fthbng77/RadarPillar.git ~/mainline/RadarPillar
cd ~/mainline/RadarPillar
# follow upstream README: Python env, spconv, OpenPCDet develop install
huggingface-cli download fthbng77/radarpillars-vod \
  radarpillar_vod_best_map52.56.pth --local-dir weights

# Point DATA_PATH / dataset config at VIDETEC-2/finetune_ds (adapt yaml
# point_cloud_range to the gantry box used above). Then:
python tools/train.py \
  --cfg_file tools/cfgs/vod_models/vod_radarpillar_rot.yaml \
  --batch_size 4 --extra_tag videtec_gantry \
  --ckpt weights/radarpillar_vod_best_map52.56.pth
```

**Config changes to expect:** expand `POINT_CLOUD_RANGE` (and matching
anchors / feature map) beyond VoD `[0,-25.6,-3,51.2,25.6,2]`; keep 7-feature
radar input; start from VoD ckpt rather than from scratch.

## 3. Export OpenVINO + re-eval

```bash
python3 sample_data/radar_intersection/export_radarpillars_ov.py \
  --ckpt /path/to/fine_tuned.pth \
  -o sample_data/radar_intersection/model_installer/FP16

python3 sample_data/radar_intersection/batch_radarpillars_infer.py ...
python3 sample_data/radar_intersection/eval_radarpillars_gnss.py \
  --videtec-origin --vod-pc-range \
  --categories person,cyclist ...
```

Quality gate: GNSS **VRU** recall @ 2 m / 3 m must beat the VoD-ego baseline
before resuming `make demo-radar`.
