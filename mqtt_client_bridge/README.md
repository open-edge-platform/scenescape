# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

# MQTT Client Bridge Service

This service provides a Docker container that runs the ROS 2 `mqtt_client` package, bridging MQTT messages to ROS 2 topics for Nav2 navigation goals.

## Overview

The service is based on the official pre-built `mqtt_client` Docker image from RWTH Aachen and adds a custom configuration layer for your SceneScape setup.

- **Base Image**: `ghcr.io/ika-rwth-aachen/mqtt_client:jazzy-slim`
- **Config Mount**: Configuration is mounted at runtime via docker-compose
- **ROS Distro**: Supports jazzy (configurable via `ROS_DISTRO` build arg)

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

## Publishing Navigation Goals via MQTT

Publish to the MQTT topic specified in your config (default: `scenescape_nav_goal`):

```bash
mosquitto_pub \
  -h broker.scenescape.intel.com \
  -p 1883 \
  -u admin \
  -P <SUPASS> \
  -t "scenescape_nav_goal" \
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

The message will be bridged to your configured ROS topic (default: `/goal_pose`) where Nav2 will receive it.

## Connecting to Remote Robots

For robots on different networks with ROS Discovery Server:

**Via environment variables:**

```bash
ROS_DISCOVERY_SERVER=192.168.1.100:11511 \
docker compose -f docker-compose-dl-streamer-mqtt-nav2.yml --profile mqtt_client up
```

**Or in `.env`:**

```
ROS_DOMAIN_ID=0
ROS_DISCOVERY_SERVER=192.168.1.100:11511
```

## Troubleshooting

### View logs

```bash
make logs
# Or
docker compose logs mqtt_client_bridge -f
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
docker compose exec mqtt_client_bridge \
  ros2 topic list
```

### Monitor goal_pose messages in real-time

```bash
docker compose exec mqtt_client_bridge \
  ros2 topic echo /goal_pose
```

## References

- [mqtt_client GitHub Repository](https://github.com/ika-rwth-aachen/mqtt_client)
- [ROS 2 PoseStamped Message](https://docs.ros.org/en/humble/p/geometry_msgs/interfaces/msg/PoseStamped.html)
- [ROS 2 Discovery Server](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Domain-ID.html)
