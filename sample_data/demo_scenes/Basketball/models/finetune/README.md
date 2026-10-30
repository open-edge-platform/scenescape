<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Fine-tune person + basketball (closed-set YOLO)

COCO `sports ball` and YOLO-World both under-detect the orange indoor ball.
Fine-tune a **2-class** YOLOv8s on demo frames, then deploy OpenVINO FP16 on
the existing GPU `gvadetect` path.

## Teacher choice (important)

Do **not** use YOLO-World (or the weak COCO head) as the label teacher: the
student cannot beat systematic teacher misses. Prefer:

| Teacher | Role | On this host |
|---------|------|----------------|
| **Grounding DINO** (default) | text → boxes (`person`, `basketball`) | Practical: ungated HF, CPU-OK |
| **SAM3** | text/concept → masks/boxes | Better when available; needs gated `facebook/sam3` + CUDA |
| Manual / corrected labels | Gold standard | Always worth spot-checking balls |

## 1. Build a labeled dataset

```bash
set -a && . ./.cursor_proxy.env && set +a

# Grounding DINO teacher (recommended default)
python3 sample_data/demo_scenes/Basketball/models/finetune/prepare_dataset.py \
  --teacher grounding-dino \
  --gdino-model IDEA-Research/grounding-dino-tiny \
  --stride 10 --thr-person 0.30 --thr-ball 0.20

# If ball recall is still weak, try --gdino-model IDEA-Research/grounding-dino-base
# SAM3 (when HF access + CUDA exist):
#   python3 .../prepare_dataset.py --teacher sam3 --device cuda
```

Outputs: `dataset/images/{train,val}`, `dataset/labels/{train,val}`
(`0=person`, `1=basketball`).

**Review ball boxes before training.**

## 2. Train + export OpenVINO FP16

```bash
YOLO_FT_EPOCHS=60 YOLO_FT_DEVICE=cpu \
  bash sample_data/demo_scenes/Basketball/models/finetune/train_and_export.sh
# GPU: YOLO_FT_DEVICE=0
```

Writes `../yolov8s-ft-person-basketball/{xml,bin,json}`.

## 3. Deploy

Point `basketball-config.json` + compose bind-mount at
`yolov8s-ft-person-basketball`, keep `detection_labels=person,basketball` and
threshold ≈ `0.25`, then:

```bash
make basketball-video-source-down && make basketball-video-source-up
```

## Notes

- Do not commit `dataset/` or `runs/`.
- Kill any train started from YOLO-World teacher labels; relabel with DINO/SAM3 first.
