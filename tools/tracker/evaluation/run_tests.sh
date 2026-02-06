#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Simple test runner for tracker evaluation pipeline
# Usage:
#   ./run_tests.sh              # Run all tests (including integration)
#   ./run_tests.sh unit         # Run only unit tests (fast)
#   ./run_tests.sh integration  # Run only integration tests

set -e

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# Determine which tests to run
case "${1:-all}" in
  unit)
    echo "Running unit tests only (no Docker required)..."
    pytest . -v -m "not integration"
    ;;
  integration)
    echo "Running integration tests only (requires Docker)..."
    pytest . -v -m integration
    ;;
  all)
    echo "Running all tests..."
    pytest . -v
    ;;
  *)
    echo "Usage: $0 [all|unit|integration]"
    exit 1
    ;;
esac
