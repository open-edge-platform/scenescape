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
docker compose up -d broker ntpserv init-models

echo "Waiting for image pull..."
wait "$pull_pid" || true

echo "Parallel warmup complete."
docker compose --profile mapping ps mapping
docker compose ps broker ntpserv
