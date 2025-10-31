#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Common utilities for model loading in SceneScape 3D mapping service.
"""

import os
from pathlib import Path

from scene_common import log

MODEL_DIR = os.getenv("MODEL_DIR", "/workspace/model_weights")

def getModelWeightsDir() -> Path:
  """Get the model weights directory."""
  model_dir = Path(MODEL_DIR)
  if not model_dir.exists():
    log.error(f"Model weights directory does not exist: {model_dir}")
    exit(1)
  return model_dir

def ensureCacheDirectories():
  """Check that all required cache directories exist."""
  cache_dirs = [
    Path("/workspace/.cache/torch"),
    Path("/workspace/.cache/huggingface"),
    getModelWeightsDir()
  ]

  missing_dirs = []
  for cache_dir in cache_dirs:
    if not cache_dir.exists():
      missing_dirs.append(str(cache_dir))

  if missing_dirs:
    log.error(f"Required cache directories do not exist: {', '.join(missing_dirs)}")
    exit(1)

def checkModelExists(model_name: str) -> bool:
  """
  Check if a model has been successfully downloaded.

  Args:
    model_name: Name of the model (e.g., 'mapanything', 'vggt')

  Returns:
    True if model exists and is ready
  """
  marker_file = getModelWeightsDir() / f"{model_name}_downloaded.txt"
  return marker_file.exists()

def createSuccessMarker(model_name: str, message: str) -> bool:
  """
  Create a success marker file for a model.

  Args:
    model_name: Name of the model
    message: Success message to write

  Returns:
    True if marker was created successfully
  """
  try:
    marker_file = getModelWeightsDir() / f"{model_name}_downloaded.txt"
    with open(marker_file, 'w') as f:
      f.write(message)
    return True
  except Exception as e:
    log.error(f"Failed to create success marker for {model_name}: {e}")
    return False
