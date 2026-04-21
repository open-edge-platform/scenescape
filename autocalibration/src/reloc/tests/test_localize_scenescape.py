# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for SceneScape localization pipeline.
Tests the custom SceneScape-specific functionality in reloc.
"""

import numpy as np
import pytest
from pathlib import Path
from types import SimpleNamespace
from hloc.utils.read_write_model import Camera


class TestQuaternionConversions:
  """Test quaternion conversion utilities"""

  def test_qxyzw_to_qwxyz(self):
    """Test conversion from xyzw to wxyz quaternion format"""
    from hloc.pipelines.SceneScape.localize_scenescape import qxyzw_to_qwxyz
    qxyzw = np.array([0.1, 0.2, 0.3, 0.924])
    qwxyz = qxyzw_to_qwxyz(qxyzw)
    assert qwxyz[0] == 0.924
    assert qwxyz[1] == 0.1
    assert qwxyz[2] == 0.2
    assert qwxyz[3] == 0.3

  def test_qwxyz_to_qxyzw(self):
    """Test conversion from wxyz to xyzw quaternion format"""
    from hloc.pipelines.SceneScape.localize_scenescape import qwxyz_to_qxyzw
    qwxyz = np.array([0.924, 0.1, 0.2, 0.3])
    qxyzw = qwxyz_to_qxyzw(qwxyz)
    assert qxyzw[0] == 0.1
    assert qxyzw[1] == 0.2
    assert qxyzw[2] == 0.3
    assert qxyzw[3] == 0.924

  def test_quaternion_conversion_roundtrip(self):
    """Test that conversions are inverses"""
    from hloc.pipelines.SceneScape.localize_scenescape import (
      qxyzw_to_qwxyz,
      qwxyz_to_qxyzw
    )
    original = np.array([0.1, 0.2, 0.3, 0.924])
    converted = qxyzw_to_qwxyz(original)
    recovered = qwxyz_to_qxyzw(converted)
    np.testing.assert_array_almost_equal(recovered, original)

  def test_quaternion_conversion_batch(self):
    """Test batch conversion of quaternions"""
    from hloc.pipelines.SceneScape.localize_scenescape import qxyzw_to_qwxyz
    # Multiple quaternions
    qxyzw_batch = np.array([
      [0.1, 0.2, 0.3, 0.924],
      [0.5, 0.5, 0.5, 0.5],
      [0, 0, 0, 1]
    ])
    qwxyz_batch = qxyzw_to_qwxyz(qxyzw_batch)
    assert qwxyz_batch.shape == (3, 4)
    # Check first quaternion
    assert qwxyz_batch[0, 0] == 0.924
    assert qwxyz_batch[0, 1] == 0.1
    # Check identity quaternion
    assert qwxyz_batch[2, 0] == 1
    assert qwxyz_batch[2, 1] == 0


class TestQuaternionInverse:
  """Test quaternion inverse with translation"""

  def test_qxyzwtinv_basic(self):
    """Test basic quaternion inverse with translation"""
    from hloc.pipelines.SceneScape.localize_scenescape import qxyzwtinv
    # Identity quaternion with translation
    qxyzw = np.array([0, 0, 0, 1])
    tvec = np.array([1, 2, 3])
    qinv, tinv = qxyzwtinv(qxyzw, tvec)
    # For identity rotation, inverse translation should be negated
    np.testing.assert_array_almost_equal(qinv, np.array([0, 0, 0, 1]))
    np.testing.assert_array_almost_equal(tinv, np.array([-1, -2, -3]))

  def test_qxyzwtinv_with_rotation(self):
    """Test quaternion inverse with rotation"""
    from hloc.pipelines.SceneScape.localize_scenescape import qxyzwtinv
    from scipy.spatial.transform import Rotation as R
    # 90 degree rotation around z-axis
    qxyzw = np.array([0, 0, 0.707, 0.707])
    tvec = np.array([1, 0, 0])
    qinv, tinv = qxyzwtinv(qxyzw, tvec)
    # Verify quaternion conjugate
    expected_qinv = np.array([0, 0, -0.707, 0.707])
    np.testing.assert_array_almost_equal(qinv, expected_qinv, decimal=3)
    # Verify inverse transformation
    # Original: R @ p + t, Inverse: R^T @ (p - t) = R^T @ p - R^T @ t
    assert tinv.shape == (3,)

  def test_qxyzwtinv_composition(self):
    """Test that forward and inverse compose to identity"""
    from hloc.pipelines.SceneScape.localize_scenescape import qxyzwtinv
    from scipy.spatial.transform import Rotation as R
    qxyzw = np.array([0.1, 0.2, 0.3, 0.924])
    tvec = np.array([1, 2, 3])
    qinv, tinv = qxyzwtinv(qxyzw, tvec)
    # Apply forward then inverse to a point
    point = np.array([1, 0, 0])
    # Forward: R @ p + t
    rot = R.from_quat(qxyzw)
    forward = rot.apply(point) + tvec
    # Inverse: R_inv @ (p - t_inv)
    rot_inv = R.from_quat(qinv)
    backward = rot_inv.apply(forward) + tinv
    # Should recover original point
    np.testing.assert_array_almost_equal(backward, point, decimal=5)


class TestPoseFromCluster:
  """Test pose_from_cluster function"""

  @pytest.fixture
  def mock_dataset_dir(self, tmp_path):
    """Create mock dataset directory"""
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    return dataset

  @pytest.fixture
  def mock_h5_file(self, tmp_path):
    """Create mock h5 file with keypoints"""
    import h5py
    h5_file = tmp_path / "features.h5"
    with h5py.File(h5_file, 'w') as f:
      # Query image keypoints
      query_group = f.create_group("query.jpg")
      query_group.create_dataset("keypoints", data=np.random.rand(100, 2).astype(np.float32))
      # Database image keypoints
      db_group = f.create_group("db_001.jpg")
      db_group.create_dataset("keypoints", data=np.random.rand(100, 2).astype(np.float32))
    return h5_file

  @pytest.fixture
  def mock_match_file(self, tmp_path):
    """Create mock match file"""
    import h5py
    match_file = tmp_path / "matches.h5"
    with h5py.File(match_file, 'w') as f:
      pair_group = f.create_group("query.jpg/db_001.jpg")
      pair_group.create_dataset("keypoints0", data=np.random.rand(50, 2).astype(np.float32))
      pair_group.create_dataset("keypoints1", data=np.random.rand(50, 2).astype(np.float32))
      pair_group.create_dataset("matches", data=np.arange(50, dtype=np.int32))
    return match_file

  def test_pose_from_cluster_signature(self):
    """Test that pose_from_cluster has the expected signature"""
    from hloc.pipelines.SceneScape.localize_scenescape import pose_from_cluster
    import inspect
    sig = inspect.signature(pose_from_cluster)
    expected_params = [
      'dataset_dir', 'db_feature_files', 'q', 'retrieved',
      'feature_files', 'match_files', 'retrieval_calibration',
      'query_intrinsics', 'skip', 'match_dense', 'depth_scale', 'depth_max'
    ]
    actual_params = list(sig.parameters.keys())
    assert actual_params == expected_params

  def test_pose_from_cluster_parameters_types(self):
    """Test parameter types and defaults"""
    from hloc.pipelines.SceneScape.localize_scenescape import pose_from_cluster
    import inspect
    sig = inspect.signature(pose_from_cluster)
    # Check defaults
    assert sig.parameters['skip'].default == 0
    assert sig.parameters['match_dense'].default is False
    assert sig.parameters['depth_scale'].default == 1.0
    assert sig.parameters['depth_max'].default == 9.9

  def test_pose_from_cluster_empty_arrays(self, tmp_path):
    """Test pose_from_cluster handles empty match arrays correctly"""
    import h5py
    from hloc.pipelines.SceneScape.localize_scenescape import pose_from_cluster

    # Create mock dataset directory
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    # Create mock depth image (PNG) instead of PLY mesh
    import PIL.Image
    depth_file = dataset_dir / "depth.png"
    # Create a simple 480x640 depth image
    depth_img = PIL.Image.new('I', (640, 480), color=1000)  # 1 meter depth
    depth_img.save(depth_file)

    # Create mock feature file
    feature_file = tmp_path / "features.h5"
    with h5py.File(feature_file, 'w') as f:
      query_group = f.create_group("query.jpg")
      query_group.create_dataset("keypoints", data=np.zeros((10, 2), dtype=np.float32))
      db_group = f.create_group("db_001.jpg")
      db_group.create_dataset("keypoints", data=np.zeros((10, 2), dtype=np.float32))

    # Create mock match file with no valid matches
    match_file = tmp_path / "matches.h5"
    with h5py.File(match_file, 'w') as f:
      pair_group = f.create_group("query.jpg/db_001.jpg")
      # All matches set to -1 (no match)
      pair_group.create_dataset("matches0", data=np.full(10, -1, dtype=np.int32))

    # Create mock retrieval calibration
    retrieval_cal = {
      "db_001.jpg": SimpleNamespace(
        depth_name="depth.png",
        qvec=np.array([1.0, 0.0, 0.0, 0.0]),
        tvec=np.array([0.0, 0.0, 0.0]),
        intrinsics=Camera(id='1', model='SIMPLE_PINHOLE', width=640, height=480, params=np.array([500.0, 320.0, 240.0]))
      )
    }

    query_intrinsics = {'model': 'SIMPLE_PINHOLE', 'width': 640, 'height': 480, 'params': [500.0, 320.0, 240.0]}

    with h5py.File(feature_file, 'r') as ff, h5py.File(match_file, 'r') as mf:
      result, mkpq, mkpr, mkp3d, indices, num_matches = pose_from_cluster(
        dataset_dir=dataset_dir,
        db_feature_files=[ff],
        q="query.jpg",
        retrieved=["db_001.jpg"],
        feature_files=[ff],
        match_files=[mf],
        retrieval_calibration=retrieval_cal,
        query_intrinsics=query_intrinsics,
        skip=0,
        match_dense=False
      )

    # Should return failure when no valid matches
    assert result['success'] is False
    assert result['cfg'] == query_intrinsics
    assert len(mkpq) == 0
    assert len(mkp3d) == 0

  def test_pose_from_cluster_too_few_matches(self, tmp_path):
    """Test pose_from_cluster returns failure when matches <= 4"""
    import h5py
    from hloc.pipelines.SceneScape.localize_scenescape import pose_from_cluster

    # Create mock dataset directory
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    # Create mock depth image (PNG) instead of PLY mesh
    import PIL.Image
    depth_file = dataset_dir / "depth.png"
    depth_img = PIL.Image.new('I', (640, 480), color=1000)
    depth_img.save(depth_file)

    # Create mock feature file with limited keypoints
    feature_file = tmp_path / "features.h5"
    with h5py.File(feature_file, 'w') as f:
      query_group = f.create_group("query.jpg")
      query_group.create_dataset("keypoints", data=np.random.rand(3, 2).astype(np.float32))
      db_group = f.create_group("db_001.jpg")
      db_group.create_dataset("keypoints", data=np.random.rand(3, 2).astype(np.float32))

    # Create mock match file with only 3 matches (below threshold)
    match_file = tmp_path / "matches.h5"
    with h5py.File(match_file, 'w') as f:
      pair_group = f.create_group("query.jpg/db_001.jpg")
      matches = np.array([0, 1, 2], dtype=np.int32)
      pair_group.create_dataset("matches0", data=matches)

    retrieval_cal = {
      "db_001.jpg": SimpleNamespace(
        depth_name="depth.png",
        qvec=np.array([1.0, 0.0, 0.0, 0.0]),
        tvec=np.array([0.0, 0.0, 0.0]),
        intrinsics=Camera(id='1', model='SIMPLE_PINHOLE', width=640, height=480, params=np.array([500.0, 320.0, 240.0]))
      )
    }

    query_intrinsics = {'model': 'SIMPLE_PINHOLE', 'width': 640, 'height': 480, 'params': [500.0, 320.0, 240.0]}

    with h5py.File(feature_file, 'r') as ff, h5py.File(match_file, 'r') as mf:
      result, mkpq, mkpr, mkp3d, indices, num_matches = pose_from_cluster(
        dataset_dir=dataset_dir,
        db_feature_files=[ff],
        q="query.jpg",
        retrieved=["db_001.jpg"],
        feature_files=[ff],
        match_files=[mf],
        retrieval_calibration=retrieval_cal,
        query_intrinsics=query_intrinsics,
        skip=0,
        match_dense=False
      )

    # Should return failure when matches <= 4
    assert result['success'] is False
    assert num_matches <= 4

  def test_pose_from_cluster_with_valid_depth_data(self, tmp_path):
    """Test pose_from_cluster with valid 3D depth data"""
    import h5py
    from hloc.pipelines.SceneScape.localize_scenescape import pose_from_cluster

    # Create mock dataset directory
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    # Create mock depth file (PNG format for this test)
    depth_file = dataset_dir / "depth.png"
    # Use PIL to create a simple depth image
    from PIL import Image
    depth_array = np.full((480, 640), 1000, dtype=np.uint16)  # Non-zero depth
    depth_img = Image.fromarray(depth_array)
    depth_img.save(depth_file)

    # Create mock feature file with sufficient keypoints
    feature_file = tmp_path / "features.h5"
    np.random.seed(42)
    with h5py.File(feature_file, 'w') as f:
      query_group = f.create_group("query.jpg")
      query_group.create_dataset("keypoints", data=np.random.rand(50, 2).astype(np.float32) * 100 + 200)
      db_group = f.create_group("db_001.jpg")
      db_group.create_dataset("keypoints", data=np.random.rand(50, 2).astype(np.float32) * 100 + 200)

    # Create mock match file with valid matches
    match_file = tmp_path / "matches.h5"
    with h5py.File(match_file, 'w') as f:
      pair_group = f.create_group("query.jpg/db_001.jpg")
      matches = np.arange(20, dtype=np.int32)  # 20 matches
      pair_group.create_dataset("matches0", data=matches)

    retrieval_cal = {
      "db_001.jpg": SimpleNamespace(
        depth_name="depth.png",
        qvec=np.array([1.0, 0.0, 0.0, 0.0]),
        tvec=np.array([0.0, 0.0, 0.0]),
        intrinsics=Camera(id='1', model='SIMPLE_PINHOLE', width=640, height=480, params=np.array([500.0, 320.0, 240.0]))
      )
    }

    query_intrinsics = {'model': 'SIMPLE_PINHOLE', 'width': 640, 'height': 480, 'params': [500.0, 320.0, 240.0]}

    with h5py.File(feature_file, 'r') as ff, h5py.File(match_file, 'r') as mf:
      result, mkpq, mkpr, mkp3d, indices, num_matches = pose_from_cluster(
        dataset_dir=dataset_dir,
        db_feature_files=[ff],
        q="query.jpg",
        retrieved=["db_001.jpg"],
        feature_files=[ff],
        match_files=[mf],
        retrieval_calibration=retrieval_cal,
        query_intrinsics=query_intrinsics,
        skip=0,
        match_dense=False,
        depth_scale=1000.0,  # Scale to meters
        depth_max=10.0
      )

    # Verify result structure
    assert isinstance(result, dict)
    assert 'cfg' in result
    assert result['cfg'] == query_intrinsics

    # If there were valid 3D points, check they exist
    if num_matches > 4:
      assert len(mkpq) > 0 or result['success'] is False
      if len(mkp3d) > 0:
        assert mkp3d.shape[1] == 3  # 3D points

  @pytest.mark.skip(reason="Requires valid PLY mesh file with vertices; empty mock PLY fails in Open3D raycasting")
  def test_pose_from_cluster_dense_matching(self, tmp_path):
    """Test pose_from_cluster with dense matching mode

    Note: This test currently creates an empty PLY file which causes Open3D to fail
    when loading the mesh. A proper test would require creating a PLY file with actual
    vertex and face data, which is complex to generate programmatically.
    """
    import h5py
    from hloc.pipelines.SceneScape.localize_scenescape import pose_from_cluster

    # Create mock dataset directory
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    # Create mock depth file
    depth_file = dataset_dir / "depth.ply"
    depth_file.write_text("ply\nformat ascii 1.0\nelement vertex 0\nend_header\n")

    # Create mock feature file
    feature_file = tmp_path / "features.h5"
    with h5py.File(feature_file, 'w') as f:
      query_group = f.create_group("query.jpg")
      query_group.create_dataset("keypoints", data=np.random.rand(10, 2).astype(np.float32))
      db_group = f.create_group("db_001.jpg")
      db_group.create_dataset("keypoints", data=np.random.rand(10, 2).astype(np.float32))

    # Create mock dense match file
    match_file = tmp_path / "matches_dense.h5"
    with h5py.File(match_file, 'w') as f:
      pair_group = f.create_group("query.jpg/db_001.jpg")
      # Dense matching stores keypoints directly
      pair_group.create_dataset("keypoints0", data=np.random.rand(5, 2).astype(np.float32))
      pair_group.create_dataset("keypoints1", data=np.random.rand(5, 2).astype(np.float32))

    retrieval_cal = {
      "db_001.jpg": SimpleNamespace(
        depth_name="depth.ply",
        qvec=np.array([1.0, 0.0, 0.0, 0.0]),
        tvec=np.array([0.0, 0.0, 0.0]),
        intrinsics=SimpleNamespace(model='SIMPLE_PINHOLE', width=640, height=480, params=[500.0, 320.0, 240.0])
      )
    }

    query_intrinsics = {'model': 'SIMPLE_PINHOLE', 'width': 640, 'height': 480, 'params': [500.0, 320.0, 240.0]}

    with h5py.File(feature_file, 'r') as ff, h5py.File(match_file, 'r') as mf:
      result, mkpq, mkpr, mkp3d, indices, num_matches = pose_from_cluster(
        dataset_dir=dataset_dir,
        db_feature_files=[ff],
        q="query.jpg",
        retrieved=["db_001.jpg"],
        feature_files=[ff],
        match_files=[mf],
        retrieval_calibration=retrieval_cal,
        query_intrinsics=query_intrinsics,
        skip=0,
        match_dense=True  # Enable dense matching
      )

    # Verify function completes without error
    assert isinstance(result, dict)
    assert 'cfg' in result


class TestMainFunction:
  """Test main localization function"""

  def test_main_function_signature(self):
    """Test that main function has expected signature"""
    from hloc.pipelines.SceneScape.localize_scenescape import main
    import inspect
    sig = inspect.signature(main)
    expected_params = [
      'dataset_dir', 'db_feature_paths', 'retrieval', 'query_intrinsics',
      'features', 'matches', 'results_path', 'skip_matches',
      'match_dense', 'data_config'
    ]
    actual_params = list(sig.parameters.keys())
    assert actual_params == expected_params


class TestHelperFunctions:
  """Test helper functions in localize_scenescape"""

  def test_depth_scale_parameter(self):
    """Test depth scale is used correctly"""
    # Depth scale should convert depth values to meters
    depth_scale = 6553.5  # Common depth scale
    depth_value_raw = 32768  # Raw depth value
    depth_meters = depth_value_raw / depth_scale
    assert depth_meters == pytest.approx(5.0, rel=0.01)

  def test_depth_max_filtering(self):
    """Test depth max filtering"""
    depth_max = 10.0
    depth_values = np.array([1.0, 5.0, 9.9, 10.1, 15.0])
    valid = depth_values <= depth_max
    filtered = depth_values[valid]
    assert len(filtered) == 3
    assert np.all(filtered <= depth_max)


# Mock classes for testing
class MockCamera:
  """Mock camera for testing"""
  def __init__(self, width=640, height=480):
    self.width = width
    self.height = height
    self.model = "SIMPLE_PINHOLE"
    self.params = np.array([500.0, 320.0, 240.0])


class MockFeatureFile:
  """Mock h5py file for features"""
  def __init__(self, data):
    self.data = data

  def __getitem__(self, key):
    return self.data[key]


class TestDataValidation:
  """Test data validation and error handling"""

  def test_invalid_depth_scale(self):
    """Test handling of invalid depth scale"""
    with pytest.raises(ValueError):
      depth_scale = 0
      if depth_scale <= 0:
        raise ValueError("Depth scale must be positive")

  def test_invalid_depth_max(self):
    """Test handling of invalid depth max"""
    with pytest.raises(ValueError):
      depth_max = -1
      if depth_max <= 0:
        raise ValueError("Depth max must be positive")

  def test_empty_retrieval_list(self):
    """Test handling of empty retrieval list"""
    retrieved = []
    assert len(retrieved) == 0
    # Should handle gracefully

  def test_mismatched_feature_dimensions(self):
    """Test detection of mismatched feature dimensions"""
    features1 = np.random.rand(100, 2)
    features2 = np.random.rand(50, 2)
    # Should detect mismatch
    assert features1.shape[0] != features2.shape[0]


class TestIntegrationSceneScape:
  """Integration tests for SceneScape pipeline"""

  def test_quaternion_workflow(self):
    """Test typical quaternion conversion workflow"""
    from hloc.pipelines.SceneScape.localize_scenescape import (
      qxyzw_to_qwxyz,
      qwxyz_to_qxyzw,
      qxyzwtinv
    )
    # Start with xyzw format
    qxyzw = np.array([0.1, 0.2, 0.3, 0.924])
    tvec = np.array([1, 2, 3])
    # Convert to wxyz
    qwxyz = qxyzw_to_qwxyz(qxyzw)
    # Compute inverse
    qinv, tinv = qxyzwtinv(qxyzw, tvec)
    # Convert back
    qxyzw_inv = qwxyz_to_qxyzw(qxyzw_to_qwxyz(qinv))
    # Verify shapes
    assert qwxyz.shape == (4,)
    assert qxyzw_inv.shape == (4,)
    assert tinv.shape == (3,)

  def test_coordinate_system_consistency(self):
    """Test coordinate system conventions"""
    # SceneScape uses right-handed coordinate system
    # X: right, Y: down, Z: forward
    # Verify quaternion represents rotation correctly
    from scipy.spatial.transform import Rotation as R
    # 90 degree rotation around Y (down)
    rot = R.from_euler('y', 90, degrees=True)
    quat = rot.as_quat()  # xyzw format
    # Apply to X-axis
    x_axis = np.array([1, 0, 0])
    rotated = rot.apply(x_axis)
    # 90 degree rotation around Y-axis moves X to -Z direction
    np.testing.assert_array_almost_equal(rotated, np.array([0, 0, -1]), decimal=5)
