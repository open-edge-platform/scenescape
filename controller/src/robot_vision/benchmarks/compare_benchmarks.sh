#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Compare benchmark results using Google Benchmark's compare.py tool

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build"
TOOLS_DIR="${BUILD_DIR}/benchmark-tools"
COMPARE_PY="${TOOLS_DIR}/tools/compare.py"

# Clone benchmark tools if they don't exist
if [ ! -f "$COMPARE_PY" ]; then
    echo "Cloning Google Benchmark tools..."
    mkdir -p "$BUILD_DIR"

    # Clone the repository with sparse checkout to get only the tools directory
    git clone --filter=blob:none --sparse -b v1.9.5 https://github.com/google/benchmark.git "$TOOLS_DIR"
    git -C "$TOOLS_DIR" sparse-checkout set tools
fi

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <baseline.json> <contender.json>"
    echo "Example: $0 old_results.json new_results.json"
    exit 1
fi


# Use a Python virtual environment in the current folder, creating it if absent
VENV_DIR="${SCRIPT_DIR}/venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# A fresh venv may lack a usable build backend; ensure it is present first
pip3 install --upgrade pip setuptools wheel || echo "Warning: Could not upgrade pip/setuptools/wheel"

# Install Python dependencies
pip3 install -r "$TOOLS_DIR/tools/requirements.txt" || echo "Warning: Could not install some Python dependencies"

# Run comparison
PYTHONPATH="${TOOLS_DIR}/tools:$PYTHONPATH" python3 "$COMPARE_PY" benchmarks "$1" "$2"

# Deactivate the virtual environment
deactivate
