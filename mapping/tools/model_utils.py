#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Common utilities for model loading in Scenescape 3D mapping service.
"""

import os
import time
from pathlib import Path
from typing import Callable, TypeVar

from scene_common import log

T = TypeVar('T')

MODEL_DIR = os.getenv("MODEL_DIR", "/workspace/model_weights")

# Retry configuration defaults - can be overridden when calling retry_with_exponential_backoff
DEFAULT_MAX_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_INITIAL_WAIT_SECONDS = 2

def get_model_weights_dir() -> Path:
  """Get the model weights directory."""
  model_dir = Path(MODEL_DIR)
  if not model_dir.exists():
    log.error(f"Model weights directory does not exist: {model_dir}")
    exit(1)
  return model_dir

def ensure_cache_directories():
  """Check that all required cache directories exist."""
  cache_dirs = [
    Path("/workspace/.cache/torch"),
    Path("/workspace/.cache/huggingface"),
    get_model_weights_dir()
  ]

  missing_dirs = []
  for cache_dir in cache_dirs:
    if not cache_dir.exists():
      missing_dirs.append(str(cache_dir))

  if missing_dirs:
    log.error(f"Required cache directories do not exist: {', '.join(missing_dirs)}")
    exit(1)

def check_model_exists(model_name: str) -> bool:
  """
  Check if a model has been successfully downloaded.

  Args:
    model_name: Name of the model (e.g., 'mapanything', 'vggt')

  Returns:
    True if model exists and is ready
  """
  marker_file = get_model_weights_dir() / f"{model_name}_downloaded.txt"
  return marker_file.exists()

def create_success_marker(model_name: str, message: str) -> bool:
  """
  Create a success marker file for a model.

  Args:
    model_name: Name of the model
    message: Success message to write

  Returns:
    True if marker was created successfully
  """
  try:
    marker_file = get_model_weights_dir() / f"{model_name}_downloaded.txt"
    with open(marker_file, 'w') as f:
      f.write(message)
    return True
  except Exception as e:
    log.error(f"Failed to create success marker for {model_name}: {e}")
    return False

def retry_with_exponential_backoff(
    func: Callable[..., T],
    max_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS,
    initial_wait_seconds: int = DEFAULT_RETRY_INITIAL_WAIT_SECONDS
) -> T:
  """
  Retry a function with exponential backoff for transient failures.

  Args:
    func: Function to retry
    max_attempts: Maximum number of attempts
    initial_wait_seconds: Initial wait time before first retry

  Returns:
    Result of the function if successful

  Raises:
    ValueError: If max_attempts is less than 1
    Exception: Re-raises the last exception if all attempts fail
  """
  if max_attempts < 1:
    raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

  last_exception = None
  wait_seconds = initial_wait_seconds

  for attempt in range(1, max_attempts + 1):
    try:
      log.info(f"Attempt {attempt}/{max_attempts}...")
      return func()
    except Exception as e:
      last_exception = e
      if attempt < max_attempts:
        log.warning(f"Attempt {attempt} failed: {e}. Retrying in {wait_seconds}s...")
        time.sleep(wait_seconds)
        wait_seconds *= 2  # Exponential backoff
      else:
        log.error(f"All {max_attempts} attempts failed. Last error: {e}")

  if last_exception is not None:
    raise last_exception
