# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

# MQTT Client Bridge Service

This service provides a Docker container that runs the ROS 2 `mqtt_client` package, bridging MQTT messages to ROS 2 topics for Nav2 navigation goals.

## Overview

The service is based on the official pre-built `mqtt_client` Docker image from RWTH Aachen and adds a custom configuration layer for your SceneScape setup.

- **Base Image**: `ghcr.io/ika-rwth-aachen/mqtt_client:jazzy-slim`
- **Config Mount**: Configuration is mounted at runtime via docker-compose
- **ROS Distro**: Supports jazzy (configurable via `ROS_DISTRO` build arg)
- **Custom Python Bridge**: `mqtt_to_ros_bridge.py` handles JSON→ROS message conversion (see [Message Format](#message-format) below)

## Building

```bash
cd mqtt_client_bridge
make build
```

## Configuration

Edit `config/mqtt_nav2_config.yaml` to customize:

- MQTT broker address and credentials
- MQTT topics to subscribe to
- ROS 2 topics to publish to
- Message types and payload handling

## Running with Docker Compose

The service is integrated into `docker-compose-dl-streamer-mqtt-nav2.yml`. Enable it with the `mqtt_client` profile:

```bash
# Start all services including mqtt_client_bridge
docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml --profile mqtt_client up

# Or with custom ROS settings
ROS_DOMAIN_ID=5 \
ROS_DISCOVERY_SERVER=192.168.1.100:11511 \
docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml --profile mqtt_client up
```

### Environment Variables

- `ROS_DOMAIN_ID`: ROS 2 domain ID (default: `0`)
- `ROS_DISCOVERY_SERVER`: IP:port of ROS discovery server for remote robots (optional)
- `ROS_LOCALHOST_ONLY`: Always set to `0` for network support

Set these in your `.env` file or as shell variables.

## Message Format

The mqtt_client bridge from RWTH Aachen expects CDR-serialized ROS messages, which is incompatible with external JSON APIs. To solve this, a custom Python bridge (`mqtt_to_ros_bridge.py`) runs alongside the service and converts JSON messages to proper ROS types.

### Supported Topics

- **Input (MQTT → ROS)**:
  - Topic: `nav2/goal_pose` (JSON)
  - Converts to ROS topic: `/goal_pose` (geometry_msgs/msg/PoseStamped)

- **Output (ROS → MQTT)**:
  - ROS topic: `/amcl_pose` (geometry_msgs/msg/PoseWithCovarianceStamped)
  - Converts to MQTT topic: `nav2/current_pose` (JSON)

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

The custom bridge will convert this to a proper ROS `PoseStamped` message and publish it to `/goal_pose` where Nav2 will receive it.

**Required Fields**:
- `header.frame_id`: Reference frame (typically "map" or "base_link")
- `pose.position.x`, `y`, `z`: 3D position coordinates
- `pose.orientation.x`, `y`, `z`, `w`: Quaternion (must be normalized)

## Architecture

The bridge consists of two components:

1. **mqtt_client_bridge** (RWTH Aachen package):
   - Subscribes to MQTT topics
   - Expects CDR-serialized ROS messages
   - Publishes to ROS topics using Zenoh RMW

2. **mqtt_to_ros_bridge.py** (Custom Python script):
   - Subscribes to JSON-formatted MQTT topics
   - Converts JSON payloads to ROS message types
   - Publishes to ROS topics
   - Runs in the nav2_simulator container alongside Nav2

### ROS Middleware (RMW)

Both bridges use Zenoh as the ROS middleware implementation for peer discovery across containers:
- **RMW Implementation**: `rmw_zenoh_cpp`
- **Zenoh Router**: Deployed in `docker-compose-dl-streamer-mqtt-nav2.yml` for inter-container discovery
- **Network Mode**: Host networking for ROS communication

## Troubleshooting

### View logs

```bash
make logs
# Or
docker compose logs mqtt_client_bridge -f
docker compose logs nav2_simulator -f  # For custom Python bridge
```

### Check MQTT connection status

The mqtt_client provides a service to check connectivity:

```bash
docker compose exec mqtt_client_bridge \
  ros2 service call /mqtt_client_bridge/is_connected \
  mqtt_client_interfaces/srv/IsConnected
```

### Verify ROS topics are being published

```bash
docker compose exec nav2_simulator bash -c \
  "source /opt/ros/jazzy/setup.bash && ros2 topic list"
```

### Monitor goal_pose messages in real-time

```bash
docker compose exec nav2_simulator bash -c \
  "source /opt/ros/jazzy/setup.bash && ros2 topic echo /goal_pose"
```

### Custom bridge not converting messages

Check the bridge logs:

```bash
docker logs nav2_simulator 2>&1 | grep mqtt_to_ros_bridge
```

Expected output:
```
[INFO] [timestamp] [mqtt_to_ros_bridge]: Connected to MQTT broker
[INFO] [timestamp] [mqtt_to_ros_bridge]: Subscribed to MQTT topic: nav2/goal_pose
[INFO] [timestamp] [mqtt_to_ros_bridge]: Received MQTT message on nav2/goal_pose: {...}
[INFO] [timestamp] [mqtt_to_ros_bridge]: Published goal_pose to ROS: position=(x, y)
```

### Message not appearing on ROS topic

1. Verify MQTT message format is valid JSON
2. Check all required fields are present (header, pose.position, pose.orientation)
3. Ensure ROS_DOMAIN_ID matches across containers
4. Check Zenoh router is running: `docker compose ps | grep zenoh`

## References

- [mqtt_client GitHub Repository](https://github.com/ika-rwth-aachen/mqtt_client)
- [ROS 2 PoseStamped Message](https://docs.ros.org/en/humble/p/geometry_msgs/interfaces/msg/PoseStamped.html)
- [ROS 2 Discovery Server](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Domain-ID.html)
