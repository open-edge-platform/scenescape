#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Gunicorn configuration file with post_fork hook to initialize model in each worker
"""

from scene_common import log

def on_starting(server):
  """Called just before the master process is initialized."""
  log.info("Gunicorn master process starting...")

def post_fork(server, worker):
  """Called just after a worker has been forked."""
  import os

  # Import here to avoid circular imports and ensure we're in the worker process
  import api_service_base

  log.info(f"Worker {worker.pid} forked, initializing model...")

  try:
    # Import the service-specific module to ensure initializeModel is overridden
    # This is necessary because the service module overrides initializeModel in api_service_base
    model_type = os.getenv("MODEL_TYPE", "mapanything")
    service_module_name = f"{model_type}_service"

    log.info(f"Worker {worker.pid} importing service module: {service_module_name}")
    __import__(service_module_name)

    # Initialize model in this worker process
    # Set device in the module
    api_service_base.device = "cpu"
    log.info(f"Worker {worker.pid} using device: {api_service_base.device}")

    # Only initialize if not already loaded (defensive check)
    if api_service_base.loaded_model is None:
      loaded_model, model_name = api_service_base.initializeModel()
      api_service_base.loaded_model = loaded_model
      api_service_base.model_name = model_name
      log.info(f"Worker {worker.pid} model initialization completed successfully")
    else:
      log.info(f"Worker {worker.pid} model already initialized")

  except Exception as e:
    log.error(f"Worker {worker.pid} failed to initialize model: {e}")
    # Don't exit here - let Gunicorn handle worker failures
    raise

def worker_int(worker):
  """Called when a worker receives INT or QUIT signal."""
  log.info(f"Worker {worker.pid} received INT/QUIT signal")

def pre_fork(server, worker):
  """Called just before a worker is forked."""
  log.debug(f"About to fork worker")

