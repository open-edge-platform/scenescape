# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Scene.save interplay and serializer get_rotation/get_translation.

Tests Scene.save() behavior with GLB applied/unapplied, and serializer methods
that return stored vectors even when one or more components are zero.

Coverage:
  C1: Saving new non-GLB map while use_glb_map=True sets use_glb_map=False
  C2: Saving new snapshot while not applied refreshes base_map_corners_lla
  C3: Serializer get_rotation/get_translation: [0,0,0] only when ALL components are 0
  C4: frame_corners_lla() fallbacks for legacy scenes
"""

import os
import tempfile
from unittest.mock import patch

import numpy as np
from django.test import TestCase, TransactionTestCase, override_settings
from PIL import Image

from manager.models import Scene
from manager.serializers import SceneSerializer
from scene_common.earth_lla import localFootprintCornersLLA


class TestSceneSaveGlbInterplay(TransactionTestCase):
  """Tests Scene.save() behavior with GLB applied/unapplied."""

  def setUp(self):
    """Create temp media root."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _create_png_file(self, name):
    """Create a dummy PNG file and return the path."""
    png_data = np.zeros((8, 8, 3), dtype=np.uint8)
    png_img = Image.fromarray(png_data)
    path = os.path.join(self.media_root, name)
    png_img.save(path, format='PNG')
    return name

  def test_save_new_png_map_while_glb_applied_sets_use_glb_map_false(self):
    """Test: saving new PNG while use_glb_map=True sets it False."""
    scene = Scene.objects.create(
      name="glb_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      use_glb_map=True,
      output_lla=True
    )
    old_corners = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    scene.map_corners_lla = old_corners
    scene.base_map_corners_lla = old_corners
    scene.save()

    # Set pose (as if GLB applied)
    scene.rotation_x = 45.0
    scene.rotation_z = 30.0

    # Assign a new PNG map
    new_png = self._create_png_file("new_map.png")
    new_corners = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=120.0, height_m=80.0
    ).tolist()

    scene.map = new_png
    scene.map_corners_lla = new_corners

    with patch.object(Scene, 'autoAlignSceneMap'), \
         patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      scene.save(send_update_command=False)

    # Verify: use_glb_map set False, base_map_corners_lla updated
    assert scene.use_glb_map is False
    assert scene.base_map_corners_lla == new_corners
    # Rotation should be reset
    assert scene.rotation_x == 0.0
    assert scene.rotation_z == 0.0

  def test_save_new_snapshot_while_not_applied_updates_base_map_corners(self):
    """Test: saving new snapshot while not applied refreshes base_map_corners_lla."""
    old_png = self._create_png_file("old_snap.png")
    old_corners = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()

    scene = Scene.objects.create(
      name="non_glb",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      map=old_png,
      map_corners_lla=old_corners,
      use_glb_map=False,
      output_lla=True
    )
    scene.save()

    # Replace snapshot with new PNG and new corners
    new_png = self._create_png_file("new_snap.png")
    new_corners = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=80.0, height_m=80.0
    ).tolist()
    scene.map = new_png
    scene.map_corners_lla = new_corners

    with patch.object(Scene, 'autoAlignSceneMap'), \
         patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      scene.save(send_update_command=False)

    # Verify: base_map_corners_lla updated to new corners
    assert scene.base_map_corners_lla == new_corners


class TestSerializerRotationTranslation(TestCase):
  """Tests SceneSerializer get_rotation/get_translation methods."""

  def setUp(self):
    """Create a scene with various rotation/translation values."""
    self.scene = Scene.objects.create(
      name="test_scene",
      map_type="geospatial_map"
    )

  def test_get_rotation_returns_zero_vector_when_all_components_zero(self):
    """Test: get_rotation returns [0,0,0] when all rotation components are 0."""
    self.scene.rotation_x = 0.0
    self.scene.rotation_y = 0.0
    self.scene.rotation_z = 0.0
    self.scene.save()

    serializer = SceneSerializer(self.scene)
    rotation = serializer.data.get('mesh_rotation')
    assert rotation == [0, 0, 0], f"Expected [0,0,0], got {rotation}"

  def test_get_rotation_preserves_nonzero_when_only_one_component(self):
    """Test: get_rotation returns vector even if only rotation_z != 0."""
    self.scene.rotation_x = 0.0
    self.scene.rotation_y = 0.0
    self.scene.rotation_z = 45.0
    self.scene.save()

    serializer = SceneSerializer(self.scene)
    rotation = serializer.data.get('mesh_rotation')
    assert rotation == [0.0, 0.0, 45.0], f"Expected [0,0,45], got {rotation}"

  def test_get_rotation_preserves_mixed_zero_nonzero(self):
    """Test: get_rotation returns vector with mixed zero/nonzero components."""
    self.scene.rotation_x = 0.0
    self.scene.rotation_y = 30.0
    self.scene.rotation_z = 0.0
    self.scene.save()

    serializer = SceneSerializer(self.scene)
    rotation = serializer.data.get('mesh_rotation')
    assert rotation == [0.0, 30.0, 0.0], f"Expected [0,30,0], got {rotation}"

  def test_get_translation_returns_zero_vector_when_all_components_zero(self):
    """Test: get_translation returns [0,0,0] when all components are 0."""
    self.scene.translation_x = 0.0
    self.scene.translation_y = 0.0
    self.scene.translation_z = 0.0
    self.scene.save()

    serializer = SceneSerializer(self.scene)
    translation = serializer.data.get('mesh_translation')
    assert translation == [0, 0, 0], f"Expected [0,0,0], got {translation}"

  def test_get_translation_preserves_nonzero_when_only_one_component(self):
    """Test: get_translation returns vector even if only translation_x != 0."""
    self.scene.translation_x = 5.5
    self.scene.translation_y = 0.0
    self.scene.translation_z = 0.0
    self.scene.save()

    serializer = SceneSerializer(self.scene)
    translation = serializer.data.get('mesh_translation')
    assert translation == [5.5, 0.0, 0.0], f"Expected [5.5,0,0], got {translation}"

  def test_get_translation_preserves_mixed_zero_nonzero(self):
    """Test: get_translation returns vector with mixed zero/nonzero components."""
    self.scene.translation_x = 0.0
    self.scene.translation_y = 10.25
    self.scene.translation_z = 0.0
    self.scene.save()

    serializer = SceneSerializer(self.scene)
    translation = serializer.data.get('mesh_translation')
    assert translation == [0.0, 10.25, 0.0], f"Expected [0,10.25,0], got {translation}"


class TestFrameCornersLlaFallback(TestCase):
  """Tests Scene.frame_corners_lla() fallback logic."""

  def test_frame_corners_lla_returns_base_map_corners_when_set(self):
    """Test: frame_corners_lla() returns base_map_corners_lla if set (geospatial + base_map)."""
    base_corners = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    map_corners = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=50.0, height_m=50.0
    ).tolist()

    scene = Scene.objects.create(
      name="geo_scene",
      map_type="geospatial_map",
      base_map_corners_lla=base_corners,
      map_corners_lla=map_corners
    )

    result = scene.frame_corners_lla()
    assert result == base_corners, "frame_corners_lla() should return base_map_corners_lla"

  def test_frame_corners_lla_returns_map_corners_when_no_base(self):
    """Test: frame_corners_lla() returns map_corners_lla when base_map_corners_lla is None."""
    map_corners = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=50.0, height_m=50.0
    ).tolist()

    scene = Scene.objects.create(
      name="geo_scene",
      map_type="geospatial_map",
      base_map_corners_lla=None,
      map_corners_lla=map_corners
    )

    result = scene.frame_corners_lla()
    assert result == map_corners, "frame_corners_lla() should return map_corners_lla"

  def test_frame_corners_lla_returns_map_corners_for_non_geospatial(self):
    """Test: frame_corners_lla() returns map_corners_lla for non-geospatial scenes."""
    map_corners = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    scene = Scene.objects.create(
      name="non_geo",
      map_type="other_type",
      map_corners_lla=map_corners
    )

    result = scene.frame_corners_lla()
    assert result == map_corners, "frame_corners_lla() should return map_corners_lla for non-geospatial scenes"
