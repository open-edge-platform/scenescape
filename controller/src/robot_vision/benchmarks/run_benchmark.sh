#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Run MultipleObjectTracker::track peak-FPS benchmark.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build"
BENCHMARK_EXEC="${BUILD_DIR}/benchmarks/RobotVisionBenchmarks"
GIT_HASH=$(git -C "${SCRIPT_DIR}/../../.." rev-parse --short HEAD 2>/dev/null || echo "nogit")
OUTPUT_DIR="${SCRIPT_DIR}/out"
mkdir -p "${OUTPUT_DIR}"

JSON_OUTPUT=false
ASSOC_CONFIG=""
PEOPLE="50"
CAMERAS="1,2"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      JSON_OUTPUT=true
      shift
      ;;
    --association-config)
      ASSOC_CONFIG="$2"
      shift 2
      ;;
    --people)
      PEOPLE="$2"
      shift 2
      ;;
    --cameras)
      CAMERAS="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [--json] [--people N[,N...]] [--cameras N[,N...]] [--association-config path.json] [benchmark flags...]"
      exit 0
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -f "${BENCHMARK_EXEC}" ]]; then
  echo "Error: Benchmark executable not found at ${BENCHMARK_EXEC}."
  echo "Run ./build_benchmark.sh first."
  exit 1
fi

ARGS=(
  --people "${PEOPLE}"
  --cameras "${CAMERAS}"
  --benchmark_report_aggregates_only=true
)

if [[ -n "${ASSOC_CONFIG}" ]]; then
  ARGS+=(--association-config "${ASSOC_CONFIG}")
fi

TAG="default"
if [[ -n "${ASSOC_CONFIG}" ]]; then
  TAG=$(basename "${ASSOC_CONFIG}" .json)
fi
OUTPUT_JSON="${OUTPUT_DIR}/rv_benchmark_${GIT_HASH}_${TAG}.json"

if [[ "${JSON_OUTPUT}" == true ]]; then
  ARGS+=(
    --benchmark_format=console
    --benchmark_out="${OUTPUT_JSON}"
    --benchmark_out_format=json
  )
fi

ARGS+=("${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")

"${BENCHMARK_EXEC}" "${ARGS[@]}"

if [[ "${JSON_OUTPUT}" == true ]]; then
  echo "${OUTPUT_JSON}"
fi
