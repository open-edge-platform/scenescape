#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os

import numpy as np
import open3d as o3d
import pytest

from scene_common.geometry import Region, Point
from scene_common.mesh_util import createRegionMesh, createObjectMesh, mergeMesh

dir = os.path.dirname(os.path.abspath(__file__))
TEST_DATA = os.path.join(dir, "test_data/scene.glb")

@pytest.mark.parametrize("input,expected", [
  (TEST_DATA, 1),
])
def test_merge_mesh(input, expected):
  merged_mesh = mergeMesh(input)
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

