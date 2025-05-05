#!/usr/bin/env python3


# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import pytest
from scene_common.mesh_util import mergeMesh
import open3d as o3d
import os

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
