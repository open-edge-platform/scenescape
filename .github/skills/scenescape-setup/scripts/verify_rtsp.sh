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

__ss_project=$(awk '/^name:[[:space:]]*/{v=$2; gsub(/[[:space:]]/,"",v); print v; exit}' docker-compose.yml 2>/dev/null || true)
NET_NAME=""
if [[ -n "${__ss_project:-}" ]]; then
  NET_NAME=$(docker network ls --format '{{.Name}}' | grep -E "^${__ss_project}_scenescape$" | head -1 || true)
fi
[[ -n "$NET_NAME" ]] || NET_NAME=$(docker network ls --format '{{.Name}}' | grep '_scenescape$' | head -1 || true)
if [[ -z "$NET_NAME" ]]; then
  echo "FAIL: scenescape Docker network not found" >&2
  exit 1
fi

failed=0
for url in "$@"; do
  echo "RTSP check: $url"
  if docker container run --rm --network "$NET_NAME" \
    linuxserver/ffmpeg:version-8.1-cli \
    -nostdin -v error -rtsp_transport tcp \
    -i "$url" \
    -t 5 -f null -; then
    echo "PASS: $url"
  else
    echo "FAIL: $url"
    failed=1
  fi
done

exit "$failed"
