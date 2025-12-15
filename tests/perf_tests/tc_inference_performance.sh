#!/bin/bash
# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

TEST_NAME="NEX-T10412"
FPS_THRESHOLD=10
echo "Executing test: ${TEST_NAME}"

# Docker volume doesn't allow uppercase letters or special characters
SAFE_TEST_NAME=$(echo "${TEST_NAME}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]//g')

# Override compose_project_name to be used in Makefile target
export COMPOSE_PROJECT_NAME="${SAFE_TEST_NAME}"
make .env init-sample-data

TESTBASE="tests/perf_tests"
COMPOSEDIR="${TESTBASE}/compose"
YMLFILE="docker-compose-inference_performance.yml"

get_camera_fps() {
  docker compose --project-name "${SAFE_TEST_NAME}" logs average-fps | grep "$1" | grep -Eo '[0-9]+\.[0-9]+' | tail -1 || echo ""
}

cleanup() {
  echo "Cleaning up test environment..."
  docker compose --project-name "${SAFE_TEST_NAME}" down -v
  # Remove orphaned volumes
  docker volume rm $(docker volume ls -q --filter "name=^${SAFE_TEST_NAME}") 2>/dev/null || true
}

# Run cleanup on exit
trap cleanup EXIT

docker compose --project-name "${SAFE_TEST_NAME}" \
  -f "${COMPOSEDIR}/${YMLFILE}" \
  --project-directory "${PWD}" \
  up --abort-on-container-exit

fps_camera1=$(get_camera_fps "camera1")
fps_camera2=$(get_camera_fps "camera2")

echo "camera1 raw avg FPS: ${fps_camera1:-not found}"
echo "camera2 raw avg FPS: ${fps_camera2:-not found}"

if [[ -z "$fps_camera1" || -z "$fps_camera2" ]]; then
  echo "Could not extract FPS for one or both cameras. FAIL"
  exit 1
fi

fps_camera1=$(printf "%.0f" "$fps_camera1")
fps_camera2=$(printf "%.0f" "$fps_camera2")

echo "camera1 FPS: $fps_camera1"
echo "camera2 FPS: $fps_camera2"

awk -v fps1="$fps_camera1" -v fps2="$fps_camera2" -v threshold="$FPS_THRESHOLD" -v testname="$TEST_NAME" 'BEGIN {
  pass1 = (fps1 >= threshold)
  pass2 = (fps2 >= threshold)

  if (pass1 && pass2) {
    print testname ": PASS"
    print "PASSED: Both cameras meet FPS threshold"
    exit 0
  } else {
    print testname ": FAIL"
    if (!pass1) print "  - camera1 FPS below threshold"
    if (!pass2) print "  - camera2 FPS below threshold"
    exit 1
  }
}'
