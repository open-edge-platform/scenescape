#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MapAnything-specific API Service
"""

from scene_common import log

# Import the base API service
from api_service_base import start_app

def initialize_model():
    """Initialize MapAnything model"""
    from mapanything_model import MapAnythingModel

    log.info("Initializing MapAnything model...")
    model = MapAnythingModel(device="cpu")
    model.load_model()
    log.info("MapAnything model loaded successfully")

    return model, "mapanything"

# Override the initialize_model function in the base module
import api_service_base
api_service_base.initialize_model = initialize_model

if __name__ == "__main__":
    start_app()