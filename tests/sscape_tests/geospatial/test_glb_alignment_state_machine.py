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

from manager import glb_alignment
from manager.models import Scene, SceneSourceMap
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
      patch.object(glb_alignment, 'generateOrthoView',
                   return_value=(np.zeros((8, 8, 3), dtype=np.uint8), 10.0)),
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

    scene = Scene.objects.get(pk=scene.pk)
    scene.glb_map = self._write_test_glb("test_glb.glb")
    scene.glb_anchor = {**ANCHOR, 'footprint_m': {'width': 10.0, 'height': 10.0}}
    scene.save()
    return Scene.objects.get(pk=scene.pk)

  def _stage_glb(self):
    """Stage a copy of the test GLB under a new token and return the token."""
    token = str(uuid.uuid4())
    os.makedirs(glb_alignment.staging_dir(), exist_ok=True)
    with open(TEST_GLB_FILE, 'rb') as src:
      with open(os.path.join(glb_alignment.staging_dir(), f"{token}.glb"), 'wb') as dst:
        dst.write(src.read())
    return token

  def _stage_preview(self, token):
    """The top view that staging renders for a token."""
    path = os.path.join(glb_alignment.staging_dir(), f'{token}.png')
    with open(path, 'wb') as f:
      f.write(b'staged')
    return path

  def _write_preview(self):
    """A cached preview next to the stored GLB."""
    with open(os.path.join(self.media_root, 'test_glb_preview.png'), 'wb') as f:
      f.write(b'png')

  def _commit(self, scene, token):
    with patch.object(glb_alignment, '_get_mesh_footprint_corners_from_glb', return_value=(10.0, 10.0)):
      return glb_alignment.commit_glb(scene, token, ANCHOR)

  def test_apply_then_unapply_restores_state_and_leaves_only_expected_files(self):
    """Apply poses the GLB without the upload auto-align and keeps trs_matrix; unapply restores the snapshot."""
    scene = self._create_scene()
    snapshot_corners = scene.map_corners_lla
    trs = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    Scene.objects.filter(pk=scene.pk).update(
      trs_matrix=trs, glb_anchor={**scene.glb_anchor, 'heading_deg': 45.0})
    scene = Scene.objects.get(pk=scene.pk)

    result = glb_alignment.apply_glb_map(scene)

    self.assertTrue(result['use_glb_map'])
    self.assertTrue(scene.map.name.endswith('.glb'))
    self.assertTrue(scene.base_map)
    self.assertNotEqual(scene.rotation_z, 0.0)
    self.assertEqual(scene.rotation_x, 0.0)
    self.assertEqual(scene.trs_matrix, trs)

    scene = Scene.objects.get(pk=scene.pk)
    glb_alignment.unapply_glb_map(scene)

    self.assertFalse(scene.use_glb_map)
    self.assertEqual((scene.rotation_x, scene.rotation_z, scene.translation_x), (0.0, 0.0, 0.0))
    self.assertFalse(scene.base_map)
    self.assertIsNone(scene.base_scale)
    self.assertEqual(scene.map_corners_lla, snapshot_corners)
    self.assertTrue(scene.glb_map)
    self.assertTrue(scene.glb_anchor)
    self.assertEqual(scene.trs_matrix, trs)
    self.assertEqual(self._stored_files(), ['test_glb.glb', 'test_scene.png'])

  def test_apply_twice_raises_error(self):
    scene = self._create_scene()
    glb_alignment.apply_glb_map(scene)

    with self.assertRaises(glb_alignment.GlbAlignmentError) as ctx:
      glb_alignment.apply_glb_map(scene)
    self.assertEqual(ctx.exception.status, 400)

  def test_apply_without_stored_anchor_raises_error(self):
    scene = self._create_scene()
    scene.glb_anchor = None

    with self.assertRaises(glb_alignment.GlbAlignmentError) as ctx:
      glb_alignment.apply_glb_map(scene)
    self.assertEqual(ctx.exception.status, 400)

  def test_unapply_when_not_applied_raises_error(self):
    scene = self._create_scene()

    with self.assertRaises(glb_alignment.GlbAlignmentError) as ctx:
      glb_alignment.unapply_glb_map(scene)
    self.assertEqual(ctx.exception.status, 400)

  def test_move_when_not_applied_updates_anchor_only(self):
    scene = self._create_scene()
    old_footprint = scene.glb_anchor['footprint_m']

    glb_alignment.move_glb_anchor(scene, {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0})

    self.assertEqual(
      (scene.glb_anchor['lat'], scene.glb_anchor['lng'], scene.glb_anchor['heading_deg']),
      (37.40, -121.95, 45.0))
    self.assertEqual(scene.glb_anchor['footprint_m'], old_footprint)

  def test_move_with_invalid_anchor_raises_error(self):
    scene = self._create_scene()

    with self.assertRaises(glb_alignment.GlbAlignmentError) as ctx:
      glb_alignment.move_glb_anchor(scene, {'lat': float('nan'), 'lng': -121.96, 'heading_deg': 0.0})
    self.assertEqual(ctx.exception.status, 400)

  def test_remove_deletes_glb_and_preview_on_commit(self):
    """Positive: removing a GLB clears the row fields and deletes the file and its cached preview."""
    scene = self._create_scene()
    self._write_preview()

    glb_alignment.remove_glb_map(scene)

    self.assertFalse(scene.glb_map)
    self.assertIsNone(scene.glb_anchor)
    self.assertEqual(self._stored_files(), ['snap.png'])

  def test_failed_remove_keeps_glb_and_preview(self):
    """Negative: a remove that fails to save leaves the files its rows still reference."""
    scene = self._create_scene()
    self._write_preview()
    before = self._stored_files()

    with patch.object(Scene, 'save', side_effect=RuntimeError('save failed')):
      with self.assertRaises(glb_alignment.GlbAlignmentError) as ctx:
        glb_alignment.remove_glb_map(scene)

    self.assertEqual(ctx.exception.status, 500)
    self.assertEqual(self._stored_files(), before)
    self.assertTrue(Scene.objects.get(pk=scene.pk).glb_map)

  def test_commit_while_applied_removes_previous_applied_map(self):
    """Positive: re-applying a new GLB deletes the previously applied map file."""
    scene = self._create_scene()
    glb_alignment.apply_glb_map(scene)
    scene = Scene.objects.get(pk=scene.pk)
    previous_map = os.path.join(self.media_root, scene.map.name)

    self._commit(scene, self._stage_glb())

    scene = Scene.objects.get(pk=scene.pk)
    self.assertFalse(os.path.exists(previous_map))
    self.assertEqual(
      self._stored_files(),
      sorted([scene.base_map.name, scene.glb_map.name, scene.map.name]))

  def test_commit_adopts_the_staged_preview(self):
    """Positive: the staged top view becomes the cached preview; nothing is rendered again."""
    scene = self._create_scene()
    token = self._stage_glb()
    staged_png = self._stage_preview(token)

    result = self._commit(scene, token)

    self.assertEqual(scene.glb_anchor['lat'], ANCHOR['lat'])
    self.assertTrue(result['exists'])
    with open(glb_alignment.glb_preview_path(scene.glb_map.path), 'rb') as f:
      self.assertEqual(f.read(), b'staged')
    self.assertTrue(result['preview_url'].endswith('_preview.png'))
    self.assertFalse(os.path.exists(staged_png))

  def test_failed_commit_removes_the_new_glb_and_preview(self):
    """Negative: a commit that fails removes the GLB and preview it stored and keeps the staged files."""
    scene = self._create_scene()
    token = self._stage_glb()
    self._stage_preview(token)
    before = self._stored_files()

    with patch.object(glb_alignment, '_get_mesh_footprint_corners_from_glb',
                      side_effect=RuntimeError('measure failed')):
      with self.assertRaises(RuntimeError):
        glb_alignment.commit_glb(scene, token, ANCHOR)

    self.assertEqual(self._stored_files(), before)

  def test_commit_removes_stale_staged_files(self):
    """Positive: committing purges staged files past the TTL and keeps fresh ones."""
    scene = self._create_scene()
    staging = glb_alignment.staging_dir()
    os.makedirs(staging, exist_ok=True)
    stale = os.path.join(staging, 'stale.glb')
    fresh = os.path.join(staging, 'fresh.glb')
    for path in (stale, fresh):
      with open(path, 'wb') as f:
        f.write(b'x')
    old = time.time() - 2 * glb_alignment.STAGING_TTL_SECONDS
    os.utime(stale, (old, old))

    self._commit(scene, self._stage_glb())

    self.assertFalse(os.path.exists(stale))
    self.assertTrue(os.path.exists(fresh))

  def test_failed_apply_leaves_no_new_files(self):
    """Negative: a failed apply removes the files it wrote and keeps the snapshot."""
    scene = self._create_scene()
    before = self._stored_files()
    cases = (
      (RuntimeError('pose failed'), 500),
      (glb_alignment.GlbAlignmentError(400, 'Cannot compute pose'), 400),
    )
    for error, status in cases:
      with self.subTest(error=type(error).__name__):
        scene = Scene.objects.get(pk=scene.pk)
        with patch.object(glb_alignment, 'compute_glb_pose_and_corners', side_effect=error):
          with self.assertRaises(glb_alignment.GlbAlignmentError) as ctx:
            glb_alignment.apply_glb_map(scene)
        self.assertEqual(ctx.exception.status, status)
        self.assertEqual(self._stored_files(), before)
        stored = Scene.objects.get(pk=scene.pk)
        self.assertFalse(stored.use_glb_map)
        self.assertEqual(stored.map.name, 'snap.png')

  def test_apply_keeps_a_map_file_shared_with_a_source_map(self):
    """Negative: applying a GLB does not delete a snapshot that a source map still uses."""
    scene = self._create_scene()
    SceneSourceMap.objects.create(scene=scene, method='user', file='snap.png')

    glb_alignment.apply_glb_map(scene)

    self.assertIn('snap.png', self._stored_files())

  def test_apply_and_unapply_leave_one_thumbnail_then_none(self):
    """Positive: each thumbnail a GLB write replaces is deleted; unapply drops the last one."""
    scene = self._create_scene()

    def thumbnails():
      return [name for name in self._stored_files() if os.path.basename(name).startswith('test_scene_2d')]

    with patch.object(Scene, 'saveThumbnail', REAL_SAVE_THUMBNAIL), \
         patch('manager.models.generateOrthoView',
               return_value=(np.zeros((8, 8, 3), dtype=np.uint8), 10.0)):
      glb_alignment.apply_glb_map(scene)
      applied = thumbnails()
      scene = Scene.objects.get(pk=scene.pk)
      glb_alignment.unapply_glb_map(scene)

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
    glb_alignment.apply_glb_map(scene)
    scene = Scene.objects.get(pk=scene.pk)
    scene.thumbnail = 'applied_2d.png'

    preview_url = glb_alignment.saved_alignment(scene)['preview_url']

    self.assertTrue(preview_url.endswith('test_glb_preview.png'))

  def test_write_response_renders_a_missing_preview_but_saved_alignment_does_not(self):
    """Positive: only write_response repairs a missing preview; the read path never writes."""
    scene = self._create_scene()
    preview = glb_alignment.glb_preview_path(scene.glb_map.path)

    self.assertIsNone(glb_alignment.saved_alignment(scene)['preview_url'])
    self.assertFalse(os.path.exists(preview))
    self.assertIsNotNone(glb_alignment.write_response(scene)['preview_url'])
    self.assertTrue(os.path.exists(preview))


class TestMigration0007CornerOrder(_MediaRootTestCase):
  """Migration 0007 reads provider-ordered (SW, NW, NE, SE) corners."""

  def test_migration_0007_normalises_provider_order_corners(self):
    """Migration 0007 derives a north-up anchor (heading 0) with unswapped width and height."""
    from django.apps import apps

    migration = importlib.import_module('manager.migrations.0007_geospatial_glb_fields')
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

    heading = scene.glb_anchor['heading_deg']
    assert min(heading, 360.0 - heading) < 1e-6
    assert scene.glb_anchor['footprint_m']['width'] == pytest.approx(300.0, rel=1e-6)
    assert scene.glb_anchor['footprint_m']['height'] == pytest.approx(200.0, rel=1e-6)
    assert scene.use_glb_map is True
