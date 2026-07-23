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


def test_detect_format_ply(ply_bytes):
  """! PLY magic bytes are detected as the PLY format. """
  assert PointCloudRegistration.detect_format(ply_bytes) == PLY_FORMAT


def test_detect_format_pcd(pcd_bytes):
  """! PCD magic bytes are detected as the PCD format. """
  assert PointCloudRegistration.detect_format(pcd_bytes) == PCD_FORMAT


def test_detect_format_pcd_ascii(pcd_ascii_bytes):
  """! Uncompressed ASCII PCD bytes are detected as the PCD format. """
  assert PointCloudRegistration.detect_format(pcd_ascii_bytes) == PCD_FORMAT


def test_detect_format_pcd_binary(pcd_binary_bytes):
  """! Uncompressed binary PCD bytes are detected as the PCD format. """
  assert PointCloudRegistration.detect_format(pcd_binary_bytes) == PCD_FORMAT


def test_detect_format_invalid():
  """! Non point cloud bytes raise PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    PointCloudRegistration.detect_format(b"not-a-point-cloud-file")


def test_decode_point_cloud_ply(ply_bytes):
  """! Valid PLY bytes decode into a non-empty point cloud. """
  pcd = PointCloudRegistration.decode_point_cloud(ply_bytes)
  assert not pcd.is_empty()


def test_decode_point_cloud_pcd(pcd_bytes):
  """! Valid PCD bytes decode into a non-empty point cloud. """
  pcd = PointCloudRegistration.decode_point_cloud(pcd_bytes)
  assert not pcd.is_empty()


def test_decode_point_cloud_pcd_ascii(pcd_ascii_bytes):
  """! Uncompressed ASCII PCD bytes decode into a non-empty point cloud. """
  pcd = PointCloudRegistration.decode_point_cloud(pcd_ascii_bytes)
  assert not pcd.is_empty()


def test_decode_point_cloud_pcd_ascii_explicit_format(pcd_ascii_bytes):
  """! Uncompressed ASCII PCD decodes when the pcd format is declared. """
  pcd = PointCloudRegistration.decode_point_cloud(pcd_ascii_bytes, fmt=PCD_FORMAT)
  assert not pcd.is_empty()


def test_decode_point_cloud_pcd_binary(pcd_binary_bytes):
  """! Uncompressed binary PCD bytes decode into a non-empty point cloud. """
  pcd = PointCloudRegistration.decode_point_cloud(pcd_binary_bytes)
  assert not pcd.is_empty()


def test_decode_point_cloud_format_mismatch(ply_bytes):
  """! A declared format that disagrees with the data raises an error. """
  with pytest.raises(PointCloudRegistrationError):
    PointCloudRegistration.decode_point_cloud(ply_bytes, fmt=PCD_FORMAT)


def test_decode_point_cloud_invalid():
  """! Garbage bytes raise PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    PointCloudRegistration.decode_point_cloud(b"garbage-bytes-not-valid")


def test_scene_mesh_to_point_cloud_glb(registration, glb_file):
  """! A GLB scene mesh is sampled into a non-empty point cloud. """
  pcd = registration.scene_mesh_to_point_cloud(glb_file, number_of_points=10000)
  assert not pcd.is_empty()
  assert len(pcd.points) == 10000


def test_scene_mesh_to_point_cloud_no_map(registration):
  """! An empty map path raises PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    registration.scene_mesh_to_point_cloud("")


def test_serialize_point_cloud_roundtrip(registration, target_cloud, tmp_path):
  """! A serialized cloud can be read back with the same point count. """
  path = str(tmp_path / "roundtrip.pcd")
  registration.serialize_point_cloud(target_cloud, path)
  restored = o3d.io.read_point_cloud(path)
  assert len(restored.points) == len(target_cloud.points)


def test_register_recovers_known_transform(registration, source_cloud,
                                            target_cloud, known_transform):
  """! Registering a displaced source cloud recovers the known transform. """
  result = registration.register(source_cloud, target_cloud)
  recovered = np.asarray(result["transform"])

  assert result["fitness"] > 0.9
  assert np.allclose(recovered, known_transform, atol=0.05)


def test_register_identical_clouds_returns_identity(registration, target_cloud):
  """! Registering a cloud against itself returns a near-identity transform. """
  result = registration.register(target_cloud, target_cloud)
  recovered = np.asarray(result["transform"])
  assert result["fitness"] > 0.9
  assert np.allclose(recovered, np.eye(4), atol=0.05)


def test_register_with_initial_transform(registration, source_cloud,
                                         target_cloud, known_transform):
  """! Providing a good initial guess still recovers the known transform. """
  result = registration.register(source_cloud, target_cloud,
                                 initial_transform=known_transform)
  recovered = np.asarray(result["transform"])
  assert np.allclose(recovered, known_transform, atol=0.05)


def test_register_invalid_initial_transform(registration, source_cloud,
                                            target_cloud):
  """! A non-4x4 initial transform raises PointCloudRegistrationError. """
  with pytest.raises(PointCloudRegistrationError):
    registration.register(source_cloud, target_cloud,
                          initial_transform=np.eye(3))


def test_register_empty_cloud(registration, target_cloud):
  """! Registering an empty cloud raises PointCloudRegistrationError. """
  empty = o3d.geometry.PointCloud()
  with pytest.raises(PointCloudRegistrationError):
    registration.register(empty, target_cloud)


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
