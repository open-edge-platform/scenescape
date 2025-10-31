#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
VGGT-specific API Service
"""

from scene_common import log

# Import the base API service
from api_service_base import startApp

def initializeModel():
  """Initialize VGGT model"""
  from vggt_model import VGGTModel

  log.info("Initializing VGGT model...")
  model = VGGTModel(device="cpu")
  model.loadModel()
  log.info("VGGT model loaded successfully")

  return model, "vggt"

# Override the initializeModel function in the base module
import api_service_base
api_service_base.initializeModel = initializeModel

if __name__ == "__main__":
  startApp()