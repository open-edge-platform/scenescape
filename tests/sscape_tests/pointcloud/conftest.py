#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
from pathlib import Path

# The point cloud registration module lives in autocalibration/src, which is
# copied to the import path inside the container. On the host it must be added
# explicitly so these unit tests can run without a container.
_AUTOCALIB_SRC = Path(__file__).resolve().parents[3] / "autocalibration" / "src"
if str(_AUTOCALIB_SRC) not in sys.path:
  sys.path.insert(0, str(_AUTOCALIB_SRC))

import numpy as np
import open3d as o3d
import pytest

from point_cloud_registration import PointCloudRegistration

TEST_MEDIA_PATH = os.path.abspath(os.path.join(__file__, "../../../ui/test_media/"))
GLB_PATH = TEST_MEDIA_PATH + "/box.glb"
BAD_GLB_PATH = TEST_MEDIA_PATH + "/box_invalid.glb"


def pytest_configure(config):
  """! Register custom markers used by the point cloud tests. """
  config.addinivalue_line(
    "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")


def _make_box_cloud(n_points, extent=2.0, seed=0):
  """! Builds a synthetic point cloud sampled from the surface of a box.

  @param    n_points   Number of points to sample.
  @param    extent     Half-extent of the box in meters.
  @param    seed       RNG seed for reproducibility.

  @return   o3d.geometry.PointCloud with estimated normals.
  """
  o3d.utility.random.seed(seed)
  mesh = o3d.geometry.TriangleMesh.create_box(width=extent, height=extent,
                                              depth=extent)
  mesh.compute_vertex_normals()
  pcd = mesh.sample_points_uniformly(number_of_points=n_points)
  pcd.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(radius=extent * 0.1, max_nn=30))
  return pcd


def _known_transform():
  """! Returns a known rigid 4x4 transform (rotation + translation). """
  angle = np.deg2rad(12.0)
  cos_a = np.cos(angle)
  sin_a = np.sin(angle)
  transform = np.eye(4)
  transform[:3, :3] = np.array([[cos_a, -sin_a, 0.0],
                                [sin_a, cos_a, 0.0],
                                [0.0, 0.0, 1.0]])
  transform[:3, 3] = [0.15, -0.10, 0.05]
  return transform


@pytest.fixture(scope="module")
def registration():
  """! Returns a PointCloudRegistration instance with test-scale voxels. """
  return PointCloudRegistration(voxel_size=0.02, scene_sample_points=50000)


@pytest.fixture(scope="module")
def glb_file():
  """! Returns the path to a valid GLB scene mesh. """
  return GLB_PATH


@pytest.fixture(scope="module")
def bad_glb_file():
  """! Returns the path to an invalid GLB file. """
  return BAD_GLB_PATH


@pytest.fixture(scope="module")
def target_cloud():
  """! Returns a synthetic target (scene) point cloud. """
  return _make_box_cloud(40000, seed=1)


@pytest.fixture(scope="module")
def known_transform():
  """! Returns the known 4x4 transform used to displace the source cloud. """
  return _known_transform()


@pytest.fixture(scope="module")
def source_cloud(target_cloud, known_transform):
  """! Returns the target cloud displaced by the inverse of the known
       transform, so that registering source onto target should recover the
       known transform. """
  source = o3d.geometry.PointCloud(target_cloud)
  source.transform(np.linalg.inv(known_transform))
  return source


@pytest.fixture(scope="module")
def pcd_bytes(target_cloud, tmp_path_factory):
  """! Returns a valid point cloud serialized as compressed binary PCD bytes.

  PCD is the default / first-class point cloud format. """
  path = str(tmp_path_factory.mktemp("pcd") / "cloud.pcd")
  o3d.io.write_point_cloud(path, target_cloud, write_ascii=False, compressed=True)
  with open(path, "rb") as handle:
    return handle.read()


@pytest.fixture(scope="module")
def pcd_ascii_bytes(target_cloud, tmp_path_factory):
  """! Returns a valid point cloud serialized as uncompressed ASCII PCD bytes. """
  path = str(tmp_path_factory.mktemp("pcd_ascii") / "cloud.pcd")
  o3d.io.write_point_cloud(path, target_cloud, write_ascii=True)
  with open(path, "rb") as handle:
    return handle.read()


@pytest.fixture(scope="module")
def pcd_binary_bytes(target_cloud, tmp_path_factory):
  """! Returns a valid point cloud serialized as uncompressed binary PCD bytes. """
  path = str(tmp_path_factory.mktemp("pcd_binary") / "cloud.pcd")
  o3d.io.write_point_cloud(path, target_cloud, write_ascii=False, compressed=False)
  with open(path, "rb") as handle:
    return handle.read()


@pytest.fixture(scope="module")
def ply_bytes(target_cloud, tmp_path_factory):
  """! Returns a valid point cloud serialized as binary PLY bytes.

  PLY is retained only to cover the interoperability path. """
  path = str(tmp_path_factory.mktemp("ply") / "cloud.ply")
  o3d.io.write_point_cloud(path, target_cloud, write_ascii=False)
  with open(path, "rb") as handle:
    return handle.read()
