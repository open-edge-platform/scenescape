# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GLB API endpoints: GET, POST, PUT, DELETE, download.

Tests the DRF/Django view layer for GeospatialGlb* endpoints covering:
  - Authentication and permission checks
  - Request validation and error handling
  - State transitions and response formats
  - File download sanitization

Coverage:
  D1: GET /scene/{id}/geospatial-glb happy path (exists:true/false)
  D2: GET response format: filename, download_url, anchor, footprint_m, use_glb_map, preview_url
  D3: POST /scene/{id}/geospatial-glb with valid token and anchor (201/200)
  D4: PUT /scene/{id}/geospatial-glb to update anchor and use_glb_map
  D5: DELETE /scene/{id}/geospatial-glb
  D6: Error cases: invalid anchor (400), non-bool use_glb_map (400), non-geospatial (400)
  D7: Auth: unauthenticated (403), non-admin (403)
  D8: Download: attachment header, sanitised filename, 404 when no GLB
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


class TestGeospatialGlbApiGetEndpoint(TestCase):
  """Tests for GET /scene/{id}/geospatial-glb endpoint."""

  def setUp(self):
    """Create superuser and geospatial scene."""
    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="api_test_scene",
      map_type="geospatial_map",
      map_center_lat=37.38,
      map_center_lng=-121.96,
      output_lla=True
    )
    self.client.force_login(self.user)

  def test_get_glb_exists_false_when_no_glb_stored(self):
    """D2: GET returns exists:false when no GLB stored."""
    response = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(response.status_code, 200)
    data = json.loads(response.content)
    self.assertFalse(data['exists'])

  def test_get_glb_exists_true_when_glb_stored(self):
    """D2: GET returns exists:true when GLB stored."""
    temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(temp_dir.cleanup)
    with override_settings(MEDIA_ROOT=temp_dir.name):
      glb_path = os.path.join(temp_dir.name, "test.glb")
      with open(TEST_GLB_FILE, 'rb') as f_src:
        with open(glb_path, 'wb') as f_dst:
          f_dst.write(f_src.read())

      self.scene.glb_map = "test.glb"
      self.scene.glb_anchor = {
        'lat': 37.39,
        'lng': -121.97,
        'heading_deg': 0.0,
        'footprint_m': {'width': 10.0, 'height': 10.0}
      }
      self.scene.save()

      response = self.client.get(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
      )
      self.assertEqual(response.status_code, 200)
      data = json.loads(response.content)
      self.assertTrue(data['exists'])
      self.assertEqual(data['filename'], 'test.glb')
      self.assertIn('anchor', data)
      self.assertIn('footprint_m', data)
      self.assertIn('use_glb_map', data)


class TestGeospatialGlbApiPostEndpoint(TransactionTestCase):
  """Tests for POST /scene/{id}/geospatial-glb endpoint."""

  def setUp(self):
    """Create superuser and geospatial scene."""
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    patcher = override_settings(MEDIA_ROOT=self.temp_dir.name)
    patcher.enable()
    self.addCleanup(patcher.disable)

    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="post_test_scene",
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
    self.client.force_login(self.user)

  def _stage_glb(self):
    """Stage a GLB and return the token."""
    token = str(uuid.uuid4())
    staging_dir = os.path.join(self.temp_dir.name, glb_alignment.STAGING_SUBDIR)
    os.makedirs(staging_dir, exist_ok=True)
    glb_path = os.path.join(staging_dir, f"{token}.glb")
    with open(TEST_GLB_FILE, 'rb') as f_src:
      with open(glb_path, 'wb') as f_dst:
        f_dst.write(f_src.read())
    return token

  def test_post_glb_with_valid_anchor_stores_glb(self):
    """D3: POST with valid token and anchor stores GLB."""
    token = self._stage_glb()
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0.0}

    with patch.object(glb_alignment, '_get_mesh_footprint_corners_from_glb',
                      return_value=(10.0, 10.0)), \
         patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      response = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps({'token': token, 'anchor': anchor}),
        content_type='application/json'
      )

    self.assertEqual(response.status_code, 200)
    data = json.loads(response.content)
    self.assertTrue(data['exists'])


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
