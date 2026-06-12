#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Summarize video-analytics health without dumping verbose FPS logs.
# Usage: check_video_analytics.sh [deploy_dir] [tail_lines]

set -euo pipefail

deploy_dir=${1:-.}
tail_lines=${2:-30}
cd "$deploy_dir"

if ! docker compose ps --status running --format '{{.Service}}' video-analytics 2>/dev/null \
  | grep -qx video-analytics; then
  echo "FAIL: video-analytics container is not running"
  exit 1
fi

health=$(docker compose ps video-analytics --format '{{.Health}}' 2>/dev/null | head -1)
echo "video-analytics health=${health:-unknown}"

summary=$(
  docker compose logs video-analytics --tail "$tail_lines" 2>&1 \
    | grep -E 'ERROR|Autostarted|RUNNING|model file|Segmentation|Connected to MQTT|Subscribed to topic' \
    | tail -20 || true
)

if [[ -z "$summary" ]]; then
  echo "WARN: no matching log lines (container may still be starting)"
else
  printf '%s\n' "$summary"
fi

if echo "$summary" | grep -qE 'Segmentation fault|model file .* does not exist'; then
  echo "FAIL: video-analytics error detected in logs"
  exit 1
fi

if echo "$summary" | grep -q 'Autostarted pipeline'; then
  echo "PASS: pipelines autostarted"
  exit 0
fi

if [[ "${health:-}" == "healthy" ]]; then
  echo "PASS: video-analytics healthy"
  exit 0
fi

echo "FAIL: pipelines not confirmed started"
exit 1
