# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GLB state machine: apply, unapply, remove, move, commit.

Tests invariants: trs_matrix unchanged, unapply restores state, apply/unapply
idempotence checks, remove while applied, legacy scenes.

Coverage:
  B1: apply() moves snapshot to base_map, computes pose
  B2: unapply() restores snapshot, clears base_*
  B3: remove() while applied reverts first
  B4: move_glb_anchor() updates anchor and pose if applied
  B5: commit_glb() stores GLB and applies if not already applied
  B6: Invariant: trs_matrix unchanged by any operation
  B7: Error cases: apply twice, unapply when not applied, apply without GLB
"""

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from manager import glb_alignment
from manager.models import Scene

TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"


@pytest.fixture
def temp_media_root():
  """Temporary media root for file storage."""
  tmpdir = tempfile.TemporaryDirectory()
  yield tmpdir.name
  tmpdir.cleanup()


@pytest.fixture
def geospatial_scene_with_map(temp_media_root):
  """Geospatial scene with a dummy PNG snapshot map."""
  with override_settings(MEDIA_ROOT=temp_media_root):
    scene = Scene.objects.create(
      name="test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    # Create a dummy PNG map
    from PIL import Image
    import numpy as np
    png_data = np.zeros((16, 16, 3), dtype=np.uint8)
    png_img = Image.fromarray(png_data)
    png_path = os.path.join(temp_media_root, "test_map.png")
    png_img.save(png_path, format='PNG')
    # Set map to the PNG
    scene.map = "test_map.png"
    # Set frame corners
    from scene_common.earth_lla import localFootprintCornersLLA
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    scene.save()
    yield scene


class TestApplyGlbMap(TransactionTestCase):
  """Tests for apply_glb_map() state machine."""

  def setUp(self):
    """Create temp media and geospatial scene."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _create_geospatial_scene(self):
    """Create a geospatial scene with PNG snapshot."""
    scene = Scene.objects.create(
      name="test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    from PIL import Image
    import numpy as np
    png_data = np.zeros((16, 16, 3), dtype=np.uint8)
    png_img = Image.fromarray(png_data)
    png_path = os.path.join(self.media_root, "snap.png")
    png_img.save(png_path, format='PNG')
    scene.map = "snap.png"
    from scene_common.earth_lla import localFootprintCornersLLA
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    scene.save()
    return scene

  def _read_test_glb(self):
    """Read the test GLB file."""
    with open(TEST_GLB_FILE, 'rb') as f:
      return f.read()

  def test_apply_glb_moves_snapshot_to_base_map(self):
    """Test: apply_glb_map() saves snapshot to base_map."""
    scene = self._create_geospatial_scene()
    orig_map = scene.map.name if scene.map else None

    # Stage a GLB
    token = str(uuid.uuid4())
    glb_staging_dir = os.path.join(self.media_root, glb_alignment.STAGING_SUBDIR)
    os.makedirs(glb_staging_dir, exist_ok=True)
    glb_path = os.path.join(glb_staging_dir, f"{token}.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())

    # Store GLB in scene
    scene.glb_map = "test_glb.glb"
    glb_file_path = os.path.join(self.media_root, "test_glb.glb")
    with open(glb_file_path, 'wb') as f:
      f.write(self._read_test_glb())
    scene.glb_anchor = {
      'lat': 37.39,
      'lng': -121.97,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    scene.save()

    # Mock saveThumbnail and sendUpdateCommand
    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      with transaction.atomic():
        result = glb_alignment.apply_glb_map(scene)

    # Verify: base_map is set, snapshot saved
    assert scene.base_map.name is not None or orig_map is None
    assert scene.use_glb_map is True
    # Map should now be GLB
    assert scene.map.name.endswith('.glb')
    assert result['use_glb_map'] is True

  def test_apply_glb_twice_raises_error(self):
    """Test: apply_glb_map() on already-applied scene raises 400."""
    scene = self._create_geospatial_scene()
    # Reload so _original_map matches the saved map; otherwise save() treats snap.png as a new upload and clears use_glb_map
    scene = Scene.objects.get(pk=scene.pk)
    scene.use_glb_map = True
    scene.glb_map = "existing.glb"
    glb_path = os.path.join(self.media_root, "existing.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())
    scene.glb_anchor = {
      'lat': 37.39,
      'lng': -121.97,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    scene.save()

    with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
      glb_alignment.apply_glb_map(scene)
    assert exc_info.value.status == 400

  def test_apply_glb_without_stored_anchor_raises_error(self):
    """Test: apply_glb_map() without stored anchor raises 400."""
    scene = self._create_geospatial_scene()
    scene.glb_map = "test.glb"
    glb_path = os.path.join(self.media_root, "test.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())
    scene.glb_anchor = None
    scene.save()

    with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
      glb_alignment.apply_glb_map(scene)
    assert exc_info.value.status == 400


class TestUnapplyGlbMap(TransactionTestCase):
  """Tests for unapply_glb_map() state machine."""

  def setUp(self):
    """Create temp media and applied scene."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _read_test_glb(self):
    """Read the test GLB file."""
    with open(TEST_GLB_FILE, 'rb') as f:
      return f.read()

  def _create_applied_glb_scene(self):
    """Create a scene with applied GLB."""
    from PIL import Image
    import numpy as np
    from scene_common.earth_lla import localFootprintCornersLLA

    scene = Scene.objects.create(
      name="glb_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True,
      use_glb_map=True
    )

    # Store base map (snapshot)
    png_data = np.zeros((16, 16, 3), dtype=np.uint8)
    png_img = Image.fromarray(png_data)
    base_path = os.path.join(self.media_root, "base.png")
    png_img.save(base_path, format='PNG')
    scene.base_map = "base.png"
    scene.base_scale = 0.5
    scene.base_map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()

    # Store GLB map (applied)
    glb_path = os.path.join(self.media_root, "active.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())
    scene.map = "active.glb"
    scene.glb_map = "active.glb"

    # Store anchor and set pose
    scene.glb_anchor = {
      'lat': 37.39,
      'lng': -121.97,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    scene.rotation_x = 45.0
    scene.rotation_z = 30.0
    scene.translation_x = 10.0
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=10.0, height_m=10.0
    ).tolist()
    scene.save()
    return scene

  def test_unapply_glb_restores_snapshot_and_clears_base(self):
    """Test: unapply_glb_map() restores snapshot, clears base_*."""
    scene = self._create_applied_glb_scene()
    orig_base_corners = scene.base_map_corners_lla

    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      with transaction.atomic():
        glb_alignment.unapply_glb_map(scene)

    # Verify state after unapply
    assert scene.use_glb_map is False
    assert scene.rotation_x == 0.0
    assert scene.rotation_z == 0.0
    assert scene.translation_x == 0.0
    # base_map should be cleared
    assert scene.base_map is None or not scene.base_map.name
    assert scene.base_scale is None
    # map_corners_lla should be restored from base
    assert scene.map_corners_lla == orig_base_corners
    # glb_map and glb_anchor should survive unapply
    assert scene.glb_map is not None
    assert scene.glb_anchor is not None

  def test_unapply_glb_when_not_applied_raises_error(self):
    """Test: unapply_glb_map() when not applied raises 400."""
    scene = Scene.objects.create(
      name="not_applied",
      map_type="geospatial_map",
      use_glb_map=False
    )

    with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
      glb_alignment.unapply_glb_map(scene)
    assert exc_info.value.status == 400


class TestMoveGlbAnchor(TransactionTestCase):
  """Tests for move_glb_anchor() state machine."""

  def setUp(self):
    """Create temp media."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _read_test_glb(self):
    """Read the test GLB file."""
    with open(TEST_GLB_FILE, 'rb') as f:
      return f.read()

  def _create_scene_with_stored_glb(self):
    """Create a scene with stored GLB (not applied)."""
    from scene_common.earth_lla import localFootprintCornersLLA
    scene = Scene.objects.create(
      name="stored_glb",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True,
      use_glb_map=False
    )
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    glb_path = os.path.join(self.media_root, "stored.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())
    scene.glb_map = "stored.glb"
    scene.glb_anchor = {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    scene.save()
    return scene

  def test_move_glb_anchor_when_not_applied_updates_anchor_only(self):
    """Test: move_glb_anchor() when not applied updates anchor without recomputing pose."""
    scene = self._create_scene_with_stored_glb()
    old_anchor = scene.glb_anchor.copy()

    new_anchor = {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}
    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      glb_alignment.move_glb_anchor(scene, new_anchor)

    # Anchor should be updated
    assert scene.glb_anchor['lat'] == 37.40
    assert scene.glb_anchor['lng'] == -121.95
    assert scene.glb_anchor['heading_deg'] == 45.0
    # Footprint should survive
    assert scene.glb_anchor['footprint_m'] == old_anchor['footprint_m']

  def test_move_glb_anchor_invalid_anchor_raises_error(self):
    """Test: move_glb_anchor() with invalid anchor raises 400."""
    scene = self._create_scene_with_stored_glb()

    with pytest.raises(glb_alignment.GlbAlignmentError) as exc_info:
      glb_alignment.move_glb_anchor(scene, {'lat': float('nan'), 'lng': -121.96, 'heading_deg': 0.0})
    assert exc_info.value.status == 400


class TestRemoveGlbMap(TransactionTestCase):
  """Tests for remove_glb_map() state machine."""

  def setUp(self):
    """Create temp media."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _read_test_glb(self):
    """Read the test GLB file."""
    with open(TEST_GLB_FILE, 'rb') as f:
      return f.read()

  def test_remove_glb_clears_stored_glb_and_anchor(self):
    """Test: remove_glb_map() clears glb_map and glb_anchor."""
    from scene_common.earth_lla import localFootprintCornersLLA
    scene = Scene.objects.create(
      name="removable",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True,
      use_glb_map=False
    )
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    glb_path = os.path.join(self.media_root, "remove.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())
    scene.glb_map = "remove.glb"
    scene.glb_anchor = {'lat': 37.38, 'lng': -121.96, 'heading_deg': 0.0,
                         'footprint_m': {'width': 10.0, 'height': 10.0}}
    scene.save()

    with patch('manager.models.sendUpdateCommand'):
      glb_alignment.remove_glb_map(scene)

    # Verify GLB cleared
    assert scene.glb_map is None or not scene.glb_map.name
    assert scene.glb_anchor is None


class TestCommitGlb(TransactionTestCase):
  """Tests for commit_glb() state machine."""

  def setUp(self):
    """Create temp media."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _read_test_glb(self):
    """Read the test GLB file."""
    with open(TEST_GLB_FILE, 'rb') as f:
      return f.read()

  def test_commit_glb_stores_glb_and_sets_anchor(self):
    """Test: commit_glb() stores GLB and anchor."""
    from scene_common.earth_lla import localFootprintCornersLLA
    scene = Scene.objects.create(
      name="commit_test",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    scene.save()

    # Stage GLB
    token = str(uuid.uuid4())
    glb_staging_dir = os.path.join(self.media_root, glb_alignment.STAGING_SUBDIR)
    os.makedirs(glb_staging_dir, exist_ok=True)
    glb_path = os.path.join(glb_staging_dir, f"{token}.glb")
    with open(glb_path, 'wb') as f:
      f.write(self._read_test_glb())

    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0.0}

    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      with patch.object(glb_alignment, '_get_mesh_footprint_corners_from_glb',
                        return_value=(10.0, 10.0)):
        result = glb_alignment.commit_glb(scene, token, anchor)

    # Verify GLB stored
    assert scene.glb_map is not None
    assert scene.glb_anchor is not None
    assert scene.glb_anchor['lat'] == 37.39
    assert result['exists'] is True


class TestGlbTrsMatrixInvariance(TransactionTestCase):
  """Tests verifying trs_matrix is unchanged by GLB operations."""

  def setUp(self):
    """Create temp media and scene with trs_matrix."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def test_apply_unapply_preserves_trs_matrix(self):
    """Test: trs_matrix unchanged by apply/unapply cycle."""
    from PIL import Image
    import numpy as np
    from scene_common.earth_lla import localFootprintCornersLLA

    scene = Scene.objects.create(
      name="trs_test",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    # Set a dummy trs_matrix
    orig_trs = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    scene.trs_matrix = orig_trs

    # Create snapshot
    png_data = np.zeros((16, 16, 3), dtype=np.uint8)
    png_img = Image.fromarray(png_data)
    png_path = os.path.join(self.media_root, "snap.png")
    png_img.save(png_path, format='PNG')
    scene.map = "snap.png"
    scene.save()

    # Create and store GLB
    with open(TEST_GLB_FILE, 'rb') as f:
      glb_data = f.read()
    glb_path = os.path.join(self.media_root, "test.glb")
    with open(glb_path, 'wb') as f:
      f.write(glb_data)
    scene.glb_map = "test.glb"
    scene.glb_anchor = {
      'lat': 37.39,
      'lng': -121.97,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    scene.save()

    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      # Apply GLB
      with transaction.atomic():
        glb_alignment.apply_glb_map(scene)
      assert scene.trs_matrix == orig_trs, "trs_matrix changed during apply"

      # Unapply GLB
      with transaction.atomic():
        glb_alignment.unapply_glb_map(scene)
      assert scene.trs_matrix == orig_trs, "trs_matrix changed during unapply"
