#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Test Runner Script for Autocalibration Module (HLOC)
# Run this script from inside the autocalibration-test container

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}SceneScape Autocalibration HLOC Tests${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "run_tests.py" ]; then
    echo -e "${RED}Error: run_tests.py not found. Please run this script from the tests directory.${NC}"
    exit 1
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}pytest not found. Installing test dependencies...${NC}"
    pip install -q pytest pytest-cov
    echo -e "${GREEN}Test dependencies installed.${NC}"
    echo ""
fi

# Default to running all tests
TEST_TARGET="${1:-.}"
TEST_MODE="${2:-all}"

echo -e "${YELLOW}Test Target:${NC} $TEST_TARGET"
echo -e "${YELLOW}Test Mode:${NC} $TEST_MODE"
echo ""

# Run tests based on mode
case "$TEST_MODE" in
    "api")
        echo -e "${GREEN}Running API tests only...${NC}"
        python3 run_tests.py --api-only
        ;;
    "functional")
        echo -e "${GREEN}Running functional tests only...${NC}"
        python3 run_tests.py --functional-only
        ;;
    "test")
        if [ -z "$TEST_TARGET" ] || [ "$TEST_TARGET" == "." ]; then
            echo -e "${RED}Error: Test name required for 'test' mode${NC}"
            echo "Usage: $0 <test_name> test"
            echo "Available tests: api, extraction, matching, matchers, database, workflows, localize_scenescape"
            exit 1
        fi
        echo -e "${GREEN}Running test: $TEST_TARGET${NC}"
        python3 run_tests.py --test "$TEST_TARGET"
        ;;
    "all")
        echo -e "${GREEN}Running all HLOC tests...${NC}"
        python3 run_tests.py
        ;;
    "coverage")
        echo -e "${GREEN}Running tests with coverage...${NC}"
        pytest "$TEST_TARGET" -v --cov=../../../src/reloc/hloc --cov-report=html --cov-report=term-missing
        echo ""
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    "pytest")
        echo -e "${GREEN}Running pytest directly...${NC}"
        pytest "$TEST_TARGET" -v
        ;;
    *)
        echo -e "${RED}Unknown test mode: $TEST_MODE${NC}"
        echo "Usage: $0 [test_target] [api|functional|test|all|coverage|pytest]"
        echo ""
        echo "Modes:"
        echo "  api        - Run API tests only"
        echo "  functional - Run functional tests only"
        echo "  test       - Run specific test (requires test name as first arg)"
        echo "  all        - Run all tests (default)"
        echo "  coverage   - Run with coverage report"
        echo "  pytest     - Run pytest directly on target"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test run completed!${NC}"
echo -e "${GREEN}========================================${NC}"
