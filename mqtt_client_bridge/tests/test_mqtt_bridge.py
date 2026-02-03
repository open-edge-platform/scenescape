#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test script to verify mqtt_client_bridge functionality.

This script:
1. Subscribes to ROS goal_pose topic
2. Publishes test navigation goals via MQTT
3. Verifies messages are received on the ROS topic
"""

import json
import sys
import time
import subprocess
from threading import Thread, Event

try:
  import paho.mqtt.client as mqtt
except ImportError:
  print("ERROR: paho.mqtt not found. Install with: pip3 install paho-mqtt")
  sys.exit(1)

try:
  import rclpy
  from geometry_msgs.msg import PoseStamped
  from rclpy.node import Node
except ImportError:
  print("ERROR: ROS 2 not found. Make sure to source setup.bash first:")
  print("  source /opt/ros/jazzy/setup.bash")
  sys.exit(1)


class GoalListener(Node):
  """ROS 2 node that listens for navigation goals."""

  def __init__(self):
    super().__init__('goal_listener')
    self.goals_received = []
    self.goal_event = Event()
    
    self.subscription = self.create_subscription(
      PoseStamped,
      '/goal_pose',
      self.goal_callback,
      10
    )

  def goal_callback(self, msg):
    """Callback for received goal messages."""
    self.goals_received.append(msg)
    self.get_logger().info(
      f'Goal received: x={msg.pose.position.x:.2f}, '
      f'y={msg.pose.position.y:.2f}, '
      f'z={msg.pose.position.z:.2f}'
    )
    self.goal_event.set()

  def wait_for_goal(self, timeout_seconds=5.0):
    """Wait for a goal message with timeout."""
    self.goal_event.clear()
    return self.goal_event.wait(timeout=timeout_seconds)


def test_mqtt_bridge():
  """Main test function."""
  print("=" * 60)
  print("MQTT Client Bridge Test")
  print("=" * 60)

  # Initialize ROS 2
  rclpy.init()
  listener = GoalListener()

  # Spin in background thread
  def spin_node():
    try:
      executor = rclpy.executors.SingleThreadedExecutor()
      executor.add_node(listener)
      executor.spin()
    except Exception as e:
      listener.get_logger().error(f"Error spinning node: {e}")

  ros_thread = Thread(target=spin_node, daemon=True)
  ros_thread.start()

  # Give ROS time to initialize
  time.sleep(2)

  # Test cases
  tests = [
    {
      'name': 'Basic Navigation Goal',
      'payload': {
        'header': {'frame_id': 'map'},
        'pose': {
          'position': {'x': 5.0, 'y': 3.0, 'z': 0.0},
          'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.383, 'w': 0.924}
        }
      }
    },
    {
      'name': 'Goal at Origin',
      'payload': {
        'header': {'frame_id': 'map'},
        'pose': {
          'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
          'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}
        }
      }
    },
    {
      'name': 'Goal with Negative Coordinates',
      'payload': {
        'header': {'frame_id': 'map'},
        'pose': {
          'position': {'x': -2.5, 'y': -1.5, 'z': 0.0},
          'orientation': {'x': 0.0, 'y': 0.0, 'z': -0.707, 'w': 0.707}
        }
      }
    }
  ]

  passed = 0
  failed = 0

  for i, test in enumerate(tests, 1):
    print(f"\n[Test {i}/{len(tests)}] {test['name']}")
    print("-" * 60)

    try:
      # Publish via MQTT using mosquitto_pub
      mqtt_payload = json.dumps(test['payload'])
      cmd = [
        'mosquitto_pub',
        '-h', 'broker.scenescape.intel.com',
        '-p', '1883',
        '-t', 'scenescape_nav_goal',
        '-m', mqtt_payload
      ]

      print(f"Publishing to MQTT: {mqtt_payload[:80]}...")
      result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=5
      )

      if result.returncode != 0:
        error_msg = result.stderr.decode() if result.stderr else "Unknown error"
        print(f"MQTT publish warning (may be OK if broker not running): {error_msg[:100]}")
        # Continue anyway - broker might start later

      # Wait for goal on ROS topic
      listener.goals_received.clear()
      if listener.wait_for_goal(timeout_seconds=3.0):
        goal = listener.goals_received[-1]
        
        # Verify coordinates match
        expected_pos = test['payload']['pose']['position']
        actual_pos = goal.pose.position
        
        pos_match = (
          abs(actual_pos.x - expected_pos['x']) < 0.01 and
          abs(actual_pos.y - expected_pos['y']) < 0.01 and
          abs(actual_pos.z - expected_pos['z']) < 0.01
        )

        if pos_match:
          print("✓ PASSED: Message bridged successfully")
          print(f"  Received: x={actual_pos.x:.2f}, y={actual_pos.y:.2f}, z={actual_pos.z:.2f}")
          passed += 1
        else:
          print("✗ FAILED: Position mismatch")
          print(f"  Expected: {expected_pos}")
          print(f"  Actual: x={actual_pos.x}, y={actual_pos.y}, z={actual_pos.z}")
          failed += 1
      else:
        print("✗ FAILED: No message received on ROS topic within timeout")
        print("  (This is expected if mqtt_client_bridge is not running)")
        failed += 1

    except subprocess.TimeoutExpired:
      print("✗ FAILED: MQTT publish timeout")
      failed += 1
    except Exception as e:
      print(f"✗ FAILED: {e}")
      failed += 1

  # Summary
  print("\n" + "=" * 60)
  print("Test Summary")
  print("=" * 60)
  print(f"Passed: {passed}/{len(tests)}")
  print(f"Failed: {failed}/{len(tests)}")

  try:
    rclpy.shutdown()
  except Exception:
    pass
  
  return 0 if failed == 0 else 1


if __name__ == '__main__':
  sys.exit(test_mqtt_bridge())
