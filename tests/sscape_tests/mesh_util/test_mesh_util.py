#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

import numpy as np
import open3d as o3d
import pytest
import trimesh
from plyfile import PlyData, PlyElement
import tempfile

from scene_common.geometry import Region, Point
from scene_common.mesh_util import createRegionMesh, createObjectMesh, mergeMesh, extractMeshFromPointCloud, extractMeshFromGLB
from scene_common.mesh_util import checkMeshConnectivity

dir = os.path.dirname(os.path.abspath(__file__))
TEST_DATA = os.path.join(dir, "test_data/scene.glb")

def create_fake_ply(file_path, num_points = 500):
  """Create a small synthetic colored point cloud and save as .ply"""
  vertices = np.zeros(num_points, dtype=[
        ('x', 'f4'),
        ('y', 'f4'),
        ('z', 'f4'),
        ('diffuse_red', 'u1'),
        ('diffuse_green', 'u1'),
        ('diffuse_blue', 'u1')
  ])

  # Simple sphere-shaped point cloud
  theta = np.random.rand(num_points) * 2 * np.pi
  phi = np.random.rand(num_points) * np.pi
  r = 0.5 + np.random.rand(num_points) * 0.1

  vertices['x'] = r * np.sin(phi) * np.cos(theta)
  vertices['y'] = r * np.sin(phi) * np.sin(theta)
  vertices['z'] = r * np.cos(phi)

  # random colors
  vertices['diffuse_red'] = np.random.randint(0, 255, num_points)
  vertices['diffuse_green'] = np.random.randint(0, 255, num_points)
  vertices['diffuse_blue'] = np.random.randint(0, 255, num_points)

  el = PlyElement.describe(vertices, 'vertex')
  PlyData([el]).write(file_path)
  return

@pytest.mark.parametrize("input,expected", [
  (TEST_DATA, 1),
])
def test_merge_mesh(input, expected):
  scene = trimesh.load(input)
  merged_mesh = mergeMesh(scene)
  assert merged_mesh.metadata["name"] == "mesh_0"
  merged_mesh.export(input)
  mesh =  o3d.io.read_triangle_model(input)
  assert len(mesh.meshes) == expected
  return

class TestObject:
  def __init__(self, loc, size, rotation):
    self.sceneLoc = loc
    self.size = size
    self.rotation = rotation
    self.mesh = None

def test_create_region_mesh():
  # Create a simple square region
  points = [
    [0, 0],
    [0, 1],
    [1, 1],
    [1, 0]
  ]
  region = Region("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "test_region", {'points': points, 'buffer_size': 0.1, 'height': 2.0})

  # Execute function
  createRegionMesh(region)

  # Verify mesh was created
  assert region.mesh is not None
  assert isinstance(region.mesh, o3d.geometry.TriangleMesh)

  # Check mesh properties
  vertices = np.asarray(region.mesh.vertices)
  assert len(vertices) > 0

  # Check height of mesh matches the region height
  z_values = vertices[:, 2]
  assert np.max(z_values) == pytest.approx(region.height)
  assert np.min(z_values) == pytest.approx(0.0)

  # Check width and length of mesh (with buffer)
  x_values = vertices[:, 0]
  y_values = vertices[:, 1]
  expected_width = 1.0 + 2 * region.buffer_size  # 1 unit width + buffer on each side
  expected_length = 1.0 + 2 * region.buffer_size  # 1 unit length + buffer on each side
  assert np.max(x_values) - np.min(x_values) == pytest.approx(expected_width)
  assert np.max(y_values) - np.min(y_values) == pytest.approx(expected_length)

def test_create_object_mesh():
  # Create test object
  loc = Point(1.0, 2.0, 0.0)
  size = [2.0, 3.0, 4.0]
  rotation = [0, 0, 0, 1]
  obj = TestObject(loc, size, rotation)

  # Execute function
  createObjectMesh(obj)

  # Verify mesh was created
  assert obj.mesh is not None
  assert isinstance(obj.mesh, o3d.geometry.TriangleMesh)

  # Check mesh has correct number of vertices (box has 8 vertices)
  vertices = np.asarray(obj.mesh.vertices)
  assert len(vertices) == 8

  # Check mesh dimensions using the axis-aligned bounding box
  bbox = obj.mesh.get_axis_aligned_bounding_box()
  bbox_min = bbox.get_min_bound()
  bbox_max = bbox.get_max_bound()

  # Check dimensions match requested size
  assert bbox_max[0] - bbox_min[0] == pytest.approx(size[0])
  assert bbox_max[1] - bbox_min[1] == pytest.approx(size[1])
  assert bbox_max[2] - bbox_min[2] == pytest.approx(size[2])

def test_extract_mesh_from_point_cloud():
  with tempfile.TemporaryDirectory() as tmpdir:
    ply_path = os.path.join(tmpdir, "fake_cloud.ply")
    create_fake_ply(ply_path)

    # Run mesh extraction
    glb_path = extractMeshFromPointCloud(ply_path)

    # Verify GLB was exported
    assert os.path.exists(glb_path), f"Expected output file {glb_path} not found"

    triangle_mesh, tensor_mesh = extractMeshFromGLB(glb_path)

    assert triangle_mesh is not None, "Triangle mesh not created"
    assert isinstance(triangle_mesh, o3d.t.geometry.TriangleMesh)
    assert len(triangle_mesh.vertex.positions) > 0, "Triangle mesh has no vertices"
    assert len(triangle_mesh.triangle.indices) > 0, "Triangle mesh has no faces"
    assert tensor_mesh is not None, "Tensor mesh not created"

def test_check_mesh_connectivity_single_surface_is_connected():
  """A single connected surface is not reported as disjoint."""
  mesh = trimesh.creation.box(extents=(4, 4, 0.1))
  assert checkMeshConnectivity(mesh) is None

def test_check_mesh_connectivity_two_separated_surfaces_reported():
  """Two large surfaces separated by a real gap are reported as disjoint."""
  a = trimesh.creation.box(extents=(4, 4, 0.1))
  b = trimesh.creation.box(extents=(4, 4, 0.1))
  b.apply_translation((100, 0, 0))
  mesh = trimesh.util.concatenate([a, b])

  error = checkMeshConnectivity(mesh)
  assert error is not None
  assert "2 spatially separate surfaces" in error

def test_check_mesh_connectivity_overlapping_unwelded_surfaces_accepted():
  """Two dominant surfaces that occupy the same space but were never
  topologically welded (separate components, overlapping geometry) are a normal
  single-scene reconstruction and must be accepted."""
  a = trimesh.creation.box(extents=(4, 4, 0.1))
  b = trimesh.creation.box(extents=(4, 4, 0.1))
  # Place the second sheet almost coincident with the first: the two sheets
  # occupy essentially the same space (minimum separation far below the scene
  # scale) even though they are distinct connected components.
  b.apply_translation((0.02, 0, 0))
  mesh = trimesh.util.concatenate([a, b])

  assert checkMeshConnectivity(mesh) is None

def test_check_mesh_connectivity_small_debris_is_ignored():
  """A dominant surface with only small incidental fragments is accepted."""
  main = trimesh.creation.icosphere(subdivisions=3)  # ~1280 faces
  debris = trimesh.creation.box(extents=(0.1, 0.1, 0.1))  # 12 faces
  debris.apply_translation((50, 0, 0))
  mesh = trimesh.util.concatenate([main, debris])

  # The debris is far below the significance threshold, so no gap is reported.
  assert checkMeshConnectivity(mesh) is None

def test_check_mesh_connectivity_three_thirds_reported():
  """Three roughly equal disjoint surfaces (the observed failure) are reported."""
  parts = []
  for i in range(3):
    box = trimesh.creation.box(extents=(4, 4, 0.1))
    box.apply_translation((100 * i, 0, 0))
    parts.append(box)
  mesh = trimesh.util.concatenate(parts)

  error = checkMeshConnectivity(mesh)
  assert error is not None
  assert "3 spatially separate surfaces" in error

def test_check_mesh_connectivity_empty_mesh_returns_none():
  """A mesh with no faces cannot be analyzed and is not reported."""
  empty = trimesh.Trimesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64))
  assert checkMeshConnectivity(empty) is None

