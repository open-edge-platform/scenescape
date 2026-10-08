<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# RadarPillars PyTorch checkpoints (fine-tune only)

These `.pth` files are **not** used by `make demo-radar` (that path loads
OpenVINO IRs from `model_installer/FP16_ft2/`).

| File | Role |
| --- | --- |
| `radarpillar_videtec_gantry_ft2_ep11.pth` | FT2 ep11 init for further gantry fine-tune / export |

**Not shipped** (download yourself into a RadarPillar checkout):

```bash
# VoD baseline (Hugging Face)
huggingface-cli download fthbng77/radarpillars-vod \
  radarpillar_vod_best_map52.56.pth --local-dir "$RADARPILLAR_ROOT/weights"
```

See [finetune/README.md](../finetune/README.md) for `RADARPILLAR_ROOT` setup.
