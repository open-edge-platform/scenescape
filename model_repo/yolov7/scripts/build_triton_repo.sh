#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0
#
# build_triton_repo.sh - Build YOLOv7 FP16 Triton model repository
#
# Converts the ONNX model (with EfficientNMS_TRT) to a TensorRT engine,
# serializes the DALI preprocessing pipeline, generates Triton config files,
# and populates the fp16/triton/ directory ready for deployment.
#
# Prerequisites:
#   - ONNX file with NMS at: ../export/onnx/yolov7-tiny-e2e-fp16input.onnx
#   - One of:
#     (a) A running Triton pod in Kubernetes (auto-detected)
#     (b) Docker with nvcr.io/nvidia/tritonserver:24.08-py3 image
#   - NVIDIA GPU accessible from the container/pod
#
# Usage:
#   ./build_triton_repo.sh                          # auto-detect method
#   ./build_triton_repo.sh --method kubectl          # force kubectl
#   ./build_triton_repo.sh --method docker            # force docker
#   ./build_triton_repo.sh --max-batch 16             # custom max batch size
#   ./build_triton_repo.sh --opt-batch 4              # custom optimal batch size
#   ./build_triton_repo.sh --input-size 1280          # for w6/e6/d6/e6e variants
#   ./build_triton_repo.sh --gpu-instances 1          # single GPU instance
#   ./build_triton_repo.sh --triton-namespace mxcp-client  # custom namespace

set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YOLOV7_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ONNX_FILE="${YOLOV7_DIR}/export/onnx/yolov7-tiny-e2e-fp16input.onnx"
OUTPUT_DIR="${YOLOV7_DIR}/fp16/triton"

# Model names (matching existing Triton deployment)
MODEL_PREPROCESS="yolov7_preprocess"
MODEL_INFERENCE="yolov7_tiny_e2e_v1"
MODEL_ENSEMBLE="yolov7_ensemble"

METHOD=""  # auto-detect
MAX_BATCH=32
OPT_BATCH=8
INPUT_SIZE=640
GPU_INSTANCES=3
TRITON_NS=""
TRITON_POD=""
TRITON_CONTAINER="tritonserver"
TRITON_IMAGE="nvcr.io/nvidia/tritonserver:24.08-py3"
TRTEXEC="/usr/src/tensorrt/bin/trtexec"
WORKSPACE_SIZE="8G"

# ──────────────────────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --method)        METHOD="$2"; shift 2 ;;
    --onnx)          ONNX_FILE="$2"; shift 2 ;;
    --output-dir)    OUTPUT_DIR="$2"; shift 2 ;;
    --max-batch)     MAX_BATCH="$2"; shift 2 ;;
    --opt-batch)     OPT_BATCH="$2"; shift 2 ;;
    --input-size)    INPUT_SIZE="$2"; shift 2 ;;
    --gpu-instances) GPU_INSTANCES="$2"; shift 2 ;;
    --triton-namespace) TRITON_NS="$2"; shift 2 ;;
    --triton-pod)    TRITON_POD="$2"; shift 2 ;;
    --triton-image)  TRITON_IMAGE="$2"; shift 2 ;;
    --workspace-size) WORKSPACE_SIZE="$2"; shift 2 ;;
    --model-preprocess) MODEL_PREPROCESS="$2"; shift 2 ;;
    --model-inference) MODEL_INFERENCE="$2"; shift 2 ;;
    --model-ensemble) MODEL_ENSEMBLE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --method <kubectl|docker>   Execution method (default: auto-detect)"
      echo "  --onnx <path>               ONNX file path (default: ../export/onnx/yolov7-tiny-e2e-fp16input.onnx)"
      echo "  --output-dir <path>         Output directory (default: ../fp16/triton)"
      echo "  --max-batch <N>             Max batch size (default: 32)"
      echo "  --opt-batch <N>             Optimal batch size for TensorRT (default: 8)"
      echo "  --input-size <N>            Input size - 640 for most, 1280 for w6/e6/d6/e6e (default: 640)"
      echo "  --gpu-instances <N>         Number of GPU instances for inference (default: 3)"
      echo "  --triton-namespace <ns>     Kubernetes namespace for Triton pod"
      echo "  --triton-pod <name>         Specific Triton pod name"
      echo "  --triton-image <image>      Docker image for Triton (default: nvcr.io/nvidia/tritonserver:24.08-py3)"
      echo "  --workspace-size <size>     TensorRT workspace size (default: 8G)"
      echo "  --model-preprocess <name>   Preprocess model name (default: yolov7_preprocess)"
      echo "  --model-inference <name>    Inference model name (default: yolov7_tiny_e2e_v1)"
      echo "  --model-ensemble <name>     Ensemble model name (default: yolov7_ensemble)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ──────────────────────────────────────────────────────────────
# Validate inputs
# ──────────────────────────────────────────────────────────────
if [[ ! -f "${ONNX_FILE}" ]]; then
  echo "ERROR: ONNX file not found: ${ONNX_FILE}"
  echo "Export the ONNX with: python export.py --weights model.pt --grid --end2end --dynamic-batch"
  exit 1
fi

echo "============================================================"
echo "YOLOv7 FP16 Triton Model Repository Builder"
echo "============================================================"
echo "ONNX source:     ${ONNX_FILE}"
echo "Output dir:      ${OUTPUT_DIR}"
echo "Max batch size:  ${MAX_BATCH}"
echo "Opt batch size:  ${OPT_BATCH}"
echo "Input size:      ${INPUT_SIZE}x${INPUT_SIZE}"
echo "GPU instances:   ${GPU_INSTANCES}"
echo "Model names:     ${MODEL_PREPROCESS}, ${MODEL_INFERENCE}, ${MODEL_ENSEMBLE}"
echo ""

# ──────────────────────────────────────────────────────────────
# Auto-detect execution method
# ──────────────────────────────────────────────────────────────
find_triton_pod() {
  local ns_list
  if [[ -n "${TRITON_NS}" ]]; then
    ns_list="${TRITON_NS}"
  else
    ns_list=$(kubectl get ns --no-headers -o custom-columns=":metadata.name" 2>/dev/null | tr '\n' ' ')
  fi

  for ns in ${ns_list}; do
    local pod
    pod=$(kubectl get pods -n "${ns}" --no-headers 2>/dev/null \
      | grep -i triton | grep Running | head -1 | awk '{print $1}') || true
    if [[ -n "${pod}" ]]; then
      TRITON_NS="${ns}"
      TRITON_POD="${pod}"
      return 0
    fi
  done
  return 1
}

if [[ -z "${METHOD}" ]]; then
  if [[ -n "${TRITON_POD}" ]] && [[ -n "${TRITON_NS}" ]]; then
    METHOD="kubectl"
    echo "Using specified Triton pod: ${TRITON_NS}/${TRITON_POD}"
  elif find_triton_pod; then
    METHOD="kubectl"
    echo "Auto-detected Triton pod: ${TRITON_NS}/${TRITON_POD}"
  elif command -v docker &>/dev/null && docker info &>/dev/null; then
    METHOD="docker"
    echo "Using Docker with image: ${TRITON_IMAGE}"
  else
    echo "ERROR: No Triton pod found and Docker is not available."
    echo "Either deploy Triton via Helm or install Docker and pull ${TRITON_IMAGE}"
    exit 1
  fi
elif [[ "${METHOD}" == "kubectl" ]]; then
  if [[ -z "${TRITON_POD}" ]] && ! find_triton_pod; then
    echo "ERROR: No running Triton pod found in any namespace."
    exit 1
  fi
  echo "Using Triton pod: ${TRITON_NS}/${TRITON_POD}"
elif [[ "${METHOD}" == "docker" ]]; then
  if ! command -v docker &>/dev/null || ! docker info &>/dev/null; then
    echo "ERROR: Docker is not available."
    exit 1
  fi
  echo "Using Docker with image: ${TRITON_IMAGE}"
else
  echo "ERROR: Unknown method '${METHOD}'. Use 'kubectl' or 'docker'."
  exit 1
fi

echo ""

# ──────────────────────────────────────────────────────────────
# Helper: run command inside Triton environment
# ──────────────────────────────────────────────────────────────
run_in_triton() {
  if [[ "${METHOD}" == "kubectl" ]]; then
    kubectl exec -n "${TRITON_NS}" "${TRITON_POD}" -c "${TRITON_CONTAINER}" -- "$@"
  else
    docker exec triton_build_tmp "$@"
  fi
}

copy_to_triton() {
  local src="$1" dst="$2"
  if [[ "${METHOD}" == "kubectl" ]]; then
    kubectl cp "${src}" "${TRITON_NS}/${TRITON_POD}:${dst}" -c "${TRITON_CONTAINER}"
  else
    docker cp "${src}" "triton_build_tmp:${dst}"
  fi
}

copy_from_triton() {
  local src="$1" dst="$2"
  if [[ "${METHOD}" == "kubectl" ]]; then
    kubectl cp "${TRITON_NS}/${TRITON_POD}:${src}" "${dst}" -c "${TRITON_CONTAINER}"
  else
    docker cp "triton_build_tmp:${src}" "${dst}"
  fi
}

# ──────────────────────────────────────────────────────────────
# Step 0: Create output directory structure
# ──────────────────────────────────────────────────────────────
echo "==> Step 0: Creating output directory structure..."
mkdir -p "${OUTPUT_DIR}/${MODEL_INFERENCE}/1"
mkdir -p "${OUTPUT_DIR}/${MODEL_PREPROCESS}/1"
mkdir -p "${OUTPUT_DIR}/${MODEL_ENSEMBLE}/1"
touch "${OUTPUT_DIR}/${MODEL_ENSEMBLE}/1/.keep"
echo "    ${OUTPUT_DIR}/ created"

# ──────────────────────────────────────────────────────────────
# Step 1: Start Docker container (if using Docker method)
# ──────────────────────────────────────────────────────────────
if [[ "${METHOD}" == "docker" ]]; then
  echo "==> Starting Triton Docker container..."
  docker rm -f triton_build_tmp 2>/dev/null || true
  docker run --gpus all -d --name triton_build_tmp \
    "${TRITON_IMAGE}" sleep infinity
  echo "    Container 'triton_build_tmp' started"
  trap 'echo "Cleaning up Docker container..."; docker rm -f triton_build_tmp 2>/dev/null || true' EXIT
fi

# ──────────────────────────────────────────────────────────────
# Step 2: Detect GPU
# ──────────────────────────────────────────────────────────────
echo "==> Step 1: Detecting GPU..."
GPU_INFO=$(run_in_triton nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>/dev/null || echo "Unknown GPU")
echo "    GPU: ${GPU_INFO}"

# ──────────────────────────────────────────────────────────────
# Step 3: Copy ONNX file to container/pod
# ──────────────────────────────────────────────────────────────
echo "==> Step 2: Copying ONNX model to build environment..."
copy_to_triton "${ONNX_FILE}" "/tmp/yolov7_e2e.onnx"
echo "    ONNX copied to /tmp/yolov7_e2e.onnx"

# ──────────────────────────────────────────────────────────────
# Step 4: Build TensorRT engine
# ──────────────────────────────────────────────────────────────
echo "==> Step 3: Building TensorRT FP16 engine (this takes several minutes)..."
echo "    Shapes: min=1, opt=${OPT_BATCH}, max=${MAX_BATCH}"
echo "    Workspace: ${WORKSPACE_SIZE}"

run_in_triton ${TRTEXEC} \
  --onnx=/tmp/yolov7_e2e.onnx \
  --fp16 \
  --inputIOFormats=fp16:chw \
  --saveEngine=/tmp/model.plan \
  --minShapes=images:1x3x${INPUT_SIZE}x${INPUT_SIZE} \
  --optShapes=images:${OPT_BATCH}x3x${INPUT_SIZE}x${INPUT_SIZE} \
  --maxShapes=images:${MAX_BATCH}x3x${INPUT_SIZE}x${INPUT_SIZE} \
  --memPoolSize=workspace:${WORKSPACE_SIZE} \
  --tacticSources=-CUDNN,-CUBLAS,-CUBLAS_LT \
  2>&1 | tail -5

echo ""
echo "==> Step 4: Verifying TensorRT engine..."
run_in_triton ${TRTEXEC} \
  --loadEngine=/tmp/model.plan \
  --shapes=images:1x3x${INPUT_SIZE}x${INPUT_SIZE} \
  2>&1 | grep -E "(Input|Output|PASSED|FAILED)" | head -10

# ──────────────────────────────────────────────────────────────
# Step 5: Copy model.plan back
# ──────────────────────────────────────────────────────────────
echo ""
echo "==> Step 5: Copying model.plan to output directory..."
copy_from_triton "/tmp/model.plan" "${OUTPUT_DIR}/${MODEL_INFERENCE}/1/model.plan"
echo "    Saved: ${OUTPUT_DIR}/${MODEL_INFERENCE}/1/model.plan"
ls -lh "${OUTPUT_DIR}/${MODEL_INFERENCE}/1/model.plan"

# ──────────────────────────────────────────────────────────────
# Step 6: Serialize DALI preprocessing pipeline
# ──────────────────────────────────────────────────────────────
echo ""
echo "==> Step 6: Serializing DALI preprocessing pipeline..."
copy_to_triton "${SCRIPT_DIR}/serialize_dali.py" "/tmp/serialize_dali.py"
run_in_triton python3 /tmp/serialize_dali.py \
  --output /tmp/model.dali \
  --batch-size "${MAX_BATCH}" \
  --input-size "${INPUT_SIZE}"

echo "==> Copying model.dali to output directory..."
copy_from_triton "/tmp/model.dali" "${OUTPUT_DIR}/${MODEL_PREPROCESS}/1/model.dali"
echo "    Saved: ${OUTPUT_DIR}/${MODEL_PREPROCESS}/1/model.dali"
ls -lh "${OUTPUT_DIR}/${MODEL_PREPROCESS}/1/model.dali"

# ──────────────────────────────────────────────────────────────
# Step 7: Generate Triton config files
# ──────────────────────────────────────────────────────────────
echo ""
echo "==> Step 7: Generating Triton config files..."

# Generate preferred_batch_size list: [1, 2, ..., MAX_BATCH]
BATCH_LIST=$(seq 1 "${MAX_BATCH}" | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')

# --- inference model config.pbtxt ---
cat > "${OUTPUT_DIR}/${MODEL_INFERENCE}/config.pbtxt" << EOF
# YOLOv7-tiny FP16 e2e TensorRT model (dynamic batch 1-${MAX_BATCH}, NMS included)
# EfficientNMS_TRT plugin baked into the engine - outputs final detections directly
#
# Output format:
#   num_dets:    [1]      INT32 - number of valid detections
#   det_boxes:   [100, 4] FP32 - x1, y1, x2, y2 (EfficientNMS_TRT always outputs FP32)
#   det_scores:  [100]    FP32 - confidence scores (EfficientNMS_TRT always outputs FP32)
#   det_classes: [100]    INT32 - class IDs

name: "${MODEL_INFERENCE}"
platform: "tensorrt_plan"
max_batch_size: ${MAX_BATCH}

input [
  {
    name: "images"
    data_type: TYPE_FP16
    dims: [ 3, ${INPUT_SIZE}, ${INPUT_SIZE} ]
  }
]

output [
  {
    name: "num_dets"
    data_type: TYPE_INT32
    dims: [ 1 ]
  },
  {
    name: "det_boxes"
    data_type: TYPE_FP32
    dims: [ 100, 4 ]
  },
  {
    name: "det_scores"
    data_type: TYPE_FP32
    dims: [ 100 ]
  },
  {
    name: "det_classes"
    data_type: TYPE_INT32
    dims: [ 100 ]
  }
]

instance_group [
  {
    kind: KIND_GPU
    count: ${GPU_INSTANCES}
  }
]

dynamic_batching {
  preferred_batch_size: [ ${BATCH_LIST} ]
  max_queue_delay_microseconds: 100000
}

optimization {
  cuda {
    graphs: false
  }
}
EOF
echo "    Generated: ${OUTPUT_DIR}/${MODEL_INFERENCE}/config.pbtxt"

# --- preprocess config.pbtxt ---
cat > "${OUTPUT_DIR}/${MODEL_PREPROCESS}/config.pbtxt" << EOF
# YOLOv7 DALI GPU preprocessing for ${INPUT_SIZE}x${INPUT_SIZE} models (dynamic batch 1-${MAX_BATCH})
# YOLOv7 expects RGB [0, 1] input -- normalize /255, BGR->RGB conversion.
# Converts: UINT8 BGR HWC [${INPUT_SIZE}, ${INPUT_SIZE}, 3] -> FP16 RGB CHW [3, ${INPUT_SIZE}, ${INPUT_SIZE}]

name: "${MODEL_PREPROCESS}"
backend: "dali"
max_batch_size: ${MAX_BATCH}

input [
  {
    name: "INPUT_IMAGES"
    data_type: TYPE_UINT8
    dims: [ ${INPUT_SIZE}, ${INPUT_SIZE}, 3 ]
  }
]

output [
  {
    name: "preprocessed_images"
    data_type: TYPE_FP16
    dims: [ 3, ${INPUT_SIZE}, ${INPUT_SIZE} ]
  }
]

instance_group [
  {
    kind: KIND_GPU
    count: 1
  }
]

dynamic_batching {
  preferred_batch_size: [ ${BATCH_LIST} ]
  max_queue_delay_microseconds: 100000
}
EOF
echo "    Generated: ${OUTPUT_DIR}/${MODEL_PREPROCESS}/config.pbtxt"

# --- ensemble config.pbtxt ---
cat > "${OUTPUT_DIR}/${MODEL_ENSEMBLE}/config.pbtxt" << EOF
# YOLOv7 FP16 Ensemble: preprocess -> e2e inference (with NMS)
# End-to-end pipeline: raw UINT8 images -> final detections
# Dynamic batch 1-${MAX_BATCH}

name: "${MODEL_ENSEMBLE}"
platform: "ensemble"
max_batch_size: ${MAX_BATCH}

input [
  {
    name: "INPUT_IMAGES"
    data_type: TYPE_UINT8
    dims: [ ${INPUT_SIZE}, ${INPUT_SIZE}, 3 ]
  }
]

output [
  {
    name: "num_dets"
    data_type: TYPE_INT32
    dims: [ 1 ]
  },
  {
    name: "det_boxes"
    data_type: TYPE_FP32
    dims: [ 100, 4 ]
  },
  {
    name: "det_scores"
    data_type: TYPE_FP32
    dims: [ 100 ]
  },
  {
    name: "det_classes"
    data_type: TYPE_INT32
    dims: [ 100 ]
  }
]

ensemble_scheduling {
  step [
    {
      model_name: "${MODEL_PREPROCESS}"
      model_version: -1
      input_map {
        key: "INPUT_IMAGES"
        value: "INPUT_IMAGES"
      }
      output_map {
        key: "preprocessed_images"
        value: "preprocessed_images"
      }
    },
    {
      model_name: "${MODEL_INFERENCE}"
      model_version: -1
      input_map {
        key: "images"
        value: "preprocessed_images"
      }
      output_map {
        key: "num_dets"
        value: "num_dets"
      }
      output_map {
        key: "det_boxes"
        value: "det_boxes"
      }
      output_map {
        key: "det_scores"
        value: "det_scores"
      }
      output_map {
        key: "det_classes"
        value: "det_classes"
      }
    }
  ]
}
EOF
echo "    Generated: ${OUTPUT_DIR}/${MODEL_ENSEMBLE}/config.pbtxt"

# ──────────────────────────────────────────────────────────────
# Step 8: Cleanup temp files inside container/pod
# ──────────────────────────────────────────────────────────────
echo ""
echo "==> Step 8: Cleaning up temp files..."
run_in_triton rm -f /tmp/yolov7_e2e.onnx /tmp/model.plan /tmp/model.dali /tmp/serialize_dali.py 2>/dev/null || true
echo "    Temp files removed"

# ──────────────────────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "BUILD COMPLETE"
echo "============================================================"
echo ""
echo "Output directory: ${OUTPUT_DIR}/"
echo ""
echo "  ${MODEL_PREPROCESS}/"
echo "    config.pbtxt"
echo "    1/model.dali"
ls -lh "${OUTPUT_DIR}/${MODEL_PREPROCESS}/1/model.dali" 2>/dev/null | awk '{print "  model.dali: " $5}'
echo ""
echo "  ${MODEL_INFERENCE}/"
echo "    config.pbtxt"
echo "    1/model.plan"
ls -lh "${OUTPUT_DIR}/${MODEL_INFERENCE}/1/model.plan" 2>/dev/null | awk '{print "  model.plan: " $5}'
echo ""
echo "  ${MODEL_ENSEMBLE}/"
echo "    config.pbtxt"
echo "    1/.keep"
echo ""
echo "GPU: ${GPU_INFO}"
echo ""
echo "These files are ready to deploy on Triton."
echo "Copy the 3 model directories to your Triton model repository."
