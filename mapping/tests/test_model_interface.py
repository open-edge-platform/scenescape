#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for Model Interface
Tests the ReconstructionModel abstract base class and helper methods.
"""

import pytest
import numpy as np
import base64
import io
import sys
from pathlib import Path
from PIL import Image

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from model_interface import ReconstructionModel


class MockReconstructionModel(ReconstructionModel):
  """Concrete implementation for testing"""

  def __init__(self, device="cpu"):
    super().__init__("mock_model", "Mock model for testing", device)

  def loadModel(self):
    self.is_loaded = True

  def runInference(self, images):
    return {
      "predictions": {},
      "camera_poses": [],
      "intrinsics": []
    }

  def getSupportedOutputs(self):
    return ["mesh", "pointcloud"]

  def getNativeOutput(self):
    return "mesh"

  def scaleIntrinsicsToOriginalSize(self, intrinsics, model_size, original_sizes, preprocessing_mode="crop"):
    return [intrinsics] * len(original_sizes)

  def createOutput(self, result, output_format=None):
    import trimesh
    return trimesh.Scene()


class TestReconstructionModel:
  """Test cases for ReconstructionModel base class"""

  def test_model_initialization(self):
    """Test model initialization sets correct attributes"""
    model = MockReconstructionModel(device="cpu")

    assert model.model_name == "mock_model"
    assert model.description == "Mock model for testing"
    assert model.device == "cpu"
    assert model.model is None
    assert model.is_loaded is False

  def test_is_model_loaded(self):
    """Test isModelLoaded returns correct status"""
    model = MockReconstructionModel(device="cpu")

    assert model.isModelLoaded() is False

    model.loadModel()
    assert model.isModelLoaded() is True

  def test_get_model_info(self):
    """Test getModelInfo returns correct information"""
    model = MockReconstructionModel(device="cpu")
    info = model.getModelInfo()

    assert info["name"] == "mock_model"
    assert info["description"] == "Mock model for testing"
    assert info["device"] == "cpu"
    assert info["loaded"] is False
    assert info["native_output"] == "mesh"
    assert "mesh" in info["supported_outputs"]
    assert "pointcloud" in info["supported_outputs"]

  def test_validate_images_valid(self):
    """Test validateImages accepts valid image data"""
    model = MockReconstructionModel()

    valid_images = [
      {"data": "base64_encoded_string_1"},
      {"data": "base64_encoded_string_2"}
    ]

    # Should not raise any exception
    model.validateImages(valid_images)

  def test_validate_images_empty_list(self):
    """Test validateImages rejects empty list"""
    model = MockReconstructionModel()

    with pytest.raises(ValueError, match="non-empty list"):
      model.validateImages([])

  def test_validate_images_not_list(self):
    """Test validateImages rejects non-list input"""
    model = MockReconstructionModel()

    with pytest.raises(ValueError, match="non-empty list"):
      model.validateImages({"data": "test"})

  def test_validate_images_not_dict(self):
    """Test validateImages rejects non-dict items"""
    model = MockReconstructionModel()

    with pytest.raises(ValueError, match="must be a dictionary"):
      model.validateImages(["not_a_dict"])

  def test_validate_images_missing_data(self):
    """Test validateImages rejects items without 'data' field"""
    model = MockReconstructionModel()

    with pytest.raises(ValueError, match="missing required field: data"):
      model.validateImages([{"other_field": "value"}])

  def test_validate_images_data_not_string(self):
    """Test validateImages rejects non-string data"""
    model = MockReconstructionModel()

    with pytest.raises(ValueError, match="must be a base64 string"):
      model.validateImages([{"data": 12345}])

  def test_decode_base64_image(self):
    """Test decodeBase64Image converts base64 to numpy array"""
    model = MockReconstructionModel()

    # Create a simple test image
    test_image = Image.new('RGB', (100, 100), color=(255, 0, 0))
    buffered = io.BytesIO()
    test_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    # Decode
    img_array = model.decodeBase64Image(img_base64)

    assert isinstance(img_array, np.ndarray)
    assert img_array.shape == (100, 100, 3)
    assert img_array.dtype == np.uint8

  def test_decode_base64_image_with_data_url_prefix(self):
    """Test decodeBase64Image handles data URL prefix"""
    model = MockReconstructionModel()

    # Create test image
    test_image = Image.new('RGB', (50, 50), color=(0, 255, 0))
    buffered = io.BytesIO()
    test_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    # Add data URL prefix
    data_url = f"data:image/png;base64,{img_base64}"

    # Decode
    img_array = model.decodeBase64Image(data_url)

    assert isinstance(img_array, np.ndarray)
    assert img_array.shape == (50, 50, 3)

  def test_decode_base64_image_converts_to_rgb(self):
    """Test decodeBase64Image converts non-RGB images to RGB"""
    model = MockReconstructionModel()

    # Create grayscale image
    test_image = Image.new('L', (50, 50), color=128)
    buffered = io.BytesIO()
    test_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    # Decode
    img_array = model.decodeBase64Image(img_base64)

    assert isinstance(img_array, np.ndarray)
    assert img_array.shape == (50, 50, 3)  # Should be converted to RGB

  def test_decode_base64_image_invalid_data(self):
    """Test decodeBase64Image raises error for invalid data"""
    model = MockReconstructionModel()

    with pytest.raises(ValueError, match="Failed to decode"):
      model.decodeBase64Image("invalid_base64_data")

  def test_rotation_matrix_to_quaternion_identity(self):
    """Test rotation matrix to quaternion conversion for identity matrix"""
    model = MockReconstructionModel()

    # Identity rotation
    R = np.eye(3)
    quat = model.rotationMatrixToQuaternion(R)

    assert quat.shape == (4,)
    # Identity quaternion is [0, 0, 0, 1] (x, y, z, w format)
    np.testing.assert_array_almost_equal(quat, [0.0, 0.0, 0.0, 1.0], decimal=6)

  def test_rotation_matrix_to_quaternion_90deg_x(self):
    """Test quaternion conversion for 90° rotation around X-axis"""
    model = MockReconstructionModel()

    # 90° rotation around X-axis
    R = np.array([
      [1, 0, 0],
      [0, 0, -1],
      [0, 1, 0]
    ], dtype=np.float64)

    quat = model.rotationMatrixToQuaternion(R)

    # Expected quaternion for 90° around X in [x, y, z, w] format: [sin(45°), 0, 0, cos(45°)]
    expected = np.array([np.sqrt(2)/2, 0.0, 0.0, np.sqrt(2)/2])
    np.testing.assert_array_almost_equal(quat, expected, decimal=6)

  def test_rotation_matrix_to_quaternion_90deg_y(self):
    """Test quaternion conversion for 90° rotation around Y-axis"""
    model = MockReconstructionModel()

    # 90° rotation around Y-axis
    R = np.array([
      [0, 0, 1],
      [0, 1, 0],
      [-1, 0, 0]
    ], dtype=np.float64)

    quat = model.rotationMatrixToQuaternion(R)

    # Expected quaternion for 90° around Y in [x, y, z, w] format: [0, sin(45°), 0, cos(45°)]
    expected = np.array([0.0, np.sqrt(2)/2, 0.0, np.sqrt(2)/2])
    np.testing.assert_array_almost_equal(quat, expected, decimal=6)

  def test_rotation_matrix_to_quaternion_90deg_z(self):
    """Test quaternion conversion for 90° rotation around Z-axis"""
    model = MockReconstructionModel()

    # 90° rotation around Z-axis
    R = np.array([
      [0, -1, 0],
      [1, 0, 0],
      [0, 0, 1]
    ], dtype=np.float64)

    quat = model.rotationMatrixToQuaternion(R)

    # Expected quaternion for 90° around Z in [x, y, z, w] format: [0, 0, sin(45°), cos(45°)]
    expected = np.array([0.0, 0.0, np.sqrt(2)/2, np.sqrt(2)/2])
    np.testing.assert_array_almost_equal(quat, expected, decimal=6)

  def test_rotation_matrix_to_quaternion_180deg(self):
    """Test quaternion conversion for 180° rotation"""
    model = MockReconstructionModel()

    # 180° rotation around X-axis
    R = np.array([
      [1, 0, 0],
      [0, -1, 0],
      [0, 0, -1]
    ], dtype=np.float64)

    quat = model.rotationMatrixToQuaternion(R)

    # Expected quaternion for 180° around X in [x, y, z, w] format: [1, 0, 0, 0]
    expected = np.array([1.0, 0.0, 0.0, 0.0])
    np.testing.assert_array_almost_equal(quat, expected, decimal=6)

  def test_rotation_matrix_to_quaternion_arbitrary(self):
    """Test quaternion conversion for arbitrary rotation"""
    model = MockReconstructionModel()

    # Create an arbitrary valid rotation matrix
    angle = np.pi / 6  # 30 degrees
    axis = np.array([1, 1, 1]) / np.sqrt(3)  # Normalized
    c = np.cos(angle)
    s = np.sin(angle)
    t = 1 - c
    x, y, z = axis

    R = np.array([
      [t*x*x + c,  t*x*y - s*z,  t*x*z + s*y],
      [t*x*y + s*z,  t*y*y + c,  t*y*z - s*x],
      [t*x*z - s*y,  t*y*z + s*x,  t*z*z + c]
    ], dtype=np.float64)

    quat = model.rotationMatrixToQuaternion(R)

    # Verify quaternion is normalized
    magnitude = np.linalg.norm(quat)
    np.testing.assert_almost_equal(magnitude, 1.0, decimal=6)

    # Verify quaternion has 4 components
    assert quat.shape == (4,)

  def test_abstract_methods_not_implemented(self):
    """Test that abstract methods raise NotImplementedError"""
    # Cannot instantiate abstract class directly
    with pytest.raises(TypeError):
      ReconstructionModel("test", "test", "cpu")


if __name__ == "__main__":
  pytest.main([__file__, "-v"])
