#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for GeospatialGlbPreview and GeospatialGlb endpoints: staging, preview, commit."""

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User

import numpy as np

from manager import glb_alignment
from manager.models import Scene, Region, RegionPoint, SingletonSensor


TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"


class TestGeospatialGlbPreview(TestCase):
  """Verifies the geospatial-glb-preview endpoint: auth, validation, staging, preview."""

  def setUp(self):
    """Create superuser, scene, mock rendering."""
    self.user = User.objects.create_superuser("test_user", "test@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="test_scene", map_type="geospatial_map",
      map_center_lat=37.38689, map_center_lng=-121.96411,
    )
    self.temp_dir = tempfile.TemporaryDirectory()
    self.staging_dir = os.path.join(self.temp_dir.name, "glb_staging")
    os.makedirs(self.staging_dir, exist_ok=True)
    override = override_settings(MEDIA_ROOT=self.temp_dir.name)
    override.enable()
    self.addCleanup(override.disable)
    self.addCleanup(self.temp_dir.cleanup)
    render_patch = patch.object(
      glb_alignment, "generateOrthoView",
      return_value=(np.zeros((8, 8, 3), dtype=np.uint8), 5.0)
    )
    self.render_mock = render_patch.start()
    self.addCleanup(render_patch.stop)

  def _read_test_glb(self):
    with open(TEST_GLB_FILE, "rb") as f:
      return f.read()

  def _upload_glb(self, scene_uid, file_data=None, filename="test.glb"):
    if file_data is None:
      file_data = self._read_test_glb()
    upload = SimpleUploadedFile(filename, file_data)
    return self.client.post(
      reverse("geospatial_glb_preview", kwargs={"scene_uid": scene_uid}),
      {"file": upload}, follow=False,
    )

  def test_superuser_upload_returns_200_with_token_and_metadata(self):
    """Superuser upload returns 200 with token, preview_url, footprint, anchor, px_per_m."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertIn("token", result)
    self.assertIn("preview_url", result)
    self.assertIn("footprint_m", result)
    self.assertIn("anchor", result)
    self.assertIn("px_per_m", result)
    self.assertIn("existing_content", result)
    self.assertIn(f"{result['token']}.png", result["preview_url"])
    self.assertGreater(result["footprint_m"]["width"], 0)
    self.assertGreater(result["footprint_m"]["height"], 0)
    self.assertAlmostEqual(result["anchor"]["lat"], self.scene.map_center_lat, places=5)
    self.assertAlmostEqual(result["anchor"]["lng"], self.scene.map_center_lng, places=5)
    self.assertEqual(result["anchor"]["heading_deg"], 0.0)
    self.assertGreater(result["px_per_m"], 0)
    glb_path = os.path.join(self.staging_dir, f"{result['token']}.glb")
    png_path = os.path.join(self.staging_dir, f"{result['token']}.png")
    self.assertTrue(os.path.exists(glb_path))
    self.assertTrue(os.path.exists(png_path))

  def test_uploaded_filename_is_server_token_not_client_name(self):
    """Uploaded file with malicious name saved as <uuid>.glb only."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id, filename="../evil.glb")
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    token = result["token"]
    glb_files = [f for f in os.listdir(self.staging_dir) if f.endswith(".glb")]
    self.assertEqual(len(glb_files), 1)
    self.assertEqual(glb_files[0], f"{token}.glb")

  def test_anonymous_request_is_rejected_with_403(self):
    """Unauthenticated requests receive 403 Forbidden."""
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 403)

  def test_non_superuser_request_is_rejected_with_403(self):
    """Logged-in non-superuser receives 403 Forbidden."""
    User.objects.create_user("regular", "regular@intel.com", "pass")
    self.client.post(reverse("sign_in"), data={"username": "regular", "password": "pass"})
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 403)

  def test_unknown_scene_uuid_returns_404(self):
    """Request for non-existent scene returns 404 Not Found."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb("00000000-0000-0000-0000-000000000000")
    self.assertEqual(response.status_code, 404)

  def test_scene_with_non_geospatial_map_type_returns_400(self):
    """Scene with map_type != 'geospatial_map' returns 400 Bad Request."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    non_geo_scene = Scene.objects.create(name="non_geo", map_type="other")
    response = self._upload_glb(non_geo_scene.id)
    self.assertEqual(response.status_code, 400)
    self.assertIn("geospatial_map", json.loads(response.content)["error"])

  def test_scene_without_map_center_returns_400(self):
    """Scene without map_center_lat/lng returns 400 Bad Request."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    no_center = Scene.objects.create(name="no_center", map_type="geospatial_map")
    response = self._upload_glb(no_center.id)
    self.assertEqual(response.status_code, 400)
    self.assertIn("centre", json.loads(response.content)["error"].lower())

  def test_missing_file_field_returns_400(self):
    """Request without 'file' field returns 400 Bad Request."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self.client.post(
      reverse("geospatial_glb_preview", kwargs={"scene_uid": self.scene.id}),
      {}, follow=False,
    )
    self.assertEqual(response.status_code, 400)

  def test_non_glb_extension_returns_400(self):
    """File with non-.glb extension returns 400 Bad Request."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id, filename="test.obj")
    self.assertEqual(response.status_code, 400)

  def test_garbage_bytes_returns_400_and_no_staged_files(self):
    """Invalid GLB data returns 400 and leaves no staged files."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id, file_data=b"garbage")
    self.assertEqual(response.status_code, 400)
    self.assertEqual(len(os.listdir(self.staging_dir)), 0)

  def test_oversized_file_returns_413(self):
    """GLB exceeding MAX_GLB_BYTES returns 413 Payload Too Large."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    with patch.object(glb_alignment, "MAX_GLB_BYTES", 10):
      response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 413)

  def test_existing_content_counts_with_region(self):
    """existing_content reflects scene Regions."""
    region = Region.objects.create(scene=self.scene, name="test", roi_type="test")
    RegionPoint.objects.create(region=region, x=0, y=0, sequence=0)
    RegionPoint.objects.create(region=region, x=1, y=0, sequence=1)
    RegionPoint.objects.create(region=region, x=1, y=1, sequence=2)
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(json.loads(response.content)["existing_content"]["regions"], 1)

  def test_existing_content_counts_sensors(self):
    """existing_content includes count of Sensors."""
    SingletonSensor.objects.create(scene=self.scene, name="sensor", sensor_id="s1")
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 200)
    result = json.loads(response.content)
    self.assertEqual(result["existing_content"]["sensors"], 1)
    self.assertEqual(result["existing_content"]["cameras"], 0)

  def test_stale_files_are_purged_before_new_upload(self):
    """Stale files (>24h old) are removed; fresh files kept."""
    stale_glb = os.path.join(self.staging_dir, "stale.glb")
    stale_png = os.path.join(self.staging_dir, "stale.png")
    fresh_glb = os.path.join(self.staging_dir, "fresh.glb")
    with open(stale_glb, "wb") as f:
      f.write(b"stale")
    with open(stale_png, "wb") as f:
      f.write(b"stale")
    with open(fresh_glb, "wb") as f:
      f.write(b"fresh")
    stale_time = time.time() - (25 * 3600)
    os.utime(stale_glb, (stale_time, stale_time))
    os.utime(stale_png, (stale_time, stale_time))
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 200)
    self.assertFalse(os.path.exists(stale_glb))
    self.assertFalse(os.path.exists(stale_png))
    self.assertTrue(os.path.exists(fresh_glb))

  def test_render_error_returns_500_and_cleans_up_staged_files(self):
    """Build_preview error returns 500 and removes staged files."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    self.render_mock.side_effect = RuntimeError("Render failed")
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 500)
    self.assertIn("error", json.loads(response.content))
    self.assertEqual(len(os.listdir(self.staging_dir)), 0)


class TestStageGlbWriteFailure(TestCase):
  """stage_glb cleans up a partially written GLB when the write fails."""

  def setUp(self):
    """Point MEDIA_ROOT at a temp dir so staging writes stay isolated."""
    temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(temp_dir.cleanup)
    override = override_settings(MEDIA_ROOT=temp_dir.name)
    override.enable()
    self.addCleanup(override.disable)
    os.makedirs(glb_alignment.staging_dir(), exist_ok=True)

  def test_write_failure_removes_partial_file_and_reraises(self):
    """OSError mid-write re-raises and leaves no partial GLB in staging."""
    upload = Mock(size=7)

    def failing_chunks():
      yield b"partial"
      raise OSError("disk full")

    upload.chunks.side_effect = failing_chunks
    with patch.object(glb_alignment, "validate_glb"):
      with self.assertRaises(OSError):
        glb_alignment.stage_glb(upload)
    self.assertEqual(os.listdir(glb_alignment.staging_dir()), [])


class CommitBaseSetup(TestCase):
  """Base for GeospatialGlbCommit tests; patches generateOrthoView and sendUpdateCommand."""

  def setUp(self):
    """Superuser, geospatial scene, temp media, real file ops, mocked render+mqtt."""
    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.scene = Scene.objects.create(
      name="geo_scene", map_type="geospatial_map",
      map_center_lat=37.38689, map_center_lng=-121.96411, output_lla=True
    )
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.media_root = self.temp_dir.name
    self.staging_dir = os.path.join(self.media_root, glb_alignment.STAGING_SUBDIR)
    os.makedirs(self.staging_dir, exist_ok=True)
    override = override_settings(MEDIA_ROOT=self.media_root)
    override.enable()
    self.addCleanup(override.disable)

    # Patch generateOrthoView to avoid renderer segfault; Scene.save() calls saveThumbnail()
    from manager import models as models_module
    render_patch = patch.object(
      models_module, "generateOrthoView",
      return_value=(np.zeros((8, 8, 3), dtype=np.uint8), 5.0)
    )
    self.render_mock = render_patch.start()
    self.addCleanup(render_patch.stop)

    # Patch sendUpdateCommand (MQTT); captured via captureOnCommitCallbacks
    mqtt_patch = patch.object(models_module, "sendUpdateCommand")
    self.mqtt_mock = mqtt_patch.start()
    self.addCleanup(mqtt_patch.stop)

    self.client.force_login(self.user)

  def _read_test_glb(self):
    with open(TEST_GLB_FILE, 'rb') as f:
      return f.read()

  def _stage_glb(self):
    """Copy test.glb to staging; return token."""
    token = str(uuid.uuid4())
    path = os.path.join(self.staging_dir, f'{token}.glb')
    with open(path, 'wb') as f:
      f.write(self._read_test_glb())
    return token

  def _create_old_map(self):
    """Create a small real PNG and set scene.map to it; return filename."""
    png = np.zeros((8, 8, 3), dtype=np.uint8)
    from PIL import Image
    img = Image.fromarray(png)
    fn = "old_map.png"
    path = os.path.join(self.media_root, fn)
    img.save(path, format='PNG')
    Scene.objects.filter(pk=self.scene.pk).update(map=fn)
    self.scene.refresh_from_db()
    return fn


class TestGeospatialGlbCommit(CommitBaseSetup):
  """Tests for POST/GET geospatial-glb endpoint: commit and read-back."""

  def test_commit_success_replaces_map_sets_corners_clears_cache(self):
    """POST with valid token, anchor -> 200; map is .glb, corners set, cache cleared."""
    old_map_fn = self._create_old_map()
    token = self._stage_glb()
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0}
    body = {'token': token, 'anchor': anchor, 'acknowledge_frame_change': False}

    # Scene should have no content (cameras/regions/sensors)
    self.scene.trs_matrix = 'dummy'  # Set to non-None to verify it's cleared
    self.scene.osm_ways_cache = {'x': 1}
    self.scene.osm_ways_cache_bbox = [0, 1, 2, 3]
    self.scene.save()

    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.assertEqual(resp.status_code, 200)
    result = json.loads(resp.content)
    self.assertIn('anchor', result)
    self.assertIn('footprint_m', result)
    self.assertIn('preview_url', result)

    self.scene.refresh_from_db()
    self.assertTrue(self.scene.map.name.endswith('.glb'))
    self.assertTrue(os.path.exists(self.scene.map.path))
    self.assertIsNotNone(self.scene.map_corners_lla)
    self.assertEqual(len(self.scene.map_corners_lla), 4)
    self.assertIsNone(self.scene.trs_matrix)
    self.assertIsNone(self.scene.osm_ways_cache)
    self.assertIsNone(self.scene.osm_ways_cache_bbox)
    self.assertEqual(self.scene.rotation_x, 90.0)

    # Staged file removed, old map deleted
    self.assertFalse(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))
    self.assertFalse(os.path.exists(os.path.join(self.media_root, old_map_fn)))

    # sendUpdateCommand scheduled
    self.mqtt_mock.assert_called_with(scene_id=self.scene.id)

  def test_commit_anchor_round_trips_with_tolerance(self):
    """GET after commit returns anchor matching posted within 1e-6 deg / 0.01 deg heading."""
    token = self._stage_glb()
    posted_lat, posted_lng, posted_hdg = 37.38689, -121.96411, 370.0
    body = {
      'token': token,
      'anchor': {'lat': posted_lat, 'lng': posted_lng, 'heading_deg': posted_hdg},
      'acknowledge_frame_change': False
    }

    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
    self.assertEqual(resp.status_code, 200)

    resp2 = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(resp2.status_code, 200)
    result = json.loads(resp2.content)

    self.assertAlmostEqual(result['anchor']['lat'], posted_lat, places=6)
    self.assertAlmostEqual(result['anchor']['lng'], posted_lng, places=6)
    # heading normalized: 370 % 360 = 10
    self.assertAlmostEqual(result['anchor']['heading_deg'], 10.0, places=2)

  def test_get_on_png_map_returns_404(self):
    """GET on scene with PNG map returns 404."""
    self._create_old_map()
    resp = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(resp.status_code, 404)

  def test_get_unknown_uuid_returns_404(self):
    """GET for non-existent scene returns 404."""
    resp = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': '00000000-0000-0000-0000-000000000000'})
    )
    self.assertEqual(resp.status_code, 404)

  def test_get_non_geospatial_scene_returns_400(self):
    """GET on non-geospatial scene returns 400."""
    non_geo = Scene.objects.create(name='non_geo', map_type='other')
    resp = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': non_geo.id})
    )
    self.assertEqual(resp.status_code, 400)

  def test_get_anonymous_returns_403(self):
    """GET by anonymous user returns 403."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}, 'acknowledge_frame_change': False}
    with self.captureOnCommitCallbacks(execute=True):
      self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.client.logout()
    resp = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(resp.status_code, 403)

  def test_get_non_superuser_allowed_read_only(self):
    """GET by logged-in non-superuser returns 200 (IsAdminOrReadOnly permits read)."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}, 'acknowledge_frame_change': False}
    with self.captureOnCommitCallbacks(execute=True):
      self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    regular_user = User.objects.create_user('regular', 'reg@intel.com', 'pass')
    self.client.force_login(regular_user)
    resp = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(resp.status_code, 200)

  def test_post_anonymous_returns_403(self):
    """POST by anonymous user returns 403."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    self.client.logout()
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 403)

  def test_post_non_superuser_returns_403(self):
    """POST by non-superuser returns 403."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    regular_user = User.objects.create_user('regular', 'reg@intel.com', 'pass')
    self.client.force_login(regular_user)
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 403)

  def test_commit_with_region_ack_missing_returns_409(self):
    """POST with region but acknowledge_frame_change missing/false returns 409; scene unchanged."""
    self._create_old_map()
    region = Region.objects.create(scene=self.scene, name='test', roi_type='test')
    RegionPoint.objects.create(region=region, x=0, y=0, sequence=0)
    RegionPoint.objects.create(region=region, x=1, y=0, sequence=1)
    RegionPoint.objects.create(region=region, x=1, y=1, sequence=2)

    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}, 'acknowledge_frame_change': False}

    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 409)

    self.scene.refresh_from_db()
    self.assertTrue(self.scene.map.name.endswith('.png'))
    self.assertTrue(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))
    self.mqtt_mock.assert_not_called()

  def test_commit_with_sensor_ack_true_succeeds(self):
    """POST with sensor but acknowledge_frame_change=true succeeds; sensor present but frame updated."""
    SingletonSensor.objects.create(scene=self.scene, name='s1', sensor_id='s1')
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}, 'acknowledge_frame_change': True}

    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.map.name.endswith('.glb'))

  def test_ack_non_bool_returns_400(self):
    """POST with acknowledge_frame_change as string/int/null returns 400."""
    token = self._stage_glb()

    for bad_ack in ['yes', 1, None]:
      body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}, 'acknowledge_frame_change': bad_ack}
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
      self.assertEqual(resp.status_code, 400, f"Expected 400 for ack={bad_ack}")

  def test_token_path_traversal_returns_400(self):
    """POST with token='../../etc/passwd' returns 400."""
    body = {'token': '../../etc/passwd', 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_token_absolute_path_returns_400(self):
    """POST with token='/etc/passwd' returns 400."""
    body = {'token': '/etc/passwd', 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_token_not_uuid_returns_400(self):
    """POST with token='not-a-uuid' returns 400."""
    body = {'token': 'not-a-uuid', 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_token_non_string_returns_400(self):
    """POST with token=123/null/[]/dict returns 400."""
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}
    for bad_token in [123, None, [], {}]:
      body = {'token': bad_token, 'anchor': anchor}
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
      self.assertEqual(resp.status_code, 400, f"Expected 400 for token={bad_token}")

  def test_token_valid_uuid_no_file_returns_404(self):
    """POST with valid UUID but no staged file returns 404."""
    body = {
      'token': str(uuid.uuid4()),
      'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}
    }
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 404)

  def test_anchor_missing_returns_400(self):
    """POST without anchor key returns 400."""
    token = self._stage_glb()
    body = {'token': token}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_anchor_not_dict_returns_400(self):
    """POST with anchor=[] / string / null returns 400."""
    token = self._stage_glb()
    for bad_anchor in [[], 'point', None, 123]:
      body = {'token': token, 'anchor': bad_anchor}
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
      self.assertEqual(resp.status_code, 400, f"Expected 400 for anchor={bad_anchor}")

  def test_anchor_lat_91_returns_400(self):
    """POST with anchor.lat=91 returns 400."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 91, 'lng': 0, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_anchor_lat_minus_91_returns_400(self):
    """POST with anchor.lat=-91 returns 400."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': -91, 'lng': 0, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_anchor_lng_181_returns_400(self):
    """POST with anchor.lng=181 returns 400."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37, 'lng': 181, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_anchor_values_as_strings_returns_400(self):
    """POST with anchor.lat/lng/heading_deg as strings returns 400."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': '37', 'lng': '-121', 'heading_deg': '0'}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_anchor_with_nan_returns_400(self):
    """POST with anchor containing NaN returns 400 (DRF JSON parser rejects it)."""
    token = self._stage_glb()
    # Python's json.dumps(float('nan')) emits NaN; DRF may reject it
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=f'{{"token": "{token}", "anchor": {{"lat": NaN, "lng": -121, "heading_deg": 0}}}}',
      content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_post_non_geospatial_scene_returns_400(self):
    """POST to non-geospatial scene returns 400."""
    non_geo = Scene.objects.create(name='non_geo', map_type='other')
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': non_geo.id}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_post_unknown_scene_returns_404(self):
    """POST to non-existent scene returns 404."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': '00000000-0000-0000-0000-000000000000'}),
      data=json.dumps(body), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 404)

  def test_post_body_not_json_object_returns_400(self):
    """POST with body as JSON list returns 400."""
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps([]), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_atomicity_failure_leaves_no_new_file_original_intact(self):
    """POST where localFootprintCornersLLA fails: 500, new map removed, old map kept."""
    old_map_fn = self._create_old_map()
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}

    with patch.object(
      glb_alignment, 'localFootprintCornersLLA',
      side_effect=RuntimeError('Alignment failed')
    ):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.assertEqual(resp.status_code, 500)

    self.scene.refresh_from_db()
    self.assertTrue(self.scene.map.name.endswith('.png'))
    self.assertIsNone(self.scene.map_corners_lla)

    # Only old map and glb_staging dir in MEDIA_ROOT
    media_files = os.listdir(self.media_root)
    self.assertIn('glb_staging', media_files)
    self.assertIn(old_map_fn, media_files)
    self.assertTrue(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))

    self.mqtt_mock.assert_not_called()

  def test_atomicity_failure_no_previous_map_leaves_no_leaked_file(self):
    """POST on scene with no map fails: 500; MEDIA_ROOT has only glb_staging, no leaked .glb."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}

    with patch.object(
      glb_alignment, 'localFootprintCornersLLA',
      side_effect=RuntimeError('Alignment failed')
    ):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.assertEqual(resp.status_code, 500)

    # Only glb_staging should exist; no loose .glb files
    media_files = os.listdir(self.media_root)
    self.assertEqual(media_files, ['glb_staging'])
    self.assertTrue(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))

  def test_commit_success_no_previous_map(self):
    """POST on scene with no previous map -> 200; new map set, corners set, staged file removed."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}

    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.map.name.endswith('.glb'))
    self.assertIsNotNone(self.scene.map_corners_lla)
    self.assertFalse(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))
    self.mqtt_mock.assert_called_with(scene_id=self.scene.id)


