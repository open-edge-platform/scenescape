#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Test Runner Script for Mapping Module
# Run this script from inside the mapping container

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}SceneScape Mapping Module Test Runner${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "conftest.py" ]; then
    echo -e "${RED}Error: conftest.py not found. Please run this script from the tests directory.${NC}"
    exit 1
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}pytest not found. Installing test dependencies...${NC}"
    pip install -q pytest pytest-cov pytest-mock
    echo -e "${GREEN}Test dependencies installed.${NC}"
    echo ""
fi

# Default to running all tests
TEST_TARGET="${1:-.}"
TEST_MODE="${2:-unit}"

echo -e "${YELLOW}Test Target:${NC} $TEST_TARGET"
echo -e "${YELLOW}Test Mode:${NC} $TEST_MODE"
echo ""

# Run tests based on mode
case "$TEST_MODE" in
    "unit")
        echo -e "${GREEN}Running unit tests...${NC}"
        pytest "$TEST_TARGET" -v -m "unit or not integration"
        ;;
    "integration")
        echo -e "${GREEN}Running integration tests...${NC}"
        pytest "$TEST_TARGET" -v -m "integration"
        ;;
    "all")
        echo -e "${GREEN}Running all tests...${NC}"
        pytest "$TEST_TARGET" -v
        ;;
    "coverage")
        echo -e "${GREEN}Running tests with coverage...${NC}"
        pytest "$TEST_TARGET" -v --cov=../src --cov-report=html --cov-report=term-missing
        echo ""
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    "fast")
        echo -e "${GREEN}Running fast tests only...${NC}"
        pytest "$TEST_TARGET" -v -m "not slow"
        ;;
    *)
        echo -e "${RED}Unknown test mode: $TEST_MODE${NC}"
        echo "Usage: $0 [test_target] [unit|integration|all|coverage|fast]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test run completed!${NC}"
echo -e "${GREEN}========================================${NC}"
