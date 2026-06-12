#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Poll mapping service health from the host.
# Usage: check_mapping_health.sh [max_attempts] [interval_seconds]

set -euo pipefail

max_attempts=${1:-30}
interval_s=${2:-10}

for ((i = 1; i <= max_attempts; i++)); do
  resp=$(curl -sk https://localhost:8444/v1/health 2>/dev/null || true)
  echo "[$i/$max_attempts] $resp"
  if echo "$resp" | grep -qE '"status"[[:space:]]*:[[:space:]]*"healthy"|"model_loaded"[[:space:]]*:[[:space:]]*true'; then
    echo "PASS: mapping service healthy"
    exit 0
  fi
  sleep "$interval_s"
done

echo "FAIL: mapping service not healthy after $((max_attempts * interval_s))s"
exit 1
