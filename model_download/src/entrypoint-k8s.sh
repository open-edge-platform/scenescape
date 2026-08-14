#!/bin/bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

echo "Starting model download with model_downloader service..."

MODEL_DIR=${MODEL_DIR:-/workspace/models-storage/models}
MODEL_CONFIG_FILE=${MODEL_CONFIG_FILE:-/workspace/model-download/models.json}
MODEL_DOWNLOADER_URL=${MODEL_DOWNLOADER_URL:-http://127.0.0.1:8000}
MODEL_DOWNLOADER_ARGS=${MODEL_DOWNLOADER_ARGS:---plugins omz}
PARALLEL_DOWNLOADS=${PARALLEL_DOWNLOADS:-false}
MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT=${MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT:-720}
MODEL_DOWNLOADER_WAIT_TIMEOUT=${MODEL_DOWNLOADER_WAIT_TIMEOUT:-720}

mkdir -p "${MODEL_DIR}"

# The model_downloader image stores downloaded files under /opt/models. Keep the existing
# Scenescape PVC layout by pointing /opt/models to the models subdirectory on the PVC.
rm -rf /opt/models
ln -s "${MODEL_DIR}" /opt/models

read -r -a downloader_args <<< "${MODEL_DOWNLOADER_ARGS}"
echo "Starting model_downloader service: /opt/entrypoint.sh ${MODEL_DOWNLOADER_ARGS}"
/opt/entrypoint.sh "${downloader_args[@]}" &
downloader_pid=$!

cleanup() {
  echo "Stopping model_downloader service..."
  kill "${downloader_pid}" >/dev/null 2>&1 || true
  wait "${downloader_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Requesting model downloads from ${MODEL_DOWNLOADER_URL}"
MODEL_DOWNLOADER_URL="${MODEL_DOWNLOADER_URL}" \
MODEL_CONFIG_FILE="${MODEL_CONFIG_FILE}" \
PARALLEL_DOWNLOADS="${PARALLEL_DOWNLOADS}" \
MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT="${MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT}" \
MODEL_DOWNLOADER_WAIT_TIMEOUT="${MODEL_DOWNLOADER_WAIT_TIMEOUT}" \
python3 /workspace/model-download/download_models.py

echo "Generating Scenescape model configuration in ${MODEL_DIR}"
python3 /workspace/model-download/generate_model_config_from_models.py \
  --models-path "${MODEL_DIR}" \
  --config-file "${MODEL_CONFIG_FILE}"

echo "Downloaded model files:"
find "${MODEL_DIR}" -type f | sort

echo "Model download completed successfully"
