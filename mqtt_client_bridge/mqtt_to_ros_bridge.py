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
import ssl
import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose


class MqttToRosBridge(Node):
    def __init__(self):
        super().__init__('mqtt_to_ros_bridge')
        
        # ROS Publishers
        self.goal_pose_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)
        
        # ROS Action Clients - use environment variable for action prefix
        nav_prefix = os.getenv('NAV2_ACTION_PREFIX', '')
        action_name = f'{nav_prefix}navigate_to_pose' if nav_prefix else 'navigate_to_pose'
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
            
            # Set pose
            if 'pose' in data:
                pose = data['pose']
                if 'position' in pose:
                    goal_msg.pose.pose.position.x = float(pose['position'].get('x', 0.0))
                    goal_msg.pose.pose.position.y = float(pose['position'].get('y', 0.0))
                    goal_msg.pose.pose.position.z = float(pose['position'].get('z', 0.0))
                if 'orientation' in pose:
                    goal_msg.pose.pose.orientation.x = float(pose['orientation'].get('x', 0.0))
                    goal_msg.pose.pose.orientation.y = float(pose['orientation'].get('y', 0.0))
                    goal_msg.pose.pose.orientation.z = float(pose['orientation'].get('z', 0.0))
                    goal_msg.pose.pose.orientation.w = float(pose['orientation'].get('w', 1.0))
            
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
                    msg.pose.position.x = float(pose['position'].get('x', 0.0))
                    msg.pose.position.y = float(pose['position'].get('y', 0.0))
                    msg.pose.position.z = float(pose['position'].get('z', 0.0))
                if 'orientation' in pose:
                    msg.pose.orientation.x = float(pose['orientation'].get('x', 0.0))
                    msg.pose.orientation.y = float(pose['orientation'].get('y', 0.0))
                    msg.pose.orientation.z = float(pose['orientation'].get('z', 0.0))
                    msg.pose.orientation.w = float(pose['orientation'].get('w', 1.0))
            
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
