#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
WebUI module for cluster analytics visualization.

This module provides a Flask-based web interface for real-time visualization
of cluster analytics data including object detection and clustering results.
"""

import json
import os
import threading
import time
from collections import defaultdict
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from scene_common import log

class WebUI:
  """
  WebUI class for cluster analytics visualization.

  Provides a Flask-SocketIO based web interface for real-time visualization
  of cluster analytics data including object detection and clustering results.
  """

  def __init__(self, clusterAnalyticsContext):
    """
    Initialize the WebUI server.

    @param clusterAnalyticsContext: Reference to the ClusterAnalyticsContext instance
    """
    # Monkey patch eventlet early for proper async support
    try:
      import eventlet
      eventlet.monkey_patch()
    except ImportError:
      pass  # eventlet not available, will use threading mode

    self.clusterContext = clusterAnalyticsContext

    # Get the directory where this file is located
    webuiDir = os.path.dirname(os.path.abspath(__file__))

    self.app = Flask(
      __name__,
      template_folder=os.path.join(webuiDir, 'templates'),
      static_folder=os.path.join(webuiDir, 'static')
    )
    self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='eventlet')

    # Store scene data and clusters for the WebUI
    # scene_id -> {objects: [], clusters: [], metadata: {}}
    self.sceneData = defaultdict(dict)
    self.availableScenes = {}  # scene_id -> scene_name mapping
    self.currentSelectedScene = None

    # Track current scene categories for clustering configuration
    self.currentSceneCategories = set()

    # Throttling mechanism for updates (Real-time by default)
    self.updateInterval = 0.0  # seconds - 0.0 means real-time
    self.lastUpdateTime = 0
    self.pendingUpdates = {
      'scene_data': False,
      'clusters': False,
      'scenes_list': False
    }
    self.updateLock = threading.Lock()
    self.delayedUpdateScheduled = False

    # Set up Flask routes
    self.setRoutes()

    # Set up SocketIO event handlers
    self.setSocketioHandlers()

    # Hook into the cluster analytics context to get data updates
    self.hookIntoAnalytics()

  def setRoutes(self):
    """Set up Flask routes for the web interface."""

    @self.app.route('/')
    def index():
      """Serve the main visualization page."""
      return render_template('index.html')

    @self.app.route('/api/scenes')
    def get_scenes():
      """API endpoint to get available scenes with names."""
      scenesInfo = [
        {"id": sceneId, "name": sceneName}
        for sceneId, sceneName in self.availableScenes.items()
      ]
      return json.dumps(scenesInfo)

    @self.app.route('/api/scene/<scene_id>')
    def get_scene_data(scene_id):
      """API endpoint to get data for a specific scene."""
      if scene_id in self.sceneData:
        return json.dumps(self.sceneData[scene_id])
      return json.dumps({"error": "Scene not found"}), 404

  def setSocketioHandlers(self):
    """Set up SocketIO event handlers for real-time communication."""

    @self.socketio.on('connect')
    def handleConnect():
      log.debug("WebUI client connected")
      # Send current available scenes with names to the newly connected client
      scenesInfo = [
        {"id": sceneId, "name": sceneName}
        for sceneId, sceneName in self.availableScenes.items()
      ]
      emit('available_scenes', scenesInfo)

    @self.socketio.on('disconnect')
    def handleDisconnect():
      log.debug("WebUI client disconnected")

    @self.socketio.on('select_scene')
    def handleSceneSelection(data):
      sceneId = data.get('scene_id')
      log.debug(f"WebUI client selected scene: {sceneId}")
      self.currentSelectedScene = sceneId

      # Send current scene data if available
      if sceneId in self.sceneData:
        emit('scene_data', {
          'scene_id': sceneId,
          'data': self.sceneData[sceneId]
        })

        # Send clustering configuration for this scene
        sceneObjects = self.sceneData[sceneId].get('objects', [])
        categories = set()
        for obj in sceneObjects:
          categories.add(obj.get('category', 'unknown'))

        # Get current DBSCAN parameters for each category in this scene
        config = {}
        for category in categories:
          # Get current active parameters (user-configured or defaults) for this scene
          params = self.clusterContext.getDbscanParamsForCategory(category, sceneId)
          # Get default parameters to show what the recommended values are
          defaults = self.clusterContext.getDefaultDbscanParamsForCategory(category)

          # Check if this category has scene-specific customization
          hasCustomParams = (sceneId in self.clusterContext.user_dbscan_params_by_scene and
                                        category.lower() in self.clusterContext.user_dbscan_params_by_scene[sceneId])

          config[category] = {
            'eps': params['eps'],
            'min_samples': params['min_samples'],
            'default_eps': defaults['eps'],
            'default_min_samples': defaults['min_samples'],
            'is_default': not hasCustomParams
          }

        emit('clustering_config', {
          'scene_id': sceneId,
          'categories': list(categories),
          'config': config
        })

    @self.socketio.on('set_refresh_rate')
    def handleRefreshRateChange(data):
      refreshRate = data.get('refresh_rate', 1.0)
      log.debug(f"WebUI client changed refresh rate to: {refreshRate}")

      # Handle "real-time" mode (0 seconds) and normal throttling
      if refreshRate == 0:
        self.updateInterval = 0.0  # Real-time updates
        log.info("WebUI refresh rate set to real-time mode")
      else:
        self.updateInterval = float(refreshRate)
        log.info(f"WebUI refresh rate set to {refreshRate} seconds")

      # Emit confirmation back to client
      emit('refresh_rate_updated', {'refresh_rate': self.updateInterval})

    @self.socketio.on('get_clustering_config')
    def handleGetClusteringConfig():
      """Send current clustering parameters for scene categories."""
      if self.currentSelectedScene and self.currentSelectedScene in self.sceneData:
        # Get categories present in current scene
        sceneObjects = self.sceneData[self.currentSelectedScene].get('objects', [])
        categories = set()
        for obj in sceneObjects:
          categories.add(obj.get('category', 'unknown'))

        # Get current DBSCAN parameters for each category in current scene
        config = {}
        for category in categories:
          # Get current active parameters (user-configured or defaults) for this scene
          params = self.clusterContext.getDbscanParamsForCategory(category, self.currentSelectedScene)
          # Get default parameters to show what the recommended values are
          defaults = self.clusterContext.getDefaultDbscanParamsForCategory(category)

          # Check if this category has scene-specific customization
          hasCustomParams = (self.currentSelectedScene in self.clusterContext.user_dbscan_params_by_scene and
                                        category.lower() in self.clusterContext.user_dbscan_params_by_scene[self.currentSelectedScene])

          config[category] = {
            'eps': params['eps'],
            'min_samples': params['min_samples'],
            'default_eps': defaults['eps'],
            'default_min_samples': defaults['min_samples'],
            'is_default': not hasCustomParams
          }

        emit('clustering_config', {
          'scene_id': self.currentSelectedScene,
          'categories': list(categories),
          'config': config
        })
      else:
        emit('clustering_config', {
          'scene_id': None,
          'categories': [],
          'config': {}
        })

    @self.socketio.on('update_clustering_config')
    def handleUpdateClusteringConfig(data):
      """Update clustering parameters for specific categories."""
      category = data.get('category')
      eps = data.get('eps')
      minSamples = data.get('min_samples')

      if category and eps is not None and minSamples is not None:
        # Update the parameters using the proper method for the current scene
        if self.currentSelectedScene:
          self.clusterContext.setUserDbscanParamsForCategory(category, eps, minSamples, self.currentSelectedScene)

          log.info(f"Updated DBSCAN parameters for '{category}' in scene '{self.currentSelectedScene}': eps={eps}, min_samples={minSamples}")
        else:
          log.warning(f"Cannot update DBSCAN parameters for '{category}': no scene selected")

        # If this is the current scene, trigger re-clustering
        if (self.currentSelectedScene and
          self.currentSelectedScene in self.sceneData):
          sceneData = self.sceneData[self.currentSelectedScene]
          if 'objects' in sceneData:
            # Trigger immediate re-clustering with updated parameters
            log.info(f"Triggering immediate re-clustering for scene {self.currentSelectedScene} with updated parameters")

            # Create detection data structure for re-clustering
            detectionData = {
              'name': sceneData.get('scene_name', 'Unknown'),
              'timestamp': sceneData.get('timestamp'),
              'objects': sceneData['objects']
            }

            # Perform re-clustering with new parameters
            self.clusterContext.analyzeObjectClusters(self.currentSelectedScene, detectionData)

            # Immediately send updated cluster data to frontend
            if 'clusters' in self.sceneData[self.currentSelectedScene]:
              emit('clusters_update', {
                'scene_id': self.currentSelectedScene,
                'clusters': self.sceneData[self.currentSelectedScene]['clusters']
              })
              log.info(f"Sent updated cluster data to frontend for scene {self.currentSelectedScene}")
            else:
              # If no clusters were formed (not enough objects), send empty clusters
              emit('clusters_update', {
                'scene_id': self.currentSelectedScene,
                'clusters': []
              })
              log.info(f"Sent empty cluster data to frontend for scene {self.currentSelectedScene} (insufficient objects)")

    @self.socketio.on('reset_clustering_config')
    def handleResetClusteringConfig(data):
      """Reset clustering parameters for a specific category back to defaults."""
      category = data.get('category')
      sceneId = data.get('scene_id')  # Use scene_id from request if provided

      # Use provided scene_id or fall back to current selected scene
      targetScene = sceneId if sceneId else self.currentSelectedScene

      if category and targetScene:
        # Reset the parameters back to defaults for the target scene
        self.clusterContext.resetUserDbscanParamsForCategory(category, targetScene)

        log.info(f"Reset DBSCAN parameters for '{category}' in scene '{targetScene}' back to defaults")

        # Send updated configuration to client
        if targetScene in self.sceneData:

          # Get the default parameters that are now active for this scene
          params = self.clusterContext.getDbscanParamsForCategory(category, targetScene)
          defaults = self.clusterContext.getDefaultDbscanParamsForCategory(category)

          emit('clustering_config_updated', {
            'category': category,
            'eps': params['eps'],
            'min_samples': params['min_samples'],
            'default_eps': defaults['eps'],
            'default_min_samples': defaults['min_samples'],
            'is_default': True
          })

          # Trigger immediate re-clustering with reset parameters
          sceneData = self.sceneData[targetScene]
          if 'objects' in sceneData:
            log.info(f"Triggering immediate re-clustering for scene {targetScene} after parameter reset")

            # Create detection data structure for re-clustering
            detectionData = {
              'name': sceneData.get('scene_name', 'Unknown'),
              'timestamp': sceneData.get('timestamp'),
              'objects': sceneData['objects']
            }

            # Perform re-clustering with reset parameters
            self.clusterContext.analyzeObjectClusters(targetScene, detectionData)

            # Immediately send updated cluster data to frontend
            if 'clusters' in self.sceneData[targetScene]:
              emit('clusters_update', {
                'scene_id': targetScene,
                'clusters': self.sceneData[targetScene]['clusters']
              })
              log.info(f"Sent updated cluster data to frontend for scene {targetScene} after reset")
            else:
              # If no clusters were formed (not enough objects), send empty clusters
              emit('clusters_update', {
                'scene_id': targetScene,
                'clusters': []
              })
              log.info(f"Sent empty cluster data to frontend for scene {targetScene} after reset (insufficient objects)")
      else:
        log.warning(f"Cannot reset DBSCAN parameters for '{category}': no scene specified")

  def scheduleThrottledUpdate(self):
    """Schedule a throttled update to avoid flooding the WebUI with too many updates."""
    with self.updateLock:
      currentTime = time.time()

      # Handle real-time mode (no throttling)
      if self.updateInterval == 0.0:
        self.sendPendingUpdates()
        self.lastUpdateTime = currentTime
        # Clear pending update flags
        self.pendingUpdates = {
          'scene_data': False,
          'clusters': False,
          'scenes_list': False
        }
        return

      # Check if enough time has passed since the last update
      if currentTime - self.lastUpdateTime >= self.updateInterval:
        self.sendPendingUpdates()
        self.lastUpdateTime = currentTime
        # Clear pending update flags
        self.pendingUpdates = {
          'scene_data': False,
          'clusters': False,
          'scenes_list': False
        }
      else:
        # Schedule an update for later if not already scheduled
        if (any(self.pendingUpdates.values()) and
            not self.delayedUpdateScheduled):
          self.delayedUpdateScheduled = True

          def delayedUpdate():
            time.sleep(
              self.updateInterval -
              (currentTime - self.lastUpdateTime)
            )
            with self.updateLock:
              if any(self.pendingUpdates.values()):
                self.sendPendingUpdates()
                self.lastUpdateTime = time.time()
                self.pendingUpdates = {
                  'scene_data': False,
                  'clusters': False,
                  'scenes_list': False
                }
              self.delayedUpdateScheduled = False

          # Start delayed update in a separate thread
          threading.Thread(target=delayedUpdate, daemon=True).start()

  def sendPendingUpdates(self):
    """Send pending updates to WebUI clients."""
    if self.pendingUpdates['scenes_list']:
      scenesInfo = [
        {"id": sid, "name": sname}
        for sid, sname in self.availableScenes.items()
      ]
      self.socketio.emit('available_scenes', scenesInfo)

    if (
      self.currentSelectedScene and
      (self.pendingUpdates['scene_data'] or
            self.pendingUpdates['clusters'])
    ):
      if self.pendingUpdates['scene_data']:
        self.socketio.emit('scene_data', {
          'scene_id': self.currentSelectedScene,
          'data': self.sceneData[self.currentSelectedScene]
        })

      if (self.pendingUpdates['clusters'] and
          'clusters' in self.sceneData[self.currentSelectedScene]):
        self.socketio.emit('clusters_update', {
          'scene_id': self.currentSelectedScene,
          'clusters': self.sceneData[self.currentSelectedScene]['clusters']
        })

  def hookIntoAnalytics(self):
    """Hook into the cluster analytics context to receive data updates."""

    # Store original methods
    originalAnalyzeClusters = self.clusterContext.analyzeObjectClusters
    originalPublishClusters = self.clusterContext.publishAllClusters

    def enhancedAnalyzeClusters(sceneId, detectionData):
      """Enhanced version that also updates WebUI data."""
      # Update WebUI data before clustering analysis
      self.updateSceneObjects(sceneId, detectionData)

      # Call original method
      result = originalAnalyzeClusters(sceneId, detectionData)

      return result

    def enhancedPublishClusters(sceneId, detectionData, allClusters):
      """Enhanced version that also updates WebUI data."""
      # Call original method
      result = originalPublishClusters(sceneId, detectionData, allClusters)

      # Get the actual tracked clusters that were published
      tracked_clusters = self.clusterContext.cluster_tracker.getActiveClusters(
          scene_id=sceneId,
          publishable_only=True
      )

      # Convert to dictionaries (same format as MQTT publication)
      cluster_dicts = [c.toDict() for c in tracked_clusters]

      # Update WebUI clusters with the actual published data
      self.updateSceneClusters(sceneId, cluster_dicts)

      return result

    # Replace methods with enhanced versions
    self.clusterContext.analyzeObjectClusters = enhancedAnalyzeClusters
    self.clusterContext.publishAllClusters = enhancedPublishClusters

  def updateSceneObjects(self, sceneId, detectionData):
    """Update scene objects data for WebUI."""
    objects = detectionData.get('objects', [])

    # Get scene name from DATA_REGULATED topic data
    sceneName = detectionData.get('name', f"Scene {sceneId[:8]}" if len(sceneId) >= 8 else sceneId)

    # Add scene to available scenes with name from DATA_REGULATED topic
    self.availableScenes[sceneId] = sceneName

    # Update scene data
    self.sceneData[sceneId]['objects'] = objects
    self.sceneData[sceneId]['metadata'] = {
      'name': sceneName,
      'timestamp': time.time(),
      'object_count': len(objects)
    }

    log.debug(
      f"WebUI: Updated scene '{sceneName}' ({sceneId}) "
      f"with {len(objects)} objects"
    )

    # Mark updates as pending for throttled delivery
    self.pendingUpdates['scenes_list'] = True
    if sceneId == self.currentSelectedScene:
      self.pendingUpdates['scene_data'] = True

    # Schedule throttled update
    self.scheduleThrottledUpdate()

  def updateSceneClusters(self, sceneId, clusters):
    """Update scene clusters data for WebUI."""
    self.sceneData[sceneId]['clusters'] = clusters

    log.debug(f"WebUI: Updated scene {sceneId} with {len(clusters) if clusters else 0} clusters")

    # Mark cluster update as pending for throttled delivery
    if sceneId == self.currentSelectedScene:
      self.pendingUpdates['clusters'] = True

    # Schedule throttled update
    self.scheduleThrottledUpdate()

  def run(self, host='0.0.0.0', port=9443, debug=False, certfile=None, keyfile=None):
    """Run the Flask-SocketIO server with HTTPS."""
    if not certfile or not keyfile:
      raise ValueError("SSL certificate and key files are required for HTTPS")

    log.debug(f"Starting WebUI server on https://{host}:{port}")
    self.socketio.run(
      self.app,
      host=host,
      port=port,
      debug=debug,
      certfile=certfile,
      keyfile=keyfile
    )

  def runInThread(self, host='0.0.0.0', port=9443, certfile=None, keyfile=None):
    """Run the Flask-SocketIO server in a separate thread using eventlet with HTTPS."""
    if not certfile or not keyfile:
      raise ValueError("SSL certificate and key files are required for HTTPS")

    def runServer():
      log.info(f"Starting WebUI server in background on https://{host}:{port}")
      # Use socketio.run() which automatically uses eventlet if available
      # This properly integrates SocketIO with the async server
      self.socketio.run(
        self.app,
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        log_output=False,
        certfile=certfile,
        keyfile=keyfile
      )

    serverThread = threading.Thread(target=runServer, daemon=True)
    serverThread.start()
    log.info(f"WebUI server thread started on {host}:{port}")
    return serverThread
