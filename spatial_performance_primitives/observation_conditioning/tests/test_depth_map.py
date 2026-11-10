# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Ray-cast depth maps and free-space conditioning on deterministic meshes."""

import numpy as np
import open3d as o3d
import pytest

from observation_conditioning import AmodalReasoner
from observation_conditioning.intersection_map import DepthMap


def _plane(z, width=20.0):
  half = width / 2
  vertices = o3d.utility.Vector3dVector([
    [-half, -half, z], [half, -half, z], [half, half, z], [-half, half, z],
  ])
  triangles = o3d.utility.Vector3iVector([[0, 1, 2], [0, 2, 3]])
  return o3d.geometry.TriangleMesh(vertices, triangles)


def _tensor_mesh(*slab_depths):
  mesh = _plane(slab_depths[0])
  for depth in slab_depths[1:]:
    mesh += _plane(depth)
  return o3d.t.geometry.TriangleMesh.from_legacy(mesh)


def _camera():
  intrinsics = np.array([
    [1.0, 0.0, 1.0],
    [0.0, 1.0, 1.0],
    [0.0, 0.0, 1.0],
  ])
  return intrinsics, np.eye(4)


def test_depth_map_queries_center_ray_and_returns_misses_outside_image():
  intrinsics, extrinsics = _camera()
  depth_map = DepthMap(intrinsics, extrinsics, _tensor_mesh(2.0), 3, 3)
  depth_map.populate()

  hits, normals = depth_map.query(np.array([
    [0.0, 0.0, 5.0],
    [100.0, 0.0, 5.0],
    [0.0, 0.0, -1.0],
  ]))

  assert hits[0] == pytest.approx(2.0, abs=1e-5)
  assert np.isinf(hits[1:]).all()
  assert np.isfinite(normals[0]).all()
  assert np.isnan(normals[1:]).all()


def test_depth_map_peels_successive_surfaces_along_a_ray():
  intrinsics, extrinsics = _camera()
  depth_map = DepthMap(intrinsics, extrinsics, _tensor_mesh(2.0, 4.0), 3, 3,
                       num_layers=2)
  depth_map.populate()

  hits, normals = depth_map.query(np.array([[0.0, 0.0, 6.0]]))

  np.testing.assert_allclose(hits[0], [2.0, 4.0], atol=2e-4)
  assert np.isfinite(normals[0]).all()


def test_amodal_reasoner_preserves_free_space_depth_gaussian():
  intrinsics, extrinsics = _camera()
  reasoner = AmodalReasoner(
    mesh=_tensor_mesh(30.0), rwc_z_up=np.array([0.0, 0.0, 1.0]),
    camera_intrinsics=intrinsics, camera_extrinsics=extrinsics,
    width=3, height=3,
  )
  observations = {
    "mu": np.zeros((1, 3), dtype=np.float32),
    "Sigma": (np.eye(3, dtype=np.float32) * 0.01)[None, :, :],
    "ray": np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
    "depth_est": np.array([5.0], dtype=np.float32),
    "depth_lo": np.array([4.0], dtype=np.float32),
    "depth_hi": np.array([6.0], dtype=np.float32),
  }

  depth, variance = reasoner.generate(observations)

  np.testing.assert_allclose(depth, observations["depth_est"], atol=1e-5)
  np.testing.assert_allclose(variance, [0.01], atol=1e-5)
