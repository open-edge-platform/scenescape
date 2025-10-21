#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
WebUI module for cluster analytics visualization.

This module provides a Flask-based web interface for real-time visualization
of cluster analytics data including object detection and clustering results.
"""

import json
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
        self.cluster_context = cluster_analytics_context
        self.app = Flask(__name__, template_folder='templates',
                         static_folder='static')
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")

        # Store scene data and clusters for the WebUI
        # scene_id -> {objects: [], clusters: [], metadata: {}}
        self.scene_data = defaultdict(dict)
        self.available_scenes = {}  # scene_id -> scene_name mapping
        self.current_selected_scene = None

        # Throttling mechanism for updates (1 second intervals)
        self.update_interval = 1.0  # seconds
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
            scenes_info = [{"id": scene_id, "name": scene_name}
                           for scene_id, scene_name in self.available_scenes.items()]
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
            scenes_info = [{"id": scene_id, "name": scene_name}
                           for scene_id, scene_name in self.available_scenes.items()]
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

    def schedule_throttled_update(self):
        """Schedule a throttled update to avoid flooding the WebUI with too many updates."""
        with self.update_lock:
            current_time = time.time()

            # Check if enough time has passed since the last update
            if current_time - self.last_update_time >= self.update_interval:
                self.send_pending_updates()
                self.last_update_time = current_time
                # Clear pending update flags
                self.pending_updates = {'scene_data': False, 'clusters': False,
                                        'scenes_list': False}
            else:
                # Schedule an update for later if not already scheduled
                if (any(self.pending_updates.values()) and
                        not self.delayed_update_scheduled):
                    self.delayed_update_scheduled = True

                    def delayed_update():
                        time.sleep(self.update_interval -
                                   (current_time - self.last_update_time))
                        with self.update_lock:
                            if any(self.pending_updates.values()):
                                self.send_pending_updates()
                                self.last_update_time = time.time()
                                self.pending_updates = {'scene_data': False,
                                                        'clusters': False,
                                                        'scenes_list': False}
                            self.delayed_update_scheduled = False

                    # Start delayed update in a separate thread
                    threading.Thread(target=delayed_update, daemon=True).start()

    def send_pending_updates(self):
        """Send pending updates to WebUI clients."""
        if self.pending_updates['scenes_list']:
            scenes_info = [{"id": sid, "name": sname}
                           for sid, sname in self.available_scenes.items()]
            self.socketio.emit('available_scenes', scenes_info)

        if (self.current_selected_scene and
                (self.pending_updates['scene_data'] or self.pending_updates['clusters'])):
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
        original_aggregate_detection = self.cluster_context.aggregateDetectionData
        original_publish_clusters = self.cluster_context.publishAllClusters

        def enhanced_aggregate_detection(scene_id, detection_data):
            """Enhanced version that also updates WebUI data."""
            # Call original method
            result = original_aggregate_detection(scene_id, detection_data)

            # Update WebUI data
            self.update_scene_objects(scene_id, detection_data)

            return result

        def enhanced_publish_clusters(scene_id, detection_data, all_clusters):
            """Enhanced version that also updates WebUI data."""
            # Call original method
            result = original_publish_clusters(scene_id, detection_data, all_clusters)

            # Update WebUI clusters
            self.update_scene_clusters(scene_id, all_clusters)

            return result

        # Replace methods with enhanced versions
        self.cluster_context.aggregateDetectionData = enhanced_aggregate_detection
        self.cluster_context.publishAllClusters = enhanced_publish_clusters

    def update_scene_objects(self, scene_id, detection_data):
        """Update scene objects data for WebUI."""
        scene_name = detection_data.get('name', 'Unknown')
        objects = detection_data.get('objects', [])

        # Add scene to available scenes with name mapping
        self.available_scenes[scene_id] = scene_name

        # Update scene data
        self.scene_data[scene_id]['objects'] = objects
        self.scene_data[scene_id]['metadata'] = {
            'name': scene_name,
            'timestamp': time.time(),
            'object_count': len(objects)
        }

        log.debug(f"WebUI: Updated scene '{scene_name}' ({scene_id}) "
                  f"with {len(objects)} objects")

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
        self.socketio.run(self.app, host=host, port=port, debug=debug,
                          allow_unsafe_werkzeug=True)

    def run_in_thread(self, host='0.0.0.0', port=5000):
        """Run the Flask-SocketIO server in a separate thread."""
        def run_server():
            log.debug(f"Starting WebUI server in background on {host}:{port}")
            self.socketio.run(self.app, host=host, port=port, debug=False,
                              allow_unsafe_werkzeug=True)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        log.debug("WebUI server thread started")
        return server_thread
