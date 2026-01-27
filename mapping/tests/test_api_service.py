#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for API Service
Tests the Flask API endpoints and request validation.
"""

import pytest
import json
import base64
import io
import sys
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestAPIService:
  """Test cases for API service endpoints"""

  @pytest.fixture
  def client(self):
    """Create Flask test client with mock model"""
    # Import here to avoid issues with model initialization
    from api_service_base import app

    # Create mock model
    mock_model = Mock()
    mock_model.is_loaded = True
    mock_model.runInference = Mock(return_value={
      "predictions": {"world_points": [], "images": [], "final_masks": []},
      "camera_poses": [
        {"rotation": [1.0, 0.0, 0.0, 0.0], "translation": [0.0, 0.0, 0.0]}
      ],
      "intrinsics": [[[1000, 0, 500], [0, 1000, 500], [0, 0, 1]]]
    })
    mock_model.createOutput = Mock(return_value=MagicMock())
    mock_model.getModelInfo = Mock(return_value={
      "name": "test_model",
      "description": "Test model",
      "device": "cpu",
      "loaded": True,
      "native_output": "mesh",
      "supported_outputs": ["mesh", "pointcloud"]
    })

    # Patch the global model
    with patch('api_service_base.loaded_model', mock_model):
      with patch('api_service_base.model_name', 'test_model'):
        app.config['TESTING'] = True
        with app.test_client() as client:
          yield client

  def create_test_image_base64(self, size=(100, 100), color=(255, 0, 0)):
    """Helper to create base64 encoded test image"""
    img = Image.new('RGB', size, color=color)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_base64

  def test_health_check(self, client):
    """Test /health endpoint"""
    response = client.get('/health')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert 'model' in data
    assert 'model_loaded' in data
    assert 'device' in data

  def test_list_models(self, client):
    """Test /models endpoint"""
    response = client.get('/models')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'model' in data
    assert 'model_info' in data
    assert 'camera_pose_format' in data

  def test_reconstruction_success(self, client):
    """Test successful reconstruction request"""
    # Create test images as file-like objects
    img_bytes = base64.b64decode(self.create_test_image_base64())

    # Prepare multipart/form-data request
    data = {
      'output_format': 'json',
      'mesh_type': 'mesh',
      'images': [
        (io.BytesIO(img_bytes), 'test1.jpg'),
        (io.BytesIO(img_bytes), 'test2.jpg')
      ]
    }

    response = client.post(
      '/reconstruction',
      data=data,
      content_type='multipart/form-data'
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'camera_poses' in data
    assert 'intrinsics' in data
    assert 'processing_time' in data

  def test_reconstruction_with_glb_output(self, client):
    """Test reconstruction with GLB output format"""
    import trimesh
    import tempfile

    # Create a mock scene that can be exported
    mock_scene = Mock(spec=trimesh.Scene)
    # Mock the export method to write a dummy file
    mock_scene.export = Mock()

    with patch('api_service_base.loaded_model') as mock_model:
      mock_model.is_loaded = True
      mock_model.runInference = Mock(return_value={
        "predictions": {"world_points": [], "images": [], "final_masks": []},
        "camera_poses": [
          {"rotation": [1.0, 0.0, 0.0, 0.0], "translation": [0.0, 0.0, 0.0]}
        ],
        "intrinsics": [[[1000, 0, 500], [0, 1000, 500], [0, 0, 1]]]
      })
      mock_model.createOutput = Mock(return_value=mock_scene)

      # Mock getMeshInfo to return valid mesh info
      with patch('api_service_base.getMeshInfo', return_value={
        "vertices": 0,
        "faces": 0,
        "bounds": [[0, 0, 0], [0, 0, 0]]
      }):
        # Create test image as file-like object
        img_bytes = base64.b64decode(self.create_test_image_base64())

        data = {
          'output_format': 'glb',
          'mesh_type': 'mesh',
          'images': [(io.BytesIO(img_bytes), 'test.jpg')]
        }

        with patch('api_service_base.model_name', 'test_model'):
          response = client.post(
            '/reconstruction',
            data=data,
            content_type='multipart/form-data'
          )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'glb_data' in data

  def test_reconstruction_missing_images(self, client):
    """Test reconstruction with missing images field"""
    request_data = {
      "output_format": "json"
    }

    response = client.post(
      '/reconstruction',
      data=json.dumps(request_data),
      content_type='application/json'
    )

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

  def test_reconstruction_empty_images(self, client):
    """Test reconstruction with empty images list"""
    request_data = {
      "images": [],
      "output_format": "json"
    }

    response = client.post(
      '/reconstruction',
      data=json.dumps(request_data),
      content_type='application/json'
    )

    assert response.status_code == 400

  def test_reconstruction_invalid_output_format(self, client):
    """Test reconstruction with invalid output format"""
    img_data = self.create_test_image_base64()
    request_data = {
      "images": [{"data": img_data}],
      "output_format": "invalid_format"
    }

    response = client.post(
      '/reconstruction',
      data=json.dumps(request_data),
      content_type='application/json'
    )

    assert response.status_code == 400

  def test_reconstruction_invalid_mesh_type(self, client):
    """Test reconstruction with invalid mesh type"""
    img_data = self.create_test_image_base64()
    request_data = {
      "images": [{"data": img_data}],
      "mesh_type": "invalid_type"
    }

    response = client.post(
      '/reconstruction',
      data=json.dumps(request_data),
      content_type='application/json'
    )

    assert response.status_code == 400

  def test_reconstruction_not_json(self, client):
    """Test reconstruction with non-JSON request"""
    response = client.post(
      '/reconstruction',
      data="not json data",
      content_type='text/plain'
    )

    assert response.status_code == 400

  def test_reconstruction_image_missing_data(self, client):
    """Test reconstruction with image missing data field"""
    request_data = {
      "images": [{"other_field": "value"}],
      "output_format": "json"
    }

    response = client.post(
      '/reconstruction',
      data=json.dumps(request_data),
      content_type='application/json'
    )

    assert response.status_code == 400

  def test_reconstruction_image_data_not_string(self, client):
    """Test reconstruction with image data not a string"""
    request_data = {
      "images": [{"data": 12345}],
      "output_format": "json"
    }

    response = client.post(
      '/reconstruction',
      data=json.dumps(request_data),
      content_type='application/json'
    )

    assert response.status_code == 400

  def test_reconstruction_model_not_loaded(self, client):
    """Test reconstruction when model is not loaded"""
    with patch('api_service_base.loaded_model', None):
      # Create test image as file-like object
      img_bytes = base64.b64decode(self.create_test_image_base64())

      data = {
        'output_format': 'json',
        'images': [(io.BytesIO(img_bytes), 'test.jpg')]
      }

      with patch('api_service_base.model_name', 'test_model'):
        response = client.post(
          '/reconstruction',
          data=data,
          content_type='multipart/form-data'
        )

      assert response.status_code == 503
      data = json.loads(response.data)
      assert 'error' in data

  def test_reconstruction_default_parameters(self, client):
    """Test reconstruction with default parameters"""
    # Create test image as file-like object
    img_bytes = base64.b64decode(self.create_test_image_base64())

    # Only provide image, let output_format and mesh_type default
    data = {
      'images': [(io.BytesIO(img_bytes), 'test.jpg')]
    }

    response = client.post(
      '/reconstruction',
      data=data,
      content_type='multipart/form-data'
    )

    # Should succeed with defaults
    assert response.status_code in [200, 500]  # May fail on actual processing

  def test_endpoint_not_found(self, client):
    """Test 404 for non-existent endpoint"""
    response = client.get('/nonexistent')

    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data

  def test_method_not_allowed(self, client):
    """Test 405 for wrong HTTP method"""
    response = client.get('/reconstruction')

    assert response.status_code == 405
    data = json.loads(response.data)
    assert 'error' in data


class TestRequestValidation:
  """Test cases for request validation functions"""

  def test_validate_reconstruction_request_valid(self):
    """Test validation with valid request"""
    from api_service_base import validateReconstructionRequest

    valid_data = {
      "images": [
        {"data": "base64_string_1"},
        {"data": "base64_string_2"}
      ],
      "output_format": "glb",
      "mesh_type": "mesh"
    }

    # Should not raise exception
    result = validateReconstructionRequest(valid_data)
    assert result is True

  def test_validate_reconstruction_request_not_dict(self):
    """Test validation rejects non-dict input"""
    from api_service_base import validateReconstructionRequest

    with pytest.raises(ValueError, match="Request must be an object"):
      validateReconstructionRequest("not a dict")

  def test_validate_reconstruction_request_missing_images(self):
    """Test validation rejects missing images"""
    from api_service_base import validateReconstructionRequest

    with pytest.raises(ValueError, match="Provide images and/or video"):
      validateReconstructionRequest({})

  def test_validate_reconstruction_request_images_not_list(self):
    """Test validation rejects non-list images"""
    from api_service_base import validateReconstructionRequest

    with pytest.raises(ValueError, match="non-empty list"):
      validateReconstructionRequest({"images": "not a list"})

  def test_validate_reconstruction_request_empty_images(self):
    """Test validation rejects empty images list"""
    from api_service_base import validateReconstructionRequest

    with pytest.raises(ValueError, match="Provide images and/or video"):
      validateReconstructionRequest({"images": []})

  def test_validate_reconstruction_request_invalid_output_format(self):
    """Test validation rejects invalid output format"""
    from api_service_base import validateReconstructionRequest

    data = {
      "images": [{"data": "test"}],
      "output_format": "invalid"
    }

    with pytest.raises(ValueError, match="output_format must be"):
      validateReconstructionRequest(data)

  def test_validate_reconstruction_request_invalid_mesh_type(self):
    """Test validation rejects invalid mesh type"""
    from api_service_base import validateReconstructionRequest

    data = {
      "images": [{"data": "test"}],
      "mesh_type": "invalid"
    }

    with pytest.raises(ValueError, match="mesh_type must be"):
      validateReconstructionRequest(data)

  def test_validate_reconstruction_request_image_not_dict(self):
    """Test validation rejects non-dict image"""
    from api_service_base import validateReconstructionRequest

    data = {
      "images": ["not a dict"]
    }

    with pytest.raises(ValueError, match="must be an object"):
      validateReconstructionRequest(data)

  def test_validate_reconstruction_request_image_missing_data(self):
    """Test validation rejects image without data field"""
    from api_service_base import validateReconstructionRequest

    data = {
      "images": [{"other_field": "value"}]
    }

    with pytest.raises(ValueError, match="missing required field: data"):
      validateReconstructionRequest(data)

  def test_validate_reconstruction_request_image_data_not_string(self):
    """Test validation rejects non-string image data"""
    from api_service_base import validateReconstructionRequest

    data = {
      "images": [{"data": 12345}]
    }

    with pytest.raises(ValueError, match="data must be a non-empty string"):
      validateReconstructionRequest(data)


if __name__ == "__main__":
  pytest.main([__file__, "-v"])
