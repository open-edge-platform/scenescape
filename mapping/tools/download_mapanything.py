#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand MapAnything model loader for SceneScape 3D mapping service.
"""

import sys
import logging
from pathlib import Path
from model_utils import get_scenescape_home, ensure_cache_directories, check_model_exists, create_success_marker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = "mapanything"

def download_mapanything_model() -> bool:
    """
    Download MapAnything model using the installed package.
    
    Returns:
        True if download successful, False otherwise
    """
    try:
        logger.info("Downloading MapAnything model...")
        
        # Add MapAnything to Python path
        mapanything_path = "/workspace/map-anything"
        sys.path.insert(0, str(mapanything_path))
        
        from mapanything.models import MapAnything
        
        # Try Apache 2.0 licensed model first
        model_name = 'facebook/map-anything-apache'
        logger.info(f'Loading {model_name}...')
        
        # This will trigger the download if not cached
        model = MapAnything.from_pretrained(model_name)
        
        # Create success marker
        success_message = f'MapAnything model {model_name} downloaded successfully'
        if not create_success_marker(MODEL_NAME, success_message):
            return False
        
        logger.info('MapAnything (Apache 2.0) model downloaded successfully!')
        return True
        
    except Exception as e:
        logger.error(f'Failed to download MapAnything model: {e}')
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
        logger.info("MapAnything model already downloaded.")
        return True
    
    # Download the model
    return download_mapanything_model()

def main():
    """Main function for standalone execution."""
    logger.info("MapAnything Model Loader")
    logger.info("=======================")
    
    success = ensure_mapanything_model()
    
    if success:
        logger.info("MapAnything model is ready for use!")
        return 0
    else:
        logger.error("Failed to ensure MapAnything model is available")
        return 1

if __name__ == "__main__":
    sys.exit(main())