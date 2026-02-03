# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

## Testing the MQTT Client Bridge

This directory contains tests to verify the mqtt_client_bridge is functioning correctly.

### Architecture

The test environment uses a custom Python bridge (`mqtt_to_ros_bridge.py`) that converts JSON MQTT messages to ROS messages. This allows external systems to send navigation goals via standard JSON over MQTT instead of requiring CDR-serialized ROS messages.

### Quick Test (No Simulation)

Run the basic connectivity test:

```bash
cd mqtt_client_bridge/tests
bash test_mqtt_bridge.sh
```

This verifies:

- MQTT broker connectivity
- Basic JSON message publishing to MQTT
- Custom Python bridge message conversion
- ROS topic message reception

### Full Integration Test (With Gazebo + Nav2)

For a complete end-to-end test with a simulated robot:

```bash
cd /path/to/scenescape

# Start all services including test harness
docker compose \
  -f docker-compose-dl-streamer-mqtt-nav2.yml \
  -f mqtt_client_bridge/docker-compose.test.yml \
  up
```

This will:

1. Start the Zenoh router for ROS peer discovery
2. Start the MQTT broker (non-TLS on port 1883)
3. Start the mqtt_client_bridge service
4. Launch the nav2_simulator with:
   - Gazebo with Turtlebot3 simulator
   - Nav2 navigation stack
   - Custom Python bridge (mqtt_to_ros_bridge.py) for JSON→ROS conversion
5. Enable manual testing of:
   - Publishing JSON goals via MQTT
   - Verifying conversion to ROS messages
   - Checking `/goal_pose` topic reception
   - Testing multiple goal scenarios

### Manual Testing

**Publish a test goal via MQTT (JSON format):**

```bash
mosquitto_pub \
  -h localhost \
  -p 1883 \
  -t "nav2/goal_pose" \
  -m '{
    "header": {"frame_id": "map"},
    "pose": {
      "position": {"x": 5.0, "y": 3.0, "z": 0.0},
      "orientation": {"x": 0.0, "y": 0.0, "z": 0.383, "w": 0.924}
    }
  }'
```

**Listen for goals on ROS topic (from nav2_simulator):**

```bash
docker exec nav2_simulator bash -c \
  "source /opt/ros/jazzy/setup.bash && ros2 topic echo /goal_pose"
```

**Check custom Python bridge logs:**

```bash
docker logs nav2_simulator 2>&1 | grep -E "mqtt_to_ros|Published goal_pose"
```

Expected output shows the conversion:
```
[INFO] [timestamp] [mqtt_to_ros_bridge]: Received MQTT message on nav2/goal_pose: {...}
[INFO] [timestamp] [mqtt_to_ros_bridge]: Published goal_pose to ROS: position=(5.0, 3.0)
```

### Test Files

- `test_mqtt_bridge.sh` - Quick connectivity and basic bridging test
- `test_mqtt_bridge.py` - Full Python test with ROS 2 integration
- `docker-compose.test.yml` - Test composition with Gazebo + Nav2 simulator

### Expected Test Output

**Successful test:**

```
============================================================
MQTT Client Bridge Test
============================================================

[Test 1/3] Basic Navigation Goal
------------------------------------------------------------
Publishing to MQTT: {"header": {"frame_id": "map"}, ...
✓ PASSED: Message bridged successfully
  Received: x=5.00, y=3.00, z=0.00

[Test 2/3] Goal at Origin
------------------------------------------------------------
✓ PASSED: Message bridged successfully
  Received: x=0.00, y=0.00, z=0.00

[Test 3/3] Goal with Negative Coordinates
------------------------------------------------------------
✓ PASSED: Message bridged successfully
  Received: x=-2.50, y=-1.50, z=0.00

============================================================
Test Summary
============================================================
Passed: 3/3
Failed: 0/3
```

### Troubleshooting

If tests fail:

1. **MQTT broker not reachable**
   - Verify broker is running: `docker compose ps broker`
   - Check broker network: `docker compose logs broker | tail -20`
   - Ensure port 1883 is not already in use

2. **Custom bridge not converting messages**
   - Check bridge is running: `docker logs nav2_simulator 2>&1 | head -50`
   - Look for "Connected to MQTT broker" and "Subscribed" messages
   - Verify MQTT message is valid JSON with all required fields
   - Check bridge logs for conversion errors

3. **No messages on ROS topic**
   - Check mqtt_to_ros_bridge logs: `docker logs nav2_simulator | grep mqtt_to_ros_bridge`
   - Verify MQTT topic is correct: `nav2/goal_pose`
   - Ensure ROS_DOMAIN_ID matches (default: 0)
   - Check Zenoh router is running: `docker compose ps | grep zenoh`

4. **Position mismatch**
   - Verify JSON message format matches PoseStamped schema
   - Check quaternion is normalized (x² + y² + z² + w² ≈ 1.0)
   - Ensure all position/orientation fields are numbers

5. **Bridge connection timeout**
   - Check broker is listening on 1883: `netstat -tuln | grep 1883`
   - Try manual MQTT test: `mosquitto_pub -h localhost -p 1883 -t test -m hello`
   - Verify TLS is disabled on port 1883 in mosquitto config

### Test Components

- **Zenoh Router**: Enables ROS 2 peer discovery across containers using Zenoh middleware
- **MQTT Broker**: Eclipse Mosquitto (non-TLS on port 1883 for testing)
- **mqtt_client_bridge**: RWTH Aachen service for MQTT↔ROS bridging (expects CDR format)
- **mqtt_to_ros_bridge.py**: Custom Python bridge for JSON→ROS conversion (runs in nav2_simulator)
- **nav2_simulator**: Pre-built Docker image with Gazebo, Turtlebot3, and Nav2 stack
- **docker-compose.test.yml**: Test overlay with nav2_simulator service

### Message Flow Diagram

```
External System (JSON)
        ↓
mosquitto_pub "nav2/goal_pose" (JSON)
        ↓
MQTT Broker (localhost:1883)
        ↓
mqtt_to_ros_bridge.py (ROS 2 Node)
        ↓
JSON → PoseStamped conversion
        ↓
ros2 publish /goal_pose (PoseStamped)
        ↓
Nav2 Navigation Stack
        ↓
Robot Goal Execution
```

### References

- [mqtt_client Documentation](https://github.com/ika-rwth-aachen/mqtt_client)
- [Custom Python Bridge](../mqtt_to_ros_bridge.py)
- [ROS 2 PoseStamped Message](https://docs.ros.org/en/jazzy/p/geometry_msgs/interfaces/msg/PoseStamped.html)
- [ROS 2 Testing Guide](https://docs.ros.org/en/jazzy/How-To-Guides/Testing-main.html)
- [Turtlebot3 Gazebo](http://wiki.ros.org/turtlebot3_gazebo)
- [Nav2 Getting Started](https://nav2.org/getting_started/index.html)
- [Zenoh RMW for ROS 2](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds)
