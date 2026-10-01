<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Camera detector: OpenVINO YOLOX-S (default)

| | |
| --- | --- |
| Hugging Face | [`OpenVINO/yolox_s-fp16-ov`](https://huggingface.co/OpenVINO/yolox_s-fp16-ov) |
| License | **Apache-2.0** |
| Why default | Fits 8 intersection cameras near 10 FPS; YOLOX-L saturates GPU/CPU |

Larger variant: `CAM_YOLOX_VARIANT=l` → [`OpenVINO/yolox_l-fp16-ov`](https://huggingface.co/OpenVINO/yolox_l-fp16-ov).
