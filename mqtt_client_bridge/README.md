# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

# MQTT Client Bridge Service

This service provides a Docker container that bridges MQTT messages to ROS 2 topics, converting JSON MQTT payloads to ROS message types. It's designed for Nav2 navigation goal injection via MQTT.

## Overview

The bridge runs a custom Python application (`mqtt_to_ros_bridge.py`) that:

- Connects to an MQTT broker
- Subscribes to MQTT topics with JSON payloads
- Converts JSON messages to ROS 2 message types
- Publishes to ROS 2 topics
- Can send goals to ROS 2 action servers (e.g., Nav2 navigate_to_pose)

- **Base Image**: `ros:jazzy` (from Docker Hub)
- **ROS Distro**: Jazzy
- **Python Bridge**: `mqtt_to_ros_bridge.py` handles JSON↔ROS message conversion

## Building

```bash
docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml build mqtt_client_bridge
```

## Running with Docker Compose

Start the service alongside the MQTT broker:

```bash
# Start broker and bridge
docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml up -d broker mqtt_client_bridge

# Or with custom ROS settings
ROS_DOMAIN_ID=5 docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml up -d broker mqtt_client_bridge
```

### Environment Variables

- `ROS_DOMAIN_ID`: ROS 2 domain ID (default: `0`)
- `ROS_LOCALHOST_ONLY`: Set to `0` for network support (auto-configured)

Set these via shell variables or in your `.env` file.

## Message Format

The bridge converts JSON MQTT messages to ROS message types and can send goals to ROS 2 action servers.

### Supported Bridging

- **Input (MQTT → ROS)**:
  - Topic: `nav2/goal_pose` (JSON)
  - Publishes to ROS topic: `/goal_pose` (geometry_msgs/msg/PoseStamped)
  - If Nav2 action server is available, sends goal to `/navigate_to_pose` action

### JSON Message Format

Publish navigation goals as JSON to `nav2/goal_pose`:

```bash
mosquitto_pub \
  -h localhost \
  -p 1883 \
  -t "nav2/goal_pose" \
  -m '{
    "header": {
      "frame_id": "map"
    },
    "pose": {
      "position": {"x": 5.0, "y": 3.0, "z": 0.0},
      "orientation": {"x": 0.0, "y": 0.0, "z": 0.383, "w": 0.924}
    }
  }'
```

The bridge converts this to a proper ROS `PoseStamped` message and either:

1. Sends it to the `/navigate_to_pose` action server (if available)
2. Publishes it to `/goal_pose` topic (fallback)

**Required Fields**:

- `header.frame_id`: Reference frame (typically "map" or "base_link")
- `pose.position.x`, `y`, `z`: 3D position coordinates
- `pose.orientation.x`, `y`, `z`, `w`: Quaternion (must be normalized)

## Architecture

The bridge is a single Python application that:

- Uses paho-mqtt library to connect to MQTT brokers
- Runs ROS 2 publishers and action clients
- Converts JSON payloads to ROS message types
- Handles both topic-based and action-based message delivery

```
MQTT Broker ←→ mqtt_client_bridge (Python) ←→ ROS 2 Topics/Actions
  Port 1883        (paho-mqtt)              (rclpy)
```

## Troubleshooting

### View logs

```bash
docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml logs mqtt_client_bridge -f
```

### Check MQTT connection status

Look for these log messages:

```bash
[INFO] [timestamp] [mqtt_to_ros_bridge]: Connected to MQTT broker with result code 0
[INFO] [timestamp] [mqtt_to_ros_bridge]: Subscribed to MQTT topic: nav2/goal_pose
```

### Verify ROS topics are being published

```bash
docker compose exec mqtt_client_bridge bash -c \
  "source /opt/ros/jazzy/setup.bash && ros2 topic list"
```

### Monitor goal_pose messages in real-time

```bash
docker compose exec mqtt_client_bridge bash -c \
  "source /opt/ros/jazzy/setup.bash && ros2 topic echo /goal_pose"
```

### Message not appearing on ROS topic

1. Verify MQTT message format is valid JSON
2. Check all required fields are present (header, pose.position, pose.orientation)
3. Ensure ROS_DOMAIN_ID matches across containers
4. Check bridge is connected to broker: `docker logs mqtt_client_bridge | grep Connected`
