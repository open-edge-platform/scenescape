# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import numpy as np
from sklearn.cluster import DBSCAN

from scene_common import log
from scene_common.mqtt import PubSub

class AnalyticsContext:
  topics_to_subscribe = []

  # Clustering configuration
  DBSCAN_EPS = 3  # Maximum distance between two objects to be considered in same cluster (meters)
  DBSCAN_MIN_SAMPLES = 2  # Minimum number of objects required to form a cluster

  def __init__(self, broker, broker_auth, cert, root_cert, rest_url, rest_auth):
    # Subscribe to data regulation topic for scene updates
    data_regulated_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id="+")
    self.topics_to_subscribe.append((data_regulated_topic, self.updateScenes))

    self.register_thread_lock = threading.Lock()
    self.current_processing_scene = None
    self.rest_url = rest_url
    self.rest_auth = rest_auth

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
    """! Process detection data and perform clustering analysis
    @param   scene_id        Scene identifier
    @param   detection_data  Raw detection data from MQTT message

    @return  None
    """
    # Store current scene metadata
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

    # Perform clustering analysis on objects
    self.analyzeObjectClusters(scene_id, detection_data)

    return

  def analyzeObjectClusters(self, scene_id, detection_data):
    """! Analyze object clusters using DBSCAN algorithm and publish results to MQTT
    @param   scene_id        Scene identifier
    @param   detection_data  Detection data containing objects with coordinates

    @return  None
    """
    objects = detection_data.get('objects', [])

    if len(objects) < self.DBSCAN_MIN_SAMPLES:
      return  # Not enough objects to form clusters

    # Group objects by category
    objects_by_category = {}
    for obj in objects:
      category = obj.get('category', 'unknown')
      if category not in objects_by_category:
        objects_by_category[category] = []
      objects_by_category[category].append(obj)

    # Analyze clusters for each category with multiple objects
    for category, category_objects in objects_by_category.items():
      if len(category_objects) < self.DBSCAN_MIN_SAMPLES:
        continue  # Skip categories with too few objects

      # Extract x,y coordinates for clustering from translation field
      coordinates = []
      for obj in category_objects:
        # Use translation field which contains world coordinates [x, y, z]
        translation = obj.get('translation', [0, 0, 0])
        if len(translation) >= 2:
          x = translation[0]  # World X coordinate
          y = translation[1]  # World Y coordinate
          coordinates.append([x, y])
        else:
          # Fallback to other coordinate fields if translation is not available
          x = obj.get('x', obj.get('center_x', obj.get('cx', 0)))
          y = obj.get('y', obj.get('center_y', obj.get('cy', 0)))
          coordinates.append([x, y])

      if len(coordinates) < self.DBSCAN_MIN_SAMPLES:
        continue

      # Apply DBSCAN clustering
      coordinates_array = np.array(coordinates)
      clustering = DBSCAN(eps=self.DBSCAN_EPS, min_samples=self.DBSCAN_MIN_SAMPLES).fit(coordinates_array)
      # Analyze cluster results
      labels = clustering.labels_
      unique_labels = set(labels)
      n_clusters = len(unique_labels) - (1 if -1 in labels else 0)  # Exclude noise points (-1)
      n_noise = list(labels).count(-1)

      if n_clusters > 0:
        log.info(f"Scene {scene_id}: Found {n_clusters} clusters for category '{category}' ({len(category_objects)} objects, {n_noise} noise points)")

        # Create cluster metadata
        cluster_metadata = {
          'scene_id': scene_id,
          'scene_name': detection_data.get('name', 'Unknown'),
          'timestamp': detection_data.get('timestamp'),
          'category': category,
          'total_objects': len(category_objects),
          'clusters': n_clusters,
          'noise_points': n_noise,
          'dbscan_params': {
            'eps': self.DBSCAN_EPS,
            'min_samples': self.DBSCAN_MIN_SAMPLES
          }
        }

        # Publish cluster metadata to MQTT
        self.publishClusterMetadata(scene_id, cluster_metadata)

  def publishClusterMetadata(self, scene_id, cluster_metadata):
    """! Publish cluster metadata to ANALYTICS_CLUSTERS MQTT topic
    @param   scene_id         Scene identifier
    @param   cluster_metadata Dictionary containing cluster information

    @return  None
    """
    if self.client is None or not self.client.isConnected():
      log.warning(f"Cannot publish cluster metadata for scene {scene_id}: MQTT client not connected")
      return

    try:
      topic = PubSub.formatTopic(PubSub.ANALYTICS_CLUSTERS, scene_id=scene_id)
      payload = json.dumps(cluster_metadata)

      result = self.client.publish(topic, payload, qos=1)
      if result.rc == 0:
        log.info(f"Published cluster metadata for scene {scene_id} category '{cluster_metadata['category']}' to {topic}")
      else:
        log.error(f"Failed to publish cluster metadata for scene {scene_id}: MQTT publish failed with rc={result.rc}")

    except Exception as e:
      log.error(f"Error publishing cluster metadata for scene {scene_id}: {e}")

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
