#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Verify person-detection-retail-0013 is present in the compose models volume.
# Usage: check_detection_models.sh [deploy_dir]

set -euo pipefail

deploy_dir=${1:-.}
cd "$deploy_dir"

MODEL_XML="omz/person-detection-retail-0013/FP32/person-detection-retail-0013.xml"

project_name=$(docker compose config --format json \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('name', 'scenescape'))")
models_volume="${project_name}_vol-models"

if docker container run --rm \
  -v "${models_volume}:/models" \
  alpine:3.23 \
  sh -c "test -f '/models/${MODEL_XML}' && head -c 5 '/models/${MODEL_XML}' | grep -q '<?xml'"; then
  echo "PASS: detection models ready in ${models_volume}"
  exit 0
fi

echo "FAIL: ${MODEL_XML} missing or invalid (not a valid OpenVINO IR file) in ${models_volume}"
exit 1
