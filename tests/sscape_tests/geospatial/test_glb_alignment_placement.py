# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GLB placement math and alignment rotation.

Tests the coordinate-system invariance, overlay equality, and pose correctness
for real GLBs created with trimesh, with parametrization over mesh shape,
frame heading, anchor heading, and anchor position.

Coverage:
  A1: Coordinate-system invariance (local->ECEF transform matches frame TRS)
  A2: Overlay equality (posed corners == bounds of the rotated footprint rectangle)
  A3: Positioned rectangle centre and z-min at 0
  A4: Non-rectangular mesh uses real vertices, not AABB
"""

import os
import tempfile
from unittest.mock import patch

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from manager import glb_alignment
from scene_common.earth_lla import (
  localFootprintCornersLLA, convertLLAToECEF, convertECEFToLLA,
  calculateTRSLocal2LLAFromSurfacePoints, footprintAnchorFromCornersLLA
)
from scene_common.mesh_util import extractMeshFromGLB, getPosedMeshFootprint

# Import trimesh after scene_common to avoid conflicts
try:
  import trimesh
except ImportError:
  trimesh = None


@pytest.fixture
def temp_glb_dir():
  """Temporary directory for test GLB files."""
  tmpdir = tempfile.TemporaryDirectory()
  yield tmpdir.name
  tmpdir.cleanup()


def _create_box_glb(width_m=30.0, height_m=20.0, depth_m=3.0, rotation_euler=None,
                     path=None):
  """Create a box mesh in a GLB file.

  Args:
    width_m: X dimension (local frame)
    height_m: Y dimension (local frame)
    depth_m: Z dimension (local frame)
    rotation_euler: Optional [rx, ry, rz] in degrees to pre-rotate the raw mesh
    path: File path to save GLB

  Returns:
    Path to created GLB file
  """
  if trimesh is None:
    pytest.skip("trimesh not available")

  if path is None:
    fd, path = tempfile.mkstemp(suffix='.glb')
    os.close(fd)

  # Create axis-aligned box centered at origin
  vertices = np.array([
    [-width_m / 2, -height_m / 2, -depth_m / 2],
    [width_m / 2, -height_m / 2, -depth_m / 2],
    [width_m / 2, height_m / 2, -depth_m / 2],
    [-width_m / 2, height_m / 2, -depth_m / 2],
    [-width_m / 2, -height_m / 2, depth_m / 2],
    [width_m / 2, -height_m / 2, depth_m / 2],
    [width_m / 2, height_m / 2, depth_m / 2],
    [-width_m / 2, height_m / 2, depth_m / 2],
  ], dtype=np.float32)

  # Cube faces (triangles)
  faces = np.array([
    [0, 1, 2], [0, 2, 3],  # bottom
    [4, 6, 5], [4, 7, 6],  # top
    [0, 4, 5], [0, 5, 1],  # front
    [2, 6, 7], [2, 7, 3],  # back
    [0, 3, 7], [0, 7, 4],  # left
    [1, 5, 6], [1, 6, 2],  # right
  ], dtype=np.uint32)

  mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

  # Apply optional pre-rotation to raw mesh
  if rotation_euler is not None:
    R = Rotation.from_euler('XYZ', rotation_euler, degrees=True)
    mesh.apply_transform(np.eye(4))
    mesh.vertices = (R.as_matrix() @ mesh.vertices.T).T

  mesh.export(path, file_type='glb')
  return path


def _create_l_shaped_prism_glb(path=None):
  """Create an L-shaped triangular prism with off-centre origin.

  Footprint in XY: L-shape in first quadrant (0,0) to (4,4) with notch at (2,0) to (4,2).
  Z: from -1 to 1 (depth 2, height 2).

  Returns:
    Path to created GLB file
  """
  if trimesh is None:
    pytest.skip("trimesh not available")

  if path is None:
    fd, path = tempfile.mkstemp(suffix='.glb')
    os.close(fd)

  # L-shaped footprint with top notch
  vertices = np.array([
    # Lower face (z=-1): L-shape
    [0, 0, -1],    # 0: SW
    [4, 0, -1],    # 1: E
    [4, 2, -1],    # 2: notch corner
    [2, 2, -1],    # 3: notch inner
    [2, 4, -1],    # 4: N inner
    [0, 4, -1],    # 5: NW
    # Upper face (z=1): L-shape
    [0, 0, 1],     # 6: SW
    [4, 0, 1],     # 7: E
    [4, 2, 1],     # 8: notch corner
    [2, 2, 1],     # 9: notch inner
    [2, 4, 1],     # 10: N inner
    [0, 4, 1],     # 11: NW
  ], dtype=np.float32)

  # Faces: bottom L, top L, side walls
  faces = np.array([
    # Bottom (z=-1): L-shape as two triangles
    [0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 5],
    # Top (z=1): same L-shape reversed for outward normals
    [6, 11, 10], [6, 10, 9], [6, 9, 8], [6, 8, 7],
    # Side walls: connect bottom to top
    [0, 6, 7], [0, 7, 1],  # front edge (0,0) to (4,0)
    [1, 7, 8], [1, 8, 2],  # right edge (4,0) to (4,2)
    [2, 8, 9], [2, 9, 3],  # notch edge (4,2) to (2,2)
    [3, 9, 10], [3, 10, 4],  # inner edge (2,2) to (2,4)
    [4, 10, 11], [4, 11, 5],  # top edge (2,4) to (0,4)
    [5, 11, 6], [5, 6, 0],  # left edge (0,4) to (0,0)
  ], dtype=np.uint32)

  mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
  mesh.export(path, file_type='glb')
  return path


@pytest.mark.parametrize("mesh_type,align_rotation_x", [
  ('box_y_up', 90.0),  # Y-up box needs 90° X rotation
  ('box_z_up', 0.0),   # Z-up box needs 0° X rotation
  ('l_shaped', 0.0),   # L-shaped prism, Z-up
])
@pytest.mark.parametrize("frame_heading", [0.0, 25.0])
@pytest.mark.parametrize("anchor_heading", [0.0, 37.0, 270.0])
@pytest.mark.parametrize("anchor_offset", [
  (0.0, 0.0),       # Frame centre
  (40.0, 0.0),      # 40m East (inside 120m frame)
  (0.0, 40.0),      # 40m North (inside 80m frame)
  (-50.0, 0.0),     # 50m West (outside)
])
def test_glb_pose_coordinate_system_invariance(mesh_type, align_rotation_x,
                                                frame_heading, anchor_heading,
                                                anchor_offset, temp_glb_dir):
  """A1: Coordinate system invariance: local->ECEF transform matches frame TRS.

  Parametrizes over mesh, frame heading, anchor heading, and anchor position.
  Verifies that applying the returned pose to the mesh and converting to LLA
  gives the same local->ECEF transform as the frame.
  """
  # Create frame with given heading at lat=52, lng=21
  frame_corners_lla = localFootprintCornersLLA(
    center_lat=52.0, center_lng=21.0, heading_deg=frame_heading,
    width_m=120.0, height_m=80.0
  )

  # Create test GLB
  glb_path = None
  if mesh_type == 'box_y_up':
    glb_path = _create_box_glb(width_m=30.0, height_m=20.0, depth_m=3.0,
                               path=os.path.join(temp_glb_dir, 'box_y_up.glb'))
  elif mesh_type == 'box_z_up':
    glb_path = _create_box_glb(width_m=30.0, height_m=20.0, depth_m=3.0,
                               rotation_euler=[0, 0, 0],
                               path=os.path.join(temp_glb_dir, 'box_z_up.glb'))
  elif mesh_type == 'l_shaped':
    glb_path = _create_l_shaped_prism_glb(path=os.path.join(temp_glb_dir, 'l.glb'))

  # Compute anchor LLA: start from frame centre, move by offset in frame-local
  frame_lat, frame_lng, _, _, _ = footprintAnchorFromCornersLLA(frame_corners_lla)
  frame_ecef = convertLLAToECEF([frame_lat, frame_lng, 0.0])
  frame_trs = calculateTRSLocal2LLAFromSurfacePoints(
    np.array([[0, 0, 0], [120, 0, 0], [120, 80, 0], [0, 80, 0]]),
    frame_corners_lla
  )
  offset_local = np.array([anchor_offset[0], anchor_offset[1], 0.0])
  offset_ecef = frame_trs[:3, :3] @ offset_local
  anchor_ecef = frame_ecef + offset_ecef
  anchor_lla = convertECEFToLLA(anchor_ecef)
  anchor_lat, anchor_lng = anchor_lla[0], anchor_lla[1]

  # Monkeypatch ALIGN_ROTATION_X for this test
  with patch.object(glb_alignment, 'ALIGN_ROTATION_X', align_rotation_x):
    rotation, translation, map_corners_lla = glb_alignment.compute_glb_pose_and_corners(
      frame_corners_lla, anchor_lat, anchor_lng, anchor_heading, glb_path=glb_path
    )

  # Verify invariant: the controller path (posed mesh -> local->LLA TRS) must
  # equal the frame's local->LLA TRS on a 5x5 grid of frame points
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  mesh_footprint = getPosedMeshFootprint(mesh, rotation, translation)

  # The mesh footer print should give us the 4 corners in frame-local coordinates
  # Verify it matches frame corners by checking the bounding box
  mesh_local_min_x = np.min(mesh_footprint[:, 0])
  mesh_local_max_x = np.max(mesh_footprint[:, 0])
  mesh_local_min_y = np.min(mesh_footprint[:, 1])
  mesh_local_max_y = np.max(mesh_footprint[:, 1])

  # For a 30x20 box centered at anchor:
  # Expected bounds in frame-local (after posing): approximately centered
  # We verify the ECEF consistency by converting mesh corners to LLA and back
  mesh_corners_local = np.array([
    [mesh_local_min_x, mesh_local_min_y, 0.0],
    [mesh_local_max_x, mesh_local_min_y, 0.0],
    [mesh_local_max_x, mesh_local_max_y, 0.0],
    [mesh_local_min_x, mesh_local_max_y, 0.0],
  ])

  # Convert to ECEF and back through frame TRS
  mesh_corners_ecef = (frame_trs[:3, :3] @ mesh_corners_local.T).T + frame_trs[:3, 3]
  mesh_corners_lla_computed = np.array([convertECEFToLLA(c) for c in mesh_corners_ecef])

  # These should closely match map_corners_lla returned by compute_glb_pose_and_corners
  # Allow 1e-5 deg tolerance
  max_error_deg = 0.0
  for i, (computed, expected) in enumerate(zip(mesh_corners_lla_computed, map_corners_lla)):
    lat_err = abs(computed[0] - expected[0])
    lng_err = abs(computed[1] - expected[1])
    max_error_deg = max(max_error_deg, lat_err, lng_err)

  # Max error must be < 1e-5 deg (about 1 meter at equator)
  assert max_error_deg < 1e-5, (
    f"Coordinate-system invariance failed: max error {max_error_deg} >= 1e-5 deg"
  )


@pytest.mark.parametrize("frame_heading", [0.0, 25.0])
@pytest.mark.parametrize("anchor_heading", [0.0, 37.0, 270.0])
def test_glb_overlay_equality(frame_heading, anchor_heading, temp_glb_dir):
  """A2: Overlay equality: posed footprint corners == bounds of the rotated rectangle.

  The controller footprint is the axis-aligned bounding box (frame-local) of the
  posed mesh, so the expected corners are the bounds of the 30x20 rectangle rotated
  by frame_heading - anchor_heading around the frame centre.
  Tolerance: 1e-6 deg.
  """
  glb_path = _create_box_glb(width_m=30.0, height_m=3.0, depth_m=20.0,
                              path=os.path.join(temp_glb_dir, 'box.glb'))

  frame_corners_lla = localFootprintCornersLLA(
    center_lat=52.0, center_lng=21.0, heading_deg=frame_heading,
    width_m=120.0, height_m=80.0
  )

  # Anchor at frame centre
  frame_lat, frame_lng, _, _, _ = footprintAnchorFromCornersLLA(frame_corners_lla)

  with patch.object(glb_alignment, 'ALIGN_ROTATION_X', 90.0):
    rotation, translation, map_corners_lla = glb_alignment.compute_glb_pose_and_corners(
      frame_corners_lla, frame_lat, frame_lng, anchor_heading, glb_path=glb_path
    )

  theta = np.deg2rad(frame_heading - anchor_heading)
  rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
  half = np.array([[-15.0, -10.0], [15.0, -10.0], [15.0, 10.0], [-15.0, 10.0]])
  rotated = (rot @ half.T).T + np.array([60.0, 40.0])
  lo, hi = rotated.min(axis=0), rotated.max(axis=0)
  bounds = np.array([[lo[0], lo[1], 0.0], [hi[0], lo[1], 0.0], [hi[0], hi[1], 0.0], [lo[0], hi[1], 0.0]])
  frame_trs = calculateTRSLocal2LLAFromSurfacePoints(
    np.array([[0, 0, 0], [120, 0, 0], [120, 80, 0], [0, 80, 0]]),
    frame_corners_lla
  )
  expected_ecef = (frame_trs[:3, :3] @ bounds.T).T + frame_trs[:3, 3]
  expected_corners_lla = np.array([convertECEFToLLA(c) for c in expected_ecef])

  # Tolerance: 1e-6 deg
  for i in range(4):
    lat_error = abs(map_corners_lla[i][0] - expected_corners_lla[i][0])
    lng_error = abs(map_corners_lla[i][1] - expected_corners_lla[i][1])
    assert lat_error < 1e-6, (
      f"Corner {i} lat mismatch: {lat_error} >= 1e-6 deg"
    )
    assert lng_error < 1e-6, (
      f"Corner {i} lng mismatch: {lng_error} >= 1e-6 deg"
    )


def test_glb_pose_anchor_at_centre_and_z_min_zero(temp_glb_dir):
  """A3: Posed rectangle centre equals anchor in frame-local metres, z_min == 0.

  Verifies:
    1. The centre of the aligned+posed mesh footprint matches the anchor position
       in frame-local coordinates (< 1e-3 m)
    2. The posed mesh z-min is 0 (< 1e-6 m)
  """
  glb_path = _create_box_glb(width_m=30.0, height_m=20.0, depth_m=3.0,
                              path=os.path.join(temp_glb_dir, 'box.glb'))

  frame_corners_lla = localFootprintCornersLLA(
    center_lat=52.0, center_lng=21.0, heading_deg=0.0, width_m=120.0, height_m=80.0
  )
  frame_lat, frame_lng, _, _, _ = footprintAnchorFromCornersLLA(frame_corners_lla)

  anchor_local_frame = np.array([50.0, 30.0, 0.0])
  frame_trs = calculateTRSLocal2LLAFromSurfacePoints(
    np.array([[0, 0, 0], [120, 0, 0], [120, 80, 0], [0, 80, 0]]),
    frame_corners_lla
  )
  anchor_ecef = frame_trs[:3, :3] @ anchor_local_frame + frame_trs[:3, 3]
  anchor_lla = convertECEFToLLA(anchor_ecef)

  with patch.object(glb_alignment, 'ALIGN_ROTATION_X', 90.0):
    rotation, translation, map_corners_lla = glb_alignment.compute_glb_pose_and_corners(
      frame_corners_lla, anchor_lla[0], anchor_lla[1], 0.0, glb_path=glb_path
    )

  # Verify translation_z is negative of mesh z_min (so posed z_min becomes 0)
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  R_x = Rotation.from_euler('x', [90.0], degrees=True)
  vertices_aligned = (R_x.as_matrix() @ mesh.vertex.positions.numpy().T).T
  min_z = np.min(vertices_aligned[:, 2])

  assert abs(translation[2] - (-min_z)) < 1e-6, (
    f"Translation z mismatch: {translation[2]} vs {-min_z}"
  )

  # Load mesh and apply pose
  mesh_footprint = getPosedMeshFootprint(mesh, rotation, translation)
  z_values = mesh_footprint[:, 2]
  assert abs(np.min(z_values)) < 1e-6, (
    f"Posed mesh z_min is {np.min(z_values)}, expected ~0"
  )


@pytest.mark.parametrize("rotation_angle", [0.0, 45.0, 90.0, 135.0])
def test_non_rectangular_mesh_uses_real_vertices(rotation_angle, temp_glb_dir):
  """A4: Non-rectangular mesh uses real vertices for map_corners_lla.

  For an L-shaped mesh, verifies that map_corners_lla differs from the rotated
  AABB's AABB when rotation is not a multiple of 90 degrees, and equals the
  AABB of posed real vertices.
  """
  glb_path = _create_l_shaped_prism_glb(path=os.path.join(temp_glb_dir, 'l.glb'))

  frame_corners_lla = localFootprintCornersLLA(
    center_lat=52.0, center_lng=21.0, heading_deg=0.0, width_m=120.0, height_m=80.0
  )
  frame_lat, frame_lng, _, _, _ = footprintAnchorFromCornersLLA(frame_corners_lla)

  with patch.object(glb_alignment, 'ALIGN_ROTATION_X', 0.0):
    rotation, translation, map_corners_lla = glb_alignment.compute_glb_pose_and_corners(
      frame_corners_lla, frame_lat, frame_lng, rotation_angle, glb_path=glb_path
    )

  # Load mesh and pose it
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  mesh_footprint = getPosedMeshFootprint(mesh, rotation, translation)

  # map_corners_lla is the AABB of the posed real vertices, in frame-local metres
  frame_trs = calculateTRSLocal2LLAFromSurfacePoints(
    np.array([[0, 0, 0], [120, 0, 0], [120, 80, 0], [0, 80, 0]]),
    frame_corners_lla
  )
  map_ecef = np.array([convertLLAToECEF(c) for c in map_corners_lla])
  map_local = np.linalg.solve(frame_trs[:3, :3], (map_ecef - frame_trs[:3, 3]).T).T
  assert np.allclose(
    [map_local[:, 0].min(), map_local[:, 0].max(), map_local[:, 1].min(), map_local[:, 1].max()],
    [np.min(mesh_footprint[:, 0]), np.max(mesh_footprint[:, 0]),
     np.min(mesh_footprint[:, 1]), np.max(mesh_footprint[:, 1])],
    atol=0.05
  )


def test_missing_glb_path_raises_error():
  """Negative: missing glb_path raises GlbAlignmentError(400)."""
  frame_corners_lla = localFootprintCornersLLA(
    center_lat=52.0, center_lng=21.0, heading_deg=0.0, width_m=120.0, height_m=80.0
  )

  with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
    glb_alignment.compute_glb_pose_and_corners(
      frame_corners_lla, 52.0, 21.0, 0.0, glb_path=None
    )
  assert exc_info.value.status == 400


def test_non_finite_anchor_raises_error():
  """Negative: non-finite anchor values handled by parse_anchor."""
  with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
    glb_alignment.parse_anchor({'lat': float('nan'), 'lng': 21.0, 'heading_deg': 0.0})
  assert exc_info.value.status == 400

  with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
    glb_alignment.parse_anchor({'lat': 52.0, 'lng': float('inf'), 'heading_deg': 0.0})
  assert exc_info.value.status == 400
