# YOLOv7 Triton Model Repository

This directory contains everything needed to build and deploy a YOLOv7-tiny
FP16 model on NVIDIA Triton Inference Server.

## Directory Structure

```
model_repo/yolov7/
├── export/onnx/
│   └── yolov7-tiny-e2e-fp16input.onnx    # Source ONNX model (24MB)
├── fp16/triton/
│   ├── yolov7_ensemble/                   # Ensemble: chains preprocess + inference
│   │   ├── config.pbtxt
│   │   └── 1/.keep
│   ├── yolov7_preprocess/                 # DALI GPU preprocessing
│   │   ├── config.pbtxt
│   │   └── 1/model.dali                   # Serialized DALI pipeline (4KB)
│   └── yolov7_tiny_e2e_v1/               # TensorRT inference
│       ├── config.pbtxt
│       └── 1/model.plan                   # TensorRT FP16 engine (13MB)
└── scripts/
    ├── build_triton_repo.sh               # Builds everything from the ONNX
    └── serialize_dali.py                  # Generates the DALI preprocessing binary
```

## Ensemble Pipeline

A single gRPC call to `yolov7_ensemble` runs both stages:

```
Input: UINT8 BGR image (640x640x3)
  -> yolov7_preprocess (DALI on GPU)
     Normalize, BGR->RGB, HWC->CHW, cast to FP16
  -> yolov7_tiny_e2e_v1 (TensorRT on GPU)
     YOLOv7-tiny detection + EfficientNMS
  -> Output: num_dets, det_boxes, det_scores, det_classes
```

Configuration: 3 GPU instances, dynamic batching 1-32, 100ms max queue delay.

## Building the Model Repository

The `model.plan` and `model.dali` files are GPU-specific. If you change GPUs
(e.g., from T4 to A100), you need to rebuild them.

### Prerequisites

- NVIDIA GPU accessible from the build environment
- One of:
  - A running Triton pod in Kubernetes (auto-detected)
  - Docker with `nvcr.io/nvidia/tritonserver:24.08-py3`

### Build

```bash
cd model_repo/yolov7/scripts
./build_triton_repo.sh
```

The script auto-detects whether to use kubectl (running Triton pod) or Docker.
Override with `--method kubectl` or `--method docker`.

Common options:
```bash
./build_triton_repo.sh --max-batch 16        # Custom max batch size (default: 32)
./build_triton_repo.sh --gpu-instances 1     # Single GPU instance (default: 3)
./build_triton_repo.sh --input-size 1280     # For larger YOLOv7 variants
```

### What the build does

1. Copies the ONNX model into a Triton pod or Docker container
2. Runs `trtexec` to convert ONNX -> TensorRT FP16 engine (`model.plan`)
3. Runs `serialize_dali.py` to generate the DALI preprocessing pipeline (`model.dali`)
4. Generates all `config.pbtxt` files
5. Copies the built artifacts back to `fp16/triton/`

## Deploying to Triton Server

The Triton server pod mounts the models PVC at `/models` and reads from
`/models/models/`. The three model directories need to be at:

```
/models/models/yolov7_ensemble/
/models/models/yolov7_preprocess/
/models/models/yolov7_tiny_e2e_v1/
```

### Method 1: Copy to PVC via kubectl

```bash
# Find the tritonserver pod
TRITON_POD=$(kubectl get pods -n <namespace> | grep triton | awk '{print $1}')

# Copy the model directories
kubectl cp fp16/triton/yolov7_ensemble     $TRITON_POD:/models/models/yolov7_ensemble     -n <namespace>
kubectl cp fp16/triton/yolov7_preprocess   $TRITON_POD:/models/models/yolov7_preprocess   -n <namespace>
kubectl cp fp16/triton/yolov7_tiny_e2e_v1  $TRITON_POD:/models/models/yolov7_tiny_e2e_v1  -n <namespace>
```

Triton auto-loads new models when `--model-control-mode=poll` is set (default).

### Method 2: Upload via MinIO

If MinIO is configured, upload to the `models` bucket:

```bash
mc cp --recursive fp16/triton/yolov7_ensemble     minio/models/models/yolov7_ensemble/
mc cp --recursive fp16/triton/yolov7_preprocess   minio/models/models/yolov7_preprocess/
mc cp --recursive fp16/triton/yolov7_tiny_e2e_v1  minio/models/models/yolov7_tiny_e2e_v1/
```

## Using the Model in SceneScape

1. In the SceneScape UI, set the camera's **Camera Chain** field to `yolov7_tiny_e2e`
2. The pipeline generator reads `model_config.json` and finds the `yolov7_tiny_e2e` entry
3. It builds a GStreamer pipeline with NVDEC decode -> Triton gRPC inference
4. The inference script (`yolov7_triton_inference.py`) sends frames to the
   `yolov7_ensemble` model on the Triton server

The `model_config.json` entry:
```json
"yolov7_tiny_e2e": {
  "type": "triton",
  "params": {
    "model": "yolov7_tiny_e2e_v1",
    "inference-script": "yolov7_triton_inference",
    "triton-url": "tritonserver:8001",
    "use-ensemble": true,
    "ensemble-model-name": "yolov7_ensemble",
    "confidence-threshold": "0.45",
    "labels": ["person"]
  }
}
```

The Triton URL is resolved at runtime to the FQDN:
`<release>-tritonserver.<namespace>.svc.cluster.local:8001`
