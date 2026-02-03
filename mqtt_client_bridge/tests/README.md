# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

## Testing the MQTT Client Bridge

This directory contains tests to verify the mqtt_client_bridge is functioning correctly.

### Quick Test (No Simulation)

Run the basic connectivity test:

```bash
cd mqtt_client_bridge/tests
bash test_mqtt_bridge.sh
```

This verifies:

- MQTT broker connectivity
- Basic message publishing
- Service availability

### Full Integration Test (With Gazebo + Nav2)

For a complete end-to-end test with a simulated robot:

```bash
cd /path/to/scenescape

# Start all services including test harness
docker compose \
  -f docker-compose-dl-streamer-mqtt-nav2.yml \
  -f mqtt_client_bridge/docker-compose.test.yml \
  --profile mqtt_client \
  up
```

This will:

1. Start the MQTT broker and mqtt_client_bridge
2. Launch Gazebo with Turtlebot3 simulator
3. Start Nav2 navigation stack
4. Run automated tests that:
   - Publish navigation goals via MQTT
   - Verify messages arrive on ROS `/goal_pose` topic
   - Check position accuracy
   - Test multiple goal scenarios

### Manual Testing

**Publish a test goal via MQTT:**

```bash
mosquitto_pub \
  -h broker.scenescape.intel.com \
  -p 1883 \
  -t "scenescape_nav_goal" \
  -m '{
    "header": {"frame_id": "map"},
    "pose": {
      "position": {"x": 5.0, "y": 3.0, "z": 0.0},
      "orientation": {"x": 0.0, "y": 0.0, "z": 0.383, "w": 0.924}
    }
  }'
```

**Listen for goals on ROS topic:**

```bash
docker exec mqtt_client_bridge ros2 topic echo /goal_pose
```

**Check MQTT to ROS bridging status:**

```bash
docker exec mqtt_client_bridge \
  ros2 service call /mqtt_client_bridge/is_connected \
  mqtt_client_interfaces/srv/IsConnected
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

2. **No messages on ROS topic**
   - Check mqtt_client_bridge logs: `docker compose logs mqtt_client_bridge`
   - Verify config: `cat mqtt_client_bridge/config/mqtt_nav2_config.yaml`
   - Ensure ROS_DOMAIN_ID matches

3. **Position mismatch**
   - Check if quaternion conversion is correct
   - Verify MQTT message format matches config schema

### References

- [mqtt_client Documentation](https://github.com/ika-rwth-aachen/mqtt_client)
- [ROS 2 Testing Guide](https://docs.ros.org/en/humble/How-To-Guides/Testing-main.html)
- [Turtlebot3 Gazebo](http://wiki.ros.org/turtlebot3_gazebo)
- [Nav2 Getting Started](https://nav2.org/getting_started/index.html)
