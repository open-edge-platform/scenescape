#!/usr/bin/env python3

"""
VGGT-specific API Service
"""

from scene_common import log

# Import the base API service
from api_service_base import start_app

def initialize_model():
    """Initialize VGGT model"""
    from vggt_model import VGGTModel

    log.info("Initializing VGGT model...")
    model = VGGTModel(device="cpu")
    model.load_model()
    log.info("VGGT model loaded successfully")

    return model, "vggt"

# Override the initialize_model function in the base module
import api_service_base
api_service_base.initialize_model = initialize_model

if __name__ == "__main__":
    start_app()