#!/bin/bash

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Build benchmarks from scratch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

cd "${PROJECT_ROOT}"

echo "Cleaning build directory..."
rm -rf build

echo "Creating build directory..."
mkdir build

echo "Configuring project..."
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON

echo "Building benchmarks..."
cmake --build . --target RobotVisionBenchmarks -- -j$(nproc)

echo "Build completed successfully!"
echo "Benchmark executable: ${PWD}/benchmarks/RobotVisionBenchmarks"
