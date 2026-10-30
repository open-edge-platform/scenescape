#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Label Basketball videos with YOLO FT (OpenVINO, preferably in the DLStreamer
# container), train TrackNet, export OpenVINO FP16 for sscape_tracknet_ball.
#
#   bash sample_data/demo_scenes/Basketball/models/tracknet/train_and_export.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${TRACKNET_DEST:-${HERE}/../tracknet-basketball}"
VENV="${TRACKNET_VENV:-/tmp/tracknet-venv}"
MANIFEST="${TRACKNET_MANIFEST:-${HERE}/dataset/manifest.jsonl}"
EPOCHS="${TRACKNET_EPOCHS:-25}"
DEVICE="${TRACKNET_DEVICE:-cpu}"
LABEL_DEVICE="${TRACKNET_LABEL_DEVICE:-GPU}"
CONTAINER="${TRACKNET_LABEL_CONTAINER:-scenescape-basketball-video-1}"

unset ALL_PROXY all_proxy SOCKS_PROXY socks_proxy SOCKS5_PROXY socks5_proxy \
  GIT_HTTP_PROXY GIT_HTTPS_PROXY || true
if [[ -f "${ROOT}/.cursor_proxy.env" ]]; then
  # shellcheck disable=SC1091
  set -a && . "${ROOT}/.cursor_proxy.env" && set +a
fi
: "${HTTP_PROXY:=http://proxy-dmz.intel.com:911}"
: "${HTTPS_PROXY:=http://proxy-dmz.intel.com:912}"
: "${http_proxy:=${HTTP_PROXY}}"
: "${https_proxy:=${HTTPS_PROXY}}"
: "${NO_PROXY:=localhost,127.0.0.1,::1,.intel.com}"
: "${no_proxy:=${NO_PROXY}}"
export HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy

mkdir -p "${HERE}/dataset" "${DEST}"

if [[ ! -f "${MANIFEST}" ]]; then
  IMAGE="${TRACKNET_LABEL_IMAGE:-docker.io/intel/dlstreamer-pipeline-server:2026.3.0-20261020-weekly-ubuntu24}"
  echo "Building TrackNet manifest via YOLO FT (${IMAGE}, device=${LABEL_DEVICE})..."
  docker run --rm --entrypoint python3 \
    --user "$(id -u):$(id -g)" \
    --device /dev/dri \
    --group-add 44 \
    --group-add 992 \
    -v "${ROOT}:/workspace" \
    -w /workspace \
    "${IMAGE}" \
    sample_data/demo_scenes/Basketball/models/tracknet/prepare_dataset.py \
      --device "${LABEL_DEVICE}" \
      --stride "${TRACKNET_LABEL_STRIDE:-2}" \
      --out sample_data/demo_scenes/Basketball/models/tracknet/dataset/manifest.jsonl
fi

python3 -m venv "${VENV}"
"${VENV}/bin/pip" install -q --upgrade pip
"${VENV}/bin/pip" install -q 'torch' 'torchvision' 'opencv-python-headless' \
  'numpy' 'openvino>=2024.0' 'onnx' 'onnxscript'

echo "Caching JPEG frames for training..."
"${VENV}/bin/python" "${HERE}/cache_frames.py" \
  --manifest "${MANIFEST}" \
  --outdir "${HERE}/dataset/frames"

echo "Training TrackNet (${EPOCHS} epochs, device=${DEVICE})"
"${VENV}/bin/python" "${HERE}/train.py" \
  --manifest "${MANIFEST}" \
  --frames-dir "${HERE}/dataset/frames" \
  --outdir "${DEST}" \
  --epochs "${EPOCHS}" \
  --device "${DEVICE}" \
  --batch "${TRACKNET_BATCH:-16}" \
  --num-workers "${TRACKNET_WORKERS:-2}" \
  --height "${TRACKNET_HEIGHT:-144}" \
  --width "${TRACKNET_WIDTH:-256}" \
  --sigma "${TRACKNET_SIGMA:-3.0}" \
  --pos-weight "${TRACKNET_POS_WEIGHT:-40}"

"${VENV}/bin/python" "${HERE}/export_ov.py"
echo "Done. IR at ${DEST}/tracknet_basketball.xml"
