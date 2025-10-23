#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand model loader for SceneScape 3D mapping service.
This script downloads the MapAnything and VGGT models only when needed, reducing Docker image size.
Combines model download coordination and individual model management.
"""

import sys
import logging
from typing import Dict
from download_mapanything import ensure_mapanything_model
from download_vggt import ensure_vggt_model

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_all_models() -> Dict[str, bool]:
    """
    Ensure all required models exist, downloading them if necessary.
    
    Returns:
        Dictionary with model names as keys and success status as values
    """
    logger.info("3D Mapping Models On-Demand Loader")
    logger.info("==================================")
    
    results = {}
    
    # Download MapAnything model
    logger.info("Checking MapAnything model...")
    results["mapanything"] = ensure_mapanything_model()
    
    # Download VGGT model  
    logger.info("Checking VGGT model...")
    results["vggt"] = ensure_vggt_model()
    
    return results

def main():
    """Main function for standalone execution."""
    results = ensure_all_models()
    
    success_count = sum(1 for success in results.values() if success)
    total_models = len(results)
    
    logger.info(f"\nModel Download Summary:")
    logger.info(f"======================")
    
    for model_name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"  - {model_name.capitalize()}: {status}")
    
    if success_count == total_models:
        logger.info(f"\nAll {total_models} models initialized successfully!")
        return 0
    else:
        logger.error(f"\nFailed to initialize {total_models - success_count} out of {total_models} models")
        for model_name, success in results.items():
            if not success:
                logger.error(f"  - {model_name}: FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())