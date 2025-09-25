# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading

from scene_common import log
from scene_common.mqtt import PubSub

class AnalyticsContext:
  topics_to_subscribe = []

  def __init__(self, broker, broker_auth, cert, root_cert, rest_url, rest_auth):
    # Subscribe to data regulation topic for scene updates
    data_regulated_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id="+")
    self.topics_to_subscribe.append((data_regulated_topic, self.updateScenes))

    self.register_thread_lock = threading.Lock()
    self.current_processing_scene = None
    self.rest_url = rest_url
    self.rest_auth = rest_auth

    # Analytics-specific data storage
    self.scene_analytics = {}  # Store analytics data per scene
    self.detection_stats = {}  # Store detection statistics

    try:
      self.client = PubSub(broker_auth, cert, root_cert, broker, keepalive=240)
      self.client.onConnect = self.mqttOnConnect
      log.info(f"Attempting to connect to broker: {broker}")
      self.client.connect()
    except Exception as e:
      log.error(f"Failed to connect to MQTT broker {broker}: {e}")
      log.info("Analytics service will continue without MQTT connectivity")
      self.client = None

    return

  def mqttOnConnect(self, client, userdata, flags, rc):
    """! Subscribes to a list of topics on MQTT.
    @param   client    Client instance for this callback.
    @param   userdata  Private user data as set in Client.
    @param   flags     Response flags sent by the broker.
    @param   rc        Connection result.

    @return  None
    """
    for topic, callback in self.topics_to_subscribe:
      log.info("Subscribing to " + topic)
      self.client.addCallback(topic, callback)
      log.info("Subscribed " + topic)
    return

  def updateScenes(self, client, userdata, message):
    """! MQTT callback function used to process analytics data from scenes and object detections.
    This function handles incoming data about scenes and detected objects for analytics processing.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    try:
      # Parse the detection data directly from MQTT message
      detection_data = json.loads(message.payload.decode("utf-8"))
      topic = PubSub.parseTopic(message.topic)
      scene_id = topic.get('scene_id', 'unknown')
      
      log.info(f"Received detection data for scene {scene_id}: {len(detection_data.get('objects', []))} objects")
      
      # Aggregate detection data per scene and frame
      self.aggregateDetectionData(scene_id, detection_data)

    except json.JSONDecodeError as e:
      log.error(f"Failed to parse detection data: {e}")
    except Exception as e:
      log.error(f"Error processing detection data: {e}")
    return

  def aggregateDetectionData(self, scene_id, detection_data):
    """! Aggregate raw detection data per scene and frame
    @param   scene_id        Scene identifier
    @param   detection_data  Raw detection data from MQTT message

    @return  None
    """
    # Initialize scene data structure if not exists
    if scene_id not in self.scene_analytics:
      self.scene_analytics[scene_id] = {
        'scene_name': detection_data.get('name', 'Unknown'),
        'frames': []
      }

    # Count objects by category
    scene_name = detection_data.get('name', 'Unknown')
    objects = detection_data.get('objects', [])

    # Count objects by category
    category_counts = {}
    for obj in objects:
      category = obj.get('category', 'unknown')
      if category not in category_counts:
        category_counts[category] = 0
      category_counts[category] += 1

    # Log category counts for this scene
    log.info(f"Scene '{scene_name}' ({scene_id}): {category_counts}")

    # Simply store the raw frame data
    self.scene_analytics[scene_id]['frames'].append(detection_data)

    # Keep only recent frames (last 1000 frames to prevent memory issues)
    if len(self.scene_analytics[scene_id]['frames']) > 1000:
      self.scene_analytics[scene_id]['frames'] = self.scene_analytics[scene_id]['frames'][-1000:]

    return

  def getRawData(self, scene_id=None):
    """! Get raw aggregated data for a specific scene or all scenes
    @param   scene_id    Optional scene identifier, if None returns all scenes

    @return  Raw aggregated data
    """
    if scene_id:
      return self.scene_analytics.get(scene_id, {'error': f'No data found for scene {scene_id}'})
    else:
      return self.scene_analytics

  def getRecentFrames(self, scene_id, frame_count=10):
    """! Get recent raw frames for a scene
    @param   scene_id     Scene identifier
    @param   frame_count  Number of recent frames to return

    @return  Recent frame data
    """
    if scene_id not in self.scene_analytics:
      return {'error': f'No data found for scene {scene_id}'}

    recent_frames = self.scene_analytics[scene_id]['frames'][-frame_count:]
    return {
      'scene_name': self.scene_analytics[scene_id]['scene_name'],
      'frames': recent_frames
    }

  def loopForever(self):
    if self.client:
      log.info("Starting MQTT client loop")
      return self.client.loopForever()
    else:
      log.info("No MQTT client available - analytics service running in offline mode")
      # Keep the process alive without MQTT
      import time
      try:
        while True:
          time.sleep(60)
          log.info("Analytics service heartbeat - running without MQTT")
      except KeyboardInterrupt:
        log.info("Analytics service shutting down")
        return
