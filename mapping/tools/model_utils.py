#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Common utilities for model loading in SceneScape 3D mapping service.
"""

import os
import logging
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MODEL_DIR = os.getenv("MODEL_DIR", "/workspace/model_weights")
SCENESCAPE_HOME = os.getenv("SCENESCAPE_HOME", "/home/scenescape/SceneScape")

def get_model_weights_dir() -> Path:
    """Get the model weights directory."""
    model_dir = Path(MODEL_DIR)
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir

def get_scenescape_home() -> Path:
    """Get the SceneScape home directory."""
    return Path(SCENESCAPE_HOME)

def ensure_cache_directories():
    """Ensure all cache directories exist."""
    cache_dirs = [
        Path("/home/scenescape/.cache/torch"),
        Path("/home/scenescape/.cache/huggingface"),
        get_model_weights_dir()
    ]
    
    for cache_dir in cache_dirs:
        cache_dir.mkdir(parents=True, exist_ok=True)

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
        logger.error(f"Failed to create success marker for {model_name}: {e}")
        return False