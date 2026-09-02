#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Wait for tracked objects on the regulated scene topic.
# Usage: verify_tracking.sh <deploy_dir> <scene_uid> [timeout_seconds]

set -euo pipefail

deploy_dir=${1:?deploy_dir required}
scene_uid=${2:?scene_uid required}
timeout_s=${3:-120}
cd "$deploy_dir"

__ss_project=$(awk '/^name:[[:space:]]*/{v=$2; gsub(/[[:space:]]/,"",v); print v; exit}' docker-compose.yml 2>/dev/null || true)
NET_NAME=""
if [[ -n "${__ss_project:-}" ]]; then
  NET_NAME=$(docker network ls --format '{{.Name}}' | grep -E "^${__ss_project}_scenescape$" | head -1 || true)
fi
[[ -n "$NET_NAME" ]] || NET_NAME=$(docker network ls --format '{{.Name}}' | grep '_scenescape$' | head -1 || true)
ca_file="$deploy_dir/secrets/certs/scenescape-ca.pem"
topic="scenescape/regulated/scene/$scene_uid"

if [[ -z "$NET_NAME" ]]; then
  echo "FAIL: scenescape Docker network not found" >&2
  exit 1
fi
if [[ ! -f "$ca_file" ]]; then
  echo "FAIL: CA cert not found: $ca_file" >&2
  exit 1
fi

echo "Waiting up to ${timeout_s}s for objects on $topic"
payload=$(
  docker container run --rm --network "$NET_NAME" \
    -v "$ca_file:/ca.pem:ro" \
    eclipse-mosquitto:2.0.22 \
    mosquitto_sub -h broker.scenescape.intel.com -p 1883 \
    --cafile /ca.pem --insecure \
    -t "$topic" -C 1 -W "$timeout_s"
) || {
  echo "FAIL: no message on regulated topic within ${timeout_s}s"
  exit 1
}

if python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if d.get('objects') else 1)" "$payload"; then
  object_count=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1]).get('objects',[])))" "$payload")
  echo "PASS: $object_count tracked object(s) on regulated topic"
  exit 0
fi

echo "FAIL: message received but objects array is empty"
exit 1
