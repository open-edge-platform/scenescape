#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MapAnything-specific API Service
"""

import os
import re

def _sanitize_no_proxy():
  """Fix malformed no_proxy entries where a dot-prefixed domain appears after
  a colon (e.g. '.svc.cluster.local:.scenescape.intel.com'), causing urllib3
  to raise 'Invalid port' errors during model loading.
  """
  for var in ('no_proxy', 'NO_PROXY'):
    value = os.environ.get(var, '')
    if not value:
      continue
    cleaned = re.sub(r'([^,]+):(\.[^,]+)', r'\1,\2', value)
    if cleaned != value:
      os.environ[var] = cleaned

_sanitize_no_proxy()

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
