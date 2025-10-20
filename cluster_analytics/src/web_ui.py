#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time
from collections import defaultdict
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from scene_common import log

class WebUI:
    def __init__(self, cluster_analytics_context):
        """
        Initialize the WebUI server
        
        @param cluster_analytics_context: Reference to the ClusterAnalyticsContext instance
        """
        self.cluster_context = cluster_analytics_context
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        # Store scene data and clusters for the WebUI
        self.scene_data = defaultdict(dict)  # scene_id -> {objects: [], clusters: [], metadata: {}}
        self.available_scenes = set()
        self.current_selected_scene = None
        
        # Set up Flask routes
        self.setup_routes()
        
        # Set up SocketIO event handlers
        self.setup_socketio_handlers()
        
        # Hook into the cluster analytics context to get data updates
        self.hook_into_analytics()
        
    def setup_routes(self):
        """Set up Flask routes for the web interface"""
        
        @self.app.route('/')
        def index():
            """Serve the main visualization page"""
            return render_template('index.html')
            
        @self.app.route('/api/scenes')
        def get_scenes():
            """API endpoint to get available scenes"""
            return json.dumps(list(self.available_scenes))
            
        @self.app.route('/api/scene/<scene_id>')
        def get_scene_data(scene_id):
            """API endpoint to get data for a specific scene"""
            if scene_id in self.scene_data:
                return json.dumps(self.scene_data[scene_id])
            else:
                return json.dumps({"error": "Scene not found"}), 404
                
    def setup_socketio_handlers(self):
        """Set up SocketIO event handlers for real-time communication"""
        
        @self.socketio.on('connect')
        def handle_connect():
            log.info(f"WebUI client connected")
            # Send current available scenes to the newly connected client
            emit('available_scenes', list(self.available_scenes))
            
        @self.socketio.on('disconnect')
        def handle_disconnect():
            log.info("WebUI client disconnected")
            
        @self.socketio.on('select_scene')
        def handle_scene_selection(data):
            scene_id = data.get('scene_id')
            log.info(f"WebUI client selected scene: {scene_id}")
            self.current_selected_scene = scene_id
            
            # Send current scene data if available
            if scene_id in self.scene_data:
                emit('scene_data', {
                    'scene_id': scene_id,
                    'data': self.scene_data[scene_id]
                })
                
    def hook_into_analytics(self):
        """Hook into the cluster analytics context to receive data updates"""
        
        # Store original methods
        original_aggregate_detection = self.cluster_context.aggregateDetectionData
        original_publish_clusters = self.cluster_context.publishAllClusters
        
        def enhanced_aggregate_detection(scene_id, detection_data):
            """Enhanced version that also updates WebUI data"""
            # Call original method
            result = original_aggregate_detection(scene_id, detection_data)
            
            # Update WebUI data
            self.update_scene_objects(scene_id, detection_data)
            
            return result
            
        def enhanced_publish_clusters(scene_id, detection_data, all_clusters):
            """Enhanced version that also updates WebUI data"""
            # Call original method
            result = original_publish_clusters(scene_id, detection_data, all_clusters)
            
            # Update WebUI clusters
            self.update_scene_clusters(scene_id, all_clusters)
            
            return result
            
        # Replace methods with enhanced versions
        self.cluster_context.aggregateDetectionData = enhanced_aggregate_detection
        self.cluster_context.publishAllClusters = enhanced_publish_clusters
        
    def update_scene_objects(self, scene_id, detection_data):
        """Update scene objects data for WebUI"""
        scene_name = detection_data.get('name', 'Unknown')
        objects = detection_data.get('objects', [])
        
        # Add scene to available scenes
        self.available_scenes.add(scene_id)
        
        # Update scene data
        self.scene_data[scene_id]['objects'] = objects
        self.scene_data[scene_id]['metadata'] = {
            'name': scene_name,
            'timestamp': time.time(),
            'object_count': len(objects)
        }
        
        log.info(f"WebUI: Updated scene {scene_id} with {len(objects)} objects")
        
        # Broadcast update to WebUI clients
        self.socketio.emit('available_scenes', list(self.available_scenes))
        
        # If this is the currently selected scene, send updated data
        if scene_id == self.current_selected_scene:
            self.socketio.emit('scene_data', {
                'scene_id': scene_id,
                'data': self.scene_data[scene_id]
            })
            
    def update_scene_clusters(self, scene_id, clusters):
        """Update scene clusters data for WebUI"""
        self.scene_data[scene_id]['clusters'] = clusters
        
        log.info(f"WebUI: Updated scene {scene_id} with {len(clusters)} clusters")
        
        # If this is the currently selected scene, send updated clusters
        if scene_id == self.current_selected_scene:
            self.socketio.emit('clusters_update', {
                'scene_id': scene_id,
                'clusters': clusters
            })
            
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask-SocketIO server"""
        log.info(f"Starting WebUI server on {host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
        
    def run_in_thread(self, host='0.0.0.0', port=5000):
        """Run the Flask-SocketIO server in a separate thread"""
        def run_server():
            log.info(f"Starting WebUI server in background on {host}:{port}")
            self.socketio.run(self.app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
            
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        log.info("WebUI server thread started")
        return server_thread