#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time

import numpy as np
import open3d as o3d
import pytest

from conftest import _make_box_cloud

from point_cloud_registration import (PointCloudRegistration,
                                       PointCloudRegistrationError,
                                       PCD_FORMAT, PLY_FORMAT)


def test_detect_format_ply(plyBytes):
  """! PLY magic bytes are detected as the PLY format. """
  assert PointCloudRegistration.detect_format(plyBytes) == PLY_FORMAT


def test_detect_format_pcd(pcdBytes):
  """! PCD magic bytes are detected as the PCD format. """
  assert PointCloudRegistration.detect_format(pcdBytes) == PCD_FORMAT


def test_detect_format_invalid():
  """! Non point cloud bytes raise PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    PointCloudRegistration.detect_format(b"not-a-point-cloud-file")


def test_decode_point_cloud_ply(plyBytes):
  """! Valid PLY bytes decode into a non-empty point cloud. """
  pcd = PointCloudRegistration.decode_point_cloud(plyBytes)
  assert not pcd.is_empty()


def test_decode_point_cloud_pcd(pcdBytes):
  """! Valid PCD bytes decode into a non-empty point cloud. """
  pcd = PointCloudRegistration.decode_point_cloud(pcdBytes)
  assert not pcd.is_empty()


def test_decode_point_cloud_format_mismatch(plyBytes):
  """! A declared format that disagrees with the data raises an error. """
  with pytest.raises(PointCloudRegistrationError):
    PointCloudRegistration.decode_point_cloud(plyBytes, fmt=PCD_FORMAT)


def test_decode_point_cloud_invalid():
  """! Garbage bytes raise PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    PointCloudRegistration.decode_point_cloud(b"garbage-bytes-not-valid")


def test_scene_mesh_to_point_cloud_glb(registration, glbFile):
  """! A GLB scene mesh is sampled into a non-empty point cloud. """
  pcd = registration.scene_mesh_to_point_cloud(glbFile, number_of_points=10000)
  assert not pcd.is_empty()
  assert len(pcd.points) == 10000


def test_scene_mesh_to_point_cloud_no_map(registration):
  """! An empty map path raises PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    registration.scene_mesh_to_point_cloud("")


def test_serialize_point_cloud_roundtrip(registration, targetCloud, tmp_path):
  """! A serialized cloud can be read back with the same point count. """
  path = str(tmp_path / "roundtrip.pcd")
  registration.serialize_point_cloud(targetCloud, path)
  restored = o3d.io.read_point_cloud(path)
  assert len(restored.points) == len(targetCloud.points)


def test_register_recovers_known_transform(registration, sourceCloud,
                                            targetCloud, knownTransform):
  """! Registering a displaced source cloud recovers the known transform. """
  result = registration.register(sourceCloud, targetCloud)
  recovered = np.asarray(result["transform"])

  assert result["fitness"] > 0.9
  assert np.allclose(recovered, knownTransform, atol=0.05)


def test_register_with_initial_transform(registration, sourceCloud,
                                         targetCloud, knownTransform):
  """! Providing a good initial guess still recovers the known transform. """
  result = registration.register(sourceCloud, targetCloud,
                                 initial_transform=knownTransform)
  recovered = np.asarray(result["transform"])
  assert np.allclose(recovered, knownTransform, atol=0.05)


def test_register_invalid_initial_transform(registration, sourceCloud,
                                            targetCloud):
  """! A non-4x4 initial transform raises PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    registration.register(sourceCloud, targetCloud,
                          initial_transform=np.eye(3))


def test_register_empty_cloud(registration, targetCloud):
  """! Registering an empty cloud raises PointCloudRegistrationError. """
  empty = o3d.geometry.PointCloud()
  with pytest.raises(PointCloudRegistrationError):
    registration.register(empty, targetCloud)


@pytest.mark.slow
def test_register_million_point_kpi():
  """! Registration of two >1M point clouds completes in under 30 seconds. """
  registration = PointCloudRegistration(voxel_size=0.05)
  target = _make_box_cloud(1_200_000, seed=2)
  transform = np.eye(4)
  transform[:3, 3] = [0.1, 0.05, -0.05]
  source = o3d.geometry.PointCloud(target)
  source.transform(np.linalg.inv(transform))

  start = time.perf_counter()
  result = registration.register(source, target)
  elapsed = time.perf_counter() - start

  assert len(target.points) > 1_000_000
  assert len(source.points) > 1_000_000
  assert elapsed < 30.0
  assert result["fitness"] > 0.9
