#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
echo "Starting model download and installation..."

# Install dependencies
apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*
pip install --no-cache-dir -r /workspace/requirements-runtime.txt

# Run the entrypoint script to download models
echo "Starting model installation with MODEL_TYPE=${MODEL_TYPE}, PRECISIONS=${MODEL_PRECISIONS}, MODEL_PROC=${MODEL_PROC}"
# Build arguments for install-omz-models
ARGS=""
case "${MODEL_TYPE}" in
  "default")
    ARGS="--default"
    ;;
  "ocr")
    ARGS="--ocr"
    ;;
  "all")
    ARGS="--all"
    ;;
  *)
    echo "Unknown MODEL_TYPE: ${MODEL_TYPE}. Using default."
    ARGS="--default"
    ;;
esac
ARGS="${ARGS} --precisions ${MODEL_PRECISIONS}"
# Add model_proc flag if enabled
if [ "${MODEL_PROC}" = "true" ]; then
  ARGS="${ARGS} --model_proc"
fi
echo "Running: python install-omz-models ${ARGS}"
mkdir -p /workspace/models-storage/models
python /workspace/install-omz-models ${ARGS}
echo "Copying config files..."
python /workspace/copy-config-files /workspace ${MODEL_DIR}
echo "Model installation completed successfully"
echo "Models installed in: ${MODEL_DIR}"
ls -la "${MODEL_DIR}" || true``

if [ -d "/workspace/models-storage/models/" ]; then
  echo "Models downloaded successfully"
else
  echo "Error: No models directory found after download"
  exit 1
fi

# Set proper ownership for shared storage
chown -R 1000:1000 /workspace/models-storage

echo "Model installation and copying completed successfully"
