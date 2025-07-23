#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Run 50-object tracking benchmark with human-readable output

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build"
BENCHMARK_EXEC="${BUILD_DIR}/benchmarks/RobotVisionBenchmarks"
GIT_HASH=$(git rev-parse --short HEAD)
OUTPUT_JSON="${SCRIPT_DIR}/out/rv_benchmark_${GIT_HASH}.json"

# Parse command line arguments
JSON_OUTPUT=false
if [[ "$1" == "--json" ]]; then
    JSON_OUTPUT=true
    # Ensure output directory exists
    mkdir -p "${SCRIPT_DIR}/out"
fi

# Check if benchmark executable exists
if [ ! -f "${BENCHMARK_EXEC}" ]; then
    echo "Error: Benchmark executable not found at ${BENCHMARK_EXEC}."
    echo "Please build the benchmarks before running this script."
    exit 1
fi

# Prepare benchmark arguments
ARGS=(
    --benchmark_report_aggregates_only=true
)

if [ "$JSON_OUTPUT" = true ]; then
    ARGS+=(
        --benchmark_format=json
        --benchmark_out="${OUTPUT_JSON}"
    )
fi

# Run benchmark
"${BENCHMARK_EXEC}" "${ARGS[@]}"

# Print output file path if JSON was requested
if [ "$JSON_OUTPUT" = true ]; then
    echo "${OUTPUT_JSON}"
fi
