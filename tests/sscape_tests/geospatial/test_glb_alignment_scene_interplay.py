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
  C5: Unapplying GLB with an unchanged map name syncs base_map_corners_lla
  C6: Corner edit without GLB applied leaves base_map_corners_lla unchanged
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

  def _save_with_patches(self, scene):
    """Save without thumbnail generation, auto-alignment, or MQTT side effects."""
    with patch.object(Scene, 'autoAlignSceneMap'), \
         patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      scene.save(send_update_command=False)

  def test_unapply_glb_with_unchanged_map_name_syncs_base_map_corners(self):
    """Test: unapplying GLB while the map filename is unchanged still syncs base_map_corners_lla."""
    png = self._create_png_file("unapply_same_map.png")
    old_corners = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    new_corners = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=80.0, height_m=80.0
    ).tolist()
    scene = Scene.objects.create(
      name="unapply_same_map",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      map=png,
      map_corners_lla=old_corners,
      use_glb_map=False,
      output_lla=True
    )
    # Persisted state of a scene with GLB applied on top of the same PNG snapshot.
    Scene.objects.filter(pk=scene.pk).update(use_glb_map=True, base_map_corners_lla=old_corners)
    scene = Scene.objects.get(pk=scene.pk)
    assert scene.use_glb_map is True

    scene.use_glb_map = False
    scene.map_corners_lla = new_corners
    self._save_with_patches(scene)

    assert scene.use_glb_map is False
    assert scene.map == png
    assert scene.base_map_corners_lla == new_corners

  def test_corner_edit_without_glb_keeps_base_map_corners(self):
    """Test: editing corners on a non-GLB scene with the same map leaves base_map_corners_lla alone."""
    png = self._create_png_file("corner_edit_same_map.png")
    old_corners = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    new_corners = localFootprintCornersLLA(
      center_lat=37.39, center_lng=-121.97, heading_deg=0.0,
      width_m=80.0, height_m=80.0
    ).tolist()
    scene = Scene.objects.create(
      name="corner_edit_same_map",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      map=png,
      map_corners_lla=old_corners,
      use_glb_map=False,
      output_lla=True
    )
    scene = Scene.objects.get(pk=scene.pk)
    base_before = scene.base_map_corners_lla

    scene.map_corners_lla = new_corners
    self._save_with_patches(scene)

    assert scene.use_glb_map is False
    assert scene.base_map_corners_lla == base_before


class TestSerializerRotationTranslation(TestCase):
  """SceneSerializer exposes mesh_rotation / mesh_translation as [x, y, z], zero components included."""

  def test_mesh_rotation_and_translation_are_vectors(self):
    """All-zero, single-component and mixed values round-trip as full three-element vectors."""
    scene = Scene.objects.create(name="test_scene", map_type="geospatial_map")
    cases = [
      ("rotation", "mesh_rotation", [0.0, 0.0, 0.0]),
      ("rotation", "mesh_rotation", [0.0, 0.0, 45.0]),
      ("rotation", "mesh_rotation", [0.0, 30.0, 0.0]),
      ("translation", "mesh_translation", [0.0, 0.0, 0.0]),
      ("translation", "mesh_translation", [5.5, 0.0, 0.0]),
      ("translation", "mesh_translation", [0.0, 10.25, 0.0]),
    ]
    for prefix, key, values in cases:
      with self.subTest(key=key, values=values):
        for axis, value in zip("xyz", values):
          setattr(scene, f"{prefix}_{axis}", value)
        scene.save()
        assert SceneSerializer(scene).data.get(key) == values


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
