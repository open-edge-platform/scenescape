#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest Configuration and Fixtures
Shared fixtures and configuration for all test modules.
"""

import pytest
import sys
import os
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def sample_image_data():
  """Fixture providing sample image data for tests"""
  import numpy as np
  import base64
  import io
  from PIL import Image

  def create_image(size=(100, 100), color=(255, 0, 0), format="PNG"):
    """Create a test image and return as base64 string"""
    img = Image.new('RGB', size, color=color)
    buffered = io.BytesIO()
    img.save(buffered, format=format)
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_base64

  return create_image


@pytest.fixture(scope="session")
def sample_camera_poses():
  """Fixture providing sample camera poses"""
  return [
    {
      "rotation": [1.0, 0.0, 0.0, 0.0],  # Identity quaternion
      "translation": [0.0, 0.0, 0.0]
    },
    {
      "rotation": [0.9239, 0.3827, 0.0, 0.0],  # ~45° around X
      "translation": [1.0, 0.0, 0.0]
    }
  ]


@pytest.fixture(scope="session")
def sample_intrinsics():
  """Fixture providing sample camera intrinsics"""
  return [
    [[1000.0, 0.0, 500.0],
     [0.0, 1000.0, 500.0],
     [0.0, 0.0, 1.0]],
    [[1000.0, 0.0, 500.0],
     [0.0, 1000.0, 500.0],
     [0.0, 0.0, 1.0]]
  ]


@pytest.fixture(scope="session")
def sample_predictions():
  """Fixture providing sample model predictions"""
  import numpy as np

  return {
    "world_points": np.random.rand(2, 100, 100, 3).astype(np.float32),
    "images": np.random.randint(0, 255, (2, 100, 100, 3), dtype=np.uint8),
    "final_masks": np.ones((2, 100, 100), dtype=bool)
  }


@pytest.fixture(scope="function")
def mock_model():
  """Fixture providing a mock reconstruction model"""
  from unittest.mock import Mock
  import numpy as np

  model = Mock()
  model.model_name = "mock_model"
  model.description = "Mock model for testing"
  model.device = "cpu"
  model.is_loaded = False
  model.model = None

  def load_model():
    model.is_loaded = True

  def run_inference(images):
    return {
      "predictions": {
        "world_points": np.random.rand(len(images), 100, 100, 3).astype(np.float32),
        "images": np.random.randint(0, 255, (len(images), 100, 100, 3), dtype=np.uint8),
        "final_masks": np.ones((len(images), 100, 100), dtype=bool)
      },
      "camera_poses": [
        {"rotation": [1.0, 0.0, 0.0, 0.0], "translation": [0.0, 0.0, 0.0]}
        for _ in images
      ],
      "intrinsics": [
        [[1000.0, 0.0, 500.0], [0.0, 1000.0, 500.0], [0.0, 0.0, 1.0]]
        for _ in images
      ]
    }

  def get_model_info():
    return {
      "name": model.model_name,
      "description": model.description,
      "device": model.device,
      "loaded": model.is_loaded,
      "native_output": "mesh",
      "supported_outputs": ["mesh", "pointcloud"]
    }

  model.loadModel = Mock(side_effect=load_model)
  model.runInference = Mock(side_effect=run_inference)
  model.getModelInfo = Mock(side_effect=get_model_info)
  model.isModelLoaded = Mock(return_value=model.is_loaded)
  model.getSupportedOutputs = Mock(return_value=["mesh", "pointcloud"])
  model.getNativeOutput = Mock(return_value="mesh")

  return model


@pytest.fixture(scope="function")
def flask_test_client(mock_model):
  """Fixture providing Flask test client with mocked model"""
  from unittest.mock import patch
  import sys
  from pathlib import Path

  # Add src to path
  src_path = Path(__file__).parent.parent / 'src'
  if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

  # Import Flask app
  from api_service_base import app

  # Configure for testing
  app.config['TESTING'] = True

  # Patch the global loaded_model and model_name
  with patch('api_service_base.loaded_model', mock_model):
    with patch('api_service_base.model_name', 'mock_model'):
      with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def temp_test_dir(tmp_path_factory):
  """Fixture providing temporary directory for test files"""
  return tmp_path_factory.mktemp("test_data")


def pytest_configure(config):
  """Pytest configuration hook"""
  # Add custom markers
  config.addinivalue_line(
    "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
  )
  config.addinivalue_line(
    "markers", "integration: marks tests as integration tests"
  )
  config.addinivalue_line(
    "markers", "unit: marks tests as unit tests"
  )


def pytest_collection_modifyitems(config, items):
  """Automatically mark tests based on their location"""
  for item in items:
    # Mark all tests as unit tests by default
    if "integration" not in item.keywords:
      item.add_marker(pytest.mark.unit)


# Environment setup for tests
def pytest_sessionstart(session):
  """Called before test run starts"""
  # Suppress unnecessary warnings
  import warnings
  warnings.filterwarnings("ignore", category=DeprecationWarning)
  warnings.filterwarnings("ignore", category=PendingDeprecationWarning)


def pytest_sessionfinish(session, exitstatus):
  """Called after whole test run finishes"""
  pass
