#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# RTSP gate check from the SceneScape Docker network.
# Usage: verify_rtsp.sh <deploy_dir> <rtsp_url> [<rtsp_url> ...]

set -euo pipefail

deploy_dir=${1:?deploy_dir required}
shift
cd "$deploy_dir"

if [[ $# -lt 1 ]]; then
  echo "Usage: verify_rtsp.sh <deploy_dir> <rtsp_url> [...]" >&2
  exit 2
fi

NET_NAME=$(docker network ls --format '{{.Name}}' | grep '_scenescape$' | head -1)
if [[ -z "$NET_NAME" ]]; then
  echo "FAIL: scenescape Docker network not found" >&2
  exit 1
fi

failed=0
for url in "$@"; do
  echo "RTSP check: $url"
  success=0
  for attempt in 1 2 3; do
    if docker container run --rm --network "$NET_NAME" \
      linuxserver/ffmpeg:version-8.1-cli \
      -nostdin -v error -rtsp_transport tcp \
      -analyzeduration 10M -probesize 10M \
      -i "$url" \
      -t 3 -f null -; then
      echo "PASS: $url"
      success=1
      break
    else
      echo "  attempt $attempt/3 failed, retrying..."
      sleep 2
    fi
  done
  if [[ "$success" -ne 1 ]]; then
    echo "FAIL: $url"
    failed=1
  fi
done

exit "$failed"
