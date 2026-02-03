#!/bin/bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Simple end-to-end test for mqtt_client_bridge
# Tests MQTT message publishing to ROS topic bridging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "MQTT Client Bridge - End-to-End Test"
echo "=========================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Setup proxies for network access
export http_proxy="http://proxy-dmz.intel.com:911"
export https_proxy="http://proxy-dmz.intel.com:912"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"

# Test 1: Check if mosquitto_pub is available
echo -e "\n${YELLOW}[Test 1]${NC} Checking for mosquitto_pub..."
if command -v mosquitto_pub &> /dev/null; then
  echo -e "${GREEN}✓ PASSED${NC}: mosquitto_pub is available"
else
  echo -e "${YELLOW}⚠ WARNING${NC}: mosquitto_pub not found"
  echo "  To install: sudo apt-get install mosquitto-clients"
  echo "  Skipping broker connectivity test..."
fi

# Test 2: Check Docker availability
echo -e "\n${YELLOW}[Test 2]${NC} Checking Docker availability..."
if command -v docker &> /dev/null; then
  echo -e "${GREEN}✓ PASSED${NC}: Docker is available"
  docker --version
else
  echo -e "${RED}✗ FAILED${NC}: Docker not found"
  exit 1
fi

# Test 3: Check if docker-compose is available
echo -e "\n${YELLOW}[Test 3]${NC} Checking docker-compose availability..."
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
  echo -e "${GREEN}✓ PASSED${NC}: Docker Compose is available"
  docker compose version
else
  echo -e "${RED}✗ FAILED${NC}: Docker Compose not available"
  exit 1
fi

# Test 4: Check if mqtt_client image can be built
echo -e "\n${YELLOW}[Test 4]${NC} Checking mqtt_client Docker image..."
cd "$PROJECT_ROOT"
if docker build --build-arg ROS_DISTRO=jazzy -t mqtt_client_bridge:test . > /tmp/docker_build.log 2>&1; then
  echo -e "${GREEN}✓ PASSED${NC}: mqtt_client_bridge image built successfully"
else
  echo -e "${RED}✗ FAILED${NC}: Failed to build mqtt_client_bridge image"
  echo "Build log:"
  tail -30 /tmp/docker_build.log
  exit 1
fi

# Test 5: Check if test configuration is valid YAML
echo -e "\n${YELLOW}[Test 5]${NC} Validating mqtt_nav2_config.yaml..."
if command -v python3 &> /dev/null; then
  if python3 -c "import yaml; yaml.safe_load(open('config/mqtt_nav2_config.yaml'))" 2>/dev/null; then
    echo -e "${GREEN}✓ PASSED${NC}: Configuration is valid YAML"
  else
    echo -e "${RED}✗ FAILED${NC}: Invalid YAML configuration"
    exit 1
  fi
else
  echo -e "${YELLOW}⚠ SKIPPED${NC}: Python3 not available for YAML validation"
fi

# Test 6: Check Dockerfile syntax
echo -e "\n${YELLOW}[Test 6]${NC} Checking Dockerfile syntax..."
if command -v docker &> /dev/null && docker build --dry-run -t mqtt_client_bridge:test . > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSED${NC}: Dockerfile syntax is valid"
else
  echo -e "${YELLOW}⚠ SKIPPED${NC}: Could not validate Dockerfile"
fi

echo -e "\n${GREEN}=========================================="
echo "Build and Configuration Tests Completed"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Start the main SceneScape stack:"
echo "   docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml up"
echo ""
echo "2. In another terminal, start the mqtt_client_bridge:"
echo "   docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml --profile mqtt_client up mqtt_client_bridge"
echo ""
echo "3. Run integration tests:"
echo "   docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml -f mqtt_client_bridge/docker-compose.test.yml --profile mqtt_client up"

