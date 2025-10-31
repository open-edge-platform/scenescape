#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MapAnything-specific API Service
"""

# Import the base API service
from api_service_base import startApp, app

def initializeModel():
  """Initialize MapAnything model"""
  from mapanything_model import MapAnythingModel

  model = MapAnythingModel(device="cpu")
  model.loadModel()

  return model, "mapanything"

# Override the initializeModel function in the base module
import api_service_base
api_service_base.initializeModel = initializeModel

if __name__ == "__main__":
  startApp()
