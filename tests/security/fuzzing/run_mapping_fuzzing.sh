#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

export SERVICE_NAME="mapping"
export SPEC_SOURCE="${SPEC_SOURCE:-/repo/docs/user-guide/microservices/mapping-service/api-docs/mapping-api.yaml}"
export SERVER_URL="https://web.scenescape.intel.com/api/v1/mapping"

exec /workspace/run_service_fuzzing.sh
