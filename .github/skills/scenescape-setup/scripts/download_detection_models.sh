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
# placeholder page instead of a 404.
MODEL_URL_BASE="https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/models_bin/1/person-detection-retail-0013/FP32"
# Digests for Open Model Zoo 2023.0 FP32 artifacts (verify after download).
MODEL_XML_SHA256="33acc96a73898256a127a53af71b6bfb169df83bd514984b01beacbcf7b2cc04"
MODEL_BIN_SHA256="f3731a76de6a26ef7f380a08831bc13d74fc1e6ae774fd9ea30267a487084f2c"

# Avoid shell pipelines into python (static scanners flag curl/wget | interpreter).
project_name=$(
  python3 -c "
import json, subprocess
out = subprocess.check_output(
  ['docker', 'compose', 'config', '--format', 'json'],
  text=True,
)
print(json.loads(out).get('name', 'scenescape'))
"
)
models_volume="${project_name}_vol-models"

if docker container run --rm \
  -v "${models_volume}:/models" \
  scenescape-model-installer:latest \
  test -f "/models/${MODEL_XML}" 2>/dev/null; then
  echo "Detection models already present in ${models_volume}."
  exit 0
fi

echo "Downloading person-detection-retail-0013 into ${models_volume}..."
docker container run --rm --user root \
  -e "http_proxy=${http_proxy:-}" \
  -e "https_proxy=${https_proxy:-}" \
  -e "MODEL_XML=${MODEL_XML}" \
  -e "MODEL_BIN=${MODEL_BIN}" \
  -e "MODEL_URL_BASE=${MODEL_URL_BASE}" \
  -e "MODEL_XML_SHA256=${MODEL_XML_SHA256}" \
  -e "MODEL_BIN_SHA256=${MODEL_BIN_SHA256}" \
  -v "${models_volume}:/models" \
  scenescape-model-installer:latest \
  bash -c '
set -euo pipefail
mkdir -p "/models/$(dirname "${MODEL_XML}")"
# Fetch model IR files only (not executable scripts); verify digests below.
curl -fsSL -o "/models/${MODEL_XML}" "${MODEL_URL_BASE}/person-detection-retail-0013.xml"
curl -fsSL -o "/models/${MODEL_BIN}" "${MODEL_URL_BASE}/person-detection-retail-0013.bin"
# Guard against silently saving an HTML error/placeholder page as the model:
# real IR XML starts with "<?xml" and the .bin is always far larger than 2KB.
head -c 5 "/models/${MODEL_XML}" | grep -q "<?xml" \
  || { echo "FAIL: downloaded XML is not a valid OpenVINO IR file" >&2; exit 1; }
[ "$(wc -c < "/models/${MODEL_BIN}")" -gt 2048 ] \
  || { echo "FAIL: downloaded BIN file is too small to be a real model" >&2; exit 1; }
printf "%s  %s\n" "${MODEL_XML_SHA256}" "/models/${MODEL_XML}" \
  | sha256sum -c -
printf "%s  %s\n" "${MODEL_BIN_SHA256}" "/models/${MODEL_BIN}" \
  | sha256sum -c -
chmod -R a+rX /models/
'
echo "Detection models ready in ${models_volume}."
