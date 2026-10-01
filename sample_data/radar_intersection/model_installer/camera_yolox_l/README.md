<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Camera detector: OpenVINO YOLOX-L

Replaces OMZ `person-vehicle-bike-detection-crossroad-1016` for the
radar-intersection cameras.

| | |
| --- | --- |
| Hugging Face | [`OpenVINO/yolox_l-fp16-ov`](https://huggingface.co/OpenVINO/yolox_l-fp16-ov) |
| License | **Apache-2.0** (commercial-use permissive) |
| Format | OpenVINO IR FP16 (`yolox_l.xml` / `yolox_l.bin`) |
| Classes | COCO-80 (maps `car`/`bus`/`truck`/`train` → `vehicle`) |

`install-camera-yolox` copies a local IR from this folder when present, otherwise
downloads from Hugging Face into `models/public/yolox_l_fp16/`.
