#!/bin/bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Script to download Ollama model for offline deployment
# Run this on a machine with internet access

set -e

MODEL_NAME="${1:-mistral}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Downloading Ollama model: $MODEL_NAME"
echo "==> Target directory: $SCRIPT_DIR"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not in PATH"
    exit 1
fi

# Clean up any existing container with the same name
docker rm -f ollama-download-temp 2>/dev/null || true

# Create temporary container with Ollama (pass proxy settings)
echo "==> Starting temporary Ollama container..."
CONTAINER_ID=$(docker run -d --rm --name ollama-download-temp \
  -e http_proxy="${http_proxy}" \
  -e https_proxy="${https_proxy}" \
  -e no_proxy="${no_proxy}" \
  -e HTTP_PROXY="${HTTP_PROXY}" \
  -e HTTPS_PROXY="${HTTPS_PROXY}" \
  -e NO_PROXY="${NO_PROXY}" \
  ollama/ollama)

# Wait for Ollama to be ready
echo "==> Waiting for Ollama service to start..."
sleep 5

# Pull the model
echo "==> Pulling model '$MODEL_NAME' (this may take several minutes)..."
docker exec ollama-download-temp ollama pull "$MODEL_NAME"

# Copy models from container
echo "==> Copying model files to $SCRIPT_DIR..."
docker cp ollama-download-temp:/root/.ollama/models/. "$SCRIPT_DIR/"

# Stop container
echo "==> Cleaning up temporary container..."
docker stop ollama-download-temp

# Check what was downloaded
echo ""
echo "==> Download complete!"
echo "==> Model files:"
ls -lh "$SCRIPT_DIR/blobs/" 2>/dev/null | head -10 || echo "  (blobs directory not found)"
echo ""
echo "==> Manifest:"
find "$SCRIPT_DIR/manifests/" -type f 2>/dev/null || echo "  (manifests directory not found)"
echo ""
echo "DONE: Model '$MODEL_NAME' is ready for offline deployment"
echo "      Copy this entire directory to your air-gapped machine"
