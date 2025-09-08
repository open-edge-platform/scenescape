# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import math
from unittest.mock import patch

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from scene_common.transform import PointCorrespondenceTransform, CameraIntrinsics
from scene_common.geometry import Point

class TestPointCorrespondenceTransform:
  def test_init_with_correspondences(self):
    """Test initialization with point correspondences"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [123.4, 87.6],   # Top-left corner of object
            [456.7, 234.8],  # Top-right corner
            [789.1, 543.2],  # Bottom-right corner
            [321.5, 678.9]   # Bottom-left corner
        ]),
        'map points': np.array([
            [2.5, 3.7, 0],   # Corresponding world points
            [5.2, 4.1, 0],
            [4.8, 1.3, 0],
            [1.9, 0.8, 0]
        ])
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)
    assert transform.cameraPoints.shape[0] == 4
    assert transform.mapPoints.shape[1] == 3

  def test_init_with_2d_map_points(self):
    """Test initialization when map points are 2D (adds z=0)"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400], [500, 500], [600, 600]
        ]),
        'map points': np.array([
            [1.5, 2.3], [3.7, 4.1], [5.2, 6.8], [7.1, 8.4], [9.3, 10.7], [11.2, 12.9]
        ])  # 2D points - need at least 6 for solvePnP
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)
    assert transform.mapPoints.shape[1] == 3
    # Z coordinates should be added as zeros
    assert math.isclose(transform.mapPoints[0, 2], 0.0, abs_tol=1e-9)
    assert math.isclose(transform.mapPoints[1, 2], 0.0, abs_tol=1e-9)

  def test_are_points_coplanar_true(self):
    """Test coplanarity check with coplanar points"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400], [500, 500], [600, 600]
        ]),
        'map points': np.array([
            [1, 2, 0], [3, 4, 0], [5, 6, 0], [7, 8, 0], [9, 10, 0], [11, 12, 0]
        ])  # All z=0, need at least 6 points
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)

    coplanar_points = np.array([
        [1.2, 2.3, 0], [3.4, 4.5, 0], [5.6, 6.7, 0], [7.8, 8.9, 0]
    ])
    assert transform.arePointsCoplanar(coplanar_points)

  def test_are_points_coplanar_false(self):
    """Test coplanarity check with non-coplanar points"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400], [500, 500], [600, 600]
        ]),
        'map points': np.array([
            [1, 2, 0], [3, 4, 0], [5, 6, 0], [7, 8, 0], [9, 10, 0], [11, 12, 0]
        ])
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)

    # Points that definitely violate coplanarity (determinant > 0.1)
    # Create a clear tetrahedron with large z differences
    non_coplanar_points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]   # Unit tetrahedron
    ])
    assert not transform.arePointsCoplanar(non_coplanar_points)

  def test_calculate_determinant(self):
    """Test determinant calculation for coplanarity"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400], [500, 500], [600, 600]
        ]),
        'map points': np.array([
            [1, 1, 0], [2, 2, 0], [3, 3, 0], [4, 4, 0], [5, 5, 0], [6, 6, 0]
        ])
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)

    # Points forming a tetrahedron
    points = np.array([
        [1.2, 2.3, 0.5],
        [4.7, 5.8, 1.2],
        [7.9, 8.1, 2.3],
        [3.4, 6.7, 0.8]
    ])
    determinant = transform.calculateDeterminant(points)
    assert isinstance(determinant, (int, float, np.number))
    # Non-coplanar points should have non-zero determinant
    assert not math.isclose(determinant, 0.0, abs_tol=1e-6)

  @patch('cv2.solvePnP')
  def test_calculate_pose_mat(self, mock_solve_pnp):
    """Test pose matrix calculation from point correspondences"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])

    # Mock cv2.solvePnP return values
    mock_rvec = np.array([[0.1], [0.2], [0.3]])
    mock_tvec = np.array([[1.0], [2.0], [3.0]])
    mock_solve_pnp.return_value = (True, mock_rvec, mock_tvec)

    pose = {
        'camera points': np.array([[100, 100], [200, 200], [300, 300], [400, 400]]),
        'map points': np.array([[1, 2, 0], [3, 4, 0], [5, 6, 0], [7, 8, 0]])
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)

    # Verify that _calculatePoseMat was called and set properties
    assert hasattr(transform, 'pose_mat')
    assert hasattr(transform, 'translation')
    assert hasattr(transform, 'quaternion_rotation')

  # Negative test cases for PointCorrespondenceTransform
  def test_init_with_insufficient_correspondences(self):
    """Test initialization with insufficient point correspondences"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([[100, 100], [200, 200]]),  # Only 2 points
        'map points': np.array([[1, 2, 0], [3, 4, 0]])
    }
    with pytest.raises((ValueError, cv2.error)):
      PointCorrespondenceTransform(pose, intrinsics)

  def test_init_with_mismatched_point_counts(self):
    """Test initialization with mismatched point counts"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([[100, 100], [200, 200], [300, 300], [400, 400]]),  # 4 points
        'map points': np.array([[1, 2, 0], [3, 4, 0]])  # Only 2 points
    }
    with pytest.raises((ValueError, cv2.error)):
      PointCorrespondenceTransform(pose, intrinsics)

  def test_init_with_invalid_camera_points_shape(self):
    """Test initialization with invalid camera points shape"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([100, 200, 300]),  # Wrong shape - 1D array
        'map points': np.array([[1, 2, 0], [3, 4, 0], [5, 6, 0]])
    }
    # OpenCV solvePnP expects specific point format and will raise cv2.error
    with pytest.raises(cv2.error):
      PointCorrespondenceTransform(pose, intrinsics)

  def test_init_with_missing_pose_keys(self):
    """Test initialization with missing pose keys"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([[100, 100], [200, 200], [300, 300], [400, 400]])
        # Missing 'map points'
    }
    with pytest.raises(KeyError):
      PointCorrespondenceTransform(pose, intrinsics)

  def test_init_with_none_intrinsics(self):
    """Test initialization with None intrinsics"""
    pose = {
        'camera points': np.array([[100, 100], [200, 200], [300, 300], [400, 400]]),
        'map points': np.array([[1, 2, 0], [3, 4, 0], [5, 6, 0], [7, 8, 0]])
    }
    with pytest.raises((TypeError, AttributeError)):
      PointCorrespondenceTransform(pose, None)

  def test_are_points_coplanar_insufficient_points(self):
    """Test coplanarity check with insufficient points - implementation may handle gracefully"""
    # Create a valid transform first with enough points
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400], [500, 500], [600, 600]
        ]),
        'map points': np.array([
            [1, 2, 0], [3, 4, 0], [5, 6, 0], [7, 8, 0], [9, 10, 0], [11, 12, 0]
        ])
    }
    transform = PointCorrespondenceTransform(pose, intrinsics)

    # Test with insufficient points - implementation may handle by returning False or a default
    insufficient_points = np.array([[1, 2, 0], [3, 4, 0]])  # Only 2 points
    result = transform.arePointsCoplanar(insufficient_points)
    # With only 2 points, coplanarity is undefined, but implementation may return False
    assert isinstance(result, bool)

class TestPointCorrespondenceTransformPrivateMethods:
  """Test private methods of PointCorrespondenceTransform class"""

  def get_test_transform(self):
    """Helper to create a test PointCorrespondenceTransform"""
    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400], [500, 500], [600, 600]
        ]),
        'map points': np.array([
            [1, 2, 0], [3, 4, 0], [5, 6, 0], [7, 8, 0], [9, 10, 0], [11, 12, 0]
        ])
    }
    return PointCorrespondenceTransform(pose, intrinsics)

  @patch('cv2.solvePnP')
  def test_calculate_pose_mat_iterative_method(self, mock_solve_pnp):
    """Test _calculatePoseMat with iterative method (coplanar points)"""
    # Mock cv2.solvePnP return values
    mock_rvec = np.array([[0.1], [0.2], [0.3]])
    mock_tvec = np.array([[1.0], [2.0], [3.0]])
    mock_solve_pnp.return_value = (True, mock_rvec, mock_tvec)

    transform = self.get_test_transform()

    # Verify that the pose matrix and properties are set
    assert hasattr(transform, 'pose_mat')
    assert transform.pose_mat.shape == (4, 4)
    assert hasattr(transform, 'translation')
    assert hasattr(transform, 'quaternion_rotation')
    assert hasattr(transform, 'euler_rotation')
    assert hasattr(transform, 'scale')

    # Verify cv2.solvePnP was called with ITERATIVE method
    mock_solve_pnp.assert_called_once()
    args, kwargs = mock_solve_pnp.call_args
    assert kwargs['flags'] == cv2.SOLVEPNP_ITERATIVE

  @patch('cv2.solvePnP')
  def test_calculate_pose_mat_p3p_method(self, mock_solve_pnp):
    """Test _calculatePoseMat with P3P method (non-coplanar points, <6 points)"""
    # Mock cv2.solvePnP return values
    mock_rvec = np.array([[0.2], [0.3], [0.4]])
    mock_tvec = np.array([[2.0], [3.0], [4.0]])
    mock_solve_pnp.return_value = (True, mock_rvec, mock_tvec)

    intrinsics = CameraIntrinsics([800, 800, 320, 240])
    # Create points that are clearly non-coplanar with only 4 points
    pose = {
        'camera points': np.array([
            [100, 100], [200, 200], [300, 300], [400, 400]
        ]),
        'map points': np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]  # Unit tetrahedron vertices
        ])
    }

    # Create transform which should trigger P3P method due to non-coplanar points and <6 points
    with patch.object(PointCorrespondenceTransform, 'arePointsCoplanar', return_value=False):
      transform = PointCorrespondenceTransform(pose, intrinsics)

    # Verify cv2.solvePnP was called with P3P method
    mock_solve_pnp.assert_called_once()
    args, kwargs = mock_solve_pnp.call_args
    assert kwargs['flags'] == cv2.SOLVEPNP_P3P

  def test_calculate_pose_mat_properties_set(self):
    """Test that _calculatePoseMat sets all required properties"""
    with patch('cv2.solvePnP') as mock_solve_pnp:
      # Mock cv2.solvePnP return values
      mock_rvec = np.array([[0.15], [0.25], [0.35]])
      mock_tvec = np.array([[1.5], [2.5], [3.5]])
      mock_solve_pnp.return_value = (True, mock_rvec, mock_tvec)

      transform = self.get_test_transform()

      # Verify all properties are set and have reasonable values
      assert isinstance(transform.translation, Point)
      assert transform.translation.is3D

      assert isinstance(transform.quaternion_rotation, np.ndarray)
      assert len(transform.quaternion_rotation) == 4

      assert isinstance(transform.euler_rotation, np.ndarray)
      assert len(transform.euler_rotation) == 3

      assert isinstance(transform.scale, list)
      assert len(transform.scale) == 3

      assert isinstance(transform.pose_mat, np.ndarray)
      assert transform.pose_mat.shape == (4, 4)

if __name__ == "__main__":
  pytest.main([__file__])
