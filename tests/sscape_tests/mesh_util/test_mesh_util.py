#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import open3d as o3d
import pytest
import trimesh
from scipy.spatial.transform import Rotation
from plyfile import PlyData, PlyElement
import tempfile

from scene_common.geometry import Region, Point
from scene_common.mesh_util import createRegionMesh, createObjectMesh, mergeMesh, extractMeshFromPointCloud, extractMeshFromGLB
from scene_common.mesh_util import checkMeshConnectivity, getMeshAxisAlignedProjectionToXY, getPosedMeshFootprint

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

def test_get_mesh_axis_aligned_projection_to_xy_corner_order():
  # Regression: corners must stay counterclockwise from the origin corner [SW, SE, NE, NW],
  # the order documented for Scene.map_corners_lla.
  legacy_mesh = o3d.geometry.TriangleMesh()
  legacy_mesh.vertices = o3d.utility.Vector3dVector(
    np.array([[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]], dtype=np.float64))
  legacy_mesh.triangles = o3d.utility.Vector3iVector(np.array([[0, 1, 2], [0, 2, 3]]))
  mesh = o3d.t.geometry.TriangleMesh.from_legacy(legacy_mesh)

  corners = getMeshAxisAlignedProjectionToXY(mesh)

  expected = np.array([
    [0, 0, 0],  # SW
    [2, 0, 0],  # SE
    [2, 3, 0],  # NE
    [0, 3, 0],  # NW
  ])
  np.testing.assert_array_equal(corners, expected)

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


@pytest.mark.django_db
@patch("manager.mesh_generator.CamSerializer")
def test_mesh_generator_accepts_far_patches_when_all_cameras_anchored(
    mock_serializer_cls, test_scene_with_cameras):
  """Demo-scene case: every camera is already calibrated (e.g. apriltag-based
  retail/queuing scenes), so there is no unanchored pose left to validate.
  Non-overlapping per-camera patches (cameras covering different parts of the
  same physical scene) must not be rejected."""
  scene = test_scene_with_cameras["scene"]
  qcam = test_scene_with_cameras["qcam"]
  qcam.transforms = [0.0] * 16
  qcam.save()

  serializer = _mock_serializer_for_test(mock_serializer_cls)
  translations = {"camera1": [0.0, 0.0, 0.0], "camera2": [2.0, 0.0, 0.0], "atag-qcam1": [100.0, 0.0, 0.0]}
  serializer.get_translation.side_effect = lambda cam: translations.get(cam.sensor_id)

  mesh_generator = MeshGenerator()
  mesh_generator.mapping_client.getReconstructionStatus = MagicMock(
    return_value=_mapping_result(_FAR_OFFSET, [100.0, 0.0, 0.0]))

  result = mesh_generator.finalizeMeshFromStatus(scene, "req-all-anchored")

  assert result["success"], result.get("error")
  assert "unanchored_cameras" not in result


@pytest.mark.django_db
@patch("manager.mesh_generator.PubSub")
@patch("manager.mesh_generator.CamSerializer")
def test_start_mesh_generation_converts_nonzero_euler_rotation_to_quaternion(
    mock_serializer_cls, mock_pubsub_cls, test_scene_with_cameras):
  """A calibrated camera's non-zero Euler
  rotation must reach the mapping service as the equivalent quaternion,
  not silently fall back to identity."""
  scene = test_scene_with_cameras["scene"]
  euler_rotation = [30.0, 45.0, 60.0]
  expected_quat = Rotation.from_euler('XYZ', euler_rotation, degrees=True).as_quat().tolist()

  serializer = mock_serializer_cls.return_value
  serializer.get_translation.return_value = [1.0, 2.0, 3.0]
  serializer.get_rotation.return_value = euler_rotation
  serializer.get_scale.return_value = [1.0, 1.0, 1.0]

  mesh_generator = MeshGenerator()
  mesh_generator.image_collector.collectImagesForScene = MagicMock(return_value=[])
  mesh_generator.mapping_client.startReconstructMesh = MagicMock(
    return_value={"request_id": "req-euler"})

  result = mesh_generator.startMeshGeneration(scene)

  assert result["success"], result.get("error")
  camera_location_order = mesh_generator.mapping_client.startReconstructMesh.call_args[0][2]
  assert camera_location_order[0]["rotation"] == pytest.approx(expected_quat)


def _pose_matrix(euler_deg, translation):
  """Build a 4x4 pose from XYZ Euler angles in degrees and a translation."""
  pose = np.eye(4)
  pose[:3, :3] = Rotation.from_euler('XYZ', euler_deg, degrees=True).as_matrix()
  pose[:3, 3] = translation
  return pose


@pytest.mark.django_db
@pytest.mark.parametrize("returned_euler, returned_translation", [
  pytest.param([10.0, 5.0, -40.0], [0.5, 2.0, 1.0], id="returned-pose-drifted"),
  pytest.param([20.0, -35.0, 70.0], [3.0, -1.0, 0.5], id="returned-pose-matches-calibration"),
])
@patch("manager.mesh_generator.CamSerializer")
def test_mesh_generator_places_mesh_at_calibrated_pose_of_translated_rotated_anchor(
    mock_serializer_cls, returned_euler, returned_translation, test_scene_with_cameras):
  """Anchored camera1 has a translated, non-zero-rotation calibrated pose. The
  mapping service returns it at a drifted pose, or at exactly its calibrated
  pose as a boundary case. A point the camera sees at p in its own frame must
  end up at scene_pose @ p in the saved mesh, checking the final vertex
  positions and orientation, not just the quaternion sent out. Re-applying the
  frame flip moves the mesh and fails both cases."""
  scene = test_scene_with_cameras["scene"]
  camera2 = test_scene_with_cameras["camera2"]

  scene_translation = [3.0, -1.0, 0.5]
  scene_euler = [20.0, -35.0, 70.0]
  scene_pose = _pose_matrix(scene_euler, scene_translation)
  returned_pose = _pose_matrix(returned_euler, returned_translation)

  # Only camera1 stays anchored, so the mesh is aligned from its pose alone.
  camera2.transforms = []
  camera2.save()

  serializer = mock_serializer_cls.return_value
  serializer.get_translation.side_effect = lambda cam: scene_translation if cam.sensor_id == "camera1" else None
  serializer.get_rotation.side_effect = lambda cam: scene_euler if cam.sensor_id == "camera1" else None

  # Offset so the box is not symmetric about the origin; a flip would then move it.
  camera_frame_box = trimesh.creation.box(extents=[1.0, 2.0, 0.5])
  camera_frame_box.apply_translation([0.7, -0.4, 1.3])
  mapping_frame_mesh = camera_frame_box.copy()
  mapping_frame_mesh.apply_transform(returned_pose)
  glb_data = base64.b64encode(mapping_frame_mesh.export(file_type="glb")).decode("utf-8")
  expected_vertices = camera_frame_box.vertices @ scene_pose[:3, :3].T + scene_pose[:3, 3]

  returned_quat = Rotation.from_matrix(returned_pose[:3, :3]).as_quat().tolist()
  mesh_generator = MeshGenerator()
  mesh_generator.mapping_client.getReconstructionStatus = MagicMock(return_value={
    "success": True,
    "state": "complete",
    "result": {
      "success": True,
      "glb_data": glb_data,
      "camera_poses": [
        {"camera_id": "camera1", "translation": returned_translation, "rotation": returned_quat},
      ],
      "intrinsics": [],
    },
  })

  result = mesh_generator.finalizeMeshFromStatus(scene, "req-pose")

  assert result["success"], result.get("error")
  assert result["unanchored_cameras"] == ["camera2", "atag-qcam1"]

  saved_glb = scene.map.save.call_args[0][1]
  saved_glb.seek(0)
  saved_mesh = trimesh.load(BytesIO(saved_glb.read()), file_type="glb").dump(concatenate=True)
  distances = np.linalg.norm(saved_mesh.vertices[:, None, :] - expected_vertices[None, :, :], axis=2)
  assert np.all(distances.min(axis=0) < 1e-4)  # every expected corner is in the saved mesh
  assert np.all(distances.min(axis=1) < 1e-4)  # and no saved vertex sits elsewhere


def create_centered_box_mesh(width, height, depth):
  """Create a box mesh centered at origin.

  Args:
    width: extent in X
    height: extent in Y (up)
    depth: extent in Z

  Returns:
    o3d.t.geometry.TriangleMesh centered at origin
  """
  # Create box at origin (extents from 0 to width/height/depth)
  legacy_mesh = o3d.geometry.TriangleMesh.create_box(width, height, depth)

  # Translate so center is at origin: box spans [-w/2, w/2] x [-h/2, h/2] x [-d/2, d/2]
  legacy_mesh.translate([-width/2, -height/2, -depth/2])

  # Convert to tensor mesh
  tensor_mesh = o3d.t.geometry.TriangleMesh.from_legacy(legacy_mesh)
  return tensor_mesh


class TestGetPosedMeshFootprint:
  """Test getPosedMeshFootprint function."""

  def test_positive_yup_box_90deg_x_rotation(self):
    """Test centred box with rotation [90,0,0] (about X) and translation.

    Box: X=10, Y=4, Z=6
    Rotation maps Y→Z (the 4-unit extent becomes vertical) and Z→-Y (the 6-unit
    extent lies along the footprint's Y axis).
    Translation = half of posed size
    Expected: size (10, 6), corners at (0, 0)
    """
    # Create box: 10 wide (X), 4 tall (Y), 6 deep (Z)
    mesh = create_centered_box_mesh(10.0, 4.0, 6.0)

    # Rotation [90, 0, 0] rotates around X: Y→Z, Z→-Y
    # So after rotation: X stays 10, Y becomes 6, Z becomes 4
    # Posed footprint (X, Y): 10 x 6
    rotation = [90, 0, 0]

    # Translation = half of posed size = (5, 3)
    translation = [5, 3, 0]

    corners, (width, height) = getPosedMeshFootprint(mesh, rotation, translation)

    # Check size (within tolerance)
    assert abs(width - 10.0) < 0.01
    assert abs(height - 6.0) < 0.01

    # Check corners ordered SW, SE, NE, NW at z=0
    sw, se, ne, nw = corners

    # SW should be at (0, 0)
    assert abs(sw[0] - 0.0) < 0.01
    assert abs(sw[1] - 0.0) < 0.01
    assert abs(sw[2] - 0.0) < 0.01

    # SE should be at (10, 0)
    assert abs(se[0] - 10.0) < 0.01
    assert abs(se[1] - 0.0) < 0.01

    # NE should be at (10, 6)
    assert abs(ne[0] - 10.0) < 0.01
    assert abs(ne[1] - 6.0) < 0.01

    # NW should be at (0, 6)
    assert abs(nw[0] - 0.0) < 0.01
    assert abs(nw[1] - 6.0) < 0.01

  def test_positive_z_up_identity_pose_equals_projection(self):
    """Test Z-up mesh with identity pose equals getMeshAxisAlignedProjectionToXY."""
    mesh = create_centered_box_mesh(20.0, 15.0, 8.0)

    rotation = [0, 0, 0]
    translation = [0, 0, 0]
    scale = None

    corners_posed, size_posed = getPosedMeshFootprint(mesh, rotation, translation, scale)
    corners_proj = getMeshAxisAlignedProjectionToXY(mesh)

    # Should match
    np.testing.assert_array_almost_equal(corners_posed, corners_proj, decimal=2)

    # Size should match
    assert abs(size_posed[0] - 20.0) < 0.01
    assert abs(size_posed[1] - 15.0) < 0.01

  def test_positive_image_style_box_identity_pose(self):
    """Test image-style box (extractMeshFromImage output) with identity pose unchanged."""
    # extractMeshFromImage creates: create_box(xdim, ydim, zdim) then translate((0, 0, -zdim))
    width, height, depth = 100.0, 80.0, 5.0
    legacy_mesh = o3d.geometry.TriangleMesh.create_box(width, height, depth)
    legacy_mesh.translate([0, 0, -depth])
    tensor_mesh = o3d.t.geometry.TriangleMesh.from_legacy(legacy_mesh)

    rotation = [0, 0, 0]
    translation = [0, 0, 0]

    _, (w, h) = getPosedMeshFootprint(tensor_mesh, rotation, translation)

    # Footprint should be (width, height)
    assert abs(w - width) < 0.01
    assert abs(h - height) < 0.01

  def test_positive_scale_doubles_width(self):
    """Test scale [2,1,1] doubles width."""
    mesh = create_centered_box_mesh(10.0, 10.0, 10.0)

    rotation = [0, 0, 0]
    translation = [0, 0, 0]
    scale = [2.0, 1.0, 1.0]  # Double X

    _, (width, height) = getPosedMeshFootprint(mesh, rotation, translation, scale)

    # Width should be 20 (10 * 2), height should be 10 (10 * 1)
    assert abs(width - 20.0) < 0.01
    assert abs(height - 10.0) < 0.01

  def test_positive_translation_shifts_corners(self):
    """Test pure translation shifts corners."""
    mesh = create_centered_box_mesh(10.0, 10.0, 10.0)

    rotation = [0, 0, 0]
    translation = [5.0, 3.0, 0]

    corners_notrans, _ = getPosedMeshFootprint(
      mesh, rotation, [0, 0, 0]
    )
    corners_trans, _ = getPosedMeshFootprint(
      mesh, rotation, translation
    )

    # Translation should shift all corners
    corner_diff = corners_trans - corners_notrans
    for i in range(4):
      assert abs(corner_diff[i, 0] - 5.0) < 0.01
      assert abs(corner_diff[i, 1] - 3.0) < 0.01
      assert abs(corner_diff[i, 2] - 0.0) < 0.01

  def test_negative_legacy_mesh_type_error(self):
    """Test TypeError for a legacy mesh (not tensor)."""
    legacy_mesh = o3d.geometry.TriangleMesh.create_box(10, 10, 10)

    with pytest.raises(TypeError, match="tensor TriangleMesh"):
      getPosedMeshFootprint(
        legacy_mesh, [0, 0, 0], [0, 0, 0]
      )

  def test_negative_wrong_rotation_length(self):
    """Test ValueError for bad rotation length."""
    mesh = create_centered_box_mesh(10, 10, 10)

    with pytest.raises(ValueError, match="Rotation must be length"):
      getPosedMeshFootprint(mesh, [0, 0], [0, 0, 0])

    with pytest.raises(ValueError, match="Rotation must be length"):
      getPosedMeshFootprint(mesh, [0, 0, 0, 0, 0], [0, 0, 0])

  def test_negative_wrong_translation_length(self):
    """Test ValueError for bad translation length."""
    mesh = create_centered_box_mesh(10, 10, 10)

    with pytest.raises(ValueError, match="Translation must be length 3"):
      getPosedMeshFootprint(mesh, [0, 0, 0], [0, 0])

    with pytest.raises(ValueError, match="Translation must be length 3"):
      getPosedMeshFootprint(mesh, [0, 0, 0], [0, 0, 0, 0])

  def test_negative_wrong_scale_length(self):
    """Test ValueError for bad scale length."""
    mesh = create_centered_box_mesh(10, 10, 10)

    with pytest.raises(ValueError, match="Scale must be length 3"):
      getPosedMeshFootprint(mesh, [0, 0, 0], [0, 0, 0], scale=[1, 1])

    with pytest.raises(ValueError, match="Scale must be length 3"):
      getPosedMeshFootprint(mesh, [0, 0, 0], [0, 0, 0], scale=[1, 1, 1, 1])

  def test_positive_mesh_not_mutated(self):
    """Test that input mesh is not mutated."""
    mesh = create_centered_box_mesh(10.0, 10.0, 10.0)

    # Store original vertices
    original_verts = mesh.vertex.positions.numpy().copy()

    rotation = [45, 30, 60]
    translation = [10, 20, 30]
    scale = [2, 1.5, 0.8]

    getPosedMeshFootprint(mesh, rotation, translation, scale)

    # Verify mesh vertices unchanged
    current_verts = mesh.vertex.positions.numpy()
    np.testing.assert_array_equal(current_verts, original_verts)

  def test_positive_various_rotations(self):
    """Test with various rotations."""
    mesh = create_centered_box_mesh(10.0, 20.0, 5.0)
    translation = [0, 0, 0]

    rotations = [
      [0, 0, 0],
      [90, 0, 0],
      [0, 90, 0],
      [0, 0, 90],
      [45, 45, 45]
    ]

    for rotation in rotations:
      corners, (width, height) = getPosedMeshFootprint(
        mesh, rotation, translation
      )

      # Footprint should have positive dimensions
      assert width > 0
      assert height > 0

      # All corners should be at z=0
      for corner in corners:
        assert abs(corner[2]) < 0.01

  def test_positive_corner_order_sw_se_ne_nw(self):
    """Test corner ordering: SW, SE, NE, NW."""
    mesh = create_centered_box_mesh(20.0, 15.0, 10.0)
    rotation = [0, 0, 0]
    translation = [10, 10, 0]

    corners, _ = getPosedMeshFootprint(mesh, rotation, translation)
    sw, se, ne, nw = corners

    # SW is min_x, min_y
    # SE is max_x, min_y
    # NE is max_x, max_y
    # NW is min_x, max_y

    assert sw[0] < se[0]  # SW x < SE x
    assert sw[1] < nw[1]  # SW y < NW y

    assert se[0] == ne[0]  # SE x == NE x
    assert se[1] < ne[1]   # SE y < NE y

    assert nw[0] < ne[0]   # NW x < NE x
    assert nw[1] == ne[1]  # NW y == NE y

  def test_positive_zero_scale_component_handling(self):
    """Test behavior with very small (near-zero) scale component."""
    mesh = create_centered_box_mesh(10.0, 10.0, 10.0)
    rotation = [0, 0, 0]
    translation = [0, 0, 0]
    scale = [1.0, 0.01, 1.0]  # Very small Y scale

    _, (width, height) = getPosedMeshFootprint(mesh, rotation, translation, scale)

    # Should still return valid footprint
    assert width > 0
    assert 0 < height < 0.5  # Height should be very small
