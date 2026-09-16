#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand MapAnything model loader for Scenescape 3D mapping service.
"""

import sys

from scene_common import log

from model_utils import (
    ensure_cache_directories,
    check_model_exists,
    create_success_marker,
    retry_with_exponential_backoff,
)

MODEL_NAME = "mapanything"
MODEL_ID = 'facebook/map-anything-apache'

def download_mapanything_model() -> bool:
  """
  Download MapAnything model using the installed package with automatic retries.

  Returns:
    True if download successful, False otherwise
  """
  def _download_attempt():
    log.info("Downloading MapAnything model...")

    # Add MapAnything to Python path (guard against duplicates across retry attempts)
    mapanything_path = "/workspace/map-anything"
    if mapanything_path not in sys.path:
      sys.path.insert(0, mapanything_path)

    from mapanything.models import MapAnything

    log.info(f'Loading {MODEL_ID}...')

    # This will trigger the download if not cached
    MapAnything.from_pretrained(MODEL_ID)

    log.info('MapAnything (Apache 2.0) model downloaded successfully!')

  try:
    # Retries cover the network download only; marker creation below is a local
    # filesystem write and isn't worth re-downloading the model to retry.
    retry_with_exponential_backoff(_download_attempt)
  except Exception as e:
    log.error(f'Failed to download MapAnything model after retries: {e}')
    return False

  success_message = f'MapAnything model {MODEL_ID} downloaded successfully'
  return create_success_marker(MODEL_NAME, success_message)

def ensure_mapanything_model() -> bool:
  """
  Ensure MapAnything model exists, downloading if necessary.

  Returns:
    True if model is available, False otherwise
  """
  # Ensure cache directories exist
  ensure_cache_directories()

  # Check if model already exists
  if check_model_exists(MODEL_NAME):
    log.info("MapAnything model already downloaded.")
    return True

  # Download the model
  return download_mapanything_model()

def main():
  """Main function for standalone execution."""
  log.info("MapAnything Model Loader")
  log.info("=======================")

  success = ensure_mapanything_model()

  if success:
    log.info("MapAnything model is ready for use!")
    return 0
  else:
    log.error("Failed to ensure MapAnything model is available")
    return 1

if __name__ == "__main__":
  sys.exit(main())
