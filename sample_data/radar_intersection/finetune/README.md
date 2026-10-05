<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# RadarPillars fine-tune on VIDETEC-2 (gantry)

SceneScape demo / MQTT work is **deferred** until GNSS **VRU** recall improves.
This directory prepares a weak-label training set and documents fine-tuning
from the VoD checkpoint ([fthbng77/RadarPillar](https://github.com/fthbng77/RadarPillar),
HF `Fatihbin/radarpillars-vod`).

**Status:** Dense-cloud + FT2→OV closed. Offline OV-FT2 ±5 on 2100–4100 →
**52.4%** VRU@3m (`model_installer/FP16_ft2/`). **FT5** (train-time densify)
did **not** beat FT2 on the full-window gate (~39% H=5). Keep FT2 for demos;
causal densify in g3d (`accumulate-past=4`) is the live default (camera-GT
recall + map FP balance on the 3270–4100 loop; past=10 matches H=5 GNSS
recall offline ~52.7% VRU@3m but smears the VRU and raises vegetation clutter);
next quality lever is multi-class fine-tune (vehicle/cyclist distillation).

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
python3 sample_data/radar_intersection/radarpillars/export_radarpillars_ov.py \
  --ckpt /path/to/fine_tuned.pth \
  -o sample_data/radar_intersection/model_installer/FP16

python3 sample_data/radar_intersection/radarpillars/batch_radarpillars_infer.py ...
python3 sample_data/radar_intersection/radarpillars/eval_radarpillars_gnss.py \
  --videtec-origin --vod-pc-range \
  --categories person,cyclist ...
```

Quality gate: GNSS **VRU** recall @ 2 m / 3 m must beat the VoD-ego baseline
before resuming `make demo-radar`.

## 4. FT6 multi-class (vehicle/cyclist distillation)

FT2 learns persons only (GNSS VRU), so the head absorbs vehicle returns as
low-score ``person`` (road false positives). FT6 adds base-VoD distilled
vehicle/cyclist boxes outside the demo eval window:

```bash
# 1) Distill from base VoD OV IR (not FT2)
python3 sample_data/radar_intersection/finetune/distill_base_labels.py \
  --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
  --config sample_data/radar_intersection/model_installer/FP16/radarpillars_ov_config.json \
  --device CPU --score-threshold 0.03 --stride 2 \
  --start-index 0 --stop-index 6000 \
  -o sample_data/radar_intersection/VIDETEC-2/distill_base_vc.jsonl

# 2) Build associated GNSS person set + distilled vehicle/cyclist
python3 sample_data/radar_intersection/finetune/build_videtec_dataset.py \
  --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
  --gnss sample_data/radar_intersection/VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55/*_gps.csv \
  --sensor sample_data/radar_intersection/VIDETEC-2/converted/frames/sensor.json \
  --vru-class Pedestrian --pc-range -20 -40 -5 60 40 3 \
  --min-points-near-gt 1 --exclude-start 3270 --exclude-end 4100 \
  --distill-jsonl sample_data/radar_intersection/VIDETEC-2/distill_base_vc.jsonl \
  --distill-score 0.03 \
  -o sample_data/radar_intersection/VIDETEC-2/finetune_ds_ft6

# 3) Train from FT2 ep11 with frozen backbone_3d (see train_videtec_gantry.py)
# 4) Export to model_installer/FP16_ft6/ (do not overwrite FP16_ft2)
# 5) Promotion gate (past=4, thr 0.1, 3270–4100 camera-GT):
#    person recall ≥ FT2; road+veg FP share < FT2; vehicle conf≥0.3 non-trivial
```

Requires a RadarPillar / OpenPCDet checkout and the FT2 ep11 ``.pth``. Without
those, keep shipping ``FP16_ft2``.
