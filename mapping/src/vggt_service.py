#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
VGGT-specific API Service
"""

# Import the base API service
from api_service_base import startApp, app

def initializeModel():
  """Initialize VGGT model"""
  from vggt_model import VGGTModel

  model = VGGTModel(device="cpu")
  model.loadModel()

  return model, "vggt"

# Override the initializeModel function in the base module
import api_service_base
api_service_base.initializeModel = initializeModel

if __name__ == "__main__":
  startApp()
