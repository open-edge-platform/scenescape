#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Simple MQTT to ROS bridge that converts JSON messages to ROS messages.
Subscribes to MQTT topics and either:
1. Publishes to ROS topics (for topic-based messages)
2. Sends goals to ROS action servers (for navigation goals)
"""

import json
import os
import numpy as np
from scipy.spatial.transform import Rotation

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose


class MqttToRosBridge(Node):
    def __init__(self):
        super().__init__('mqtt_to_ros_bridge')

        # Load coordinate transformation
        self.coordinate_transform = self.load_coordinate_transform()

        # ROS Publishers
        self.goal_pose_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)

        # ROS Action Clients - use environment variable for action prefix
        ros_prefix = os.getenv('ROS_PREFIX', '')
        action_name = f'{ros_prefix}navigate_to_pose' if ros_prefix else 'navigate_to_pose'
        self.nav_client = ActionClient(self, NavigateToPose, action_name)
        self.get_logger().info(f'Using navigate_to_pose action at: {action_name}')

        # MQTT Client setup
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message

        # Connect to MQTT broker
        self.get_logger().info('Connecting to MQTT broker at localhost:1883')
        self.mqtt_client.connect('localhost', 1883, 60)
        self.mqtt_client.loop_start()

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        self.get_logger().info(f'Connected to MQTT broker with result code {rc}')
        # Subscribe to MQTT topics
        client.subscribe('nav2/goal_pose')
        self.get_logger().info('Subscribed to MQTT topic: nav2/goal_pose')

    def load_coordinate_transform(self):
        """Load coordinate transformation configuration from JSON file"""
        transform_file = 'coordinate_transform.json'
        try:
            if os.path.exists(transform_file):
                with open(transform_file, 'r') as f:
                    transform = json.load(f)
                    self.get_logger().info(f'Loaded coordinate transform from {transform_file}')
                    return transform
            else:
                self.get_logger().warn(f'Coordinate transform file {transform_file} not found. Using identity transform.')
                return None
        except Exception as e:
            self.get_logger().error(f'Error loading coordinate transform: {str(e)}')
            return None

    def transform_pose(self, position, orientation):
        """Apply coordinate transformation to pose"""
        if not self.coordinate_transform:
            return position, orientation

        try:
            # Extract transformation parameters
            translation = self.coordinate_transform.get('translation', {'x': 0, 'y': 0, 'z': 0})
            rotation = self.coordinate_transform.get('rotation', {'x': 0, 'y': 0, 'z': 0, 'w': 1})
            scale = self.coordinate_transform.get('scale', {'x': 1, 'y': 1, 'z': 1})

            # Transform position (apply scale then translation)
            transformed_pos = {
                'x': position.get('x', 0) * scale.get('x', 1) + translation.get('x', 0),
                'y': position.get('y', 0) * scale.get('y', 1) + translation.get('y', 0),
                'z': position.get('z', 0) * scale.get('z', 1) + translation.get('z', 0)
            }

            # Transform orientation using quaternion multiplication
            # Create rotations from quaternions (scipy uses [x, y, z, w] format)
            q_rot_xyzw = [rotation.get('x', 0), rotation.get('y', 0), rotation.get('z', 0), rotation.get('w', 1)]
            q_input_xyzw = [orientation.get('x', 0), orientation.get('y', 0), orientation.get('z', 0), orientation.get('w', 1)]

            rot_transform = Rotation.from_quat(q_rot_xyzw)
            rot_input = Rotation.from_quat(q_input_xyzw)

            # Compose rotations: result = rot_transform * rot_input
            rot_result = rot_transform * rot_input
            q_result_xyzw = rot_result.as_quat()  # Returns [x, y, z, w]

            transformed_ori = {
                'x': float(q_result_xyzw[0]),
                'y': float(q_result_xyzw[1]),
                'z': float(q_result_xyzw[2]),
                'w': float(q_result_xyzw[3])
            }

            return transformed_pos, transformed_ori
        except Exception as e:
            self.get_logger().error(f'Error transforming pose: {str(e)}')
            return position, orientation


    def on_mqtt_message(self, client, userdata, msg):
        """Callback when MQTT message is received"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            self.get_logger().info(f'Received MQTT message on {topic}: {payload[:100]}...')

            if topic == 'nav2/goal_pose':
                # Try action client first (preferred for navigation)
                self.send_nav_goal(payload)
            else:
                self.get_logger().warn(f'Unknown topic: {topic}')

        except Exception as e:
            self.get_logger().error(f'Error processing MQTT message: {str(e)}')

    def send_nav_goal(self, payload):
        """Send goal to navigate_to_pose action server"""
        try:
            data = json.loads(payload)

            # Wait for action server to be available (increased timeout for ROS 2 discovery)
            self.get_logger().info('Waiting for navigate_to_pose action server...')
            if not self.nav_client.wait_for_server(timeout_sec=5.0):
                self.get_logger().warn('navigate_to_pose action server not available, publishing to topic instead')
                self.handle_goal_pose(payload)
                return

            self.get_logger().info('Action server available, sending goal')

            # Create navigation goal
            goal_msg = NavigateToPose.Goal()

            # Set header
            if 'header' in data:
                if 'frame_id' in data['header']:
                    goal_msg.pose.header.frame_id = data['header']['frame_id']
                else:
                    goal_msg.pose.header.frame_id = 'map'
            else:
                goal_msg.pose.header.frame_id = 'map'

            goal_msg.pose.header.stamp = self.get_clock().now().to_msg()

            # Set pose and apply coordinate transformation
            if 'pose' in data:
                pose = data['pose']

                # Extract original position and orientation
                position = pose.get('position', {'x': 0.0, 'y': 0.0, 'z': 0.0})
                orientation = pose.get('orientation', {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0})

                # Apply coordinate transformation
                position, orientation = self.transform_pose(position, orientation)

                # Set transformed position
                goal_msg.pose.pose.position.x = float(position.get('x', 0.0))
                goal_msg.pose.pose.position.y = float(position.get('y', 0.0))
                goal_msg.pose.pose.position.z = float(position.get('z', 0.0))

                # Set transformed orientation
                goal_msg.pose.pose.orientation.x = float(orientation.get('x', 0.0))
                goal_msg.pose.pose.orientation.y = float(orientation.get('y', 0.0))
                goal_msg.pose.pose.orientation.z = float(orientation.get('z', 0.0))
                goal_msg.pose.pose.orientation.w = float(orientation.get('w', 1.0))

            # Send goal to action server
            future = self.nav_client.send_goal_async(goal_msg)
            self.get_logger().info(f'Sent navigation goal to action server: position=({goal_msg.pose.pose.position.x}, {goal_msg.pose.pose.position.y})')

        except json.JSONDecodeError as e:
            self.get_logger().error(f'Invalid JSON: {str(e)}')
        except Exception as e:
            self.get_logger().error(f'Error sending navigation goal: {str(e)}')

    def handle_goal_pose(self, payload):
        """Convert JSON to PoseStamped and publish to ROS"""
        try:
            data = json.loads(payload)

            msg = PoseStamped()

            # Header
            if 'header' in data:
                if 'frame_id' in data['header']:
                    msg.header.frame_id = data['header']['frame_id']
                if 'stamp' in data['header']:
                    msg.header.stamp.sec = data['header']['stamp'].get('sec', 0)
                    msg.header.stamp.nanosec = data['header']['stamp'].get('nanosec', 0)

            # Pose
            if 'pose' in data:
                pose = data['pose']
                if 'position' in pose:
                    position = pose['position']
                    orientation = pose.get('orientation', {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0})

                    # Apply coordinate transformation for fallback path too
                    position, orientation = self.transform_pose(position, orientation)

                    msg.pose.position.x = float(position.get('x', 0.0))
                    msg.pose.position.y = float(position.get('y', 0.0))
                    msg.pose.position.z = float(position.get('z', 0.0))

                    # Use transformed orientation
                    msg.pose.orientation.x = float(orientation.get('x', 0.0))
                    msg.pose.orientation.y = float(orientation.get('y', 0.0))
                    msg.pose.orientation.z = float(orientation.get('z', 0.0))
                    msg.pose.orientation.w = float(orientation.get('w', 1.0))
                elif 'orientation' in pose:
                    # If only orientation without position, still transform it
                    orientation = pose.get('orientation', {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0})
                    position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
                    position, orientation = self.transform_pose(position, orientation)

                    msg.pose.orientation.x = float(orientation.get('x', 0.0))
                    msg.pose.orientation.y = float(orientation.get('y', 0.0))
                    msg.pose.orientation.z = float(orientation.get('z', 0.0))
                    msg.pose.orientation.w = float(orientation.get('w', 1.0))

            # Publish to ROS
            self.goal_pose_pub.publish(msg)
            self.get_logger().info(f'Published goal_pose to ROS: position=({msg.pose.position.x}, {msg.pose.position.y})')

        except json.JSONDecodeError as e:
            self.get_logger().error(f'Invalid JSON: {str(e)}')
        except Exception as e:
            self.get_logger().error(f'Error converting message: {str(e)}')


def main(args=None):
    rclpy.init(args=args)
    bridge = MqttToRosBridge()

    try:
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.mqtt_client.loop_stop()
        bridge.mqtt_client.disconnect()
        bridge.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
