#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand MapAnything model loader for SceneScape 3D mapping service.
"""

import sys

from scene_common import log

from model_utils import ensureCacheDirectories, checkModelExists, createSuccessMarker

MODEL_NAME = "mapanything"

def downloadMapanythingModel() -> bool:
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

    # This will trigger the download if not cached
    model = MapAnything.from_pretrained(model_name)

    # Create success marker
    success_message = f'MapAnything model {model_name} downloaded successfully'
    if not createSuccessMarker(MODEL_NAME, success_message):
      return False

    log.info('MapAnything (Apache 2.0) model downloaded successfully!')
    return True

  except Exception as e:
    log.error(f'Failed to download MapAnything model: {e}')
    return False

def ensureMapanythingModel() -> bool:
  """
  Ensure MapAnything model exists, downloading if necessary.

  Returns:
    True if model is available, False otherwise
  """
  # Ensure cache directories exist
  ensureCacheDirectories()

  # Check if model already exists
  if checkModelExists(MODEL_NAME):
    log.info("MapAnything model already downloaded.")
    return True

  # Download the model
  return downloadMapanythingModel()

def main():
  """Main function for standalone execution."""
  log.info("MapAnything Model Loader")
  log.info("=======================")

  success = ensureMapanythingModel()

  if success:
    log.info("MapAnything model is ready for use!")
    return 0
  else:
    log.error("Failed to ensure MapAnything model is available")
    return 1

if __name__ == "__main__":
  sys.exit(main())
