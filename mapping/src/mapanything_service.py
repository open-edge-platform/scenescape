#!/usr/bin/env python3

"""
MapAnything-specific API Service
"""

import sys
import logging

# Import the base API service
from api_service_base import app, start_app

logger = logging.getLogger(__name__)

def initialize_model():
    """Initialize MapAnything model"""
    from mapanything_model import MapAnythingModel
    
    logger.info("Initializing MapAnything model...")
    model = MapAnythingModel(device="cpu")
    model.load_model()
    logger.info("MapAnything model loaded successfully")
    
    return model, "mapanything"

# Override the initialize_model function in the base module
import api_service_base
api_service_base.initialize_model = initialize_model

if __name__ == "__main__":
    start_app()