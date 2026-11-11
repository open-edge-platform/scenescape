#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

export SERVICE_NAME="autocalibration"
export SPEC_SOURCE="${SPEC_SOURCE:-/repo/docs/user-guide/microservices/auto-calibration/_assets/autocalibration-api.yaml}"
export SERVER_URL="https://web.scenescape.intel.com/api/v1/autocalibration"
export AUTOCAL_SCENE_ID="${AUTOCAL_SCENE_ID:-a6d8053f-54e4-40a5-ae1f-3d7b3f826c1f}"
export AUTOCAL_CAMERA_ID="${AUTOCAL_CAMERA_ID:-atag-qcam1}"

exec /workspace/run_service_fuzzing.sh
