#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Download OpenVINO person-detection-retail-0013 into the compose models volume.
# Safe to run in the background during Step 7 RTSP validation.
#
# Usage: download_detection_models.sh [deploy_dir]

set -euo pipefail

deploy_dir=${1:-.}
cd "$deploy_dir"

MODEL_XML="intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml"
MODEL_BIN="intel/person-detection-retail-0013/FP32/person-detection-retail-0013.bin"
# NOTE: the upstream bucket does not have an "intel/" path segment (unlike the
# local /models layout used above) - including it silently returns a small HTML
# placeholder page instead of a 404, which wget treats as success.
MODEL_URL_BASE="https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/models_bin/1/person-detection-retail-0013/FP32"

project_name=$(docker compose config --format json \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('name', 'scenescape'))")
models_volume="${project_name}_vol-models"

if docker run --rm \
  -v "${models_volume}:/models" \
  scenescape-model-installer:latest \
  test -f "/models/${MODEL_XML}" 2>/dev/null; then
  echo "Detection models already present in ${models_volume}."
  exit 0
fi

echo "Downloading person-detection-retail-0013 into ${models_volume}..."
docker run --rm --user root \
  -e "http_proxy=${http_proxy:-}" \
  -e "https_proxy=${https_proxy:-}" \
  -v "${models_volume}:/models" \
  scenescape-model-installer:latest bash -c "
set -euo pipefail
mkdir -p /models/$(dirname "${MODEL_XML}")
wget -nv -O /models/${MODEL_XML} ${MODEL_URL_BASE}/person-detection-retail-0013.xml
wget -nv -O /models/${MODEL_BIN} ${MODEL_URL_BASE}/person-detection-retail-0013.bin
# Guard against silently saving an HTML error/placeholder page as the model:
# real IR XML starts with '<?xml' and the .bin is always far larger than 2KB.
head -c 5 /models/${MODEL_XML} | grep -q '<?xml' || { echo 'FAIL: downloaded XML is not a valid OpenVINO IR file' >&2; exit 1; }
[ \$(wc -c < /models/${MODEL_BIN}) -gt 2048 ] || { echo 'FAIL: downloaded BIN file is too small to be a real model' >&2; exit 1; }
chmod -R a+rX /models/
"
echo "Detection models ready in ${models_volume}."
