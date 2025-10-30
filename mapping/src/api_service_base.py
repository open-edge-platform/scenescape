#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Simplified 3D Mapping API Service
Flask service with build-time model selection (no runtime model parameter needed).
"""

import base64
import os
import signal
import sys
import tempfile
import time
from typing import Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

from scene_common import log

from mesh_utils import get_mesh_info

# Helper functions for request validation
def validate_reconstruction_request(data):
    """Validate reconstruction request data"""
    if not isinstance(data, dict):
        raise ValueError("Request must be a JSON object")

    # Check required fields (model_type is no longer needed)
    if 'images' not in data:
        raise ValueError("Missing required field: images")

    # Validate images
    if not isinstance(data['images'], list) or len(data['images']) == 0:
        raise ValueError("Images must be a non-empty list")

    # Validate output format
    output_format = data.get('output_format', 'glb')
    if output_format not in ['glb', 'json']:
        raise ValueError("output_format must be 'glb' or 'json'")

    # Validate mesh type
    mesh_type = data.get('mesh_type', 'mesh')
    if mesh_type not in ['mesh', 'pointcloud']:
        raise ValueError("mesh_type must be 'mesh' or 'pointcloud'")

    # Validate each image
    for i, img in enumerate(data['images']):
        if not isinstance(img, dict):
            raise ValueError(f"Image {i} must be an object")
        if 'data' not in img:
            raise ValueError(f"Image {i} missing required field: data")
        if not isinstance(img['data'], str):
            raise ValueError(f"Image {i} data must be a string")

    return True

# Global variables for device and loaded model
device = "cpu"
loaded_model = None
model_name = None

# Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure Flask app
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max request size

def initialize_model():
    """Initialize the model - this will be overridden by model-specific services"""
    raise NotImplementedError("This should be overridden by model-specific services")

def run_model_inference(images: list) -> Dict[str, Any]:
    """
    Run inference using the loaded model.

    Args:
        images: List of image dictionaries

    Returns:
        Dictionary containing predictions, camera poses, and intrinsics
    """
    global loaded_model

    if loaded_model is None:
        raise RuntimeError("Model not loaded")

    try:
        result = loaded_model.run_inference(images)
        return result

    except Exception as e:
        log.error(f"Model inference failed: {e}")
        raise RuntimeError(f"Model inference failed: {e}")

def create_glb_file(result: Dict[str, Any], mesh_type: str = "mesh") -> str:
    """Create GLB file from model results and return file path"""
    global loaded_model

    temp_glb_fd, temp_glb_path = tempfile.mkstemp(suffix=".glb")

    try:
        # Use the model's create_output method
        scene_3d = loaded_model.create_output(result, output_format=mesh_type)
        scene_3d.export(temp_glb_path)

        mesh_info = get_mesh_info(scene_3d)
        log.info(f"GLB created: {mesh_info}")

        return temp_glb_path

    except Exception as e:
        if os.path.exists(temp_glb_path):
            os.unlink(temp_glb_path)
        raise RuntimeError(f"Failed to create GLB file: {e}")

    finally:
        os.close(temp_glb_fd)

@app.route("/reconstruct", methods=["POST"])
def reconstruct_3d():
    """
    Perform 3D reconstruction from input images
    """
    global loaded_model, model_name

    start_time = time.time()
    glb_path = None

    try:
        # Get JSON data from request
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        data = request.get_json()

        # Validate request
        try:
            validate_reconstruction_request(data)
        except ValueError as e:
            log.error(f"Request validation failed: {e}")
            return jsonify({"Request validation failed"}), 400

        images = data["images"]
        output_format = data.get("output_format", "glb")
        mesh_type = data.get("mesh_type", "mesh")

        log.info(f"Received reconstruction request: model={model_name}, images={len(images)}, format={output_format}")

        # Validate model availability
        if loaded_model is None:
            log.error(f"Model {model_name} not available")
            return jsonify({"error": f"Model {model_name} not available"}), 503

        # Run inference
        log.info(f"Starting {model_name} inference...")
        result = run_model_inference(images)

        # Generate GLB file if requested
        glb_data = None
        if output_format == "glb":
            log.info("Generating GLB file...")
            glb_path = create_glb_file(result, mesh_type)

            # Read GLB file and encode as base64
            with open(glb_path, "rb") as f:
                glb_bytes = f.read()
                glb_data = base64.b64encode(glb_bytes).decode('utf-8')
            log.info(f"GLB file generated successfully ({len(glb_bytes)} bytes)")

        processing_time = time.time() - start_time
        log.info(f"Request completed successfully in {processing_time:.2f} seconds")

        response_data = {
            "success": True,
            "model": model_name,  # Inform client which model was used
            "glb_data": glb_data,
            "camera_poses": result["camera_poses"],  # Camera-to-world transformations (rotation as quaternion [w,x,y,z], translation as [x,y,z])
            "intrinsics": result["intrinsics"],      # Scaled for original image dimensions
            "processing_time": processing_time,
            "message": f"Successfully processed {len(images)} images with {model_name}"
        }

        return jsonify(response_data), 200

    except Exception as e:
        processing_time = time.time() - start_time
        log.error(f"Reconstruction failed after {processing_time:.2f} seconds: {str(e)}")
        return jsonify({
            "error": f"Reconstruction failed due to internal error",
            "processing_time": processing_time
        }), 500

    finally:
        # Clean up temporary files
        if glb_path and os.path.exists(glb_path):
            os.unlink(glb_path)

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    global loaded_model, model_name

    health_status = {
        "status": "healthy",
        "model": model_name,
        "model_loaded": loaded_model is not None and loaded_model.is_loaded,
        "device": device,
    }

    log.debug(f"Health check: {health_status}")
    return jsonify(health_status), 200

@app.route("/models", methods=["GET"])
def list_models():
    """List the available model and its status"""
    global loaded_model, model_name

    model_info = None
    if loaded_model is not None:
        model_info = loaded_model.get_model_info()

    models_data = {
        "model": model_name,
        "model_info": model_info,
        "camera_pose_format": {
            "rotation": "quaternion [w, x, y, z]",
            "translation": "vector [x, y, z]",
            "coordinate_system": "OpenCV (camera-to-world transformation, standard CV coordinates)"
        }
    }
    return jsonify(models_data), 200

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "Request too large"}), 413

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({"error": "Internal server error"}), 500

def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) gracefully"""
    log.info("Received SIGINT (Ctrl+C), shutting down gracefully...")
    sys.exit(0)

def start_app():
    """Start the application with model initialization"""
    global device, loaded_model, model_name

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log.info("Starting 3D Mapping API server...")

    # Initialize model before starting server
    device = "cpu"
    log.info(f"Using device: {device}")

    try:
        loaded_model, model_name = initialize_model()
        log.info("API Service startup completed successfully")

        log.info("Flask server starting on http://0.0.0.0:8000")
        log.info("Press Ctrl+C to stop the server")

        # Run Flask development server
        app.run(
            host="0.0.0.0",
            port=8000,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        log.info("Server interrupted by user")
    except Exception as e:
        log.error(f"Server error: {e}")
        raise
    finally:
        log.info("Server shutdown complete")

if __name__ == "__main__":
    start_app()