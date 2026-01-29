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
if [ ! -f "test_api.py" ]; then
    echo -e "${RED}Error: test files not found. Please run this script from the tests directory.${NC}"
    exit 1
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
        pytest test_api.py -v
        ;;
    "functional")
        echo -e "${GREEN}Running functional tests only...${NC}"
        pytest test_extraction.py test_matching.py test_matchers.py test_database.py test_workflows.py test_localize_scenescape.py -v
        ;;
    "all")
        echo -e "${GREEN}Running all HLOC tests...${NC}"
        pytest "$TEST_TARGET" -v
        ;;
    "coverage")
        echo -e "${GREEN}Running tests with coverage...${NC}"
        pytest "$TEST_TARGET" -v --cov=../hloc --cov-report=html --cov-report=term-missing
        echo ""
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    "fast")
        echo -e "${GREEN}Running fast tests only...${NC}"
        pytest "$TEST_TARGET" -v -m "not slow"
        ;;
    *)
        echo -e "${RED}Unknown test mode: $TEST_MODE${NC}"
        echo "Usage: $0 [test_target] [api|functional|all|coverage|fast]"
        echo ""
        echo "Modes:"
        echo "  api        - Run API tests only"
        echo "  functional - Run functional tests only"
        echo "  all        - Run all tests (default)"
        echo "  coverage   - Run with coverage report"
        echo "  fast       - Skip slow tests"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test run completed!${NC}"
echo -e "${GREEN}========================================${NC}"
