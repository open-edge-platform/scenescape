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
pip3 install --break-system-packages openvino-dev 2>&1 | grep Successfully
/usr/local/bin/omz_downloader --name person-detection-retail-0013 -o /models/
chmod -R a+rX /models/
"
echo "Detection models ready in ${models_volume}."
