#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
from unittest.mock import MagicMock, patch

import numpy as np
import open3d as o3d
import pytest
import trimesh
from plyfile import PlyData, PlyElement
import tempfile

from scene_common.geometry import Region, Point
from scene_common.mesh_util import createRegionMesh, createObjectMesh, mergeMesh, extractMeshFromPointCloud, extractMeshFromGLB
from scene_common.mesh_util import checkMeshConnectivity

from manager.mesh_generator import MeshGenerator
from manager.models import Cam, Scene

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


# ITEP-94846: Unanchored camera merge scenarios
_PATCH_EXTENTS = (4, 4, 0.1)
_CLOSE_OFFSET = (0.02, 0.0, 0.0)
_FAR_OFFSET = (100.0, 0.0, 0.0)


def _build_merged_glb_base64(qcam_offset):
  """Simulate the mapping service's merged GLB: the anchored cameras' shared
  surface plus the free camera's own reconstructed patch, offset by
  qcam_offset from the anchored surface."""
  anchored_patch = trimesh.creation.box(extents=_PATCH_EXTENTS)
  qcam_patch = trimesh.creation.box(extents=_PATCH_EXTENTS)
  qcam_patch.apply_translation(qcam_offset)
  merged = trimesh.util.concatenate([anchored_patch, qcam_patch])
  glb_bytes = merged.export(file_type="glb")
  return base64.b64encode(glb_bytes).decode("utf-8")


@pytest.fixture
def test_scene_with_cameras():
  """Create a test scene with 3 cameras: 2 anchored, 1 unanchored."""
  media_tempdir = tempfile.TemporaryDirectory()
  with patch("django.test.utils.override_settings"):
    scene = Scene.objects.create(name="test_scene", map="test_map")
    scene.map = MagicMock()
    scene.save = MagicMock()

    camera1 = Cam.objects.create(
      sensor_id="camera1", name="camera1", scene=scene, type="camera")
    camera2 = Cam.objects.create(
      sensor_id="camera2", name="camera2", scene=scene, type="camera")
    qcam = Cam.objects.create(
      sensor_id="atag-qcam1", name="atag-qcam1", scene=scene, type="camera")

    camera1.transforms = [0.0] * 16
    camera1.save()
    camera2.transforms = [0.0] * 16
    camera2.save()
    qcam.transforms = []
    qcam.save()

    yield {"scene": scene, "camera1": camera1, "camera2": camera2, "qcam": qcam}

    media_tempdir.cleanup()


def _mock_serializer_for_test(mock_serializer_cls):
  """Configure mocked CamSerializer with preset translation/rotation values."""
  translations = {"camera1": [0.0, 0.0, 0.0], "camera2": [2.0, 0.0, 0.0]}
  serializer = mock_serializer_cls.return_value
  serializer.get_translation.side_effect = lambda cam: translations.get(cam.sensor_id)
  serializer.get_rotation.side_effect = lambda cam: [0.0, 0.0, 0.0]
  serializer.get_scale.side_effect = lambda cam: [1.0, 1.0, 1.0]
  return serializer


def _mapping_result(qcam_offset, qcam_translation):
  """Construct a synthetic mapping service response with merged GLB + camera poses + intrinsics."""
  return {
    "success": True,
    "state": "complete",
    "result": {
      "success": True,
      "glb_data": _build_merged_glb_base64(qcam_offset),
      "camera_poses": [
        {"camera_id": "camera1", "translation": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0]},
        {"camera_id": "camera2", "translation": [2.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0]},
        {"camera_id": "atag-qcam1", "translation": qcam_translation, "rotation": [0.0, 0.0, 0.0, 1.0]},
      ],
      "intrinsics": [
        {"camera_id": "atag-qcam1", "K": [[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]]},
      ],
    },
  }


@pytest.mark.django_db
@patch("manager.mesh_generator.CamSerializer")
def test_mesh_generator_succeeds_with_warning_when_unanchored_camera_merges_close_to_anchors(
    mock_serializer_cls, test_scene_with_cameras):
  """Positive case: atag-qcam1's solved surface lands close enough to the
  anchored cameras' surface to read as one connected mesh. Generation must
  succeed, report atag-qcam1 as unanchored, and leave its pose untouched."""
  scene = test_scene_with_cameras["scene"]
  camera1 = test_scene_with_cameras["camera1"]
  camera2 = test_scene_with_cameras["camera2"]
  qcam = test_scene_with_cameras["qcam"]

  _mock_serializer_for_test(mock_serializer_cls)
  mesh_generator = MeshGenerator()
  mesh_generator.mapping_client.getReconstructionStatus = MagicMock(
    return_value=_mapping_result(_CLOSE_OFFSET, [2.02, 0.0, 0.0]))

  result = mesh_generator.finalizeMeshFromStatus(scene, "req-close")

  assert result["success"], result.get("error")
  assert result.get("unanchored_cameras") == ["atag-qcam1"]

  camera1.refresh_from_db()
  camera2.refresh_from_db()
  qcam.refresh_from_db()
  # Anchored cameras' calibration must be preserved exactly (skipped write-back).
  assert camera1.transforms == [0.0] * 16
  assert camera2.transforms == [0.0] * 16
  # Unanchored camera stays at its default pose; only intrinsics are updated.
  assert qcam.transforms == []
  assert qcam.intrinsics_fx == 500.0


@pytest.mark.django_db
@patch("manager.mesh_generator.CamSerializer")
def test_mesh_generator_rejected_when_unanchored_camera_lands_far_from_anchors(
    mock_serializer_cls, test_scene_with_cameras):
  """Negative/control case: same setup, but atag-qcam1's solved surface is
  far from the anchored surface (the "different room" failure). This must
  still be rejected by the connectivity check, and no camera should be
  mutated, proving the positive case above genuinely depends on proximity."""
  scene = test_scene_with_cameras["scene"]
  camera1 = test_scene_with_cameras["camera1"]
  camera2 = test_scene_with_cameras["camera2"]
  qcam = test_scene_with_cameras["qcam"]

  _mock_serializer_for_test(mock_serializer_cls)
  mesh_generator = MeshGenerator()
  mesh_generator.mapping_client.getReconstructionStatus = MagicMock(
    return_value=_mapping_result(_FAR_OFFSET, [100.0, 0.0, 0.0]))

  result = mesh_generator.finalizeMeshFromStatus(scene, "req-far")

  assert not result["success"]
  assert "spatially separate" in result["error"]

  camera1.refresh_from_db()
  camera2.refresh_from_db()
  qcam.refresh_from_db()
  assert camera1.transforms == [0.0] * 16
  assert camera2.transforms == [0.0] * 16
  assert qcam.transforms == []
  # Never reached the write-back, so intrinsics stay at Cam's own default
  # (set on first save), not the mocked mapping-service K matrix (500.0).
  assert qcam.intrinsics_fx == Cam.DEFAULT_INTRINSICS["fx"]


