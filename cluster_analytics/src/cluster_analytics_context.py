# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time
import numpy as np
from collections import Counter, defaultdict
from sklearn.cluster import DBSCAN

from scene_common import log
from scene_common.mqtt import PubSub

class ClusterAnalyticsContext:
  topics_to_subscribe = []

  # Clustering configuration - Category-specific DBSCAN parameters
  # Default parameters for all object types
  DEFAULT_DBSCAN_EPS = 1
  DEFAULT_DBSCAN_MIN_SAMPLES = 3

  # Category-specific DBSCAN parameters
  # Different object types require different clustering parameters due to their spatial characteristics
  CATEGORY_DBSCAN_PARAMS = {
    'person': {
      'eps': 1,        # People can form clusters at slightly larger distances (social distancing, queues)
      'min_samples': 3   # Minimum 3 people to form a meaningful cluster
    },
    'vehicle': {
      'eps': 4.0,        # Vehicles need larger clustering distance (parking, traffic jams)
      'min_samples': 2   # Even 2 vehicles can form a significant cluster (convoy, parking)
    },
    'bicycle': {
      'eps': 1.5,        # Bicycles cluster more tightly
      'min_samples': 2   # 2 bicycles can form a cluster (bike rack, group riding)
    },
    'motorcycle': {
      'eps': 2.5,        # Motorcycles have moderate clustering distance
      'min_samples': 2   # 2 motorcycles can form a cluster
    },
    'truck': {
      'eps': 5.0,        # Trucks need large clustering distance due to size
      'min_samples': 2   # 2 trucks can form a significant cluster
    },
    'bus': {
      'eps': 6.0,        # Buses need very large clustering distance
      'min_samples': 2   # 2 buses form a significant cluster (bus stops, depots)
    }
  }

  # Shape detection configuration
  SHAPE_VARIANCE_THRESHOLD = 0.5  # Threshold for determining circle vs rectangle based on distance variance
  QUADRANT_ANGLE = np.pi / 2  # 90 degrees - angle for dividing points into quadrants for rectangle detection
  ANGLE_DISTRIBUTION_THRESHOLD = 0.5  # Threshold for uniform angle distribution in circular formation
  LINEAR_FORMATION_AREA_THRESHOLD = 0.5  # Area threshold for detecting linear formations

  # Movement analysis configuration
  ALIGNMENT_THRESHOLD = 0.5  # Threshold for determining movement alignment (positive/negative)
  CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD = 0.6  # Threshold for convergence/divergence detection

  # Velocity analysis configuration
  STATIONARY_THRESHOLD = 0.1  # Velocity magnitude threshold for considering objects stationary (m/s)
  VELOCITY_COHERENCE_THRESHOLD = 0.3  # Threshold for determining if cluster has coherent movement

  def __init__(self, broker, broker_auth, cert, root_cert, enable_webui=True, webui_port=5000, webui_certfile=None, webui_keyfile=None):
    # Subscribe to data regulation topic for scene updates
    data_regulated_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id="+")
    self.topics_to_subscribe.append((data_regulated_topic, self.processSceneAnalytics))

    self.register_thread_lock = threading.Lock()
    self.current_processing_scene = None
    self.webui_port = webui_port
    self.webui_certfile = webui_certfile
    self.webui_keyfile = webui_keyfile

    # User-configured DBSCAN parameters (overrides for defaults)
    # This dictionary stores custom parameters set by users through the WebUI
    # Format: {'scene_id': {'category': {'eps': value, 'min_samples': value}}}
    # This allows different scenes to have different clustering parameters
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
    params = self.CATEGORY_DBSCAN_PARAMS.get(category_lower)
    if params:
      log.info(f"Using default DBSCAN parameters for '{category}': eps={params['eps']}, min_samples={params['min_samples']}")
      return params

    # Use global default parameters for unknown categories
    default_params = {
      'eps': self.DEFAULT_DBSCAN_EPS,
      'min_samples': self.DEFAULT_DBSCAN_MIN_SAMPLES
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

    # Return category-specific default parameters if available
    if category_lower in self.CATEGORY_DBSCAN_PARAMS:
      return self.CATEGORY_DBSCAN_PARAMS[category_lower].copy()
    else:
      # Use global default parameters for unknown categories
      return {
        'eps': self.DEFAULT_DBSCAN_EPS,
        'min_samples': self.DEFAULT_DBSCAN_MIN_SAMPLES
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

      # Perform clustering analysis on objects
      self.analyzeObjectClusters(scene_id, detection_data)

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
    """! Analyze object clusters using DBSCAN algorithm and publish results to MQTT
    @param   scene_id        Scene identifier
    @param   detection_data  Detection data containing objects with coordinates

    @return  None
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
    min_required_objects = min(min_samples_list, default=self.DEFAULT_DBSCAN_MIN_SAMPLES)

    if len(objects) < min_required_objects:
      log.info(f"Scene {scene_id}: Insufficient objects ({len(objects)}) for clustering (minimum {min_required_objects} required based on user parameters)")
      return

    # Analyze clusters for each category with multiple objects
    for category, category_objects in objects_by_category.items():
      # Get category-specific DBSCAN parameters for this scene
      dbscan_params = self.getDbscanParamsForCategory(category, scene_id)

      if len(category_objects) < dbscan_params['min_samples']:
        continue  # Skip categories with too few objects for this category's requirements

      # Extract x,y coordinates for clustering
      coordinates = self.extractCoordinatesFromObjects(category_objects)

      # Prepare coordinates for clustering
      coordinates_array = np.array(coordinates)

      # Apply DBSCAN clustering using meter coordinates directly with category-specific parameters
      clustering = DBSCAN(eps=dbscan_params['eps'], min_samples=dbscan_params['min_samples']).fit(coordinates_array)
      # Analyze cluster results
      labels = clustering.labels_
      n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
      n_noise = np.sum(labels == -1)  # Count noise points efficiently using NumPy

      if n_clusters > 0:
        log.info(f"Scene {scene_id}: Found {n_clusters} clusters for category '{category}' ({len(category_objects)} objects, {n_noise} noise points)")

        # Create metadata for each individual cluster, skipping noise points
        for cluster_id in set(labels) - {-1}:

          # Get objects belonging to this cluster
          cluster_objects = []
          cluster_coordinates = []
          for i, label in enumerate(labels):
            if label == cluster_id:
              cluster_objects.append(category_objects[i])
              cluster_coordinates.append(coordinates[i])

          # Extract features and calculate cluster center (centroid)
          cluster_coordinates_array = np.array(cluster_coordinates)
          _, cluster_center = self.extractPointFeatures(cluster_coordinates_array)

          # Detect cluster shape using ML techniques
          shape_analysis = self.detectShapeMl(cluster_coordinates)

          # Analyze cluster velocity patterns
          velocity_analysis = self.analyzeClusterVelocity(cluster_objects, cluster_center)

          # Create individual cluster metadata
          cluster_metadata = {
            'cluster_id': str(cluster_id),  # TODO: Replace with persistent UUID for temporal tracking
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
              'category': category  # Include category to show which params were used
            }
          }

          # Log cluster summary
          log.debug(f"Detailed cluster metadata: {json.dumps(cluster_metadata, indent=2)}")

          # Add cluster to the batch for publishing
          all_clusters.append(cluster_metadata)

    # Always publish cluster results for this scene (even if empty)
    # This ensures the WebUI gets updated when clustering parameters result in no clusters
    self.publishAllClusters(scene_id, detection_data, all_clusters)

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

    # Extract features from points
    features, _ = self.extractPointFeatures(points_array)

    # Analyze feature patterns
    dist_variance = np.var(features[:, 0])  # Variance in distances to center
    distances = features[:, 0]
    angles = features[:, 1]

    # Shape classification logic with size calculations
    if dist_variance < self.SHAPE_VARIANCE_THRESHOLD:
      # Consistent distance to center suggests circular formation
      radius = np.mean(distances)
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
    elif len(points_array) == 4:
      # For 4 points, check if they form rectangular pattern
      angle_groups = len(np.unique(np.round(features[:, 1] / self.QUADRANT_ANGLE)))
      if angle_groups >= 3:  # At least 3 different quadrants
        # Calculate rectangle dimensions
        x_coords = points_array[:, 0]
        y_coords = points_array[:, 1]

        width = np.max(x_coords) - np.min(x_coords)
        height = np.max(y_coords) - np.min(y_coords)
        area = width * height
        perimeter = 2 * (width + height)

        # Find corner points (approximate)
        corners = [
          [np.min(x_coords), np.min(y_coords)],  # Bottom-left
          [np.max(x_coords), np.min(y_coords)],  # Bottom-right
          [np.max(x_coords), np.max(y_coords)],  # Top-right
          [np.min(x_coords), np.max(y_coords)]   # Top-left
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
    elif len(points_array) >= 5:
      # For more points, analyze angle distribution
      angle_diffs = np.diff(np.sort(angles))
      if np.std(angle_diffs) < self.ANGLE_DISTRIBUTION_THRESHOLD:  # Relatively uniform angle distribution
        # Treat as circle
        radius = np.mean(distances)
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
      else:
        # Irregular shape - calculate bounding box
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

    # Check for linear formation
    if len(points_array) >= 3:
      # Calculate if points are roughly collinear
      areas = []
      for i in range(len(points_array) - 2):
        p1, p2, p3 = points_array[i], points_array[i+1], points_array[i+2]
        area = abs((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1])) / 2
        areas.append(area)

      if np.mean(areas) < self.LINEAR_FORMATION_AREA_THRESHOLD:  # Small area suggests linear formation
        # Calculate line length and endpoints
        x_coords = points_array[:, 0]
        y_coords = points_array[:, 1]

        # Find endpoints (furthest points)
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

    # Default to irregular with bounding box
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
    # Check if cluster is stationary
    if avg_speed < self.STATIONARY_THRESHOLD:
      return "stationary"

    # Check for coherent movement (parallel motion)
    if velocity_coherence > self.VELOCITY_COHERENCE_THRESHOLD:
      return "coordinated_parallel"

    # Analyze convergence/divergence patterns
    convergence_score = 0
    divergence_score = 0

    for i, (pos, vel) in enumerate(zip(positions, velocities)):
      # Vector from object position to cluster center
      to_center = cluster_center - pos
      to_center_norm = to_center / (np.linalg.norm(to_center) + 1e-6)

      # Normalize velocity (use only X,Y components for 2D movement analysis)
      vel_2d = vel[:2]  # Extract vx, vy components
      vel_norm = vel_2d / (np.linalg.norm(vel_2d) + 1e-6)

      # Dot product indicates alignment
      alignment = np.dot(vel_norm, to_center_norm)

      if alignment > self.ALIGNMENT_THRESHOLD:  # Moving toward center
        convergence_score += 1
      elif alignment < -self.ALIGNMENT_THRESHOLD:  # Moving away from center
        divergence_score += 1

    total_objects = len(velocities)
    convergence_ratio = convergence_score / total_objects
    divergence_ratio = divergence_score / total_objects

    # Classification based on movement patterns
    if convergence_ratio > self.CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD:
      return "converging"
    elif divergence_ratio > self.CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD:
      return "diverging"
    elif velocity_coherence > 0.2:  # Some coordination but not high
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
