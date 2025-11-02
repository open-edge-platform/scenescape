#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for Mesh Utilities
Tests the mesh and point cloud utility functions.
"""

import pytest
import numpy as np
import trimesh
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from mesh_utils import createPointcloudFromMesh, getMeshInfo


class TestMeshUtils:
  """Test cases for mesh utility functions"""

  def test_create_pointcloud_from_mesh_basic(self):
    """Test creating point cloud from basic MapAnything predictions"""
    # Create mock predictions
    predictions = {
      "world_points": np.random.rand(2, 100, 100, 3).astype(np.float32),
      "images": np.random.randint(0, 255, (2, 100, 100, 3), dtype=np.uint8),
      "final_masks": np.ones((2, 100, 100), dtype=bool)
    }

    scene = createPointcloudFromMesh(predictions)

    assert isinstance(scene, trimesh.Scene)
    assert len(scene.geometry) > 0

  def test_create_pointcloud_without_masks(self):
    """Test creating point cloud without masks"""
    predictions = {
      "world_points": np.random.rand(2, 50, 50, 3).astype(np.float32),
      "images": np.random.randint(0, 255, (2, 50, 50, 3), dtype=np.uint8),
    }

    scene = createPointcloudFromMesh(predictions)

    assert isinstance(scene, trimesh.Scene)
    assert len(scene.geometry) > 0

  def test_create_pointcloud_without_images(self):
    """Test creating point cloud without color information"""
    predictions = {
      "world_points": np.random.rand(2, 50, 50, 3).astype(np.float32),
      "final_masks": np.ones((2, 50, 50), dtype=bool)
    }

    scene = createPointcloudFromMesh(predictions)

    assert isinstance(scene, trimesh.Scene)
    assert len(scene.geometry) > 0

  def test_create_pointcloud_with_partial_masks(self):
    """Test creating point cloud with partial masks (some points filtered out)"""
    # Create masks that filter out half the points
    masks = np.zeros((2, 50, 50), dtype=bool)
    masks[:, :25, :] = True  # Keep first half

    predictions = {
      "world_points": np.random.rand(2, 50, 50, 3).astype(np.float32),
      "images": np.random.randint(0, 255, (2, 50, 50, 3), dtype=np.uint8),
      "final_masks": masks
    }

    scene = createPointcloudFromMesh(predictions)

    assert isinstance(scene, trimesh.Scene)
    # Check that point cloud was created with filtered points
    for geom in scene.geometry.values():
      if hasattr(geom, 'vertices'):
        # Should have fewer points due to masking
        assert len(geom.vertices) < (2 * 50 * 50)

  def test_create_pointcloud_with_nan_points(self):
    """Test that NaN points are filtered out"""
    # Create points with some NaNs
    world_points = np.random.rand(2, 50, 50, 3).astype(np.float32)
    world_points[0, 10:20, 10:20, :] = np.nan  # Add some NaN values

    predictions = {
      "world_points": world_points,
      "images": np.random.randint(0, 255, (2, 50, 50, 3), dtype=np.uint8),
      "final_masks": np.ones((2, 50, 50), dtype=bool)
    }

    scene = createPointcloudFromMesh(predictions)

    assert isinstance(scene, trimesh.Scene)
    # Verify no NaN points in the final point cloud
    for geom in scene.geometry.values():
      if hasattr(geom, 'vertices'):
        assert not np.any(np.isnan(geom.vertices))

  def test_create_pointcloud_with_inf_points(self):
    """Test that infinite points are filtered out"""
    # Create points with some infinities
    world_points = np.random.rand(2, 50, 50, 3).astype(np.float32)
    world_points[0, 5:10, 5:10, :] = np.inf  # Add some infinite values

    predictions = {
      "world_points": world_points,
      "images": np.random.randint(0, 255, (2, 50, 50, 3), dtype=np.uint8),
      "final_masks": np.ones((2, 50, 50), dtype=bool)
    }

    scene = createPointcloudFromMesh(predictions)

    assert isinstance(scene, trimesh.Scene)
    # Verify no infinite points in the final point cloud
    for geom in scene.geometry.values():
      if hasattr(geom, 'vertices'):
        assert not np.any(np.isinf(geom.vertices))

  def test_create_pointcloud_color_normalization(self):
    """Test that colors above 1.0 are normalized"""
    predictions = {
      "world_points": np.random.rand(1, 10, 10, 3).astype(np.float32),
      "images": np.random.randint(0, 255, (1, 10, 10, 3), dtype=np.uint8),
      "final_masks": np.ones((1, 10, 10), dtype=bool)
    }

    scene = createPointcloudFromMesh(predictions)

    # Check that colors are normalized
    for geom in scene.geometry.values():
      if hasattr(geom, 'visual') and hasattr(geom.visual, 'vertex_colors'):
        colors = geom.visual.vertex_colors[:, :3] / 255.0  # trimesh stores as 0-255
        assert np.all(colors <= 1.0)
        assert np.all(colors >= 0.0)

  def test_create_pointcloud_missing_world_points(self):
    """Test that missing world_points raises error"""
    predictions = {
      "images": np.random.randint(0, 255, (2, 50, 50, 3), dtype=np.uint8),
      "final_masks": np.ones((2, 50, 50), dtype=bool)
    }

    with pytest.raises(ValueError, match="No world_points found"):
      createPointcloudFromMesh(predictions)

  def test_get_mesh_info_with_mesh(self):
    """Test getMeshInfo with a mesh"""
    # Create a simple mesh
    vertices = np.array([
      [0, 0, 0],
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1]
    ])
    faces = np.array([
      [0, 1, 2],
      [0, 1, 3],
      [0, 2, 3],
      [1, 2, 3]
    ])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    scene = trimesh.Scene([mesh])

    info = getMeshInfo(scene)

    assert info["geometries"] == 1
    assert info["total_vertices"] == 4
    assert info["total_faces"] == 4
    assert "mesh" in info["geometry_types"]

  def test_get_mesh_info_with_pointcloud(self):
    """Test getMeshInfo with a point cloud"""
    # Create a point cloud
    points = np.random.rand(100, 3)
    colors = np.random.rand(100, 3)

    pointcloud = trimesh.PointCloud(vertices=points, colors=colors)
    scene = trimesh.Scene([pointcloud])

    info = getMeshInfo(scene)

    assert info["geometries"] == 1
    assert info["total_vertices"] == 100
    assert info["total_faces"] == 0
    assert "pointcloud" in info["geometry_types"]
    assert info["has_colors"] is True

  def test_get_mesh_info_with_multiple_geometries(self):
    """Test getMeshInfo with multiple geometries"""
    # Create mesh
    mesh_vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    mesh_faces = np.array([[0, 1, 2]])
    mesh = trimesh.Trimesh(vertices=mesh_vertices, faces=mesh_faces)

    # Create point cloud
    points = np.random.rand(50, 3)
    pointcloud = trimesh.PointCloud(vertices=points)

    scene = trimesh.Scene([mesh, pointcloud])

    info = getMeshInfo(scene)

    assert info["geometries"] == 2
    assert info["total_vertices"] == 53  # 3 from mesh + 50 from pointcloud
    assert info["total_faces"] == 1
    assert "mesh" in info["geometry_types"]
    assert "pointcloud" in info["geometry_types"]

  def test_get_mesh_info_empty_scene(self):
    """Test getMeshInfo with empty scene"""
    scene = trimesh.Scene()

    info = getMeshInfo(scene)

    assert info["geometries"] == 0
    assert info["total_vertices"] == 0
    assert info["total_faces"] == 0
    assert info["has_colors"] is False
    assert info["is_watertight"] is False

  def test_get_mesh_info_watertight_mesh(self):
    """Test getMeshInfo detects watertight meshes"""
    # Create a watertight mesh (simple cube)
    mesh = trimesh.creation.box()
    scene = trimesh.Scene([mesh])

    info = getMeshInfo(scene)

    assert info["is_watertight"] is True

  def test_get_mesh_info_non_watertight_mesh(self):
    """Test getMeshInfo detects non-watertight meshes"""
    # Create a non-watertight mesh (single triangle)
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    faces = np.array([[0, 1, 2]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    scene = trimesh.Scene([mesh])

    info = getMeshInfo(scene)

    assert info["is_watertight"] is False


if __name__ == "__main__":
  pytest.main([__file__, "-v"])
