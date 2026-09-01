#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Deploy Intel(R) SceneScape for the IGK6 demo room. Implements the four demo
# steps: check out the demo branch, bring up the stack, purge the out-of-box
# scenes/cameras, and import the IGK6 demo scene.
#
# Usage:
#   ./sample_data/deploy-demo.sh                Full deploy (steps 1-4)
#   ./sample_data/deploy-demo.sh --post-deploy  Only steps 3-4 against a running
#                                               stack (invoked by `make demo-room`)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DEMO_BRANCH="${DEMO_BRANCH:-demo-room-igk6}"
MANAGER_URL="${MANAGER_URL:-https://localhost}"
DEMO_USER="${DEMO_USER:-admin}"
SCENE_ZIP="${SCENE_ZIP:-$SCRIPT_DIR/demo_scene/IGK6-demo-room.zip}"
API_TIMEOUT="${API_TIMEOUT:-300}"

POST_DEPLOY_ONLY=0
if [[ "${1:-}" == "--post-deploy" ]]; then
  POST_DEPLOY_ONLY=1
fi

log() { echo "[deploy-demo] $*"; }
die() { echo "[deploy-demo] ERROR: $*" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."
}

# Step 1: ensure the demo branch is checked out.
checkout_branch() {
  require git
  local current
  current="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
  if [[ "$current" != "$DEMO_BRANCH" ]]; then
    log "Checking out '$DEMO_BRANCH' (current: '$current')..."
    git -C "$REPO_ROOT" checkout "$DEMO_BRANCH"
  else
    log "Already on '$DEMO_BRANCH'."
  fi
}

# Step 2: build the images and start the demo stack. `make demo-room` invokes
# this script again with --post-deploy once the containers are up.
deploy_stack() {
  [[ -n "${SUPASS:-}" ]] || \
    die "SUPASS must be set to the SceneScape super user password."
  log "Building images..."
  make -C "$REPO_ROOT"
  log "Starting the demo stack..."
  make -C "$REPO_ROOT" demo-room
}

# Block until the manager REST API reports the database is ready.
wait_for_api() {
  local deadline code
  deadline=$(( $(date +%s) + API_TIMEOUT ))
  log "Waiting for the SceneScape API at $MANAGER_URL (timeout ${API_TIMEOUT}s)..."
  while true; do
    code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
      --insecure "$MANAGER_URL/api/v1/database-ready" || true)"
    if [[ "$code" == "200" ]]; then
      log "API is ready."
      return 0
    fi
    if (( $(date +%s) >= deadline )); then
      die "Timed out waiting for the API (last HTTP status: ${code:-none})."
    fi
    sleep 5
  done
}

# Obtain an auth token for the super user.
get_token() {
  local response
  response="$(curl --silent --show-error --insecure -X POST \
    -d "username=${DEMO_USER}&password=${SUPASS}" \
    "$MANAGER_URL/api/v1/auth")"
  TOKEN="$(printf '%s' "$response" | jq -r '.token // empty')"
  [[ -n "$TOKEN" ]] || die "Failed to obtain an auth token."
}

# Wrapper for authenticated REST calls.
api() {
  local method="$1" path="$2"
  shift 2
  curl --silent --show-error --insecure -X "$method" \
    -H "Authorization: Token $TOKEN" \
    "$@" "$MANAGER_URL$path"
}

# Step 3: remove the out-of-box demo scenes and their cameras.
purge_out_of_box() {
  local uid uids
  log "Removing out-of-box cameras..."
  uids="$(api GET /api/v1/cameras | jq -r '.results[]?.uid')"
  for uid in $uids; do
    log "  deleting camera '$uid'"
    api DELETE "/api/v1/camera/$uid" >/dev/null || \
      log "  WARNING: failed to delete camera '$uid'"
  done

  log "Removing out-of-box scenes..."
  uids="$(api GET /api/v1/scenes | jq -r '.results[]?.uid')"
  for uid in $uids; do
    log "  deleting scene '$uid'"
    api DELETE "/api/v1/scene/$uid" >/dev/null || \
      log "  WARNING: failed to delete scene '$uid'"
  done
}

# Step 4: import the IGK6 demo scene archive.
import_scene() {
  [[ -f "$SCENE_ZIP" ]] || die "Scene archive not found: $SCENE_ZIP"
  log "Importing demo scene from '$SCENE_ZIP'..."
  local response code body
  response="$(curl --silent --show-error --insecure --write-out '\n%{http_code}' \
    -X POST -H "Authorization: Token $TOKEN" \
    -F "zipFile=@${SCENE_ZIP}" \
    "$MANAGER_URL/api/v1/import-scene/")"
  code="$(printf '%s' "$response" | tail -n1)"
  body="$(printf '%s' "$response" | sed '$d')"
  if [[ "$code" != "201" && "$code" != "200" ]]; then
    die "Scene import failed (HTTP $code): $body"
  fi
  log "Scene import complete."
}

configure_demo() {
  require curl
  require jq
  [[ -n "${SUPASS:-}" ]] || \
    die "SUPASS must be set to the SceneScape super user password."
  wait_for_api
  get_token
  purge_out_of_box
  import_scene
  log "Demo room is ready. Grafana: http://<host IP>:3000 (admin/admin)."
}

main() {
  if [[ "$POST_DEPLOY_ONLY" -eq 1 ]]; then
    configure_demo
    return
  fi
  checkout_branch
  deploy_stack
}

main "$@"
