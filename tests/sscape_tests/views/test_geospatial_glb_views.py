#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for GeospatialGlbPreview endpoint: GLB staging, rendering, preview."""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

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
      return_value=(np.zeros((8, 8, 3)), 5.0)
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



