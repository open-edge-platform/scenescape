# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

# MQTT Client Bridge Service

This service provides a Docker container that bridges MQTT messages to ROS 2 topics, converting JSON MQTT payloads to ROS message types. It's designed for Nav2 navigation goal injection via MQTT.

## Overview

The bridge runs a custom Python application (`mqtt_to_ros_bridge.py`) that:

- Connects to an MQTT broker with optional authentication and TLS
- Subscribes to MQTT topics with JSON payloads
- Converts JSON messages to ROS 2 message types
- Publishes to ROS 2 topics or sends goals to ROS 2 action servers
- Supports configurable Nav2 action server paths via environment variables

**Architecture**:

- **Base Image**: `ros:jazzy` (official from Docker Hub)
- **ROS Distro**: Jazzy
- **Dependencies**: paho-mqtt (Python MQTT client), ros-jazzy-nav2-msgs
- **Python Bridge**: `mqtt_to_ros_bridge.py` handles JSON↔ROS message conversion and bridging logic

## Building

From the repository root:

```bash
# Build just the mqtt_client_bridge service
make build-mqtt-client-bridge

# Or using docker-compose directly
docker compose -f docker-compose.yml build mqtt_client_bridge
```

## Running

### Docker Compose

The service is integrated into the main docker-compose.yml and can be started with:

```bash
# Start the complete stack including mqtt_client_bridge
docker compose -f docker-compose.yml up -d

# Or just the bridge and broker
docker compose -f docker-compose.yml up -d broker mqtt_client_bridge
```

### Command-Line Arguments

The bridge accepts the following arguments (typically passed via docker-compose):

```bash
python3 mqtt_to_ros_bridge.py \
  --broker <hostname:port>              # MQTT broker address (default: localhost:1883)
  --brokerauth <path>                   # Authentication file (JSON or user:password format)
  --rootcert <path>                     # CA certificate for TLS (optional, port-dependent)
```

### Environment Variables

- `ROS_DOMAIN_ID`: ROS 2 domain ID (default: `4` in docker-compose)
- `NAV2_ACTION_PREFIX`: Prefix for Nav2 action server path (default: `/j100_1234/`)
  - Full action name becomes: `{NAV2_ACTION_PREFIX}navigate_to_pose`

### Docker Compose Configuration

From [docker-compose.yml](../docker-compose.yml):

```yaml
mqtt_client_bridge:
  build:
    context: ./mqtt_client_bridge
  depends_on:
    broker:
      condition: service_started
  command: >
    --broker broker.scenescape.intel.com
    --brokerauth /run/secrets/controller.auth
    --rootcert /run/secrets/certs/scenescape-ca.pem
  environment:
    - ROS_DOMAIN_ID=4
    - NAV2_ACTION_PREFIX=/j100_1234/
```

## Message Format

### Input: MQTT → ROS

The bridge listens to the `nav2/goal_pose` MQTT topic and converts JSON payloads to ROS messages.

**Topic**: `nav2/goal_pose`
**Output**:

- Attempts to send to `/j100_1234/navigate_to_pose` action server (or path specified by `NAV2_ACTION_PREFIX`)
- Falls back to publishing `geometry_msgs/msg/PoseStamped` to `/goal_pose` topic if action server unavailable

### JSON Message Format

Publish navigation goals as JSON to `nav2/goal_pose`:

```bash
mosquitto_pub \
  -h broker.scenescape.intel.com \
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

The bridge converts this to a `geometry_msgs/msg/PoseStamped` message and either:

1. **Sends to Nav2 action server** (primary): `/{NAV2_ACTION_PREFIX}/navigate_to_pose`
   - Waits 5 seconds for action server availability
   - Sends `nav2_msgs/action/NavigateToPose` goal
2. **Publishes to ROS topic** (fallback): `/goal_pose` if action server unavailable

**Required Fields**:

- `header.frame_id`: Reference frame (typically "map" or "base_link")
- `pose.position.x`, `y`, `z`: 3D position coordinates (floats)
- `pose.orientation.x`, `y`, `z`, `w`: Quaternion components (must be normalized, floats)

## Architecture

The bridge is a single Python application (`mqtt_to_ros_bridge.py`) running in a ROS 2 Jazzy container that:

- Uses `paho-mqtt` library to connect to MQTT brokers
- Runs ROS 2 publishers and action clients via `rclpy`
- Converts JSON payloads to ROS message types
- Handles both topic-based and action-based message delivery

```
┌──────────────┐                    ┌──────────────────────┐
│ MQTT Broker  │◄──────────────────►│ mqtt_client_bridge   │
│ Port 1883    │   (paho-mqtt)      │ (Python rclpy)       │
│ (non-TLS)    │                    │                      │
│ Port 1885    │                    │ • Action Client      │
│ (TLS v1.3)   │                    │ • Topic Publishers   │
└──────────────┘                    └──────────────────────┘
                                             │
                                    ┌────────▼──────────┐
                                    │   ROS 2 Jazzy     │
                                    │ • /goal_pose topic │
                                    │ • /j100_1234/      │
                                    │   navigate_to_pose │
                                    │   action server    │
                                    └───────────────────┘
```

**Connection Details**:

- **MQTT Port Selection**: Automatically selects based on broker configuration:
  - Port 1883 (default): Non-TLS, anonymous/username-password auth
  - Port 1885: TLS v1.3 with client certificate (optional, not currently used)
  - Port 1884: WebSocket (not currently used)

- **TLS Handling**:
  - Only enabled on non-default ports (1885, 1884)
  - Port 1883 connections are never TLS-encrypted
  - If `--rootcert` is provided but port is 1883, TLS is skipped with info log

## Troubleshooting

### View logs

```bash
docker compose -f docker-compose.yml logs mqtt_client_bridge -f
```

### Check MQTT connection status

Look for these success indicators:

```
[INFO] [timestamp] [mqtt_to_ros_bridge]: Using navigate_to_pose action at: /j100_1234/navigate_to_pose
[INFO] [timestamp] [mqtt_to_ros_bridge]: Port 1883 is non-TLS, skipping TLS setup...
[INFO] [timestamp] [mqtt_to_ros_bridge]: Using authentication with username: {user...
[INFO] [timestamp] [mqtt_to_ros_bridge]: Connected to MQTT broker with result code 0
[INFO] [timestamp] [mqtt_to_ros_bridge]: Subscribed to MQTT topic: nav2/goal_pose
```

### Test message delivery

**Publish a test message** (from host or another container on the scenescape network):

```bash
docker run --network scenescape_scenescape -it --rm eclipse-mosquitto:2.0.22 \
  mosquitto_pub -h broker.scenescape.intel.com -p 1883 \
  -t "nav2/goal_pose" \
  -m '{"header":{"frame_id":"map"},"pose":{"position":{"x":1.0,"y":0.0,"z":0.0},"orientation":{"x":0.0,"y":0.0,"z":0.0,"w":1.0}}}'
```

**Verify message received**:

```bash
docker logs mqtt_client_bridge | grep "Received MQTT message"
```

Expected log output:

```
[INFO] [timestamp] [mqtt_to_ros_bridge]: Received MQTT message on nav2/goal_pose: {"header"...
[INFO] [timestamp] [mqtt_to_ros_bridge]: Waiting for navigate_to_pose action server...
[WARN] [timestamp] [mqtt_to_ros_bridge]: navigate_to_pose action server not available, publishing to topic instead
[INFO] [timestamp] [mqtt_to_ros_bridge]: Published goal_pose to ROS: position=(1.0, 0.0)
```

### Monitor goal_pose messages in real-time

```bash
docker compose exec mqtt_client_bridge bash -c \
  "source /opt/ros/jazzy/setup.bash && ros2 topic echo /goal_pose"
```

### Common Issues

**Problem**: Connection Refused

- **Cause**: Broker not running or incorrect hostname/port
- **Solution**: Verify broker is running: `docker compose ps broker`
- **Check**: `docker logs scenescape-broker-1 | tail -20`

**Problem**: TLS Connection Error (SSL handshake failed)

- **Cause**: Connecting to non-TLS port (1883) with TLS enabled
- **Solution**: Ensure port 1883 is used or TLS port (1885) if cert is valid
- **Check**: Bridge logs should show "Port 1883 is non-TLS" message

**Problem**: Authentication Failed

- **Cause**: Invalid authentication file or format
- **Solution**: Verify auth file exists and contains valid JSON or user:password format
- **Check**: `docker compose exec -it mqtt_client_bridge cat /run/secrets/controller.auth`

**Problem**: Message not appearing on ROS topic

- **Cause**: Multiple possible issues (invalid JSON, wrong topic, auth failure)
- **Solution**:
  1. Verify MQTT message is valid JSON: `jq . < message.json`
  2. Check all required fields are present
  3. Ensure ROS_DOMAIN_ID matches: `echo $ROS_DOMAIN_ID` in bridge container
  4. Verify bridge is subscribed: `docker logs mqtt_client_bridge | grep "Subscribed"`
