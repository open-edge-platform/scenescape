#!/usr/bin/env python3

"""
Mapping Models REST API Service
Flask service that provides endpoints for 3D reconstruction using pluggable model architecture.
"""

import base64
import logging
import os
import signal
import sys
import tempfile
import time
from typing import Dict, Any

import numpy as np
from scipy.spatial.transform import Rotation

from flask import Flask, request, jsonify
from flask_cors import CORS

# Configure logging for Docker environment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import plugin architecture components
from model_registry import get_available_models, load_model, get_models_status
from mesh_utils import get_mesh_info

# Import model plugins to register them
import mapanything_model
import vggt_model



# Helper functions for request validation
def validate_reconstruction_request(data):
    """Validate reconstruction request data"""
    if not isinstance(data, dict):
        raise ValueError("Request must be a JSON object")
    
    # Check required fields
    if 'images' not in data:
        raise ValueError("Missing required field: images")
    if 'model_type' not in data:
        raise ValueError("Missing required field: model_type")
    
    # Validate images
    if not isinstance(data['images'], list) or len(data['images']) == 0:
        raise ValueError("Images must be a non-empty list")
    
    # Validate model type - use dynamic model list from registry
    available_models = get_available_models()
    if data['model_type'] not in available_models:
        raise ValueError(f"model_type must be one of: {available_models}")
    
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

# Global variables for device and loaded models cache
device = "cpu"
loaded_models_cache = {}

# Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure Flask app
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max request size

def initialize_models():
    """Initialize all registered models on startup"""
    global device, loaded_models_cache
    
    device = "cpu"
    logger.info(f"Using device: {device}")
    
    try:
        available_models = get_available_models()
        logger.info(f"Available models: {available_models}")
        
        # Load all models during startup
        for model_id in available_models:
            logger.info(f"Loading {model_id} model...")
            model_instance = load_model(model_id, device)
            loaded_models_cache[model_id] = model_instance
            logger.info(f"{model_id} model loaded successfully")
        
        logger.info("All models initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing models: {e}")
        raise

# Initialize models when module is imported
def init_app():
    """Initialize models on startup"""
    logger.info("Starting up 3D Mapping Models API Service...")
    try:
        initialize_models()
        logger.info("API Service startup completed successfully")
    except Exception as e:
        logger.error(f"Failed to start API service: {e}")
        raise

def get_model_instance(model_id: str):
    """Get a loaded model instance from the cache."""
    if model_id not in loaded_models_cache:
        raise ValueError(f"Model {model_id} not loaded. Available models: {list(loaded_models_cache.keys())}")
    return loaded_models_cache[model_id]

def run_model_inference(model_id: str, images: list) -> Dict[str, Any]:
    """
    Run inference using the plugin architecture.
    
    Args:
        model_id: ID of the model to use
        images: List of image dictionaries
    
    Returns:
        Dictionary containing predictions, camera poses, and intrinsics
    """
    try:
        model_instance = get_model_instance(model_id)
        result = model_instance.run_inference(images)
        return result
        
    except Exception as e:
        logger.error(f"Model {model_id} inference failed: {e}")
        raise RuntimeError(f"Model {model_id} inference failed: {e}")

def create_glb_file(result: Dict[str, Any], model: 'ReconstructionModel', mesh_type: str = "mesh") -> str:
    """Create GLB file from model results and return file path using plugin architecture"""
    temp_glb_path = tempfile.mktemp(suffix=".glb")
    
    try:
        # Use the model's create_output method
        scene_3d = model.create_output(result, output_format=mesh_type)
        scene_3d.export(temp_glb_path)
        
        mesh_info = get_mesh_info(scene_3d)
        logger.info(f"GLB created: {mesh_info}")
        
        return temp_glb_path
        
    except Exception as e:
        if os.path.exists(temp_glb_path):
            os.unlink(temp_glb_path)
        raise RuntimeError(f"Failed to create GLB file: {e}")

def transform_to_opencv_coordinate_system(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform model outputs to OpenCV coordinate system for consistent API output.
    
    This ensures all models output data in the same coordinate convention:
    - Standard computer vision: X:right, Y:down, Z:forward -> OpenCV: X:right, Y:down, Z:forward
    - The transformation is applied to both camera poses and any world points in predictions
    
    Args:
        result: Raw model result containing camera_poses, intrinsics, and predictions
        
    Returns:
        Result with coordinate system aligned to OpenCV convention
    """
    # Note: Currently models already output in standard CV coordinate system
    # This function serves as a placeholder for future coordinate system standardization
    # and ensures consistent API behavior regardless of underlying model conventions
    
    # For now, return the result as-is since models use standard CV coordinates
    # Future models with different coordinate systems can be transformed here
    return result

@app.route("/reconstruct", methods=["POST"])
def reconstruct_3d():
    """
    Perform 3D reconstruction from input images
    """
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
            logger.error(f"Request validation failed: {e}")
            return jsonify({"error": str(e)}), 400
        
        model_type = data["model_type"]
        images = data["images"]
        output_format = data.get("output_format", "glb")
        mesh_type = data.get("mesh_type", "mesh")
        
        logger.info(f"Received reconstruction request: model={model_type}, images={len(images)}, format={output_format}")
        
        # Validate model availability
        if model_type not in loaded_models_cache:
            logger.error(f"Model {model_type} not available")
            return jsonify({"error": f"Model {model_type} not available"}), 503
        
        # Run inference using plugin architecture
        logger.info(f"Starting {model_type} inference...")
        result = run_model_inference(model_type, images)
        
        # Apply coordinate system transformation to ensure consistent API output
        result = transform_to_opencv_coordinate_system(result)
        
        logger.info(f"Inference completed in {time.time() - start_time:.2f} seconds")
        
        # Generate GLB file if requested
        glb_data = None
        if output_format == "glb":
            logger.info("Generating GLB file...")
            # Get model instance for output generation
            model = loaded_models_cache[model_type]
            glb_path = create_glb_file(result, model, mesh_type)
            
            # Read GLB file and encode as base64
            with open(glb_path, "rb") as f:
                glb_bytes = f.read()
                glb_data = base64.b64encode(glb_bytes).decode('utf-8')
            logger.info(f"GLB file generated successfully ({len(glb_bytes)} bytes)")
        
        processing_time = time.time() - start_time
        logger.info(f"Request completed successfully in {processing_time:.2f} seconds")
        
        response_data = {
            "success": True,
            "glb_data": glb_data,
            "camera_poses": result["camera_poses"],  # Camera-to-world transformations (rotation as quaternion [w,x,y,z], translation as [x,y,z])
            "intrinsics": result["intrinsics"],      # Scaled for original image dimensions
            "processing_time": processing_time,
            "message": f"Successfully processed {len(images)} images with {model_type}"
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Reconstruction failed after {processing_time:.2f} seconds: {str(e)}")
        return jsonify({
            "error": f"Reconstruction failed: {str(e)}",
            "processing_time": processing_time
        }), 500
    
    finally:
        # Clean up temporary files
        if glb_path and os.path.exists(glb_path):
            os.unlink(glb_path)

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    models_status = get_models_status()
    health_status = {
        "status": "healthy",
        "models": {model_id: info["loaded"] for model_id, info in models_status.items()},
        "device": device,
    }
    
    logger.debug(f"Health check: {health_status}")
    return jsonify(health_status), 200

@app.route("/models", methods=["GET"])
def list_models():
    """List available models and their status"""
    models_status = get_models_status()
    
    models_data = {
        "available_models": get_available_models(),
        "model_status": models_status,
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
    logger.info("Received SIGINT (Ctrl+C), shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting 3D Mapping Models API server...")
    
    # Initialize models before starting server
    init_app()
    
    logger.info("Flask server starting on http://0.0.0.0:8000")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        # Run Flask development server
        app.run(
            host="0.0.0.0",
            port=8000,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("Server shutdown complete")