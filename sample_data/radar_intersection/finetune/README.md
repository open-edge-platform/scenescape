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

Fine-tune is **optional** and separate from `make demo-radar` (demo uses
shipped OpenVINO IRs only).

### RadarPillar checkout (portable)

Do **not** assume `~/mainline/RadarPillar`. Set an env var or clone as a
**sibling** of the Scenescape repo:

```bash
# From the parent of your scenescape checkout:
git clone https://github.com/fthbng77/RadarPillar.git RadarPillar
export RADARPILLAR_ROOT="$(pwd)/RadarPillar"   # or any absolute path
cd "$RADARPILLAR_ROOT"
# follow upstream README: Python env, spconv, OpenPCDet develop install
```

Scenescape tools resolve the tree via `finetune/radarpillar_env.py`:

1. `--radarpillar-root` / `RADARPILLAR_ROOT`
2. else `<scenescape>/../RadarPillar`

### Init weights

| Checkpoint | Where |
| --- | --- |
| **FT2 ep11** (recommended further fine-tune init) | Shipped: `sample_data/radar_intersection/weights/radarpillar_videtec_gantry_ft2_ep11.pth` |
| VoD baseline | Download into `$RADARPILLAR_ROOT/weights/` (not in Scenescape): |

```bash
huggingface-cli download fthbng77/radarpillars-vod \
  radarpillar_vod_best_map52.56.pth --local-dir "$RADARPILLAR_ROOT/weights"
```

### Train

```bash
# Preferred: NaN-guarded wrapper (defaults pretrained → shipped FT2 ep11)
"$RADARPILLAR_ROOT"/.venv/bin/python \
  sample_data/radar_intersection/finetune/train_videtec_gantry.py \
  --radarpillar-root "$RADARPILLAR_ROOT" \
  --cfg_file tools/cfgs/vod_models/videtec_radarpillar_gantry.yaml \
  --pretrained_model sample_data/radar_intersection/weights/radarpillar_videtec_gantry_ft2_ep11.pth

# Or upstream tools/train.py from $RADARPILLAR_ROOT (point DATA_PATH at finetune_ds)
```

Copy `finetune/videtec_radarpillar_gantry.yaml` into the RadarPillar cfg tree
if not already present. Expand `POINT_CLOUD_RANGE` beyond VoD
`[0,-25.6,-3,51.2,25.6,2]`; keep 7-feature radar input.

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

## 4. Multi-class distillation (FT6) — abandoned

A CPU multi-class fine-tune from FT2 + distilled Car/Cyclist **failed** the
camera-GT promotion gate (2026-10-08); IR/trainer artifacts were discarded.
**Ship ``FP16_ft2`` only.** Distill helpers (`distill_base_labels.py`,
``build_videtec_dataset.py --distill-jsonl``) remain if a GPU OpenPCDet retry
is ever warranted — not on the demo path.
