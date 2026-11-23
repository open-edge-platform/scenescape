# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GLB API endpoints: GET, POST, PUT, DELETE, download.

Tests the DRF/Django view layer for GeospatialGlbLayer* endpoints covering:
  - Authentication and permission checks
  - Request validation and error handling
  - State transitions and response formats
  - File download sanitization

Coverage:
  D4: PUT /scene/{id}/geospatial-glbs/{layer_id} to move a layer or place/take off the map
  D5: DELETE /scene/{id}/geospatial-glbs/{layer_id}
  D6: Error cases: invalid anchor (400), non-bool enabled (400), non-geospatial (400)
  D7: Auth: unauthenticated (403), non-admin (403)
  D8: Download: attachment header, sanitised filename, 404 when no layer

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
import pytest
from django.contrib.auth.models import User
from django.core.files import File
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from manager import glb_staging, glb_state
from manager.models import GlbLayer, Scene, glb_preview_name
from tests.utils.geo_footprint import localFootprintCornersLLA

TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"
POSE_FIELDS = ("rotation_x", "rotation_y", "rotation_z", "translation_x", "translation_y", "translation_z")


def _store_layer(scene, anchor, enabled=False, name='stored.glb'):
  """Store the test GLB as a layer of the scene; the layer file is written under MEDIA_ROOT."""
  layer = GlbLayer(scene=scene, anchor=anchor, enabled=enabled, order=scene.glb_layers.count())
  with open(TEST_GLB_FILE, 'rb') as f_src:
    layer.file.save(name, File(f_src), save=False)
  layer.save()
  return layer


class _GlbApplyHelpers:
  """Helpers that place or take off the stored GLB layer of a scene through the API."""

  def _layer_url(self):
    return reverse('geospatial_glb_layer', kwargs={'scene_uid': self.scene.id, 'layer_id': self.layer.id})

  def _put(self, payload):
    """PUT the layer endpoint with thumbnail and MQTT side effects stubbed."""
    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      return self.client.put(
        self._layer_url(),
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
  """Tests for PUT /scene/{id}/geospatial-glbs/{layer_id} endpoint."""

  def setUp(self):
    """Create superuser, geospatial scene and one stored GLB layer."""
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
    self.scene.save()
    self.layer = _store_layer(self.scene, {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    })
    self.client.force_login(self.user)

  def test_put_glb_updates_anchor(self):
    """D4: PUT with new anchor updates the layer anchor."""
    response = self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}})

    self.assertEqual(response.status_code, 200)
    self.layer.refresh_from_db()
    self.assertAlmostEqual(self.layer.anchor['lat'], 37.40, places=5)

  def test_put_glb_invalid_enabled_returns_400(self):
    """D6: PUT with non-bool or null enabled returns 400."""
    for value in ('yes', 'false', None):
      with self.subTest(enabled=value):
        response = self.client.put(
          self._layer_url(),
          data=json.dumps({'enabled': value}),
          content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'enabled must be a boolean'})

  def test_put_empty_anchor_returns_400_and_keeps_stored_anchor(self):
    """Negative: an empty anchor object is rejected instead of being ignored."""
    anchor_before = self.layer.anchor

    response = self._put({'anchor': {}})

    self.assertEqual(response.status_code, 400)
    self.layer.refresh_from_db()
    self.assertEqual(self.layer.anchor, anchor_before)

  def test_put_anchor_boundaries(self):
    """Boundary: longitude at +/-180, the 50 km placement limit and the antimeridian, each with its status."""
    cases = [
      ('lng -180 accepted', 37.40, -180.0, 37.40, -180.0, 200),
      ('lng 180 accepted', 37.40, 180.0, 37.40, 180.0, 200),
      ('49 km accepted', 37.38, -121.96, 37.38 + 49.0 / 111.195, -121.96, 200),
      ('51 km rejected', 37.38, -121.96, 37.38 + 51.0 / 111.195, -121.96, 400),
      ('antimeridian short way', 37.40, 179.9, 37.40, -179.9, 200),
      ('lng past 180 rejected', 37.38, -121.96, 37.40, 180.5, 400),
    ]
    for label, center_lat, center_lng, lat, lng, status in cases:
      with self.subTest(case=label):
        Scene.objects.filter(pk=self.scene.pk).update(map_center_lat=center_lat, map_center_lng=center_lng)
        anchor_before = GlbLayer.objects.get(pk=self.layer.pk).anchor

        response = self._put({'anchor': {'lat': lat, 'lng': lng, 'heading_deg': 0.0}})

        self.assertEqual(response.status_code, status)
        self.layer.refresh_from_db()
        if status == 200:
          self.assertEqual(self.layer.anchor['lng'], lng)
        else:
          self.assertEqual(self.layer.anchor, anchor_before)

  def test_put_enabled_true_returns_applied_scene_fields(self):
    """D4: PUT enabled=true places the layer and returns the pose and corners it wrote."""
    pre_apply_corners = self.scene.map_corners_lla
    self._set_snapshot_map()

    response = self._put({'enabled': True})

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    fields = response.json()['scene_fields']
    self.assertEqual(fields, glb_state.scene_form_fields(self.scene))
    self.assertEqual(fields['map_corners_lla'], self.scene.map_corners_lla)
    self.assertNotEqual(fields['map_corners_lla'], pre_apply_corners)

  def test_put_enabled_false_returns_base_scene_fields(self):
    """D4: PUT enabled=false takes the layer off and returns the snapshot frame with the pose cleared."""
    pre_apply_corners = self.scene.map_corners_lla
    self._set_snapshot_map()
    self.assertEqual(self._put({'enabled': True}).status_code, 200)

    response = self._put({'enabled': False})

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.use_glb_map)
    fields = response.json()['scene_fields']
    self.assertEqual(fields, glb_state.scene_form_fields(self.scene))
    self.assertEqual(fields['map_corners_lla'], pre_apply_corners)
    for name in POSE_FIELDS:
      self.assertEqual(fields[name], 0.0, name)

  def test_put_anchor_while_applied_returns_moved_scene_fields(self):
    """D4: moving a placed layer returns the recomputed pose and corners."""
    self._set_snapshot_map()
    applied = self._put({'enabled': True}).json()['scene_fields']

    response = self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}})

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    fields = response.json()['scene_fields']
    self.assertEqual(fields, glb_state.scene_form_fields(self.scene))
    self.assertEqual(fields['map_corners_lla'], self.scene.map_corners_lla)
    self.assertNotEqual(fields['map_corners_lla'], applied['map_corners_lla'])

  def test_put_anchor_and_enable_with_missing_frame_rolls_back(self):
    """A move followed by a failed placement rolls back together: the stored anchor and map are kept."""
    self._set_snapshot_map()
    anchor_before = self.layer.anchor
    Scene.objects.filter(pk=self.scene.pk).update(map_corners_lla=None, base_map_corners_lla=None)

    response = self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}, 'enabled': True})

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json(), {'error': 'Cannot compute pose: missing frame'})
    self.layer.refresh_from_db()
    self.assertEqual(self.layer.anchor, anchor_before)
    self.assertFalse(self.layer.enabled)
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.use_glb_map)


class TestGeospatialGlbUnappliedPreview(_GlbApplyHelpers, TransactionTestCase):
  """Unapplied preview contract: GET is read-only, write paths render and cache the preview."""

  RENDER = (np.zeros((8, 8, 3), dtype=np.uint8), 5.0, [0.0, 0.0])

  def setUp(self):
    """Create superuser and scene with a stored GLB layer that has no preview yet."""
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
    self.scene.save()
    self.layer = _store_layer(self.scene, {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    })
    self.preview_path = glb_preview_name(self.layer.file.path)
    self.client.force_login(self.user)

  def _get(self):
    return self.client.get(reverse('geospatial_glbs', kwargs={'scene_uid': self.scene.id}))

  def test_get_does_not_render_or_write_preview(self):
    """GET renders nothing, writes no file and returns preview_url null when no preview is cached."""
    with patch.object(glb_staging, 'generateOrthoView') as render:
      response = self._get()

    self.assertEqual(response.status_code, 200)
    render.assert_not_called()
    self.assertIsNone(response.json()['layers'][0]['preview_url'])
    self.assertFalse(os.path.exists(self.preview_path))

  def test_unapply_renders_preview_on_write_path(self):
    """Taking the layer off renders the unapplied preview once with alignment rotation and returns its URL."""
    self._set_snapshot_map()
    with patch.object(glb_staging, 'generateOrthoView', return_value=self.RENDER) as render:
      self.assertEqual(self._put({'enabled': True}).status_code, 200)
      response = self._put({'enabled': False})

    self.assertEqual(response.status_code, 200)
    render.assert_called_once()
    self.assertEqual(render.call_args.args[0].rotation_x, glb_staging.ALIGN_ROTATION_X)
    self.assertTrue(os.path.exists(self.preview_path))
    self.assertTrue(response.json()['preview_url'].endswith(os.path.basename(self.preview_path)))

  @pytest.mark.real_glb_render
  def test_real_render_writes_valid_preview_png(self):
    """Unapplying with the real renderer caches a non-empty PNG preview."""
    self._set_snapshot_map()
    self.assertEqual(self._put({'enabled': True}).status_code, 200)

    response = self._put({'enabled': False})

    self.assertEqual(response.status_code, 200)
    self.assertTrue(os.path.exists(self.preview_path))
    with Image.open(self.preview_path) as img:
      self.assertEqual(img.format, 'PNG')
      self.assertGreater(img.size[0], 0)
      self.assertGreater(img.size[1], 0)

  def test_failed_render_is_retried_on_next_write_not_on_get(self):
    """A failed preview render is logged and returns null; GET does not retry it, the next write does."""
    with patch.object(glb_staging, 'generateOrthoView', side_effect=RuntimeError('boom')) as render:
      first = self._put({'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0.0}})
      self.assertEqual(first.status_code, 200)
      self.assertIsNone(first.json()['preview_url'])
      self.assertEqual(render.call_count, 1)

      self._get()
      self.assertEqual(render.call_count, 1)

      self._put({'anchor': {'lat': 37.40, 'lng': -121.95, 'heading_deg': 0.0}})
      self.assertEqual(render.call_count, 2)


class TestSceneFormFields(SimpleTestCase):
  """Unit tests for glb_state.scene_form_fields."""

  def test_returns_only_glb_form_fields_with_scene_values(self):
    """The form payload carries the pose, scale and corners and nothing else."""
    scene = SimpleNamespace(
      name='ignored', use_glb_map=True, scale=2.5,
      rotation_x=90.0, rotation_y=1.0, rotation_z=2.0,
      translation_x=3.0, translation_y=4.0, translation_z=5.0,
      map_corners_lla=[[37.0, -122.0, 0.0]],
    )

    fields = glb_state.scene_form_fields(scene)

    self.assertEqual(set(fields), set(glb_state.SCENE_FORM_GLB_FIELDS))
    self.assertEqual(fields, {
      'scale': 2.5,
      'rotation_x': 90.0, 'rotation_y': 1.0, 'rotation_z': 2.0,
      'translation_x': 3.0, 'translation_y': 4.0, 'translation_z': 5.0,
      'map_corners_lla': [[37.0, -122.0, 0.0]],
    })


class TestGeospatialGlbApiDeleteEndpoint(_GlbApplyHelpers, TransactionTestCase):
  """Tests for DELETE /scene/{id}/geospatial-glb endpoint."""

  def setUp(self):
    """Create superuser, geospatial scene and one stored GLB layer."""
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
    self.scene.save()
    self.layer = _store_layer(self.scene, {
      'lat': 37.38,
      'lng': -121.96,
      'heading_deg': 0.0,
      'footprint_m': {'width': 10.0, 'height': 10.0}
    })
    self.client.force_login(self.user)

  def test_delete_glb_removes_stored_glb(self):
    """D5: DELETE removes the stored layer and its row."""
    layer_pk = self.layer.pk
    with patch('manager.models.sendUpdateCommand'):
      response = self.client.delete(self._layer_url())

    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()['success'])
    self.assertFalse(GlbLayer.objects.filter(pk=layer_pk).exists())

  def test_delete_applied_glb_returns_unapplied_scene_fields(self):
    """D5: DELETE of an applied GLB unapplies it and returns the restored scene fields."""
    pre_apply_corners = self.scene.map_corners_lla
    self._set_snapshot_map()
    self.assertEqual(self._put({'enabled': True}).status_code, 200)

    with patch('manager.models.sendUpdateCommand'):
      response = self.client.delete(self._layer_url())

    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertTrue(data['success'])
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.use_glb_map)
    self.assertEqual(data['scene_fields'], glb_state.scene_form_fields(self.scene))
    self.assertEqual(data['scene_fields']['map_corners_lla'], pre_apply_corners)
    for name in POSE_FIELDS:
      self.assertEqual(data['scene_fields'][name], 0.0, name)

  def test_delete_unapplied_glb_returns_unchanged_scene_fields(self):
    """D5: DELETE of a stored but unapplied GLB returns the scene's pose and corners untouched."""
    self.scene.translation_x = 3.5
    self.scene.rotation_z = 45.0
    self.scene.save()
    expected = glb_state.scene_form_fields(self.scene)

    with patch('manager.models.sendUpdateCommand'):
      response = self.client.delete(self._layer_url())

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertEqual(response.json()['scene_fields'], expected)
    self.assertEqual(response.json()['scene_fields'], glb_state.scene_form_fields(self.scene))
    self.assertEqual(response.json()['scene_fields']['translation_x'], 3.5)
    self.assertEqual(response.json()['scene_fields']['rotation_z'], 45.0)

  def test_delete_glb_unauthenticated_returns_403(self):
    """D7: DELETE without authentication returns 403."""
    self.client.logout()
    response = self.client.delete(self._layer_url())

    self.assertEqual(response.status_code, 403)


class TestGeospatialGlbDownload(TestCase):
  """Tests for GLB download endpoint."""

  def setUp(self):
    """Create superuser and scene with one stored GLB layer."""
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
    self.layer = _store_layer(self.scene, {'lat': 37.38, 'lng': -121.96, 'heading_deg': 0.0})
    self.client.force_login(self.user)

  def _download_url(self, layer_id=None):
    return reverse('geospatial_glb_layer_download', kwargs={
      'scene_uid': self.scene.id,
      'layer_id': layer_id or self.layer.id,
    })

  def test_download_glb_returns_file_with_attachment_header(self):
    """D8: Download returns file with Content-Disposition: attachment."""
    response = self.client.get(self._download_url())

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response['Content-Type'], 'model/gltf-binary')
    self.assertIn('attachment', response['Content-Disposition'])

  def test_download_glb_filename_sanitized(self):
    """D8: Download filename is sanitised (no CR/LF/quotes/path separators)."""
    layer = _store_layer(self.scene, {'lat': 37.38, 'lng': -121.96, 'heading_deg': 0.0}, name='safe_name.glb')

    response = self.client.get(self._download_url(layer_id=layer.id))

    self.assertEqual(response.status_code, 200)
    disposition = response['Content-Disposition']
    self.assertNotIn('\n', disposition)
    self.assertNotIn('\r', disposition)
    filename = disposition.split('filename=', 1)[-1].strip('"')
    self.assertNotIn('"', filename)
    self.assertNotIn('/', filename)

  def test_download_glb_no_glb_returns_404(self):
    """D8: Download with no GLB stored returns 404."""
    response = self.client.get(self._download_url(layer_id=uuid.uuid4()))

    self.assertEqual(response.status_code, 404)

  def test_download_glb_unauthenticated_redirects_to_login(self):
    """D8: Download without authentication redirects to login (302)."""
    self.client.logout()
    response = self.client.get(self._download_url())

    self.assertEqual(response.status_code, 302)
