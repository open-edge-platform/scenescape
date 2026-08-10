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
from datetime import datetime, timezone
from typing import Dict, Any
from werkzeug.utils import secure_filename
import uuid
import threading
import json
import re
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS

from scene_common import log

from mesh_utils import get_mesh_info

RECON_STATUS = {}
RECON_LOCK = threading.Lock()
INIT_STATUS_LOCK = threading.Lock()
INIT_STATUS = {
  "state": "starting",
  "stage": "boot",
  "progress": 0.0,
  "message": "service booting",
  "error": None,
  "updated_at": time.time(),
}

def set_status(request_id: str, **fields):
  with RECON_LOCK:
    cur = RECON_STATUS.get(request_id, {})
    cur.update(fields)
    RECON_STATUS[request_id] = cur

def get_status(request_id: str):
  with RECON_LOCK:
    return RECON_STATUS.get(request_id)

def prune_status(max_age_seconds=3600):
  now = time.time()
  with RECON_LOCK:
    to_delete = [
      rid for rid, st in RECON_STATUS.items()
      if (now - st.get("updated_at", st.get("created_at", now))) > max_age_seconds
    ]
    for rid in to_delete:
      del RECON_STATUS[rid]

def set_init_status(
  state: str,
  stage: str | None = None,
  progress: float | None = None,
  message: str | None = None,
  error: str | None = None,
):
  """Update mapping service initialization state exposed via /health."""
  with INIT_STATUS_LOCK:
    INIT_STATUS["state"] = state
    if stage is not None:
      INIT_STATUS["stage"] = stage
    if progress is not None:
      INIT_STATUS["progress"] = min(100.0, max(0.0, float(progress)))
    if message is not None:
      INIT_STATUS["message"] = message
    INIT_STATUS["error"] = error
    INIT_STATUS["updated_at"] = time.time()


def get_init_status() -> dict[str, Any]:
  """Return a shallow copy of current initialization state."""
  with INIT_STATUS_LOCK:
    return dict(INIT_STATUS)

def _start_status_cleanup_thread():
  def _cleanup_loop():
    while True:
      time.sleep(STATUS_CLEANUP_INTERVAL_SECONDS)
      prune_status()
  t = threading.Thread(target=_cleanup_loop, daemon=True, name="status-cleanup")
  t.start()

# Helper functions for request validation
def validate_reconstruction_request(data):
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
API_PREFIX = "/v1"

# Input validation constants
CAMERA_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
_REQUEST_ID_RE = re.compile(r'^[0-9a-f]{32}$')
MAX_IMAGES = 50
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024   # 20MB per image
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024   # 50MB video

# Status management constants
STATUS_CLEANUP_INTERVAL_SECONDS = 300     # 5 minutes

def initialize_model():
  """Initialize the model - this will be overridden by model-specific services"""
  raise NotImplementedError("This should be overridden by model-specific services")

def run_model_inference(input_data: Dict[str, Any]) -> Dict[str, Any]:
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
      video_frames = loaded_model._frames_from_video_as_base64_dicts(
        video_path=video,
        max_frames=loaded_model._max_frames_for_time_budget(
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
    return loaded_model.run_inference(all_frames)

  except Exception as e:
    log.error(f"Model inference failed: {e}\n{traceback.format_exc()}")
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

@app.route(f"{API_PREFIX}/reconstruction", methods=["POST"])
def reconstruct3D():
  """
  Perform 3D reconstruction from multipart images OR video
  """
  global loaded_model, model_name

  request_id = uuid.uuid4().hex
  start_time = time.time()

  # Create initial status
  set_status(
    request_id,
    state="processing",
    message="queued",
    created_at=time.time(),
    updated_at=time.time(),
  )

  output_format = request.form.get("output_format", "glb")
  mesh_type = request.form.get("mesh_type", "mesh")
  use_keyframes = request.form.get("use_keyframes", True)

  image_files = request.files.getlist("images")
  video_file = request.files.get("video")
  camera_ids = request.form.getlist("camera_ids")
  camera_locations = request.form.getlist("camera_locations", None)

  if (not image_files) and (video_file is None):
    set_status(request_id, state="failed", updated_at=time.time(), error="Provide images and/or video")
    return jsonify({"success": False, "request_id": request_id, "error": "Provide images and/or video"}), 400

  if loaded_model is None:
    set_status(request_id, state="failed", updated_at=time.time(), error=f"Model {model_name} not available")
    return jsonify({"success": False, "request_id": request_id, "error": f"Model {model_name} not available"}), 503

  # Build images payload (base64) in-request
  images = None
  if image_files:
    if len(image_files) > MAX_IMAGES:
      set_status(request_id, state="failed", updated_at=time.time(), error="Invalid input")
      return jsonify({"success": False, "request_id": request_id, "error": f"Too many images (max {MAX_IMAGES})"}), 400

    images = []

    for idx, f in enumerate(image_files):
      if not f or not f.filename:
        continue

      raw = f.read()
      if not raw:
        continue

      if len(raw) > MAX_IMAGE_SIZE_BYTES:
        set_status(request_id, state="failed", updated_at=time.time(), error="Invalid input")
        return jsonify({"success": False, "request_id": request_id, "error": "Image file exceeds size limit"}), 400

      cam_id = camera_ids[idx] if idx < len(camera_ids) else None

      if cam_id and not CAMERA_ID_PATTERN.match(cam_id):
        set_status(request_id, state="failed", updated_at=time.time(), error="Invalid input")
        return jsonify({"success": False, "request_id": request_id, "error": "Invalid camera_id format"}), 400

      cam_loc = None
      if camera_locations and idx < len(camera_locations):
        try:
          cam_loc = json.loads(camera_locations[idx])
        except Exception as e:
          log.warning(
                f"Invalid JSON camera location for camera {idx} | error: {e}"
          )
          cam_loc = None

      images.append({
          "filename": secure_filename(f.filename),
          "camera_id": cam_id,
          "camera_location": cam_loc,   # Only populated if provided
          "data": base64.b64encode(raw).decode("utf-8"),
      })

    if not images:
      set_status(request_id, state="failed", updated_at=time.time(), error="No valid images uploaded")
      return jsonify({"success": False, "request_id": request_id, "error": "No valid images uploaded"}), 400

  # Save video to disk so worker can access it later
  video_path = None
  if video_file:
    uploads_dir = os.getenv("UPLOADS_DIR", "/tmp/uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    os.chmod(uploads_dir, 0o700)
    video_file.stream.seek(0, 2)
    video_size = video_file.stream.tell()
    video_file.stream.seek(0)
    if video_size > MAX_VIDEO_SIZE_BYTES:
      set_status(request_id, state="failed", updated_at=time.time(), error="Invalid input")
      return jsonify({"success": False, "request_id": request_id, "error": "Video file exceeds size limit"}), 400
    filename = secure_filename(video_file.filename or "video.mp4")
    video_path = os.path.join(uploads_dir, f"{request_id}_{filename}")
    video_file.save(video_path)

  inference_payload = {
    "output_format": output_format,
    "mesh_type": mesh_type,
    "images": images,
    "use_keyframes": use_keyframes,
    "video": video_path,
    "_start_time": start_time,
  }

  try:
    validate_reconstruction_request(inference_payload)
  except ValueError as e:
    # Log detailed validation error on the server, but do not expose it to the client
    log.error(f"Reconstruction request validation failed for {request_id}: {e}\n{traceback.format_exc()}")
    generic_error = "Invalid reconstruction request"
    set_status(request_id, state="failed", updated_at=time.time(), error=generic_error)
    return jsonify({"success": False, "request_id": request_id, "error": generic_error}), 400

  # --- Background worker does the heavy work ---
  def worker():
    glb_path = None
    try:
      set_status(request_id, state="processing", updated_at=time.time(), message="running inference")
      result = run_model_inference(inference_payload)

      glb_data = None
      if output_format == "glb":
        set_status(request_id, state="processing", updated_at=time.time(), message="generating glb")
        glb_path = create_glb_file(result, mesh_type)
        with open(glb_path, "rb") as f:
          glb_data = base64.b64encode(f.read()).decode("utf-8")

      processing_time = time.time() - inference_payload["_start_time"]

      final = {
        "success": True,
        "request_id": request_id,
        "glb_data": glb_data,
        "camera_poses": result["camera_poses"],
        "intrinsics": result["intrinsics"],
        "processing_time": processing_time,
        "message": "complete",
      }

      set_status(
        request_id,
        state="complete",
        updated_at=time.time(),
        message="complete",
        processing_time=processing_time,
        result=final,
      )

    except Exception as e:
      set_status(request_id, state="failed", updated_at=time.time(), message="failed", error=str(e))
    finally:
      if glb_path and os.path.exists(glb_path):
        try: os.unlink(glb_path)
        except Exception: pass
      if video_path and os.path.exists(video_path):
        try: os.unlink(video_path)
        except Exception: pass

  threading.Thread(target=worker, daemon=True).start()

  # Return immediately so browser can poll
  return jsonify({"success": True, "request_id": request_id, "state": "processing"}), 200


@app.route(f"{API_PREFIX}/health", methods=["GET"])
def health_check():
  """Health check endpoint with unified readiness contract."""
  global loaded_model, model_name

  model_loaded = loaded_model is not None and loaded_model.is_loaded
  init_status = get_init_status()
  init_state = init_status.get("state")

  # Keep init status synchronized with readiness, regardless of startup mode.
  if model_loaded and init_status.get("state") != "ready":
    set_init_status(
      state="ready",
      stage="model_loaded",
      progress=100.0,
      message="model loaded",
      error=None,
    )
    init_status = get_init_status()

  if model_loaded:
    service_status = "healthy"
    status_code = 200
  elif init_state == "failed":
    service_status = "unhealthy"
    status_code = 503
  else:
    service_status = "degraded"
    status_code = 202

  health_status = {
    "status": service_status,
    "ready": model_loaded,
    "component": "mapping",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "version": "1.0",
    "details": {
      "models": {
        "loaded": model_loaded,
        "active": model_name,
      },
      "runtime": {
        "device": device,
      },
    },
    "model": model_name,
    "model_loaded": model_loaded,
    "device": device,
    "initialization": init_status,
  }

  log.debug(f"Health check: {health_status}")
  return jsonify(health_status), status_code

@app.route(f"{API_PREFIX}/models", methods=["GET"])
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
      "rotation": "quaternion [x, y, z, w]",
      "translation": "vector [x, y, z]",
      "coordinate_system": "OpenCV (camera-to-world transformation, standard CV coordinates)"
    }
  }
  return jsonify(models_data), 200

@app.route(f"{API_PREFIX}/reconstruction/status/<request_id>", methods=["GET"])
def reconstruction_status(request_id):
  if not _REQUEST_ID_RE.match(request_id):
    return jsonify({"success": False, "error": "Invalid request ID"}), 400
  prune_status()
  status = get_status(request_id)
  if not status:
    return jsonify({"success": False, "error": "unknown request_id"}), 404

  safe = {
    "state": status.get("state"),
    "message": status.get("message"),
    "processing_time": status.get("processing_time"),
  }
  if status.get("state") == "complete":
    result = status.get("result", {})
    safe["result"] = {k: v for k, v in result.items() if k != "model"}
  elif status.get("state") == "failed":
    safe["error"] = "Reconstruction failed"

  return jsonify({"success": True, "request_id": request_id, **safe}), 200

# Error handlers
@app.errorhandler(404)
def not_found(error):
  return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
  return jsonify({"success": False, "error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(error):
  # Drain the remaining request body before returning. When a reverse proxy
  # (e.g., Apache) forwards an upload and the backend closes the connection
  # without consuming the body, the proxy sees a connection reset and returns
  # 502 instead of forwarding this 413. Reading and discarding the bytes
  # empties the pipe so the proxy can receive and forward the response cleanly.
  try:
    stream = request.environ.get('wsgi.input')
    if stream is not None:
      cap = request.content_length or (app.config.get('MAX_CONTENT_LENGTH', 0) * 2)
      drained = 0
      while drained < cap:
        chunk = stream.read(min(65536, cap - drained))
        if not chunk:
          break
        drained += len(chunk)
  except Exception:
    pass
  return jsonify({"success": False, "error": "Request too large"}), 413

@app.errorhandler(500)
def internal_server_error(error):
  return jsonify({"success": False, "error": "Internal server error"}), 500

def signal_handler(sig, frame):
  """Handle SIGINT (Ctrl+C) gracefully"""
  log.info("Received SIGINT (Ctrl+C), shutting down gracefully...")
  sys.exit(0)

def run_development_server():
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
    log.error(f"Server error: {e}\n{traceback.format_exc()}")
  finally:
    log.info("Server shutdown complete")

def run_production_server(cert_file=None, key_file=None):
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
    log.error(f"Gunicorn failed to start: {e}\n{traceback.format_exc()}")
    sys.exit(1)
  except KeyboardInterrupt:
    log.info("Server interrupted by user")
  except Exception as e:
    log.error(f"Server error: {e}\n{traceback.format_exc()}")
    sys.exit(1)

def start_app():
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
  signal.signal(signal.SIGINT, signal_handler)
  signal.signal(signal.SIGTERM, signal_handler)

  # Start background status cleanup thread
  _start_status_cleanup_thread()

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
      set_init_status("starting", "model_init_begin", 10.0, "initializing model")
      loaded_model, model_name = initialize_model()
      set_init_status("ready", "model_loaded", 100.0, "model loaded")
      log.info("API Service startup completed successfully")
      run_development_server()
    else:
      # For production server, model will be initialized in each worker via post_fork hook
      # Don't initialize here as Gunicorn will fork workers with separate memory spaces
      set_init_status("starting", "waiting_for_worker", 5.0, "waiting for worker model initialization")
      log.info("API Service starting (model will be initialized in Gunicorn workers)")
      run_production_server(cert_file=args.cert_file, key_file=args.key_file)

  except KeyboardInterrupt:
    log.info("Server interrupted by user")
  except Exception as e:
    set_init_status("failed", "startup_error", 100.0, "startup failed", str(e))
    log.error(f"Server error: {e}")
    raise
  finally:
    log.info("Server shutdown complete")

if __name__ == "__main__":
  start_app()
