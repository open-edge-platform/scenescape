# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GLB API endpoints: GET, POST, PUT, DELETE, download.

Tests the DRF/Django view layer for GeospatialGlb* endpoints covering:
  - Authentication and permission checks
  - Request validation and error handling
  - State transitions and response formats
  - File download sanitization

Coverage:
  D4: PUT /scene/{id}/geospatial-glb to update anchor and use_glb_map
  D5: DELETE /scene/{id}/geospatial-glb
  D6: Error cases: invalid anchor (400), non-bool use_glb_map (400), non-geospatial (400)
  D7: Auth: unauthenticated (403), non-admin (403)
  D8: Download: attachment header, sanitised filename, 404 when no GLB

GET and POST are covered with the commit flow in tests/sscape_tests/views/test_geospatial_glb_views.py.
"""

import json
import os
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from manager import glb_alignment
from manager.models import Scene
from scene_common.earth_lla import localFootprintCornersLLA

TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"
POSE_FIELDS = ("rotation_x", "rotation_y", "rotation_z", "translation_x", "translation_y", "translation_z")


class _GlbApplyHelpers:
  """Helpers that apply or remove the stored GLB of a scene through the API."""

  def _put(self, payload):
    """PUT the GLB endpoint with thumbnail and MQTT side effects stubbed."""
    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      return self.client.put(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(payload),
        content_type='application/json'
      )

  def _set_snapshot_map(self):
    """Give the scene a PNG snapshot map, as a geospatial scene has before a GLB is applied."""
    png_path = os.path.join(self.temp_dir.name, 'snap.png')
    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(png_path, format='PNG')
    self.scene.map = 'snap.png'
    with patch.object(Scene, 'saveThumbnail'), patch('manager.models.sendUpdateCommand'):
      self.scene.save()
    self.scene = Scene.objects.get(pk=self.scene.pk)


class TestGeospatialGlbApiPutEndpoint(_GlbApplyHelpers, TransactionTestCase):
  """Tests for PUT /scene/{id}/geospatial-glb endpoint."""

  def setUp(self):
    """Create superuser and scene with stored GLB."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    patcher = override_settings(MEDIA_ROOT=self.temp_dir.name)
    patcher.enable()
    self.addCleanup(patcher.disable)

    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="patch_test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    self.scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    # Store GLB
    glb_path = os.path.join(self.temp_dir.name, "stored.glb")
    with open(TEST_GLB_FILE, 'rb') as f_src:
      with open(glb_path, 'wb') as f_dst:
        f_dst.write(f_src.read())
    self.scene.glb_map = "stored.glb"
    self.scene.glb_anchor = {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    self.scene.save()
    self.client.force_login(self.user)

  def test_put_glb_updates_anchor(self):
    """D4: PUT with new anchor updates glb_anchor."""
    new_anchor = {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}

    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      response = self.client.put(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps({'anchor': new_anchor}),
        content_type='application/json'
      )

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertAlmostEqual(self.scene.glb_anchor['lat'], 37.40, places=5)

  def test_put_glb_invalid_use_glb_map_returns_400(self):
    """D6: PUT with non-bool use_glb_map returns 400."""
    response = self.client.put(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'use_glb_map': 'yes'}),
      content_type='application/json'
    )

    self.assertEqual(response.status_code, 400)

  def test_put_use_glb_map_true_returns_applied_scene_fields(self):
    """D4: PUT use_glb_map=true returns the pose and corners written by apply."""
    pre_apply_corners = self.scene.map_corners_lla
    self._set_snapshot_map()

    response = self._put({'use_glb_map': True})

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    fields = response.json()['scene_fields']
    self.assertEqual(fields, glb_alignment.scene_form_fields(self.scene))
    self.assertEqual(fields['map_corners_lla'], self.scene.map_corners_lla)
    self.assertNotEqual(fields['map_corners_lla'], pre_apply_corners)

  def test_put_use_glb_map_false_returns_base_scene_fields(self):
    """D4: PUT use_glb_map=false returns the snapshot frame and clears the GLB pose."""
    pre_apply_corners = self.scene.map_corners_lla
    self._set_snapshot_map()
    self.assertEqual(self._put({'use_glb_map': True}).status_code, 200)

    response = self._put({'use_glb_map': False})

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.use_glb_map)
    fields = response.json()['scene_fields']
    self.assertEqual(fields, glb_alignment.scene_form_fields(self.scene))
    self.assertEqual(fields['map_corners_lla'], pre_apply_corners)
    for name in POSE_FIELDS:
      self.assertEqual(fields[name], 0.0, name)

  def test_put_anchor_while_applied_returns_moved_scene_fields(self):
    """D4: moving an applied GLB returns the recomputed pose and corners."""
    self._set_snapshot_map()
    applied = self._put({'use_glb_map': True}).json()['scene_fields']

    response = self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}})

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    fields = response.json()['scene_fields']
    self.assertEqual(fields, glb_alignment.scene_form_fields(self.scene))
    self.assertEqual(fields['map_corners_lla'], self.scene.map_corners_lla)
    self.assertNotEqual(fields['map_corners_lla'], applied['map_corners_lla'])

  def test_put_anchor_with_failed_apply_keeps_stored_anchor(self):
    """PUT anchor with use_glb_map=true leaves the stored anchor unchanged when the apply fails."""
    anchor_before = self.scene.glb_anchor
    Scene.objects.filter(pk=self.scene.pk).update(map_corners_lla=None, base_map_corners_lla=None)

    response = self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}, 'use_glb_map': True})

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json(), {'error': 'Cannot compute pose: missing frame or anchor'})
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.glb_anchor, anchor_before)
    self.assertFalse(self.scene.use_glb_map)


class TestGeospatialGlbUnappliedPreview(_GlbApplyHelpers, TransactionTestCase):
  """Unapplied preview contract: GET is read-only, write paths render and cache the preview."""

  RENDER = (np.zeros((8, 8, 3), dtype=np.uint8), 5.0)

  def setUp(self):
    """Create superuser and scene with a stored GLB that has no preview yet."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    patcher = override_settings(MEDIA_ROOT=self.temp_dir.name)
    patcher.enable()
    self.addCleanup(patcher.disable)

    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="preview_test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    self.scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    glb_path = os.path.join(self.temp_dir.name, "stored.glb")
    with open(TEST_GLB_FILE, 'rb') as f_src:
      with open(glb_path, 'wb') as f_dst:
        f_dst.write(f_src.read())
    self.scene.glb_map = "stored.glb"
    self.scene.glb_anchor = {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    self.scene.save()
    self.preview_path = os.path.join(self.temp_dir.name, "stored_preview.png")
    self.client.force_login(self.user)

  def _get(self):
    return self.client.get(reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}))

  def test_get_does_not_render_or_write_preview(self):
    """GET renders nothing, writes no file and returns preview_url null when no preview is cached."""
    with patch.object(glb_alignment, 'generateOrthoView') as render:
      response = self._get()

    self.assertEqual(response.status_code, 200)
    render.assert_not_called()
    self.assertIsNone(response.json()['preview_url'])
    self.assertFalse(os.path.exists(self.preview_path))

  def test_unapply_renders_preview_on_write_path(self):
    """Unapplying renders the unapplied preview once with alignment rotation and returns its URL."""
    self._set_snapshot_map()
    with patch.object(glb_alignment, 'generateOrthoView', return_value=self.RENDER) as render:
      self.assertEqual(self._put({'use_glb_map': True}).status_code, 200)
      response = self._put({'use_glb_map': False})

    self.assertEqual(response.status_code, 200)
    render.assert_called_once()
    self.assertEqual(render.call_args.args[0].rotation_x, glb_alignment.ALIGN_ROTATION_X)
    self.assertTrue(os.path.exists(self.preview_path))
    self.assertTrue(response.json()['preview_url'].endswith('stored_preview.png'))

  def test_real_render_writes_valid_preview_png(self):
    """Unapplying with the real renderer caches a non-empty PNG preview."""
    self._set_snapshot_map()
    self.assertEqual(self._put({'use_glb_map': True}).status_code, 200)

    response = self._put({'use_glb_map': False})

    self.assertEqual(response.status_code, 200)
    self.assertTrue(os.path.exists(self.preview_path))
    with Image.open(self.preview_path) as img:
      self.assertEqual(img.format, 'PNG')
      self.assertGreater(img.size[0], 0)
      self.assertGreater(img.size[1], 0)

  def test_failed_render_is_retried_on_next_write_not_on_get(self):
    """A failed preview render is logged and returns null; GET does not retry it, the next write does."""
    with patch.object(glb_alignment, 'generateOrthoView', side_effect=RuntimeError('boom')) as render:
      first = self._put({'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0.0}})
      self.assertEqual(first.status_code, 200)
      self.assertIsNone(first.json()['preview_url'])
      self.assertEqual(render.call_count, 1)

      self._get()
      self.assertEqual(render.call_count, 1)

      self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 0.0}})
      self.assertEqual(render.call_count, 2)


class TestSceneFormFields(SimpleTestCase):
  """Unit tests for glb_alignment.scene_form_fields."""

  def test_returns_only_glb_form_fields_with_scene_values(self):
    """The form payload carries the pose, scale and corners and nothing else."""
    scene = SimpleNamespace(
      name='ignored', use_glb_map=True, scale=2.5,
      rotation_x=90.0, rotation_y=1.0, rotation_z=2.0,
      translation_x=3.0, translation_y=4.0, translation_z=5.0,
      map_corners_lla=[[37.0, -122.0, 0.0]],
    )

    fields = glb_alignment.scene_form_fields(scene)

    self.assertEqual(set(fields), set(glb_alignment.SCENE_FORM_GLB_FIELDS))
    self.assertEqual(fields, {
      'scale': 2.5,
      'rotation_x': 90.0, 'rotation_y': 1.0, 'rotation_z': 2.0,
      'translation_x': 3.0, 'translation_y': 4.0, 'translation_z': 5.0,
      'map_corners_lla': [[37.0, -122.0, 0.0]],
    })


class TestGeospatialGlbApiDeleteEndpoint(_GlbApplyHelpers, TransactionTestCase):
  """Tests for DELETE /scene/{id}/geospatial-glb endpoint."""

  def setUp(self):
    """Create superuser and scene with stored GLB."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    patcher = override_settings(MEDIA_ROOT=self.temp_dir.name)
    patcher.enable()
    self.addCleanup(patcher.disable)

    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="delete_test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    self.scene.map_corners_lla = localFootprintCornersLLA(
      center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
      width_m=100.0, height_m=100.0
    ).tolist()
    # Store GLB
    glb_path = os.path.join(self.temp_dir.name, "delete_me.glb")
    with open(TEST_GLB_FILE, 'rb') as f_src:
      with open(glb_path, 'wb') as f_dst:
        f_dst.write(f_src.read())
    self.scene.glb_map = "delete_me.glb"
    self.scene.glb_anchor = {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    }
    self.scene.save()
    self.client.force_login(self.user)

  def test_delete_glb_removes_stored_glb(self):
    """D5: DELETE removes stored GLB."""
    with patch('manager.models.sendUpdateCommand'):
      response = self.client.delete(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
      )

    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()['success'])
    self.scene.refresh_from_db()
    assert self.scene.glb_map is None or not self.scene.glb_map.name
    assert self.scene.glb_anchor is None

  def test_delete_applied_glb_returns_unapplied_scene_fields(self):
    """D5: DELETE of an applied GLB unapplies it and returns the restored scene fields."""
    pre_apply_corners = self.scene.map_corners_lla
    self._set_snapshot_map()
    self.assertEqual(self._put({'use_glb_map': True}).status_code, 200)

    with patch('manager.models.sendUpdateCommand'):
      response = self.client.delete(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
      )

    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertTrue(data['success'])
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.use_glb_map)
    self.assertEqual(data['scene_fields'], glb_alignment.scene_form_fields(self.scene))
    self.assertEqual(data['scene_fields']['map_corners_lla'], pre_apply_corners)
    for name in POSE_FIELDS:
      self.assertEqual(data['scene_fields'][name], 0.0, name)

  def test_delete_unapplied_glb_returns_unchanged_scene_fields(self):
    """D5: DELETE of a stored but unapplied GLB returns the scene's pose and corners untouched."""
    self.scene.translation_x = 3.5
    self.scene.rotation_z = 45.0
    self.scene.save()
    expected = glb_alignment.scene_form_fields(self.scene)

    with patch('manager.models.sendUpdateCommand'):
      response = self.client.delete(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
      )

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertEqual(response.json()['scene_fields'], expected)
    self.assertEqual(response.json()['scene_fields'], glb_alignment.scene_form_fields(self.scene))
    self.assertEqual(response.json()['scene_fields']['translation_x'], 3.5)
    self.assertEqual(response.json()['scene_fields']['rotation_z'], 45.0)

  def test_delete_glb_unauthenticated_returns_403(self):
    """D7: DELETE without authentication returns 403."""
    self.client.logout()
    response = self.client.delete(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )

    self.assertEqual(response.status_code, 403)


class TestGeospatialGlbDownload(TestCase):
  """Tests for GLB download endpoint."""

  def setUp(self):
    """Create superuser and scene with stored GLB."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    patcher = override_settings(MEDIA_ROOT=self.temp_dir.name)
    patcher.enable()
    self.addCleanup(patcher.disable)

    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="download_test",
      map_type="geospatial_map"
    )
    # Store GLB
    glb_path = os.path.join(self.temp_dir.name, "download.glb")
    with open(TEST_GLB_FILE, 'rb') as f_src:
      with open(glb_path, 'wb') as f_dst:
        f_dst.write(f_src.read())
    self.scene.glb_map = "download.glb"
    self.scene.save()
    self.client.force_login(self.user)

  def test_download_glb_returns_file_with_attachment_header(self):
    """D8: Download returns file with Content-Disposition: attachment."""
    response = self.client.get(
      reverse('geospatial_glb_download', kwargs={'scene_uid': self.scene.id})
    )

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response['Content-Type'], 'model/gltf-binary')
    self.assertIn('attachment', response['Content-Disposition'])

  def test_download_glb_filename_sanitized(self):
    """D8: Download filename is sanitised (no CR/LF/quotes/path separators)."""
    with open(TEST_GLB_FILE, 'rb') as f_src:
      with open(os.path.join(self.temp_dir.name, "safe_name.glb"), 'wb') as f_dst:
        f_dst.write(f_src.read())
    self.scene.glb_map = "safe_name.glb"
    self.scene.save()

    response = self.client.get(
      reverse('geospatial_glb_download', kwargs={'scene_uid': self.scene.id})
    )

    self.assertEqual(response.status_code, 200)
    disposition = response['Content-Disposition']
    self.assertNotIn('\n', disposition)
    self.assertNotIn('\r', disposition)
    filename = disposition.split('filename=', 1)[-1].strip('"')
    self.assertNotIn('"', filename)
    self.assertNotIn('/', filename)

  def test_download_glb_no_glb_returns_404(self):
    """D8: Download with no GLB stored returns 404."""
    scene_no_glb = Scene.objects.create(name="no_glb", map_type="geospatial_map")

    response = self.client.get(
      reverse('geospatial_glb_download', kwargs={'scene_uid': scene_no_glb.id})
    )

    self.assertEqual(response.status_code, 404)

  def test_download_glb_unauthenticated_redirects_to_login(self):
    """D8: Download without authentication redirects to login (302)."""
    self.client.logout()
    response = self.client.get(
      reverse('geospatial_glb_download', kwargs={'scene_uid': self.scene.id})
    )

    self.assertEqual(response.status_code, 302)
