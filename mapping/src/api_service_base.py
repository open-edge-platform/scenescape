#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Simplified 3D Mapping API Service
Flask service with build-time model selection (no runtime model parameter needed).
"""

import argparse
import base64
import os
import signal
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any
from werkzeug.utils import secure_filename

from flask import Flask, request, jsonify
from flask_cors import CORS

from scene_common import log

from mesh_utils import getMeshInfo

# Helper functions for request validation
def validateReconstructionRequest(data):
  """Validate reconstruction request data (supports images OR video)"""

  if not isinstance(data, dict):
    raise ValueError("Request must be an object")

  output_format = data.get("output_format", "glb")
  if output_format not in ["glb", "json"]:
    raise ValueError("output_format must be 'glb' or 'json'")

  mesh_type = data.get("mesh_type", "mesh")
  if mesh_type not in ["mesh", "pointcloud"]:
    raise ValueError("mesh_type must be 'mesh' or 'pointcloud'")

  images = data.get("images")
  video = data.get("video")

  if not images and not video:
    raise ValueError("Provide images and/or video")

  if video:
    if not isinstance(video, str) or not video.strip():
      raise ValueError("video must be a non-empty string path")

  if images:
    if not isinstance(images, list) or len(images) == 0:
      raise ValueError("images must be a non-empty list")

    for i, img in enumerate(images):
      if not isinstance(img, dict):
        raise ValueError(f"Image {i} must be an object")
      if "data" not in img:
        raise ValueError(f"Image {i} missing required field: data")
      if not isinstance(img["data"], str) or not img["data"].strip():
        raise ValueError(f"Image {i} data must be a non-empty string")

      if "filename" in img and not isinstance(img["filename"], str):
        raise ValueError(f"Image {i} filename must be a string")

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

def initializeModel():
  """Initialize the model - this will be overridden by model-specific services"""
  raise NotImplementedError("This should be overridden by model-specific services")

def runModelInference(input_data: Dict[str, Any]) -> Dict[str, Any]:
  """
  Run inference using the loaded model.

  Args:
    input_data: Dictionary containing images and/or video path

  Returns:
    Dictionary containing predictions, camera poses, and intrinsics
  """
  global loaded_model

  if loaded_model is None:
    raise RuntimeError("Model not loaded")

  images = input_data.get("images")
  video = input_data.get("video")

  try:
    # Accumulate all frames from both sources
    all_frames = []

    # Add frames from images if provided
    if images:
      all_frames.extend(images)
      log.info(f"Added {len(images)} frames from uploaded images")

    # Extract and add frames from video if provided
    if video:
      use_keyframes = input_data.get("use_keyframes")
      if isinstance(use_keyframes, str):
        use_keyframes = use_keyframes.lower() in ("1", "true", "yes", "y", "on")

      # Extract frames from video using the model's internal method
      video_frames = loaded_model._framesFromVideoAsBase64Dicts(
        video_path=video,
        max_frames=loaded_model._maxFramesForTimeBudget(
          time_budget_seconds=int(os.getenv("GUNICORN_TIMEOUT", "300")),
          overhead=30
        ),
        use_keyframes=use_keyframes,
      )
      all_frames.extend(video_frames)
      log.info(f"Added {len(video_frames)} frames from video")

    if not all_frames:
      raise RuntimeError("No frames available for inference")

    log.info(f"Running inference on {len(all_frames)} total frames")
    return loaded_model.runInference(all_frames)

  except Exception as e:
    log.error(f"Model inference failed: {e}")
    raise RuntimeError(f"Model inference failed: {e}")

def createGlbFile(result: Dict[str, Any], mesh_type: str = "mesh") -> str:
  """Create GLB file from model results and return file path"""
  global loaded_model

  temp_glb_fd, temp_glb_path = tempfile.mkstemp(suffix=".glb")

  try:
    # Use the model's createOutput method
    scene_3d = loaded_model.createOutput(result, output_format=mesh_type)
    scene_3d.export(temp_glb_path)

    mesh_info = getMeshInfo(scene_3d)
    log.info(f"GLB created: {mesh_info}")

    return temp_glb_path

  except Exception as e:
    if os.path.exists(temp_glb_path):
      os.unlink(temp_glb_path)
    raise RuntimeError(f"Failed to create GLB file: {e}")

  finally:
    os.close(temp_glb_fd)

@app.route("/reconstruction", methods=["POST"])
def reconstruct3D():
  """
  Perform 3D reconstruction from multipart images OR video
  """
  global loaded_model, model_name

  start_time = time.time()
  glb_path = None
  video_path = None

  try:
    output_format = request.form.get("output_format", "glb")
    mesh_type = request.form.get("mesh_type", "mesh")
    use_keyframes = request.form.get("use_keyframes", True)

    image_files = request.files.getlist("images")
    video_file = request.files.get("video")

    if (not image_files) and (video_file is None):
      return jsonify({"error": "Provide images and/or video"}), 400

    # Validate model availability
    if loaded_model is None:
      log.error(f"Model {model_name} not available")
      return jsonify({"error": f"Model {model_name} not available"}), 503

    # Run inference
    images = None

    if image_files:
      images = []
      for f in image_files:
        if not f or not f.filename:
          continue
        raw = f.read()
        if not raw:
          continue
        images.append({
          "filename": secure_filename(f.filename),
          "data": base64.b64encode(raw).decode("utf-8"),
        })

      if not images:
        return jsonify({"error": "No valid images uploaded"}), 400

      log.info(f"Received reconstruction request: model={model_name}, images={len(images)}, format={output_format}")

    if video_file:
      # Video path: save to a temp file and pass the path (recommended for video)
      uploads_dir = os.getenv("UPLOADS_DIR", "/tmp/uploads")
      os.makedirs(uploads_dir, exist_ok=True)

      filename = secure_filename(video_file.filename or "video.mp4")
      video_path = os.path.join(uploads_dir, filename)
      video_file.save(video_path)
      log.info(f"Received reconstruction request: model={model_name}, video={filename}, format={output_format}")

    inference_payload = {
      "output_format": output_format,
      "mesh_type": mesh_type,
      "images": images,
      "use_keyframes": use_keyframes,
      "video": video_path,
    }

    try:
      validateReconstructionRequest(inference_payload)
    except ValueError as e:
      log.error(f"Request validation failed: {e}")
      return jsonify({"error": "Request validation failed"}), 400

    log.info(f"Starting {model_name} inference...")
    result = runModelInference(inference_payload)

    # Generate GLB file if requested
    glb_data = None
    if output_format == "glb":
      log.info("Generating GLB file...")
      glb_path = createGlbFile(result, mesh_type)

      # Read GLB file and encode as base64
      with open(glb_path, "rb") as f:
        glb_bytes = f.read()
        glb_data = base64.b64encode(glb_bytes).decode('utf-8')

      log.info(f"GLB file generated successfully ({len(glb_bytes)} bytes)")

    processing_time = time.time() - start_time
    log.info(f"Request completed successfully in {processing_time:.2f} seconds")

    # Build message based on what was provided
    parts = []
    if isinstance(images, list) and images:
      parts.append(f"{len(images)} images")
    if video_path:
      parts.append("video")
    input_description = " and ".join(parts)

    response_data = {
      "success": True,
      "model": model_name,  # Inform client which model was used
      "glb_data": glb_data,
      "camera_poses": result["camera_poses"],  # Camera-to-world transformations (rotation as quaternion [w,x,y,z], translation as [x,y,z])
      "intrinsics": result["intrinsics"],  # Scaled for original image dimensions
      "processing_time": processing_time,
      "message": f"Successfully processed {input_description} with {model_name}"
    }
    return jsonify(response_data), 200

  finally:
    # Clean up temporary files
    if glb_path and os.path.exists(glb_path):
      os.unlink(glb_path)

@app.route("/health", methods=["GET"])
def healthCheck():
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
def listModels():
  """List the available model and its status"""
  global loaded_model, model_name

  model_info = None
  if loaded_model is not None:
    model_info = loaded_model.getModelInfo()

  models_data = {
    "model": model_name,
    "model_info": model_info,
    "camera_pose_format": {
      "rotation": "quaternion [x, y, z, w]",
      "translation": "vector [x, y, z]",
      "coordinate_system": "OpenCV (camera-to-world transformation, standard CV coordinates)"
    }
  }
  return jsonify(models_data), 200

# Error handlers
@app.errorhandler(404)
def notFound(error):
  return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def methodNotAllowed(error):
  return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(413)
def requestEntityTooLarge(error):
  return jsonify({"error": "Request too large"}), 413

@app.errorhandler(500)
def internalServerError(error):
  return jsonify({"error": "Internal server error"}), 500

def signalHandler(sig, frame):
  """Handle SIGINT (Ctrl+C) gracefully"""
  log.info("Received SIGINT (Ctrl+C), shutting down gracefully...")
  sys.exit(0)

def runDevelopmentServer():
  """Run Flask development server"""
  log.info("Starting in DEVELOPMENT mode...")
  log.info("Flask development server starting on https://0.0.0.0:8444")
  log.info("Press Ctrl+C to stop the server")

  try:
    # Run Flask development server
    app.run(
      host="0.0.0.0",
      port=8444,
      debug=False,
      threaded=True
    )
  except KeyboardInterrupt:
    log.info("Server interrupted by user")
  except Exception as e:
    log.error(f"Server error: {e}")
  finally:
    log.info("Server shutdown complete")

def runProductionServer(cert_file=None, key_file=None):
  """Run Gunicorn production server with TLS"""
  log.info("Starting in PRODUCTION mode with TLS...")

  # Check if certificates exist
  if not os.path.exists(cert_file):
    log.error(f"TLS certificate file not found: {cert_file}")
    sys.exit(1)

  if not os.path.exists(key_file):
    log.error(f"TLS key file not found: {key_file}")
    sys.exit(1)

  log.info(f"Using TLS certificate: {cert_file}")
  log.info(f"Using TLS key: {key_file}")
  log.info("Gunicorn HTTPS server starting on https://0.0.0.0:8444")

  # Determine the service module based on model type
  model_type = os.getenv("MODEL_TYPE", "mapanything")
  service_module = f"{model_type}_service:app"

  # Get the directory where this script is located
  script_dir = os.path.dirname(os.path.abspath(__file__))
  gunicorn_config = os.path.join(script_dir, "gunicorn_config.py")

  # Gunicorn command arguments
  gunicorn_cmd = [
    "gunicorn",
    "--bind", "0.0.0.0:8444",
    "--workers", "1",
    "--worker-class", "sync",
    "--timeout", os.getenv("GUNICORN_TIMEOUT", "300"),
    "--keep-alive", "5",
    "--max-requests", "1000",
    "--max-requests-jitter", "100",
    "--access-logfile", "-",
    "--error-logfile", "-",
    "--log-level", "info",
    "--certfile", cert_file,
    "--keyfile", key_file,
    "--config", gunicorn_config,
    service_module
  ]

  log.info(f"Starting Gunicorn with service module: {service_module}")
  log.info(f"Using Gunicorn config: {gunicorn_config}")

  try:
    # Run Gunicorn with TLS
    # Note: We don't initialize the model here because Gunicorn will fork workers
    # and each worker needs to initialize the model in its own process via post_fork hook
    subprocess.run(gunicorn_cmd, check=True)
  except subprocess.CalledProcessError as e:
    log.error(f"Gunicorn failed to start: {e}")
    sys.exit(1)
  except KeyboardInterrupt:
    log.info("Server interrupted by user")
  except Exception as e:
    log.error(f"Server error: {e}")
    sys.exit(1)

def startApp():
  """Start the application with command line argument parsing"""
  parser = argparse.ArgumentParser(description="3D Mapping Models API Server")
  parser.add_argument(
    "--dev-mode",
    action="store_true",
    help="Run in development mode with Flask development server (default: production mode with Gunicorn + TLS)"
  )
  parser.add_argument(
    "--development",
    action="store_true",
    help="Alias for --dev-mode"
  )
  parser.add_argument(
    "--cert-file",
    default="/run/secrets/certs/scenescape-mapping.crt",
    help="Path to TLS certificate file (default: /run/secrets/certs/scenescape-mapping.crt)"
  )
  parser.add_argument(
    "--key-file",
    default="/run/secrets/certs/scenescape-mapping.key",
    help="Path to TLS private key file (default: /run/secrets/certs/scenescape-mapping.key)"
  )

  args = parser.parse_args()

  # Set up signal handler for graceful shutdown
  signal.signal(signal.SIGINT, signalHandler)
  signal.signal(signal.SIGTERM, signalHandler)

  log.info("Starting 3D Mapping API server...")

  # Determine which server to run
  dev_mode = args.dev_mode or args.development or os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")

  # Initialize model before starting server
  global device, loaded_model, model_name
  device = "cpu"
  log.info(f"Using device: {device}")

  try:
    if dev_mode:
      # For development server, initialize model here (single process)
      loaded_model, model_name = initializeModel()
      log.info("API Service startup completed successfully")
      runDevelopmentServer()
    else:
      # For production server, model will be initialized in each worker via post_fork hook
      # Don't initialize here as Gunicorn will fork workers with separate memory spaces
      log.info("API Service starting (model will be initialized in Gunicorn workers)")
      runProductionServer(cert_file=args.cert_file, key_file=args.key_file)

  except KeyboardInterrupt:
    log.info("Server interrupted by user")
  except Exception as e:
    log.error(f"Server error: {e}")
    raise
  finally:
    log.info("Server shutdown complete")

if __name__ == "__main__":
  startApp()
