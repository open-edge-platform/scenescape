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

    def __init__(self, cluster_analytics_context):
        """
        Initialize the WebUI server.

        @param cluster_analytics_context: Reference to the ClusterAnalyticsContext instance
        """
        # Monkey patch eventlet early for proper async support
        try:
            import eventlet
            eventlet.monkey_patch()
        except ImportError:
            pass  # eventlet not available, will use threading mode
        
        self.cluster_context = cluster_analytics_context
        
        # Get the directory where this file is located
        webui_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.app = Flask(
            __name__,
            template_folder=os.path.join(webui_dir, 'templates'),
            static_folder=os.path.join(webui_dir, 'static')
        )
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='eventlet')

        # Store scene data and clusters for the WebUI
        # scene_id -> {objects: [], clusters: [], metadata: {}}
        self.scene_data = defaultdict(dict)
        self.available_scenes = {}  # scene_id -> scene_name mapping
        self.current_selected_scene = None

        # Track current scene categories for clustering configuration
        self.current_scene_categories = set()

        # Throttling mechanism for updates (Real-time by default)
        self.update_interval = 0.0  # seconds - 0.0 means real-time
        self.last_update_time = 0
        self.pending_updates = {
            'scene_data': False,
            'clusters': False,
            'scenes_list': False
        }
        self.update_lock = threading.Lock()
        self.delayed_update_scheduled = False

        # Set up Flask routes
        self.setup_routes()

        # Set up SocketIO event handlers
        self.setup_socketio_handlers()

        # Hook into the cluster analytics context to get data updates
        self.hook_into_analytics()

    def setup_routes(self):
        """Set up Flask routes for the web interface."""

        @self.app.route('/')
        def index():
            """Serve the main visualization page."""
            return render_template('index.html')

        @self.app.route('/api/scenes')
        def get_scenes():
            """API endpoint to get available scenes with names."""
            scenes_info = [
                {"id": scene_id, "name": scene_name}
                for scene_id, scene_name in self.available_scenes.items()
            ]
            return json.dumps(scenes_info)

        @self.app.route('/api/scene/<scene_id>')
        def get_scene_data(scene_id):
            """API endpoint to get data for a specific scene."""
            if scene_id in self.scene_data:
                return json.dumps(self.scene_data[scene_id])
            return json.dumps({"error": "Scene not found"}), 404

    def setup_socketio_handlers(self):
        """Set up SocketIO event handlers for real-time communication."""

        @self.socketio.on('connect')
        def handle_connect():
            log.debug("WebUI client connected")
            # Send current available scenes with names to the newly connected client
            scenes_info = [
                {"id": scene_id, "name": scene_name}
                for scene_id, scene_name in self.available_scenes.items()
            ]
            emit('available_scenes', scenes_info)

        @self.socketio.on('disconnect')
        def handle_disconnect():
            log.debug("WebUI client disconnected")

        @self.socketio.on('select_scene')
        def handle_scene_selection(data):
            scene_id = data.get('scene_id')
            log.debug(f"WebUI client selected scene: {scene_id}")
            self.current_selected_scene = scene_id

            # Send current scene data if available
            if scene_id in self.scene_data:
                emit('scene_data', {
                    'scene_id': scene_id,
                    'data': self.scene_data[scene_id]
                })

                # Send clustering configuration for this scene
                scene_objects = self.scene_data[scene_id].get('objects', [])
                categories = set()
                for obj in scene_objects:
                    categories.add(obj.get('category', 'unknown'))

                # Get current DBSCAN parameters for each category in this scene
                config = {}
                for category in categories:
                    # Get current active parameters (user-configured or defaults) for this scene
                    params = self.cluster_context.getDbscanParamsForCategory(category, scene_id)
                    # Get default parameters to show what the recommended values are
                    defaults = self.cluster_context.getDefaultDbscanParamsForCategory(category)

                    # Check if this category has scene-specific customization
                    has_custom_params = (scene_id in self.cluster_context.user_dbscan_params_by_scene and
                                       category.lower() in self.cluster_context.user_dbscan_params_by_scene[scene_id])

                    config[category] = {
                        'eps': params['eps'],
                        'min_samples': params['min_samples'],
                        'default_eps': defaults['eps'],
                        'default_min_samples': defaults['min_samples'],
                        'is_default': not has_custom_params
                    }

                emit('clustering_config', {
                    'scene_id': scene_id,
                    'categories': list(categories),
                    'config': config
                })

        @self.socketio.on('set_refresh_rate')
        def handle_refresh_rate_change(data):
            refresh_rate = data.get('refresh_rate', 1.0)
            log.debug(f"WebUI client changed refresh rate to: {refresh_rate}")

            # Handle "real-time" mode (0 seconds) and normal throttling
            if refresh_rate == 0:
                self.update_interval = 0.0  # Real-time updates
                log.info("WebUI refresh rate set to real-time mode")
            else:
                self.update_interval = float(refresh_rate)
                log.info(f"WebUI refresh rate set to {refresh_rate} seconds")

            # Emit confirmation back to client
            emit('refresh_rate_updated', {'refresh_rate': self.update_interval})

        @self.socketio.on('get_clustering_config')
        def handle_get_clustering_config():
            """Send current clustering parameters for scene categories."""
            if self.current_selected_scene and self.current_selected_scene in self.scene_data:
                # Get categories present in current scene
                scene_objects = self.scene_data[self.current_selected_scene].get('objects', [])
                categories = set()
                for obj in scene_objects:
                    categories.add(obj.get('category', 'unknown'))

                # Get current DBSCAN parameters for each category in current scene
                config = {}
                for category in categories:
                    # Get current active parameters (user-configured or defaults) for this scene
                    params = self.cluster_context.getDbscanParamsForCategory(category, self.current_selected_scene)
                    # Get default parameters to show what the recommended values are
                    defaults = self.cluster_context.getDefaultDbscanParamsForCategory(category)

                    # Check if this category has scene-specific customization
                    has_custom_params = (self.current_selected_scene in self.cluster_context.user_dbscan_params_by_scene and
                                       category.lower() in self.cluster_context.user_dbscan_params_by_scene[self.current_selected_scene])

                    config[category] = {
                        'eps': params['eps'],
                        'min_samples': params['min_samples'],
                        'default_eps': defaults['eps'],
                        'default_min_samples': defaults['min_samples'],
                        'is_default': not has_custom_params
                    }

                emit('clustering_config', {
                    'scene_id': self.current_selected_scene,
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
        def handle_update_clustering_config(data):
            """Update clustering parameters for specific categories."""
            category = data.get('category')
            eps = data.get('eps')
            min_samples = data.get('min_samples')

            if category and eps is not None and min_samples is not None:
                # Update the parameters using the proper method for the current scene
                if self.current_selected_scene:
                    self.cluster_context.setUserDbscanParamsForCategory(category, eps, min_samples, self.current_selected_scene)

                    log.info(f"Updated DBSCAN parameters for '{category}' in scene '{self.current_selected_scene}': eps={eps}, min_samples={min_samples}")
                else:
                    log.warning(f"Cannot update DBSCAN parameters for '{category}': no scene selected")

                # If this is the current scene, trigger re-clustering
                if (self.current_selected_scene and
                    self.current_selected_scene in self.scene_data):
                    scene_data = self.scene_data[self.current_selected_scene]
                    if 'objects' in scene_data:
                        # Trigger immediate re-clustering with updated parameters
                        log.info(f"Triggering immediate re-clustering for scene {self.current_selected_scene} with updated parameters")

                        # Create detection data structure for re-clustering
                        detection_data = {
                            'name': scene_data.get('scene_name', 'Unknown'),
                            'timestamp': scene_data.get('timestamp'),
                            'objects': scene_data['objects']
                        }

                        # Perform re-clustering with new parameters
                        self.cluster_context.analyzeObjectClusters(self.current_selected_scene, detection_data)

                        # Immediately send updated cluster data to frontend
                        if 'clusters' in self.scene_data[self.current_selected_scene]:
                            emit('clusters_update', {
                                'scene_id': self.current_selected_scene,
                                'clusters': self.scene_data[self.current_selected_scene]['clusters']
                            })
                            log.info(f"Sent updated cluster data to frontend for scene {self.current_selected_scene}")
                        else:
                            # If no clusters were formed (not enough objects), send empty clusters
                            emit('clusters_update', {
                                'scene_id': self.current_selected_scene,
                                'clusters': []
                            })
                            log.info(f"Sent empty cluster data to frontend for scene {self.current_selected_scene} (insufficient objects)")

        @self.socketio.on('reset_clustering_config')
        def handle_reset_clustering_config(data):
            """Reset clustering parameters for a specific category back to defaults."""
            category = data.get('category')
            scene_id = data.get('scene_id')  # Use scene_id from request if provided

            # Use provided scene_id or fall back to current selected scene
            target_scene = scene_id if scene_id else self.current_selected_scene

            if category and target_scene:
                # Reset the parameters back to defaults for the target scene
                self.cluster_context.resetUserDbscanParamsForCategory(category, target_scene)

                log.info(f"Reset DBSCAN parameters for '{category}' in scene '{target_scene}' back to defaults")

                # Send updated configuration to client
                if target_scene in self.scene_data:

                    # Get the default parameters that are now active for this scene
                    params = self.cluster_context.getDbscanParamsForCategory(category, target_scene)
                    defaults = self.cluster_context.getDefaultDbscanParamsForCategory(category)

                    emit('clustering_config_updated', {
                        'category': category,
                        'eps': params['eps'],
                        'min_samples': params['min_samples'],
                        'default_eps': defaults['eps'],
                        'default_min_samples': defaults['min_samples'],
                        'is_default': True
                    })

                    # Trigger immediate re-clustering with reset parameters
                    scene_data = self.scene_data[target_scene]
                    if 'objects' in scene_data:
                        log.info(f"Triggering immediate re-clustering for scene {target_scene} after parameter reset")

                        # Create detection data structure for re-clustering
                        detection_data = {
                            'name': scene_data.get('scene_name', 'Unknown'),
                            'timestamp': scene_data.get('timestamp'),
                            'objects': scene_data['objects']
                        }

                        # Perform re-clustering with reset parameters
                        self.cluster_context.analyzeObjectClusters(target_scene, detection_data)

                        # Immediately send updated cluster data to frontend
                        if 'clusters' in self.scene_data[target_scene]:
                            emit('clusters_update', {
                                'scene_id': target_scene,
                                'clusters': self.scene_data[target_scene]['clusters']
                            })
                            log.info(f"Sent updated cluster data to frontend for scene {target_scene} after reset")
                        else:
                            # If no clusters were formed (not enough objects), send empty clusters
                            emit('clusters_update', {
                                'scene_id': target_scene,
                                'clusters': []
                            })
                            log.info(f"Sent empty cluster data to frontend for scene {target_scene} after reset (insufficient objects)")
            else:
                log.warning(f"Cannot reset DBSCAN parameters for '{category}': no scene specified")

    def schedule_throttled_update(self):
        """Schedule a throttled update to avoid flooding the WebUI with too many updates."""
        with self.update_lock:
            current_time = time.time()

            # Handle real-time mode (no throttling)
            if self.update_interval == 0.0:
                self.send_pending_updates()
                self.last_update_time = current_time
                # Clear pending update flags
                self.pending_updates = {
                    'scene_data': False,
                    'clusters': False,
                    'scenes_list': False
                }
                return

            # Check if enough time has passed since the last update
            if current_time - self.last_update_time >= self.update_interval:
                self.send_pending_updates()
                self.last_update_time = current_time
                # Clear pending update flags
                self.pending_updates = {
                    'scene_data': False,
                    'clusters': False,
                    'scenes_list': False
                }
            else:
                # Schedule an update for later if not already scheduled
                if (any(self.pending_updates.values()) and
                        not self.delayed_update_scheduled):
                    self.delayed_update_scheduled = True

                    def delayed_update():
                        time.sleep(
                            self.update_interval -
                            (current_time - self.last_update_time)
                        )
                        with self.update_lock:
                            if any(self.pending_updates.values()):
                                self.send_pending_updates()
                                self.last_update_time = time.time()
                                self.pending_updates = {
                                    'scene_data': False,
                                    'clusters': False,
                                    'scenes_list': False
                                }
                            self.delayed_update_scheduled = False

                    # Start delayed update in a separate thread
                    threading.Thread(target=delayed_update, daemon=True).start()

    def send_pending_updates(self):
        """Send pending updates to WebUI clients."""
        if self.pending_updates['scenes_list']:
            scenes_info = [
                {"id": sid, "name": sname}
                for sid, sname in self.available_scenes.items()
            ]
            self.socketio.emit('available_scenes', scenes_info)

        if (
            self.current_selected_scene and
            (self.pending_updates['scene_data'] or
             self.pending_updates['clusters'])
        ):
            if self.pending_updates['scene_data']:
                self.socketio.emit('scene_data', {
                    'scene_id': self.current_selected_scene,
                    'data': self.scene_data[self.current_selected_scene]
                })

            if (self.pending_updates['clusters'] and
                    'clusters' in self.scene_data[self.current_selected_scene]):
                self.socketio.emit('clusters_update', {
                    'scene_id': self.current_selected_scene,
                    'clusters': self.scene_data[self.current_selected_scene]['clusters']
                })

    def hook_into_analytics(self):
        """Hook into the cluster analytics context to receive data updates."""

        # Store original methods
        original_analyze_clusters = self.cluster_context.analyzeObjectClusters
        original_publish_clusters = self.cluster_context.publishAllClusters

        def enhanced_analyze_clusters(scene_id, detection_data):
            """Enhanced version that also updates WebUI data."""
            # Update WebUI data before clustering analysis
            self.update_scene_objects(scene_id, detection_data)
            
            # Call original method
            result = original_analyze_clusters(scene_id, detection_data)

            return result

        def enhanced_publish_clusters(scene_id, detection_data, all_clusters):
            """Enhanced version that also updates WebUI data."""
            # Call original method
            result = original_publish_clusters(scene_id, detection_data, all_clusters)

            # Update WebUI clusters
            self.update_scene_clusters(scene_id, all_clusters)

            return result

        # Replace methods with enhanced versions
        self.cluster_context.analyzeObjectClusters = enhanced_analyze_clusters
        self.cluster_context.publishAllClusters = enhanced_publish_clusters

    def update_scene_objects(self, scene_id, detection_data):
        """Update scene objects data for WebUI."""
        objects = detection_data.get('objects', [])

        # Get scene name from DATA_REGULATED topic data
        scene_name = detection_data.get('name', f"Scene {scene_id[:8]}" if len(scene_id) >= 8 else scene_id)

        # Add scene to available scenes with name from DATA_REGULATED topic
        self.available_scenes[scene_id] = scene_name

        # Update scene data
        self.scene_data[scene_id]['objects'] = objects
        self.scene_data[scene_id]['metadata'] = {
            'name': scene_name,
            'timestamp': time.time(),
            'object_count': len(objects)
        }

        log.debug(
            f"WebUI: Updated scene '{scene_name}' ({scene_id}) "
            f"with {len(objects)} objects"
        )

        # Mark updates as pending for throttled delivery
        self.pending_updates['scenes_list'] = True
        if scene_id == self.current_selected_scene:
            self.pending_updates['scene_data'] = True

        # Schedule throttled update
        self.schedule_throttled_update()

    def update_scene_clusters(self, scene_id, clusters):
        """Update scene clusters data for WebUI."""
        self.scene_data[scene_id]['clusters'] = clusters

        log.debug(f"WebUI: Updated scene {scene_id} with {len(clusters)} clusters")

        # Mark cluster update as pending for throttled delivery
        if scene_id == self.current_selected_scene:
            self.pending_updates['clusters'] = True

        # Schedule throttled update
        self.schedule_throttled_update()

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask-SocketIO server."""
        log.debug(f"Starting WebUI server on {host}:{port}")
        self.socketio.run(
            self.app,
            host=host,
            port=port,
            debug=debug
        )

    def run_in_thread(self, host='0.0.0.0', port=5000):
        """Run the Flask-SocketIO server in a separate thread using eventlet."""
        def run_server():
            log.info(f"Starting WebUI server in background on {host}:{port}")
            # Use socketio.run() which automatically uses eventlet if available
            # This properly integrates SocketIO with the async server
            self.socketio.run(
                self.app,
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                log_output=False
            )

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        log.info(f"WebUI server thread started on {host}:{port}")
        return server_thread
