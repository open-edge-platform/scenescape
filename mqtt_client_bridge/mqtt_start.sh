#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

echo "=== MQTT Client Bridge Startup ==="

# Source ROS setup
if [ -f /opt/ros/jazzy/setup.sh ]; then
  . /opt/ros/jazzy/setup.sh
  echo "✓ ROS setup sourced"
fi

# Source any workspace overlay if present
if [ -f /docker-ros/ws/install/setup.sh ]; then
  . /docker-ros/ws/install/setup.sh
  echo "✓ Workspace overlay sourced"
fi

echo "Starting MQTT Client with config: /mqtt_client_config/config.yaml"

# Start mqtt_client with custom configuration
exec ros2 launch mqtt_client standalone.launch.xml params_file:=/mqtt_client_config/config.yaml
