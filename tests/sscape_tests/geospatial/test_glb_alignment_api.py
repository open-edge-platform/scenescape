# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GLB API endpoints: GET, POST, PATCH, DELETE, download.

Tests the DRF/Django view layer for GeospatialGlb* endpoints covering:
  - Authentication and permission checks
  - Request validation and error handling
  - State transitions and response formats
  - File download sanitization

Coverage:
  D1: GET /scene/{id}/geospatial-glb happy path (exists:true/false)
  D2: GET response format: filename, download_url, anchor, footprint_m, use_glb_map, preview_url
  D3: POST /scene/{id}/geospatial-glb with valid token and anchor (201/200)
  D4: PATCH /scene/{id}/geospatial-glb to update anchor and use_glb_map
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
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from manager import glb_alignment
from manager.models import Scene
from scene_common.earth_lla import localFootprintCornersLLA

TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"


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

  def test_get_glb_unknown_scene_returns_404(self):
    """D6: GET with unknown scene returns 404."""
    response = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': '00000000-0000-0000-0000-000000000000'})
    )
    self.assertEqual(response.status_code, 404)

  def test_get_glb_non_geospatial_scene_returns_400(self):
    """D6: GET on non-geospatial scene returns 400."""
    non_geo = Scene.objects.create(name="non_geo", map_type="other")
    response = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': non_geo.id})
    )
    self.assertEqual(response.status_code, 400)

  def test_get_glb_unauthenticated_returns_403(self):
    """D7: GET without authentication returns 403."""
    self.client.logout()
    response = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(response.status_code, 403)

  def test_get_glb_non_admin_is_allowed_read_only(self):
    """D7: GET as non-admin user is allowed (read-only); writes stay admin-only."""
    User.objects.create_user("user", "user@intel.com", "pass")
    self.client.force_login(User.objects.get(username="user"))
    response = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(response.status_code, 200)


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

  def test_post_glb_invalid_anchor_returns_400(self):
    """D6: POST with invalid anchor returns 400."""
    token = self._stage_glb()
    anchor = {'lat': float('nan'), 'lng': -121.97, 'heading_deg': 0.0}

    response = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'token': token, 'anchor': anchor}),
      content_type='application/json'
    )

    self.assertEqual(response.status_code, 400)
    self.assertIn('error', json.loads(response.content))

  def test_post_glb_missing_anchor_returns_400(self):
    """D6: POST without anchor returns 400."""
    token = self._stage_glb()

    response = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'token': token}),
      content_type='application/json'
    )

    self.assertEqual(response.status_code, 400)

  def test_post_glb_unauthenticated_returns_403(self):
    """D7: POST without authentication returns 403."""
    self.client.logout()
    token = self._stage_glb()
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0.0}

    response = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'token': token, 'anchor': anchor}),
      content_type='application/json'
    )

    self.assertEqual(response.status_code, 403)


class TestGeospatialGlbApiPatchEndpoint(TransactionTestCase):
  """Tests for PATCH /scene/{id}/geospatial-glb endpoint."""

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

  def test_patch_glb_updates_anchor(self):
    """D4: PATCH with new anchor updates glb_anchor."""
    new_anchor = {'lat': 37.40, 'lng': -121.95, 'heading_deg': 45.0}

    with patch.object(Scene, 'saveThumbnail'), \
         patch('manager.models.sendUpdateCommand'):
      response = self.client.patch(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps({'anchor': new_anchor}),
        content_type='application/json'
      )

    self.assertEqual(response.status_code, 200)
    self.scene.refresh_from_db()
    self.assertAlmostEqual(self.scene.glb_anchor['lat'], 37.40, places=5)

  def test_patch_glb_invalid_use_glb_map_returns_400(self):
    """D6: PATCH with non-bool use_glb_map returns 400."""
    response = self.client.patch(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'use_glb_map': 'yes'}),
      content_type='application/json'
    )

    self.assertEqual(response.status_code, 400)


class TestGeospatialGlbApiDeleteEndpoint(TransactionTestCase):
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
