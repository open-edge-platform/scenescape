#!/usr/bin/env python3

"""
VGGT-specific API Service
"""

import sys
import logging

# Import the base API service
from api_service_base import app, start_app

logger = logging.getLogger(__name__)

def initialize_model():
    """Initialize VGGT model"""
    from vggt_model import VGGTModel
    
    logger.info("Initializing VGGT model...")
    model = VGGTModel(device="cpu")
    model.load_model()
    logger.info("VGGT model loaded successfully")
    
    return model, "vggt"

# Override the initialize_model function in the base module
import api_service_base
api_service_base.initialize_model = initialize_model

if __name__ == "__main__":
    start_app()