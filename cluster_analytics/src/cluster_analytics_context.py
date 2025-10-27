# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import threading
import time
import numpy as np
from collections import Counter, defaultdict
from sklearn.cluster import DBSCAN

from scene_common import log
from scene_common.mqtt import PubSub

class ClusterAnalyticsConfig:
  """Configuration settings for cluster analytics loaded from config.json"""

  def __init__(self, config_path=None):
    """Load configuration from JSON file
    @param config_path  Path to config.json file (optional, auto-detected if not provided)
    """
    if config_path is None:
      # Auto-detect config path relative to this file
      current_dir = os.path.dirname(os.path.abspath(__file__))
      # Try container path first (/app/config/config.json), then fallback to dev path
      config_path = os.path.join(current_dir, 'config', 'config.json')
      if not os.path.exists(config_path):
        config_path = os.path.join(current_dir, '..', 'config', 'config.json')

    # Load configuration from JSON file
    try:
      with open(config_path, 'r') as f:
        config_data = json.load(f)
      log.info(f"Loaded configuration from {config_path}")
    except FileNotFoundError:
      log.error(f"Configuration file not found: {config_path}")
      raise
    except json.JSONDecodeError as e:
      log.error(f"Failed to parse configuration file: {e}")
      raise

    # Load DBSCAN parameters
    dbscan_config = config_data.get('dbscan', {})
    default_params = dbscan_config.get('default', {})
    self.DEFAULT_DBSCAN_EPS = default_params.get('eps', 1)
    self.DEFAULT_DBSCAN_MIN_SAMPLES = default_params.get('min_samples', 3)
    self.CATEGORY_DBSCAN_PARAMS = dbscan_config.get('category_specific', {})

    # Load shape detection thresholds
    shape_config = config_data.get('shape_detection', {})
    self.SHAPE_VARIANCE_THRESHOLD = shape_config.get('variance_threshold', 0.5)
    self.QUADRANT_ANGLE = shape_config.get('quadrant_angle', np.pi / 2)
    self.ANGLE_DISTRIBUTION_THRESHOLD = shape_config.get('angle_distribution_threshold', 0.5)
    self.LINEAR_FORMATION_AREA_THRESHOLD = shape_config.get('linear_formation_area_threshold', 0.5)

    # Load movement analysis thresholds
    movement_config = config_data.get('movement_analysis', {})
    self.ALIGNMENT_THRESHOLD = movement_config.get('alignment_threshold', 0.5)
    self.CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD = movement_config.get('convergence_divergence_ratio_threshold', 0.6)

    # Load velocity analysis thresholds
    velocity_config = config_data.get('velocity_analysis', {})
    self.STATIONARY_THRESHOLD = velocity_config.get('stationary_threshold', 0.1)
    self.VELOCITY_COHERENCE_THRESHOLD = velocity_config.get('velocity_coherence_threshold', 0.3)

class ClusterAnalyticsContext:
  def __init__(self, broker, broker_auth, cert, root_cert, enable_webui=True, webui_port=5000, webui_certfile=None, webui_keyfile=None):
    self.config = ClusterAnalyticsConfig()
    self.webui_port = webui_port
    self.webui_certfile = webui_certfile
    self.webui_keyfile = webui_keyfile

    self.user_dbscan_params_by_scene = {}

    # Initialize WebUI if enabled
    self.webUi = None
    if enable_webui:
      try:
        # Import WebUI from tools/webui directory
        import sys
        import os
        # Get the directory where cluster_analytics_context.py is located (/app in container, or src/ in dev)
        currentDir = os.path.dirname(os.path.abspath(__file__))
        # In container: /app -> /app/tools/webui
        # In dev: src/ -> ../tools/webui
        webuiPath = os.path.join(currentDir, 'tools', 'webui')
        if not os.path.exists(webuiPath):
          # Fallback for development environment where webui is at ../tools/webui
          webuiPath = os.path.join(currentDir, '..', 'tools', 'webui')
        webuiPath = os.path.abspath(webuiPath)
        sys.path.insert(0, webuiPath)
        from web_ui import WebUI
        self.webUi = WebUI(self)
        log.info("WebUI initialized successfully")
      except ImportError as e:
        log.warn(f"WebUI dependencies not available: {e}")
        log.info("Cluster Analytics service will continue without WebUI")
      except Exception as e:
        log.error(f"Failed to initialize WebUI: {e}")
        log.info("Cluster Analytics service will continue without WebUI")
    else:
      log.info("WebUI disabled via command line argument")

    try:
      self.client = PubSub(broker_auth, cert, root_cert, broker, keepalive=240)
      self.client.onConnect = self.mqttOnConnect
      log.info(f"Attempting to connect to broker: {broker}")
      self.client.connect()
    except Exception as e:
      log.error(f"Failed to connect to MQTT broker {broker}: {e}")
      log.info("Cluster Analytics service will continue without MQTT connectivity")
      self.client = None

    return

  def getDbscanParamsForCategory(self, category, scene_id=None):
    """! Get DBSCAN parameters optimized for a specific object category in a specific scene
    @param   category  Object category (person, vehicle, bicycle, etc.)
    @param   scene_id  Scene identifier (optional, for scene-specific parameters)
    @return  Dictionary with 'eps' and 'min_samples' parameters
    """
    # Normalize category to lowercase for consistent lookup
    category_lower = category.lower()

    # Check scene-specific user-configured parameters first
    if scene_id:
      scene_params = self.user_dbscan_params_by_scene.get(scene_id)
      if scene_params:
        params = scene_params.get(category_lower)
        if params:
          log.info(f"Using scene-specific user-configured DBSCAN parameters for '{category}' in scene '{scene_id}': eps={params['eps']}, min_samples={params['min_samples']}")
          return params

    # Return category-specific default parameters if available
    params = self.config.CATEGORY_DBSCAN_PARAMS.get(category_lower)
    if params:
      log.info(f"Using default DBSCAN parameters for '{category}': eps={params['eps']}, min_samples={params['min_samples']}")
      return params

    default_params = {
      'eps': self.config.DEFAULT_DBSCAN_EPS,
      'min_samples': self.config.DEFAULT_DBSCAN_MIN_SAMPLES
    }
    log.info(f"Using global default DBSCAN parameters for unknown category '{category}': eps={default_params['eps']}, min_samples={default_params['min_samples']}")
    return default_params

  def setUserDbscanParamsForCategory(self, category, eps, min_samples, scene_id=None):
    """! Set user-configured DBSCAN parameters for a specific object category in a specific scene
    @param   category     Object category (person, vehicle, bicycle, etc.)
    @param   eps          DBSCAN eps parameter
    @param   min_samples  DBSCAN min_samples parameter
    @param   scene_id     Scene identifier (optional, for scene-specific parameters)
    @return  None
    """
    # Normalize category to lowercase for consistent lookup
    category_lower = category.lower()

    # Store scene-specific user configuration
    if scene_id:
      # Initialize scene parameters if not exists
      if scene_id not in self.user_dbscan_params_by_scene:
        self.user_dbscan_params_by_scene[scene_id] = {}

      # Store parameters for this scene and category
      self.user_dbscan_params_by_scene[scene_id][category_lower] = {
        'eps': float(eps),
        'min_samples': int(min_samples)
      }

      log.info(f"Set scene-specific user-configured DBSCAN parameters for '{category}' in scene '{scene_id}': eps={eps}, min_samples={min_samples}")
    else:
      log.warning(f"Cannot set DBSCAN parameters for '{category}': no scene_id provided")

  def getDefaultDbscanParamsForCategory(self, category):
    """! Get the default (hardcoded) DBSCAN parameters for a category
    @param   category  Object category (person, vehicle, bicycle, etc.)
    @return  Dictionary with 'eps' and 'min_samples' default parameters
    """
    # Normalize category to lowercase for consistent lookup
    category_lower = category.lower()

    if category_lower in self.config.CATEGORY_DBSCAN_PARAMS:
      return self.config.CATEGORY_DBSCAN_PARAMS[category_lower].copy()
    else:
      return {
        'eps': self.config.DEFAULT_DBSCAN_EPS,
        'min_samples': self.config.DEFAULT_DBSCAN_MIN_SAMPLES
      }

  def resetUserDbscanParamsForCategory(self, category, scene_id=None):
    """! Reset user-configured parameters for a category in a specific scene back to defaults
    @param   category  Object category (person, vehicle, bicycle, etc.)
    @param   scene_id  Scene identifier (optional, for scene-specific parameters)
    @return  None
    """
    # Normalize category to lowercase for consistent lookup
    category_lower = category.lower()

    # Remove scene-specific user configuration for this category
    if scene_id and scene_id in self.user_dbscan_params_by_scene:
      scene_params = self.user_dbscan_params_by_scene[scene_id]
      if category_lower in scene_params:
        del scene_params[category_lower]
        log.info(f"Reset DBSCAN parameters for '{category}' in scene '{scene_id}' back to defaults")

        # Clean up empty scene entries
        if not scene_params:
          del self.user_dbscan_params_by_scene[scene_id]
      else:
        log.info(f"No custom DBSCAN parameters found for '{category}' in scene '{scene_id}' to reset")
    else:
      log.warning(f"Cannot reset DBSCAN parameters for '{category}': scene '{scene_id}' not found or no scene_id provided")

  def mqttOnConnect(self, client, userdata, flags, rc):
    """! Subscribes to MQTT topics on connection.
    @param   client    Client instance for this callback.
    @param   userdata  Private user data as set in Client.
    @param   flags     Response flags sent by the broker.
    @param   rc        Connection result.

    @return  None
    """
    data_regulated_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id="+")
    log.info("Subscribing to " + data_regulated_topic)
    self.client.addCallback(data_regulated_topic, self.processSceneAnalytics)
    log.info("Subscribed " + data_regulated_topic)
    return

  def processSceneAnalytics(self, client, userdata, message):
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

      all_clusters = self.analyzeObjectClusters(scene_id, detection_data)
      self.publishAllClusters(scene_id, detection_data, all_clusters)

    except json.JSONDecodeError as e:
      log.error(f"Failed to parse detection data: {e}")
    except Exception as e:
      log.error(f"Error processing detection data: {e}")
    return

  def extractCoordinatesFromObjects(self, objects):
    """! Extract x,y coordinates from object detection data for clustering
    @param   objects  List of object detection data
    @return  List of [x, y] coordinate pairs
    """
    coordinates = []
    for obj in objects:
      # Use translation field which contains world coordinates [x, y, z]
      translation = obj.get('translation', [0, 0, 0])
      if len(translation) >= 2:
        coordinates.append(translation[:2])
      else:
        # Fallback to other coordinate fields if translation is not available
        x = obj.get('x', obj.get('center_x', obj.get('cx', 0)))
        y = obj.get('y', obj.get('center_y', obj.get('cy', 0)))
        coordinates.append([x, y])
    return coordinates

  def analyzeObjectClusters(self, scene_id, detection_data):
    """! Analyze object clusters using DBSCAN algorithm
    @param   scene_id        Scene identifier
    @param   detection_data  Detection data containing objects with coordinates

    @return  List of cluster metadata dictionaries
    """
    # Extract scene metadata for logging
    scene_name = detection_data.get('name', 'Unknown')
    objects = detection_data.get('objects', [])

    # Log object categories for monitoring
    category_counts = Counter(obj.get('category', 'unknown') for obj in objects)
    log.info(f"Scene '{scene_name}' ({scene_id}): {category_counts}")

    # Collect all clusters for this scene to publish them together
    all_clusters = []

    # Group objects by category first
    objects_by_category = defaultdict(list)
    for obj in objects:
      category = obj.get('category', 'unknown')
      objects_by_category[category].append(obj)

    # Get the minimum min_samples requirement across all categories that have objects
    min_samples_list = [
      self.getDbscanParamsForCategory(category, scene_id)['min_samples']
      for category in objects_by_category
    ]
    min_required_objects = min(min_samples_list, default=self.config.DEFAULT_DBSCAN_MIN_SAMPLES)

    if len(objects) < min_required_objects:
      log.info(f"Scene {scene_id}: Insufficient objects ({len(objects)}) for clustering (minimum {min_required_objects} required based on user parameters)")
      return all_clusters

    for category, category_objects in objects_by_category.items():
      dbscan_params = self.getDbscanParamsForCategory(category, scene_id)

      if len(category_objects) < dbscan_params['min_samples']:
        continue

      coordinates = self.extractCoordinatesFromObjects(category_objects)
      coordinates_array = np.array(coordinates)

      clustering = DBSCAN(eps=dbscan_params['eps'], min_samples=dbscan_params['min_samples']).fit(coordinates_array)
      labels = clustering.labels_
      n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
      n_noise = np.sum(labels == -1)

      if n_clusters > 0:
        log.info(f"Scene {scene_id}: Found {n_clusters} clusters for category '{category}' ({len(category_objects)} objects, {n_noise} noise points)")

        for cluster_id in set(labels) - {-1}:
          cluster_objects = []
          cluster_coordinates = []
          for i, label in enumerate(labels):
            if label == cluster_id:
              cluster_objects.append(category_objects[i])
              cluster_coordinates.append(coordinates[i])

          cluster_coordinates_array = np.array(cluster_coordinates)
          _, cluster_center = self.extractPointFeatures(cluster_coordinates_array)

          shape_analysis = self.detectShapeMl(cluster_coordinates)
          velocity_analysis = self.analyzeClusterVelocity(cluster_objects, cluster_center)

          cluster_metadata = {
            'cluster_id': str(cluster_id),
            'category': category,
            'objects_in_cluster': len(cluster_objects),
            'cluster_center': {
              'x': float(cluster_center[0]),
              'y': float(cluster_center[1])
            },
            'shape_analysis': shape_analysis,
            'velocity_analysis': velocity_analysis,
            'object_ids': [obj.get('id', 'unknown') for obj in cluster_objects],
            'dbscan_params': {
              'eps': dbscan_params['eps'],
              'min_samples': dbscan_params['min_samples'],
              'category': category
            }
          }

          log.debug(f"Detailed cluster metadata: {json.dumps(cluster_metadata, indent=2)}")
          all_clusters.append(cluster_metadata)

    return all_clusters

  def publishAllClusters(self, scene_id, detection_data, all_clusters):
    """! Publish all clusters for a scene at once to ANALYTICS_CLUSTERS MQTT topic
    @param   scene_id        Scene identifier
    @param   detection_data  Original detection data containing scene metadata
    @param   all_clusters    List of all cluster metadata dictionaries for the scene

    @return  None
    """
    if self.client is None or not self.client.isConnected():
      log.warning(f"Cannot publish cluster data for scene {scene_id}: MQTT client not connected")
      return

    try:
      # Create aggregated cluster data structure
      cluster_batch_data = {
        'scene_id': scene_id,
        'scene_name': detection_data.get('name', 'Unknown'),
        'timestamp': detection_data.get('timestamp'),
        'total_clusters': len(all_clusters),
        'clusters': all_clusters,
        'summary': {
          'categories': list(set(cluster['category'] for cluster in all_clusters)) if all_clusters else [],
          'total_objects_in_clusters': sum(cluster['objects_in_cluster'] for cluster in all_clusters) if all_clusters else 0
        }
      }

      topic = PubSub.formatTopic(PubSub.ANALYTICS_CLUSTERS, scene_id=scene_id)
      payload = json.dumps(cluster_batch_data)

      result = self.client.publish(topic, payload, qos=1)
      if result.rc == 0:
        if len(all_clusters) > 0:
          log.info(f"Published batch of {len(all_clusters)} clusters for scene {scene_id} containing {cluster_batch_data['summary']['total_objects_in_clusters']} objects")
        else:
          log.info(f"Published empty cluster batch for scene {scene_id} (no clusters detected with current parameters)")
      else:
        log.error(f"Failed to publish cluster batch for scene {scene_id}: MQTT publish failed with rc={result.rc}")

    except Exception as e:
      log.error(f"Error publishing cluster batch for scene {scene_id}: {e}")

  def _publishClusterMetadata(self, scene_id, cluster_metadata):
    """! Legacy method for publishing individual cluster metadata to ANALYTICS_CLUSTERS MQTT topic
    This method is kept for backward compatibility but is no longer used in the main flow.
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
        log.info(f"Published cluster {cluster_metadata['cluster_id']} metadata for scene {scene_id} category '{cluster_metadata['category']}'")
      else:
        log.error(f"Failed to publish cluster metadata for scene {scene_id}: MQTT publish failed with rc={result.rc}")

    except Exception as e:
      log.error(f"Error publishing cluster metadata for scene {scene_id}: {e}")

  def extractPointFeatures(self, points):
    """! Extract distance and angle features from cluster points relative to centroid
    @param   points  Array of coordinate points in the cluster

    @return  Tuple of (features array, centroid array)
    """
    features = []
    centroid = np.mean(points, axis=0)

    for point in points:
      # Distance to centroid
      dist_to_center = np.linalg.norm(point - centroid)

      # Angle from centroid
      angle = np.arctan2(point[1] - centroid[1], point[0] - centroid[0])

      features.append([dist_to_center, angle])

    return np.array(features), centroid

  def _getCircleShape(self, radius):
    """! Create circle shape metadata
    @param   radius  Circle radius
    @return  Dictionary with circle shape and size data
    """
    diameter = radius * 2
    area = np.pi * radius ** 2
    return {
      "shape": "circle",
      "size": {
        "radius": float(radius),
        "diameter": float(diameter),
        "area": float(area),
        "circumference": float(2 * np.pi * radius)
      }
    }

  def _getRectangleShape(self, points_array):
    """! Create rectangle shape metadata
    @param   points_array  Array of coordinate points
    @return  Dictionary with rectangle shape and size data
    """
    x_coords = points_array[:, 0]
    y_coords = points_array[:, 1]

    width = np.max(x_coords) - np.min(x_coords)
    height = np.max(y_coords) - np.min(y_coords)
    area = width * height
    perimeter = 2 * (width + height)

    corners = [
      [np.min(x_coords), np.min(y_coords)],
      [np.max(x_coords), np.min(y_coords)],
      [np.max(x_coords), np.max(y_coords)],
      [np.min(x_coords), np.max(y_coords)]
    ]

    return {
      "shape": "rectangle",
      "size": {
        "width": float(width),
        "height": float(height),
        "area": float(area),
        "perimeter": float(perimeter),
        "corner_points": [[float(x), float(y)] for x, y in corners]
      }
    }

  def _getIrregularShape(self, points_array, distances):
    """! Create irregular shape metadata
    @param   points_array  Array of coordinate points
    @param   distances     Array of distances from centroid
    @return  Dictionary with irregular shape and size data
    """
    x_coords = points_array[:, 0]
    y_coords = points_array[:, 1]

    width = np.max(x_coords) - np.min(x_coords)
    height = np.max(y_coords) - np.min(y_coords)
    bounding_area = width * height

    return {
      "shape": "irregular",
      "size": {
        "bounding_width": float(width),
        "bounding_height": float(height),
        "bounding_area": float(bounding_area),
        "point_spread": float(np.std(distances))
      }
    }

  def _getLineShape(self, points_array):
    """! Create line shape metadata
    @param   points_array  Array of coordinate points
    @return  Dictionary with line shape and size data
    """
    x_coords = points_array[:, 0]
    y_coords = points_array[:, 1]

    distances_matrix = np.zeros((len(points_array), len(points_array)))
    for i in range(len(points_array)):
      for j in range(len(points_array)):
        distances_matrix[i, j] = np.linalg.norm(points_array[i] - points_array[j])

    max_dist_idx = np.unravel_index(np.argmax(distances_matrix), distances_matrix.shape)
    endpoint1 = points_array[max_dist_idx[0]]
    endpoint2 = points_array[max_dist_idx[1]]
    line_length = distances_matrix[max_dist_idx[0], max_dist_idx[1]]

    return {
      "shape": "line",
      "size": {
        "length": float(line_length),
        "endpoints": [[float(endpoint1[0]), float(endpoint1[1])],
                     [float(endpoint2[0]), float(endpoint2[1])]],
        "width_spread": float(np.std([np.min(y_coords), np.max(y_coords)]))
      }
    }

  def detectShapeMl(self, points):
    """! Detect the geometric shape formed by a cluster of points using ML techniques
    @param   points  Array of coordinate points in the cluster

    @return  Dictionary with shape type and size measurements
    """
    if len(points) < 3:
      return {
        "shape": "insufficient_points",
        "size": {}
      }

    points_array = np.array(points)

    features, _ = self.extractPointFeatures(points_array)

    dist_variance = np.var(features[:, 0])
    distances = features[:, 0]
    angles = features[:, 1]

    if dist_variance < self.config.SHAPE_VARIANCE_THRESHOLD:
      return self._getCircleShape(np.mean(distances))

    elif len(points_array) == 4:
      angle_groups = len(np.unique(np.round(features[:, 1] / self.config.QUADRANT_ANGLE)))
      if angle_groups >= 3:
        return self._getRectangleShape(points_array)

    elif len(points_array) >= 5:
      angle_diffs = np.diff(np.sort(angles))
      if np.std(angle_diffs) < self.config.ANGLE_DISTRIBUTION_THRESHOLD:
        return self._getCircleShape(np.mean(distances))
      else:
        return self._getIrregularShape(points_array, distances)

    if len(points_array) >= 3:
      areas = []
      for i in range(len(points_array) - 2):
        p1, p2, p3 = points_array[i], points_array[i+1], points_array[i+2]
        area = abs((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1])) / 2
        areas.append(area)

      if np.mean(areas) < self.config.LINEAR_FORMATION_AREA_THRESHOLD:
        return self._getLineShape(points_array)

    return self._getIrregularShape(points_array, distances)

  def analyzeClusterVelocity(self, cluster_objects, cluster_center):
    """! Analyze velocity patterns and movement characteristics of a cluster
    @param   cluster_objects  List of objects in the cluster
    @param   cluster_center   Centroid coordinates of the cluster

    @return  Dictionary with velocity analysis results
    """
    velocities = []
    positions = []

    # Extract velocity and position data
    for obj in cluster_objects:
      velocity = obj.get('velocity', [0, 0, 0])
      translation = obj.get('translation', [0, 0, 0])

      if len(velocity) >= 3 and len(translation) >= 2:
        velocities.append([velocity[0], velocity[1], velocity[2]])  # vx, vy, vz
        positions.append([translation[0], translation[1]])  # x, y

    if len(velocities) < 2:
      return {
        "movement_type": "insufficient_data",
        "average_velocity": [0, 0, 0],
        "velocity_magnitude": 0,
        "movement_direction_degrees": 0,
        "velocity_coherence": 0
      }

    velocities = np.array(velocities)
    positions = np.array(positions)

    # Calculate basic velocity statistics
    avg_velocity = np.mean(velocities, axis=0)
    avg_speed = np.linalg.norm(avg_velocity)

    # Calculate movement direction in degrees
    movement_direction = np.arctan2(avg_velocity[1], avg_velocity[0]) * 180 / np.pi

    # Calculate velocity coherence (how similar the velocities are)
    velocity_std = np.std(velocities, axis=0)
    velocity_coherence = 1.0 - (np.linalg.norm(velocity_std) / (avg_speed + 1e-6))
    velocity_coherence = max(0, min(1, velocity_coherence))  # Clamp between 0 and 1

    # Analyze movement patterns relative to cluster center
    movement_type = self.classifyMovementPattern(
      velocities, positions, cluster_center, avg_speed, velocity_coherence
    )

    return {
      "movement_type": movement_type,
      "average_velocity": [float(avg_velocity[0]), float(avg_velocity[1]), float(avg_velocity[2])],
      "velocity_magnitude": float(avg_speed),
      "movement_direction_degrees": float(movement_direction),
      "velocity_coherence": float(velocity_coherence)
    }

  def classifyMovementPattern(self, velocities, positions, cluster_center, avg_speed, velocity_coherence):
    """! Classify the movement pattern of a cluster based on velocity analysis
    @param   velocities       Array of velocity vectors for each object
    @param   positions        Array of position vectors for each object
    @param   cluster_center   Centroid of the cluster
    @param   avg_speed        Average speed of the cluster
    @param   velocity_coherence How coherent the velocities are (0-1)

    @return  String describing the movement pattern
    """
    if avg_speed < self.config.STATIONARY_THRESHOLD:
      return "stationary"

    if velocity_coherence > self.config.VELOCITY_COHERENCE_THRESHOLD:
      return "coordinated_parallel"

    convergence_score = 0
    divergence_score = 0

    for i, (pos, vel) in enumerate(zip(positions, velocities)):
      to_center = cluster_center - pos
      to_center_norm = to_center / (np.linalg.norm(to_center) + 1e-6)

      vel_2d = vel[:2]
      vel_norm = vel_2d / (np.linalg.norm(vel_2d) + 1e-6)

      alignment = np.dot(vel_norm, to_center_norm)

      if alignment > self.config.ALIGNMENT_THRESHOLD:
        convergence_score += 1
      elif alignment < -self.config.ALIGNMENT_THRESHOLD:
        divergence_score += 1

    total_objects = len(velocities)
    convergence_ratio = convergence_score / total_objects
    divergence_ratio = divergence_score / total_objects

    if convergence_ratio > self.config.CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD:
      return "converging"
    elif divergence_ratio > self.config.CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD:
      return "diverging"
    elif velocity_coherence > 0.2:
      return "loosely_coordinated"
    else:
      return "chaotic"

  def loopForever(self):
    # Start WebUI server in a separate thread if available
    if self.webUi:
      try:
        webThread = self.webUi.runInThread(
          host='0.0.0.0',
          port=self.webui_port,
          certfile=self.webui_certfile,
          keyfile=self.webui_keyfile
        )
        log.info(f"WebUI server started on https://0.0.0.0:{self.webui_port}")
      except Exception as e:
        log.error(f"Failed to start WebUI server: {e}")

    if self.client:
      log.info("Starting MQTT client loop")
      return self.client.loopForever()
    else:
      log.info("No MQTT client available - cluster analytics service running in offline mode")
      # Keep the process alive without MQTT
      try:
        while True:
          time.sleep(60)
          log.info("Cluster Analytics service heartbeat - running without MQTT")
      except KeyboardInterrupt:
        log.info("Cluster Analytics service shutting down")
        return
