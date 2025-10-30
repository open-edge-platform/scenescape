#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Basic tests for the mapping service plugin architecture.
"""

import pytest
import sys
import os

# Add workspace to path for testing
sys.path.insert(0, '/workspace')


def test_model_interface_import():
  """Test that model interface can be imported."""
  try:
    from model_interface import ReconstructionModel
    assert ReconstructionModel is not None
  except ImportError as e:
    pytest.fail(f"Failed to import ReconstructionModel: {e}")


def test_model_registry_import():
  """Test that model registry can be imported."""
  try:
    from model_registry import ModelRegistry, get_available_models
    assert ModelRegistry is not None
    assert callable(get_available_models)
  except ImportError as e:
    pytest.fail(f"Failed to import ModelRegistry: {e}")


def test_model_plugins_import():
  """Test that model plugins can be imported."""
  try:
    # These imports register the models
    import mapanything_model
    import vggt_model
    
    from model_registry import get_available_models
    
    available = get_available_models()
    assert 'mapanything' in available
    assert 'vggt' in available
    
  except ImportError as e:
    pytest.fail(f"Failed to import model plugins: {e}")


def test_api_service_import():
  """Test that API service can be imported."""
  try:
    # Mock Flask for testing
    sys.modules['flask'] = type('MockFlask', (), {
      'Flask': lambda *args, **kwargs: None,
      'request': None,
      'jsonify': lambda x: x
    })()
    sys.modules['flask_cors'] = type('MockCORS', (), {
      'CORS': lambda *args, **kwargs: None
    })()
    
    import api_service
    assert api_service is not None
    
  except ImportError as e:
    pytest.fail(f"Failed to import api_service: {e}")


if __name__ == "__main__":
  pytest.main([__file__, "-v"])