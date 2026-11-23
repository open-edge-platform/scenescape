# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the GLB state machine: apply, unapply, move, remove, commit and their files.

Tests invariants: trs_matrix unchanged, unapply restores state, apply twice and other error
cases, files written by a write are cleaned up on success and on failure, migration 0007.
"""

import importlib
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from django.test import TransactionTestCase, override_settings
from PIL import Image

from manager import glb_staging, glb_state
from manager.models import GlbLayer, Scene, SceneSourceMap, glb_preview_name
from scene_common.earth_lla import localFootprintCornersLLA

TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"
# Taken before a test stubs it, for the tests that check the thumbnail files
REAL_SAVE_THUMBNAIL = Scene.saveThumbnail
ANCHOR = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0.0}


class _MediaRootTestCase(TransactionTestCase):
  """Temporary media root for the files a test writes."""

  def setUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    patcher = override_settings(MEDIA_ROOT=self.media_root)
    patcher.enable()
    self.addCleanup(patcher.disable)

  def _write_test_glb(self, name):
    """Copy the test GLB into the media root under name and return name."""
    with open(TEST_GLB_FILE, 'rb') as src, open(os.path.join(self.media_root, name), 'wb') as dst:
      dst.write(src.read())
    return name

  def _stored_files(self):
    """Relative paths of every file under the temp media root."""
    found = []
    for root, _, names in os.walk(self.media_root):
      for name in names:
        found.append(os.path.relpath(os.path.join(root, name), self.media_root))
    return sorted(found)


class TestGlbStateMachine(_MediaRootTestCase):
  """Apply, unapply, move, remove and commit; thumbnails, MQTT and ortho renders are stubbed."""

  def setUp(self):
    super().setUp()
    stubs = (
      patch.object(Scene, 'saveThumbnail'),
      patch('manager.models.sendUpdateCommand'),
      patch.object(glb_staging, 'generateOrthoView',
                   return_value=(np.zeros((8, 8, 3), dtype=np.uint8), 10.0, [0.0, 0.0])),
    )
    for stub in stubs:
      stub.start()
      self.addCleanup(stub.stop)

  def _create_scene(self):
    """Geospatial scene whose map is a PNG snapshot, with a stored GLB and anchor."""
    scene = Scene.objects.create(
      name="test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(
      os.path.join(self.media_root, "snap.png"), format='PNG')
    scene.map = "snap.png"
    scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    scene.save()

    self._write_test_glb("test_glb.glb")
    GlbLayer.objects.create(scene=scene, order=0, enabled=False, file="test_glb.glb",
                            anchor={**ANCHOR, 'footprint_m': {'width': 10.0, 'height': 10.0}})
    return Scene.objects.get(pk=scene.pk)

  def _stage_glb(self):
    """Stage a copy of the test GLB under a new token and return the token."""
    token = str(uuid.uuid4())
    os.makedirs(glb_staging.staging_dir(), exist_ok=True)
    with open(TEST_GLB_FILE, 'rb') as src:
      with open(os.path.join(glb_staging.staging_dir(), f"{token}.glb"), 'wb') as dst:
        dst.write(src.read())
    return token

  def _stage_preview(self, token):
    """The top view that staging renders for a token."""
    path = os.path.join(glb_staging.staging_dir(), f'{token}.png')
    with open(path, 'wb') as f:
      f.write(b'staged')
    return path

  def _write_preview(self):
    """A cached preview next to the stored GLB."""
    with open(os.path.join(self.media_root, 'test_glb_preview.png'), 'wb') as f:
      f.write(b'png')

  def _commit(self, scene, token, layer=None, enable=False):
    with patch.object(glb_state, '_get_aligned_footprint_size_m', return_value=(10.0, 10.0)):
      layer = glb_state.commit_layer(scene, token, ANCHOR, layer=layer, enable=enable)
      return glb_state.write_response(layer)

  def test_apply_then_unapply_restores_state_and_leaves_only_expected_files(self):
    """Apply poses the GLB without the upload auto-align and keeps trs_matrix; unapply restores the snapshot."""
    scene = self._create_scene()
    snapshot_corners = scene.map_corners_lla
    trs = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    Scene.objects.filter(pk=scene.pk).update(trs_matrix=trs)
    layer = scene.glb_layers.get()
    GlbLayer.objects.filter(pk=layer.pk).update(anchor={**layer.anchor, 'heading_deg': 45.0})
    scene = Scene.objects.get(pk=scene.pk)

    glb_state.set_layer_enabled(scene, layer, True)

    layer.refresh_from_db()
    self.assertTrue(layer.enabled)
    self.assertTrue(scene.map.name.endswith('.glb'))
    self.assertTrue(scene.base_map)
    self.assertNotEqual(scene.rotation_z, 0.0)
    self.assertEqual(scene.rotation_x, glb_staging.ALIGN_ROTATION_X)
    self.assertEqual(scene.trs_matrix, trs)

    scene = Scene.objects.get(pk=scene.pk)
    glb_state.set_layer_enabled(scene, layer, False)

    self.assertFalse(scene.use_glb_map)
    self.assertEqual((scene.rotation_x, scene.rotation_z, scene.translation_x), (0.0, 0.0, 0.0))
    self.assertFalse(scene.base_map)
    self.assertIsNone(scene.base_scale)
    self.assertEqual(scene.map_corners_lla, snapshot_corners)
    self.assertTrue(GlbLayer.objects.filter(pk=layer.pk).exists())
    self.assertEqual(scene.trs_matrix, trs)
    self.assertEqual(self._stored_files(), ['test_glb.glb', 'test_scene.png'])

  def test_apply_twice_raises_error(self):
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    glb_state.set_layer_enabled(scene, layer, True)

    with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
      glb_state.set_layer_enabled(scene, layer, True)
    self.assertEqual(ctx.exception.status, 400)

  def test_move_enabled_layer_without_footprint_raises_error(self):
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    glb_state.set_layer_enabled(scene, layer, True)
    GlbLayer.objects.filter(pk=layer.pk).update(anchor={**ANCHOR, 'footprint_m': {}})
    layer.refresh_from_db()

    with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
      glb_state.move_layer(scene, layer, {'lat': 37.40, 'lng': -121.95, 'heading_deg': 0.0})
    self.assertEqual(ctx.exception.status, 400)

  def test_unapply_when_not_applied_raises_error(self):
    scene = self._create_scene()

    with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
      glb_state.set_layer_enabled(scene, scene.glb_layers.get(), False)
    self.assertEqual(ctx.exception.status, 400)

  def test_move_when_not_applied_updates_anchor_only(self):
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    old_footprint = layer.anchor['footprint_m']

    glb_state.move_layer(scene, layer, {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0})

    layer.refresh_from_db()
    self.assertEqual(
      (layer.anchor['lat'], layer.anchor['lng'], layer.anchor['heading_deg']),
      (37.40, -121.95, 45.0))
    self.assertEqual(layer.anchor['footprint_m'], old_footprint)

  def test_move_with_invalid_anchor_raises_error(self):
    scene = self._create_scene()

    with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
      glb_state.move_layer(scene, scene.glb_layers.get(), {'lat': float('nan'), 'lng': -121.96, 'heading_deg': 0.0})
    self.assertEqual(ctx.exception.status, 400)

  def test_remove_deletes_glb_and_preview_on_commit(self):
    """Positive: removing a layer deletes its row, its file and its cached preview."""
    scene = self._create_scene()
    self._write_preview()

    glb_state.remove_layer(scene, scene.glb_layers.get())

    self.assertFalse(scene.glb_layers.exists())
    self.assertEqual(self._stored_files(), ['snap.png'])

  def test_failed_remove_keeps_glb_and_preview(self):
    """Negative: a remove that fails to save leaves the files its rows still reference."""
    scene = self._create_scene()
    self._write_preview()
    before = self._stored_files()
    layer = scene.glb_layers.get()
    layer_id = layer.pk

    with patch.object(Scene, 'save', side_effect=RuntimeError('save failed')):
      with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
        glb_state.remove_layer(scene, layer)

    self.assertEqual(ctx.exception.status, 500)
    self.assertEqual(self._stored_files(), before)
    self.assertTrue(GlbLayer.objects.filter(pk=layer_id).exists())

  def test_commit_while_applied_removes_previous_applied_map(self):
    """Positive: replacing an applied layer's file deletes the previously applied map file."""
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    glb_state.set_layer_enabled(scene, layer, True)
    scene = Scene.objects.get(pk=scene.pk)
    previous_map = os.path.join(self.media_root, scene.map.name)

    self._commit(scene, self._stage_glb(), layer=layer)

    scene = Scene.objects.get(pk=scene.pk)
    layer.refresh_from_db()
    self.assertFalse(os.path.exists(previous_map))
    self.assertEqual(
      self._stored_files(),
      sorted([scene.base_map.name, layer.file.name, scene.map.name,
              os.path.splitext(layer.file.name)[0] + '_preview.png']))

  def test_commit_adopts_the_staged_preview(self):
    """Positive: the staged top view becomes the cached preview; nothing is rendered again."""
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    token = self._stage_glb()
    staged_png = self._stage_preview(token)

    result = self._commit(scene, token, layer=layer)

    layer.refresh_from_db()
    self.assertEqual(layer.anchor['lat'], ANCHOR['lat'])
    with open(glb_preview_name(layer.file.path), 'rb') as f:
      self.assertEqual(f.read(), b'staged')
    self.assertTrue(result['preview_url'].endswith('_preview.png'))
    self.assertFalse(os.path.exists(staged_png))

  def test_failed_commit_removes_the_new_glb_and_preview(self):
    """Negative: a commit that fails removes the GLB and preview it stored and keeps the staged files."""
    scene = self._create_scene()
    token = self._stage_glb()
    self._stage_preview(token)
    before = self._stored_files()
    layer = scene.glb_layers.get()

    with patch.object(glb_state, '_get_aligned_footprint_size_m',
                      side_effect=RuntimeError('measure failed')):
      with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
        glb_state.commit_layer(scene, token, ANCHOR, layer=layer)

    self.assertEqual(ctx.exception.status, 500)

    self.assertEqual(self._stored_files(), before)

  def test_commit_removes_stale_staged_files(self):
    """Positive: committing purges staged files past the TTL and keeps fresh ones."""
    scene = self._create_scene()
    staging = glb_staging.staging_dir()
    os.makedirs(staging, exist_ok=True)
    stale = os.path.join(staging, 'stale.glb')
    fresh = os.path.join(staging, 'fresh.glb')
    for path in (stale, fresh):
      with open(path, 'wb') as f:
        f.write(b'x')
    old = time.time() - 2 * glb_staging.STAGING_TTL_SECONDS
    os.utime(stale, (old, old))

    self._commit(scene, self._stage_glb(), layer=scene.glb_layers.get())

    self.assertFalse(os.path.exists(stale))
    self.assertTrue(os.path.exists(fresh))

  def test_failed_apply_leaves_no_new_files(self):
    """Negative: a failed apply removes the files it wrote and keeps the snapshot."""
    scene = self._create_scene()
    before = self._stored_files()
    cases = (
      (RuntimeError('pose failed'), 500),
      (glb_staging.GlbAlignmentError(400, 'Cannot compute pose'), 400),
    )
    for error, status in cases:
      with self.subTest(error=type(error).__name__):
        scene = Scene.objects.get(pk=scene.pk)
        with patch.object(glb_state, 'compute_glb_pose_and_corners', side_effect=error):
          with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
            glb_state.set_layer_enabled(scene, scene.glb_layers.get(), True)
        self.assertEqual(ctx.exception.status, status)
        self.assertEqual(self._stored_files(), before)
        stored = Scene.objects.get(pk=scene.pk)
        self.assertFalse(stored.use_glb_map)
        self.assertEqual(stored.map.name, 'snap.png')

  def test_apply_keeps_a_map_file_shared_with_a_source_map(self):
    """Negative: applying a GLB does not delete a snapshot that a source map still uses."""
    scene = self._create_scene()
    SceneSourceMap.objects.create(scene=scene, method='user', file='snap.png')

    glb_state.set_layer_enabled(scene, scene.glb_layers.get(), True)

    self.assertIn('snap.png', self._stored_files())

  def test_apply_and_unapply_leave_one_thumbnail_then_none(self):
    """Positive: each thumbnail a GLB write replaces is deleted; unapply drops the last one."""
    scene = self._create_scene()

    def thumbnails():
      return [name for name in self._stored_files() if os.path.basename(name).startswith('test_scene_2d')]

    with patch.object(Scene, 'saveThumbnail', REAL_SAVE_THUMBNAIL), \
         patch('manager.models.generateOrthoView',
               return_value=(np.zeros((8, 8, 3), dtype=np.uint8), 10.0, [0.0, 0.0])):
      layer = scene.glb_layers.get()
      glb_state.set_layer_enabled(scene, layer, True)
      applied = thumbnails()
      scene = Scene.objects.get(pk=scene.pk)
      glb_state.set_layer_enabled(scene, layer, False)

    self.assertEqual(len(applied), 1)
    self.assertEqual(thumbnails(), [])

  def test_scene_delete_removes_glb_files(self):
    """Positive: deleting a scene deletes its GLB and cached preview with its map."""
    scene = self._create_scene()
    self._write_preview()

    scene.delete()

    self.assertEqual(self._stored_files(), [])

  def test_preview_url_is_the_glb_preview_when_applied(self):
    """Positive: the overlay preview is the GLB top view in both states, not the posed thumbnail."""
    scene = self._create_scene()
    self._write_preview()
    layer = scene.glb_layers.get()
    glb_state.set_layer_enabled(scene, layer, True)
    scene = Scene.objects.get(pk=scene.pk)
    scene.thumbnail = 'applied_2d.png'

    preview_url = glb_state.saved_alignment(layer)['preview_url']

    self.assertTrue(preview_url.endswith('test_glb_preview.png'))

  def test_write_response_renders_a_missing_preview_but_saved_alignment_does_not(self):
    """Positive: only write_response repairs a missing preview; the read path never writes."""
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    preview = glb_preview_name(layer.file.path)

    self.assertIsNone(glb_state.saved_alignment(layer)['preview_url'])
    self.assertFalse(os.path.exists(preview))
    self.assertIsNotNone(glb_state.write_response(layer)['preview_url'])
    self.assertTrue(os.path.exists(preview))

  def _add_layer(self, scene, name, order):
    """A second stored layer with its own GLB file, not applied."""
    self._write_test_glb(name)
    return GlbLayer.objects.create(scene=scene, order=order, enabled=False, file=name,
                                   anchor={**ANCHOR, 'footprint_m': {'width': 10.0, 'height': 10.0}})

  def test_two_layers_keep_use_glb_map_equal_to_any_enabled(self):
    """Positive: with two layers the scene stays a GLB map until the last enabled layer is taken off."""
    scene = self._create_scene()
    first = scene.glb_layers.get()
    second = self._add_layer(scene, 'second_glb.glb', order=1)

    def toggle(layer, enabled):
      fresh = Scene.objects.get(pk=scene.pk)
      glb_state.set_layer_enabled(fresh, layer, enabled)
      return Scene.objects.get(pk=scene.pk)

    for layer, enabled, expected in ((first, True, True), (second, True, True),
                                     (first, False, True), (second, False, False)):
      with self.subTest(layer=layer.order, enabled=enabled):
        scene = toggle(layer, enabled)
        self.assertEqual(scene.use_glb_map, expected)
        self.assertEqual(scene.use_glb_map, scene.glb_layers.filter(enabled=True).exists())

    self.assertFalse(scene.base_map)

  def test_removing_one_of_two_layers_keeps_the_other_applied(self):
    """Positive: removing a stored layer leaves the applied layer's row and file in place."""
    scene = self._create_scene()
    first = scene.glb_layers.get()
    second = self._add_layer(scene, 'second_glb.glb', order=1)
    glb_state.set_layer_enabled(scene, first, True)
    scene = Scene.objects.get(pk=scene.pk)

    glb_state.remove_layer(scene, second)

    first.refresh_from_db()
    self.assertTrue(first.enabled)
    self.assertFalse(GlbLayer.objects.filter(pk=second.pk).exists())
    self.assertTrue(scene.use_glb_map)
    self.assertNotIn('second_glb.glb', self._stored_files())

  @override_settings(GLB_MAX_LAYERS=1)
  def test_new_layer_past_the_limit_is_refused_and_stores_nothing(self):
    """Negative: at the default limit of one layer a new upload is refused with 409 and no file is written."""
    scene = self._create_scene()
    token = self._stage_glb()
    before = self._stored_files()

    with self.assertRaises(glb_staging.GlbAlignmentError) as ctx:
      self._commit(scene, token)

    self.assertEqual(ctx.exception.status, 409)
    self.assertEqual(scene.glb_layers.count(), 1)
    self.assertEqual(self._stored_files(), before)

  @override_settings(GLB_MAX_LAYERS=1)
  def test_replacing_a_layer_file_keeps_the_row_at_the_limit(self):
    """Positive: with a layer stored, committing with layer= replaces its file and keeps one row."""
    scene = self._create_scene()
    layer = scene.glb_layers.get()
    old_path = os.path.join(self.media_root, 'test_glb.glb')

    self._commit(scene, self._stage_glb(), layer=layer)

    self.assertEqual(scene.glb_layers.count(), 1)
    self.assertFalse(os.path.exists(old_path))
    layer.refresh_from_db()
    self.assertTrue(os.path.exists(layer.file.path))


class TestMigration0012CornerOrder(_MediaRootTestCase):
  """Migration 0012 reads provider-ordered (SW, NW, NE, SE) corners."""

  def test_migration_0012_normalises_provider_order_corners(self):
    """Migration 0012 derives a north-up anchor (heading 0) with unswapped width and height."""
    from django.apps import apps

    migration = importlib.import_module('manager.migrations.0012_geospatial_glb_fields')
    ccw = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=300.0, height_m=200.0
    )
    provider_order = ccw[[0, 3, 2, 1]].tolist()  # SW, NW, NE, SE

    scene = Scene.objects.create(
      name="legacy_migrate",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    scene.map = self._write_test_glb("legacy_migrate.glb")
    scene.map_corners_lla = provider_order
    scene.save()

    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      migration.migrate_existing_glb_maps(apps, None)
    scene.refresh_from_db()

    layer = scene.glb_layers.get()
    heading = layer.anchor['heading_deg']
    assert min(heading, 360.0 - heading) < 1e-6
    assert layer.anchor['footprint_m']['width'] == pytest.approx(300.0, rel=1e-6)
    assert layer.anchor['footprint_m']['height'] == pytest.approx(200.0, rel=1e-6)
    assert scene.use_glb_map is True
