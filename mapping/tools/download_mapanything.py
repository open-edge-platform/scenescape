#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand MapAnything model loader for Scenescape 3D mapping service.
"""

import os
import sys

from scene_common import log

from model_utils import ensure_cache_directories, check_model_exists, create_success_marker

MODEL_NAME = "mapanything"

def download_mapanything_model() -> bool:
  """
  Download MapAnything model using the installed package.

  Returns:
    True if download successful, False otherwise
  """
  try:
    log.info("Downloading MapAnything model...")

    # Add MapAnything to Python path
    mapanything_path = "/workspace/map-anything"
    sys.path.insert(0, str(mapanything_path))

    from mapanything.models import MapAnything

    # Try Apache 2.0 licensed model first
    model_name = 'facebook/map-anything-apache'
    log.info(f'Loading {model_name}...')

    # Cache first: an offline edge node with seeded volumes must not reach
    # for the Hub (which stalls or fails); only download on a real cache miss.
    try:
      model = MapAnything.from_pretrained(model_name, local_files_only=True)
      log.info('MapAnything weights found in the local Hugging Face cache')
    except Exception as cache_miss:  # noqa: BLE001
      if os.environ.get('HF_HUB_OFFLINE', '').strip().lower() in ('1', 'true', 'yes'):
        raise RuntimeError(f'{model_name} not cached and HF_HUB_OFFLINE is set') from cache_miss
      model = MapAnything.from_pretrained(model_name)

    # Create success marker
    success_message = f'MapAnything model {model_name} downloaded successfully'
    if not create_success_marker(MODEL_NAME, success_message):
      return False

    log.info('MapAnything (Apache 2.0) model downloaded successfully!')
    return True

  except Exception as e:
    log.error(f'Failed to download MapAnything model: {e}')
    return False

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
