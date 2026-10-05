<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# FP16_ft6 (placeholder)

Multi-class fine-tune (FT6) from FT2 + base-VoD distilled vehicle/cyclist
labels. **Not shipped yet** — train/export/promote still open (needs RadarPillar
+ FT2 ep11 `.pth`).

Dataset tooling is ready (`VIDETEC-2/finetune_ds_ft6/` when built). Full plan
and status:

[`.github/plans/radar-tuning-and-eval.md`](../../../.github/plans/radar-tuning-and-eval.md)
(section 4).

Until FT6 promotes, keep using **FP16_ft2** with `nms_thresh=0.05` and
`RADAR_ACCUMULATE_PAST=4`.
