#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Start long-running deployment warmups in parallel with Step 7 RTSP validation.
#
# Usage: parallel_warmup.sh [deploy_dir]

set -euo pipefail

deploy_dir=${1:-.}
cd "$deploy_dir"

echo "Pulling video-analytics and mapping images (background)..."
docker compose pull video-analytics mapping &
pull_pid=$!

echo "Starting mapping (init volumes, then download/load MapAnything weights)..."
docker compose --profile mapping up -d mapping

echo "Starting pipeline validation stack (video-analytics deferred until models ready)..."
base_services=(broker ntpserv init-models)
if [[ -f docker-compose.override.yml ]]; then
  echo "docker-compose.override.yml detected: starting local video-file media server..."
  base_services+=(mediaserver)
  # One publisher service per camera (video-file-<camera_id>), plus legacy
  # video-file-cams if an older override is still present.
  mapfile -t file_cam_services < <(
    docker compose config --services 2>/dev/null | grep -E '^video-file-' || true
  )
  if ((${#file_cam_services[@]})); then
    base_services+=("${file_cam_services[@]}")
  fi
fi
docker compose up -d "${base_services[@]}"

echo "Waiting for image pull..."
wait "$pull_pid" || true

echo "Parallel warmup complete."
docker compose --profile mapping ps mapping
docker compose ps broker ntpserv
