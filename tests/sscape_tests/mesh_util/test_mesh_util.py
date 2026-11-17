#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
from unittest.mock import MagicMock, patch

import numpy as np
import open3d as o3d
import pytest
import trimesh
from PIL import Image
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

@pytest.mark.parametrize("instance_count", [1, 2, 46])
def test_merge_mesh_preserves_instances_and_source(instance_count):
  """Every placement is merged without modifying the shared source mesh."""
  scene = trimesh.Scene()
  source = trimesh.creation.box()
  source.visual = trimesh.visual.texture.TextureVisuals(
      uv=np.zeros((len(source.vertices), 2)))
  source.metadata['materials'] = [{'baseColorTexture': 'test-texture'}]
  scene.geometry['shared'] = source
  original_vertices = source.vertices.copy()
  original_faces = source.faces.copy()
  original_uv = source.visual.uv.copy()
  original_metadata = source.metadata.copy()
  expected_vertices = []
  for index in range(instance_count):
    transform = trimesh.transformations.translation_matrix([index * 2, 0, 0])
    scene.graph.update(frame_to=f'instance_{index}', geometry='shared', matrix=transform)
    expected_vertices.append(trimesh.transform_points(original_vertices, transform))

  merged = mergeMesh(scene)

  np.testing.assert_allclose(merged.vertices, np.vstack(expected_vertices))
  assert len(merged.faces) == instance_count * len(original_faces)
  np.testing.assert_array_equal(merged.visual.uv, np.tile(original_uv, (instance_count, 1)))
  np.testing.assert_array_equal(source.vertices, original_vertices)
  np.testing.assert_array_equal(source.faces, original_faces)
  np.testing.assert_array_equal(source.visual.uv, original_uv)
  assert source.metadata == original_metadata
  assert merged.metadata['name'] == 'mesh_0'

def test_merge_mesh_resolves_nested_transforms():
  """Parent rotation and child translation are composed into the base frame."""
  scene = trimesh.Scene()
  source = trimesh.creation.box()
  scene.geometry['shared'] = source
  parent = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1])
  parent[:3, 3] = [10, 20, 30]
  child = trimesh.transformations.translation_matrix([2, 0, 0])
  scene.graph.update(frame_to='group', matrix=parent)
  scene.graph.update(frame_to='instance', frame_from='group', geometry='shared', matrix=child)

  merged = mergeMesh(scene)

  expected = trimesh.transform_points(source.vertices, parent @ child)
  np.testing.assert_allclose(merged.vertices, expected)
  assert len(merged.faces) == len(source.faces)

def test_merge_mesh_missing_geometry_raises():
  """An invalid geometry reference fails visibly rather than dropping the instance."""
  scene = MagicMock()
  scene.geometry = {}
  scene.graph.nodes = ['instance']
  scene.graph.nodes_geometry = ['instance']
  scene.graph.__getitem__.return_value = (np.eye(4), 'missing')

  with pytest.raises(KeyError, match='missing'):
    mergeMesh(scene)

@pytest.mark.parametrize("cutoff", [None, 0.0, 0.7])
@pytest.mark.parametrize("factor, expected_colors", [
  ([1.0, 1.0, 1.0, 1.0], [(255, 255, 0, 255), (0, 0, 255, 255)]),
  ([0.5, 0.5, 0.5, 1.0], [(188, 188, 0, 255), (0, 0, 188, 255)]),
])
def test_merge_mesh_preserves_masked_material_colors(tmp_path, cutoff, factor, expected_colors):
  """Masked textures retain colors through merging and GLB export/reload."""
  scene = trimesh.Scene()
  colors = [(255, 255, 0, 255), (0, 0, 255, 255)]
  materials = []
  for index, color in enumerate(colors):
    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=Image.new('RGBA', (2, 2), color),
        baseColorFactor=factor,
        alphaMode='MASK', alphaCutoff=cutoff)
    materials.append(material)
    mesh = trimesh.creation.box()
    mesh.visual = trimesh.visual.texture.TextureVisuals(
        uv=np.full((len(mesh.vertices), 2), 0.5), material=material)
    scene.add_geometry(mesh, transform=trimesh.transformations.translation_matrix([index * 3, 0, 0]))

  merged = mergeMesh(scene)

  assert merged.visual.kind == 'texture'
  expected = np.repeat(np.array(expected_colors), 8, axis=0)
  np.testing.assert_array_equal(merged.visual.to_color().vertex_colors, expected)
  assert all(material.alphaCutoff == cutoff for material in materials)
  for material, color in zip(materials, colors):
    np.testing.assert_array_equal(np.array(material.baseColorTexture)[0, 0], color)
    np.testing.assert_allclose(material.baseColorFactor / 255.0, factor, atol=1 / 255.0)
  output = tmp_path / 'merged.glb'
  merged.export(output)
  reloaded = trimesh.load(output)
  assert len(reloaded.geometry) == 1
  mesh = next(iter(reloaded.geometry.values()))
  assert mesh.visual.kind == 'texture'
  np.testing.assert_array_equal(mesh.visual.to_color().vertex_colors, expected)

def test_merge_mesh_rejects_lost_textures():
  """A Trimesh visual merge failure must not silently export an untextured mesh."""
  scene = trimesh.Scene()
  for index in range(2):
    mesh = trimesh.creation.box()
    mesh.visual = trimesh.visual.texture.TextureVisuals(
        uv=np.full((len(mesh.vertices), 2), 0.5))
    scene.add_geometry(mesh, geom_name=f'mesh_{index}')

  with patch.object(trimesh.visual.texture.TextureVisuals, 'concatenate',
                    side_effect=ValueError('synthetic material failure')):
    with pytest.raises(ValueError, match='lost materials or textures'):
      mergeMesh(scene)

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


# Generate Mesh write-back + connectivity scenarios
_PATCH_EXTENTS = (4, 4, 0.1)
_CLOSE_OFFSET = (0.02, 0.0, 0.0)
_FAR_OFFSET = (100.0, 0.0, 0.0)
_IDENTITY_MESH_TRANSFORM = {
  "rotation_matrix": np.eye(3),
  "translation": np.zeros(3),
  "center_offset": np.zeros(3),
}


def _build_merged_glb_base64(qcam_offset):
  """Simulate the mapping service's merged GLB: a shared surface plus a second
  camera patch offset by qcam_offset."""
  primary_patch = trimesh.creation.box(extents=_PATCH_EXTENTS)
  qcam_patch = trimesh.creation.box(extents=_PATCH_EXTENTS)
  qcam_patch.apply_translation(qcam_offset)
  merged = trimesh.util.concatenate([primary_patch, qcam_patch])
  glb_bytes = merged.export(file_type="glb")
  return base64.b64encode(glb_bytes).decode("utf-8")


@pytest.fixture
def test_scene_with_cameras():
  """Create a test scene with 3 cameras (mix of prior transforms and empty)."""
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

    # Prior DB poses must not be preserved across Generate Mesh.
    camera1.transforms = [0.0] * 16
    camera1.save()
    camera2.transforms = [0.0] * 16
    camera2.save()
    qcam.transforms = []
    qcam.save()

    yield {"scene": scene, "camera1": camera1, "camera2": camera2, "qcam": qcam}

    media_tempdir.cleanup()


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
        {
          "camera_id": "camera1",
          "K": [[900.0, 0.0, 640.0], [0.0, 900.0, 360.0], [0.0, 0.0, 1.0]],
          "width": 1280,
          "height": 720,
        },
        {
          "camera_id": "camera2",
          "K": [[910.0, 0.0, 640.0], [0.0, 910.0, 360.0], [0.0, 0.0, 1.0]],
          "width": 1280,
          "height": 720,
        },
        {
          "camera_id": "atag-qcam1",
          "K": [[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]],
          "width": 640,
          "height": 480,
        },
      ],
    },
  }


def _identity_align(mesh):
  """Skip floor-fit so write-back tests can assert raw mapping poses."""
  return mesh, _IDENTITY_MESH_TRANSFORM


@pytest.mark.django_db
def test_mesh_generator_applies_mapping_poses_to_all_cameras(test_scene_with_cameras):
  """Generate Mesh installs mapping poses/intrinsics for every camera, including
  ones that already had transforms in the DB."""
  scene = test_scene_with_cameras["scene"]
  camera1 = test_scene_with_cameras["camera1"]
  camera2 = test_scene_with_cameras["camera2"]
  qcam = test_scene_with_cameras["qcam"]

  mesh_generator = MeshGenerator()
  mesh_generator.mapping_client.getReconstructionStatus = MagicMock(
    return_value=_mapping_result(_CLOSE_OFFSET, [2.02, 0.0, 0.0]))
  mesh_generator.alignMeshToXYPlane = MagicMock(side_effect=_identity_align)

  result = mesh_generator.finalizeMeshFromStatus(scene, "req-close")

  assert result["success"], result.get("error")
  assert "unanchored_cameras" not in result

  camera1.refresh_from_db()
  camera2.refresh_from_db()
  qcam.refresh_from_db()
  assert camera1.transforms[:3] == pytest.approx([0.0, 0.0, 0.0])
  assert camera1.transforms[3:7] == pytest.approx([0.0, 0.0, 0.0, 1.0])
  assert camera2.transforms[:3] == pytest.approx([2.0, 0.0, 0.0])
  assert camera2.transforms[3:7] == pytest.approx([0.0, 0.0, 0.0, 1.0])
  assert qcam.transforms[:3] == pytest.approx([2.02, 0.0, 0.0])
  assert qcam.transforms[3:7] == pytest.approx([0.0, 0.0, 0.0, 1.0])
  assert qcam.intrinsics_fx == 500.0
  assert qcam.width == 640 and qcam.height == 480
  # Cam resolution is Manager's source of truth: mapping K for 1280x720 must be
  # scaled into the registered 640x480 frame, not overwrite width/height.
  assert camera1.width == 640 and camera1.height == 480
  assert camera2.width == 640 and camera2.height == 480
  # 1280x720 -> 640x480 is sx=0.5, sy=2/3
  assert camera1.intrinsics_fx == pytest.approx(450.0)
  assert camera1.intrinsics_fy == pytest.approx(600.0)
  assert camera1.intrinsics_cx == pytest.approx(320.0)
  assert camera1.intrinsics_cy == pytest.approx(240.0)
  assert camera2.intrinsics_fx == pytest.approx(455.0)


@pytest.mark.django_db
def test_mesh_generator_rejected_when_camera_patch_lands_far_away(test_scene_with_cameras):
  """Disconnected reconstruction (different-room failure) is rejected before
  any camera pose is mutated."""
  scene = test_scene_with_cameras["scene"]
  camera1 = test_scene_with_cameras["camera1"]
  camera2 = test_scene_with_cameras["camera2"]
  qcam = test_scene_with_cameras["qcam"]

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
  assert qcam.intrinsics_fx == Cam.DEFAULT_INTRINSICS["fx"]


@pytest.mark.django_db
def test_mesh_generator_rejects_far_patches_even_when_all_cameras_have_poses(
    test_scene_with_cameras):
  """Having prior transforms in the DB does not skip connectivity validation."""
  scene = test_scene_with_cameras["scene"]
  qcam = test_scene_with_cameras["qcam"]
  qcam.transforms = [0.0] * 16
  qcam.save()

  mesh_generator = MeshGenerator()
  mesh_generator.mapping_client.getReconstructionStatus = MagicMock(
    return_value=_mapping_result(_FAR_OFFSET, [100.0, 0.0, 0.0]))

  result = mesh_generator.finalizeMeshFromStatus(scene, "req-all-posed")

  assert not result["success"]
  assert "spatially separate" in result["error"]


@pytest.mark.django_db
@patch("manager.mesh_generator.PubSub")
def test_start_mesh_generation_does_not_send_db_poses_as_priors(
    mock_pubsub_cls, test_scene_with_cameras):
  """UI Generate Mesh must not feed scene-DB poses into mapping as priors."""
  scene = test_scene_with_cameras["scene"]

  mesh_generator = MeshGenerator()
  mesh_generator.image_collector.collectImagesForScene = MagicMock(return_value=[])
  mesh_generator.mapping_client.startReconstructMesh = MagicMock(
    return_value={"request_id": "req-no-priors"})

  result = mesh_generator.startMeshGeneration(scene)

  assert result["success"], result.get("error")
  camera_order = mesh_generator.mapping_client.startReconstructMesh.call_args[0][1]
  camera_location_order = mesh_generator.mapping_client.startReconstructMesh.call_args[0][2]
  assert camera_order == ["camera1", "camera2", "atag-qcam1"]
  assert camera_location_order == [None, None, None]


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


def _footprint_size(corners):
  """! (width, height) XY extents of a (4,3) footprint corner array."""
  return (corners[:, 0].max() - corners[:, 0].min(), corners[:, 1].max() - corners[:, 1].min())


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

    corners = getPosedMeshFootprint(mesh, rotation, translation)
    width, height = _footprint_size(corners)

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

    corners_posed = getPosedMeshFootprint(mesh, rotation, translation, scale)
    size_posed = _footprint_size(corners_posed)
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

    w, h = _footprint_size(getPosedMeshFootprint(tensor_mesh, rotation, translation))

    # Footprint should be (width, height)
    assert abs(w - width) < 0.01
    assert abs(h - height) < 0.01

  def test_positive_scale_doubles_width(self):
    """Test scale [2,1,1] doubles width."""
    mesh = create_centered_box_mesh(10.0, 10.0, 10.0)

    rotation = [0, 0, 0]
    translation = [0, 0, 0]
    scale = [2.0, 1.0, 1.0]  # Double X

    width, height = _footprint_size(getPosedMeshFootprint(mesh, rotation, translation, scale))

    # Width should be 20 (10 * 2), height should be 10 (10 * 1)
    assert abs(width - 20.0) < 0.01
    assert abs(height - 10.0) < 0.01

  def test_positive_translation_shifts_corners(self):
    """Test pure translation shifts corners."""
    mesh = create_centered_box_mesh(10.0, 10.0, 10.0)

    rotation = [0, 0, 0]
    translation = [5.0, 3.0, 0]

    corners_notrans = getPosedMeshFootprint(
      mesh, rotation, [0, 0, 0]
    )
    corners_trans = getPosedMeshFootprint(
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

  @pytest.mark.parametrize("rotation, translation, scale, message", [
    ([0, 0], [0, 0, 0], None, "Rotation must be length"),
    ([0, 0, 0, 0, 0], [0, 0, 0], None, "Rotation must be length"),
    ([0, 0, 0], [0, 0], None, "Translation must be length 3"),
    ([0, 0, 0], [0, 0, 0, 0], None, "Translation must be length 3"),
    ([0, 0, 0], [0, 0, 0], [1, 1], "Scale must be length 3"),
    ([0, 0, 0], [0, 0, 0], [1, 1, 1, 1], "Scale must be length 3"),
  ])
  def test_negative_wrong_vector_length(self, rotation, translation, scale, message):
    """Test ValueError for bad rotation, translation and scale lengths."""
    mesh = create_centered_box_mesh(10, 10, 10)

    with pytest.raises(ValueError, match=message):
      getPosedMeshFootprint(mesh, rotation, translation, scale=scale)

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
      corners = getPosedMeshFootprint(
        mesh, rotation, translation
      )
      width, height = _footprint_size(corners)

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

    corners = getPosedMeshFootprint(mesh, rotation, translation)
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

    width, height = _footprint_size(getPosedMeshFootprint(mesh, rotation, translation, scale))

    # Should still return valid footprint
    assert width > 0
    assert 0 < height < 0.5  # Height should be very small
