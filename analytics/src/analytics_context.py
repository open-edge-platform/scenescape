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
      command = str(message.payload.decode("utf-8"))
      log.info(f"Received command: {command} on topic: {message.topic}")
      
      if command == "update":
        topic = PubSub.parseTopic(message.topic)
        scene_id = topic.get('scene_id', 'unknown')
        
        # Collect analytics data about scenes and detected objects
        log.info(f"Processing analytics data for scene {scene_id}")
        self.processSceneAnalytics(scene_id, command)
      elif command == "detection_data":
        # Handle object detection data
        topic = PubSub.parseTopic(message.topic)
        scene_id = topic.get('scene_id', 'unknown')
        log.info(f"Processing object detection data for scene {scene_id}")
        self.processDetectionData(scene_id, message)
    except Exception as e:
      log.error(f"Error in updateScenes: {e}")
    return

  def processSceneAnalytics(self, scene_id, command):
    """! Process analytics data for a scene
    @param   scene_id    Scene identifier
    @param   command     Command received

    @return  None
    """
    log.info(f"Collecting analytics data for scene {scene_id} - command: {command}")
    # TODO: Implement scene analytics data collection
    # This could include:
    # - Scene metadata collection
    # - Performance metrics
    # - Usage statistics
    return

  def processDetectionData(self, scene_id, message):
    """! Process object detection data for analytics
    @param   scene_id    Scene identifier  
    @param   message     MQTT message with detection data

    @return  None
    """
    try:
      # Extract detection data from message payload
      detection_payload = json.loads(message.payload.decode("utf-8"))
      log.info(f"Processing detection data for scene {scene_id}: {len(detection_payload.get('objects', []))} objects detected")
      
      # TODO: Implement object detection analytics
      # This could include:
      # - Object counting and classification
      # - Tracking patterns
      # - Density analysis
      # - Performance metrics
      
    except json.JSONDecodeError as e:
      log.error(f"Failed to parse detection data for scene {scene_id}: {e}")
    except Exception as e:
      log.error(f"Error processing detection data for scene {scene_id}: {e}")
    except Exception as e:
      log.error(f"Error in updateScenes: {e}")
    return

  def getAnalyticsSummary(self, scene_id=None):
    """! Get analytics summary for a specific scene or all scenes
    @param   scene_id    Optional scene identifier, if None returns all scenes

    @return  Analytics summary data
    """
    if scene_id:
      return {
        'scene_analytics': self.scene_analytics.get(scene_id, {}),
        'detection_stats': self.detection_stats.get(scene_id, {})
      }
    else:
      return {
        'scene_analytics': self.scene_analytics,
        'detection_stats': self.detection_stats
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
