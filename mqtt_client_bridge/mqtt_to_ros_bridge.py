#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Simple MQTT to ROS bridge that converts JSON messages to ROS messages.
Subscribes to MQTT topics and publishes to corresponding ROS topics.
"""

import json
import ssl
import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry


class MqttToRosBridge(Node):
    def __init__(self):
        super().__init__('mqtt_to_ros_bridge')
        
        # ROS Publishers
        self.goal_pose_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)
        
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
                self.handle_goal_pose(payload)
            else:
                self.get_logger().warn(f'Unknown topic: {topic}')
                
        except Exception as e:
            self.get_logger().error(f'Error processing MQTT message: {str(e)}')
            
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
