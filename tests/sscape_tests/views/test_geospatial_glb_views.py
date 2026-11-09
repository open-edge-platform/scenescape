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
from scene_common.earth_lla import localFootprintCornersLLA
from scene_common.glb_top_view import getMeshSize
from scene_common.mesh_util import extractMeshFromGLB


TEST_GLB_FILE = Path(__file__).resolve().parent.parent / "mesh_util" / "test_data" / "scene.glb"
MAP_REQUIRED_MSG = "If 'Output geospatial coordinates' is enabled then map corners LLA and map file are required."


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
    rendered_scene = self.render_mock.call_args[0][0]
    self.assertEqual(rendered_scene.rotation_x, glb_alignment.ALIGN_ROTATION_X)

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

  def test_garbage_bytes_returns_400_with_validation_message_and_no_staged_files(self):
    """Invalid GLB data returns 400 with the scene upload form's message and leaves no staged files."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id, file_data=b"garbage")
    self.assertEqual(response.status_code, 400)
    self.assertIn("(.glb)", json.loads(response.content)["error"])
    self.assertEqual(len(os.listdir(self.staging_dir)), 0)

  def test_existing_content_counts_regions_and_sensors(self):
    """existing_content reflects the scene's regions and sensors."""
    region = Region.objects.create(scene=self.scene, name="test", roi_type="test")
    for seq, (x, y) in enumerate([(0, 0), (1, 0), (1, 1)]):
      RegionPoint.objects.create(region=region, x=x, y=y, sequence=seq)
    SingletonSensor.objects.create(scene=self.scene, name="sensor", sensor_id="s1")
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(
      json.loads(response.content)["existing_content"], {"cameras": 0, "regions": 1, "sensors": 1}
    )

  def test_oversized_file_returns_413(self):
    """GLB exceeding MAX_GLB_BYTES returns 413 Payload Too Large."""
    self.client.post(reverse("sign_in"), data={"username": "test_user", "password": "pass"})
    with patch.object(glb_alignment, "MAX_GLB_BYTES", 10):
      response = self._upload_glb(self.scene.id)
    self.assertEqual(response.status_code, 413)

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

  def _set_frame(self):
    """Give the scene a 100 m frame so GLB apply can compute its pose."""
    frame = localFootprintCornersLLA(
      center_lat=37.38689, center_lng=-121.96411, heading_deg=0.0,
      width_m=100.0, height_m=100.0,
    ).tolist()
    Scene.objects.filter(pk=self.scene.pk).update(map_corners_lla=frame)
    self.scene.refresh_from_db()

  def _apply_glb(self):
    return self.client.put(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'use_glb_map': True}), content_type='application/json'
    )


class TestGeospatialGlbCommit(CommitBaseSetup):
  """Tests for POST/GET geospatial-glb endpoint: commit and read-back."""

  def test_commit_stores_glb_then_put_applies_it(self):
    """POST stores the GLB and leaves the map alone; PUT use_glb_map applies it."""
    old_map_fn = self._create_old_map()
    self._set_frame()
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0}}

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
    self.assertTrue(self.scene.glb_map.name.endswith('.glb'))
    self.assertFalse(self.scene.use_glb_map)
    self.assertTrue(self.scene.map.name.endswith('.png'))
    self.assertTrue(os.path.exists(os.path.join(self.media_root, old_map_fn)))
    self.assertFalse(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))

    # Footprint follows the X/Y extents after the ALIGN_ROTATION_X axis conversion
    mesh, _ = extractMeshFromGLB(self.scene.glb_map.path, rotation=[glb_alignment.ALIGN_ROTATION_X, 0.0, 0.0])
    extent_w, extent_h, _ = getMeshSize(mesh)
    self.assertAlmostEqual(result['footprint_m']['width'], extent_w, places=2)
    self.assertAlmostEqual(result['footprint_m']['height'], extent_h, places=2)

    with self.captureOnCommitCallbacks(execute=True):
      resp = self._apply_glb()
    self.assertEqual(resp.status_code, 200)

    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    self.assertTrue(self.scene.map.name.endswith('.glb'))
    self.assertTrue(os.path.exists(self.scene.map.path))
    self.assertEqual(len(self.scene.map_corners_lla), 4)
    self.assertTrue(self.scene.base_map.name.endswith('.png'))
    self.mqtt_mock.assert_called_with(scene_id=self.scene.id)

  def test_commit_stores_thumbnail_when_save_skips_regeneration(self):
    """Thumbnail is stored on apply even when Scene.save() skips regenerating it."""
    self._create_old_map()
    self._set_frame()
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0}}

    with self.captureOnCommitCallbacks(execute=True):
      self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
    with patch.object(Scene, "regenerateThumbnail", return_value=False):
      with self.captureOnCommitCallbacks(execute=True):
        resp = self._apply_glb()

    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.thumbnail)

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

  def test_get_on_png_map_reports_no_glb(self):
    """GET on a scene with only a PNG map returns 200 with exists=false."""
    self._create_old_map()
    resp = self.client.get(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    )
    self.assertEqual(resp.status_code, 200)
    self.assertFalse(json.loads(resp.content)['exists'])

  def test_commit_with_sensor_and_region_stores_without_map_change(self):
    """POST succeeds with existing sensors/regions and does not change the applied map."""
    old_map_fn = self._create_old_map()
    region = Region.objects.create(scene=self.scene, name='test', roi_type='test')
    RegionPoint.objects.create(region=region, x=0, y=0, sequence=0)
    RegionPoint.objects.create(region=region, x=1, y=0, sequence=1)
    RegionPoint.objects.create(region=region, x=1, y=1, sequence=2)
    SingletonSensor.objects.create(scene=self.scene, name='s1', sensor_id='s1')
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}

    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.map.name.endswith('.png'))
    self.assertEqual(self.scene.map.name, old_map_fn)
    self.assertTrue(self.scene.glb_map.name.endswith('.glb'))

  def _post_commit(self, scene_uid=None, **body):
    return self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': scene_uid or self.scene.id}),
      data=json.dumps(body), content_type='application/json'
    )

  def test_unknown_or_non_geospatial_scene_is_rejected(self):
    """GET and POST return 404 for an unknown scene and 400 for a non-geospatial one."""
    non_geo = Scene.objects.create(name='non_geo', map_type='other')
    unknown = '00000000-0000-0000-0000-000000000000'
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}
    for scene_uid, status in ((unknown, 404), (non_geo.id, 400)):
      with self.subTest(scene_uid=scene_uid, method='GET'):
        resp = self.client.get(reverse('geospatial_glb', kwargs={'scene_uid': scene_uid}))
        self.assertEqual(resp.status_code, status)
      with self.subTest(scene_uid=scene_uid, method='POST'):
        resp = self._post_commit(scene_uid, token=self._stage_glb(), anchor=anchor)
        self.assertEqual(resp.status_code, status)

  def test_get_is_read_only_for_regular_users_and_closed_to_anonymous(self):
    """GET is allowed for a logged-in non-superuser (IsAdminOrReadOnly) and refused when anonymous."""
    self.client.force_login(User.objects.create_user('regular', 'reg@intel.com', 'pass'))
    url = reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id})
    self.assertEqual(self.client.get(url).status_code, 200)
    self.client.logout()
    self.assertEqual(self.client.get(url).status_code, 403)

  def test_post_requires_superuser(self):
    """POST is refused for anonymous and non-superuser users and stores nothing."""
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}
    token = self._stage_glb()
    self.client.logout()
    resp = self._post_commit(token=token, anchor=anchor)
    self.assertEqual(resp.status_code, 403)
    self.client.force_login(User.objects.create_user('regular', 'reg@intel.com', 'pass'))
    resp = self._post_commit(token=token, anchor=anchor)
    self.assertEqual(resp.status_code, 403)
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.glb_map)

  def test_malformed_token_is_rejected(self):
    """Path-like, non-UUID and non-string tokens return 400; an unknown UUID returns 404."""
    anchor = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}
    for bad_token in ['../../etc/passwd', '/etc/passwd', 'not-a-uuid', 123, None, [], {}]:
      with self.subTest(token=bad_token):
        self.assertEqual(self._post_commit(token=bad_token, anchor=anchor).status_code, 400)
    resp = self._post_commit(token=str(uuid.uuid4()), anchor=anchor)
    self.assertEqual(resp.status_code, 404)

  def test_invalid_anchor_is_rejected(self):
    """Missing, mistyped, out-of-range and NaN anchors return 400."""
    token = self._stage_glb()
    good = {'lat': 37, 'lng': -121, 'heading_deg': 0}
    bad_anchors = [
      [], 'point', None, 123,
      {**good, 'lat': 91}, {**good, 'lat': -91}, {**good, 'lng': 181},
      {'lat': '37', 'lng': '-121', 'heading_deg': '0'},
    ]
    resp = self._post_commit(token=token)
    self.assertEqual(resp.status_code, 400, 'missing anchor')
    for bad_anchor in bad_anchors:
      with self.subTest(anchor=bad_anchor):
        self.assertEqual(self._post_commit(token=token, anchor=bad_anchor).status_code, 400)
    # NaN is not valid JSON; the DRF parser rejects it
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=f'{{"token": "{token}", "anchor": {{"lat": NaN, "lng": -121, "heading_deg": 0}}}}',
      content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_post_body_not_json_object_returns_400(self):
    """POST with body as JSON list returns 400."""
    resp = self.client.post(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps([]), content_type='application/json'
    )
    self.assertEqual(resp.status_code, 400)

  def test_atomicity_failure_leaves_no_new_file_original_intact(self):
    """POST where mesh footprint fails: 500, new map removed, old map kept."""
    old_map_fn = self._create_old_map()
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}

    with patch.object(
      glb_alignment, '_get_mesh_footprint_corners_from_glb',
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
      glb_alignment, '_get_mesh_footprint_corners_from_glb',
      side_effect=RuntimeError('Alignment failed')
    ):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.assertEqual(resp.status_code, 500)

    # Only the staged GLB may remain as a .glb; the failed commit must not leak one
    stored = [os.path.join(d, f) for d, _, files in os.walk(self.media_root) for f in files if f.endswith('.glb')]
    self.assertEqual(stored, [os.path.join(self.staging_dir, f'{token}.glb')])

  def test_commit_success_no_previous_map(self):
    """POST on scene with no previous map -> 200; GLB stored, map stays empty, staged file removed."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 0}}

    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )

    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.glb_map.name.endswith('.glb'))
    self.assertFalse(self.scene.map)
    self.assertFalse(self.scene.use_glb_map)
    self.assertFalse(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))
    self.mqtt_mock.assert_called_with(scene_id=self.scene.id)


class TestSceneUpdateGlbAnchor(CommitBaseSetup):
  """Save Scene Updates persists a shifted saved-GLB anchor posted as glb_anchor."""

  SHIFTED = {'lat': 37.391, 'lng': -121.969, 'heading_deg': 90.0}

  def setUp(self):
    super().setUp()
    self._create_old_map()
    self._set_frame()

  def _commit_glb(self):
    """Store a GLB at the default anchor; the map is left unchanged."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0}}
    with self.captureOnCommitCallbacks(execute=True):
      resp = self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()

  def _post_scene_form(self, **overrides):
    """POST the scene update form with the current scene values, then overrides."""
    data = {
      'name': self.scene.name,
      'map_type': 'geospatial_map',
      'output_lla': 'True',
      'map_corners_lla': json.dumps(self.scene.map_corners_lla),
      'map_center_lat': self.scene.map_center_lat,
      'map_center_lng': self.scene.map_center_lng,
      'camera_calibration': self.scene.camera_calibration,
      'rotation_x': 0.0, 'rotation_y': 0.0, 'rotation_z': 0.0,
      'translation_x': 0.0, 'translation_y': 0.0, 'translation_z': 0.0,
      'scale_x': 1.0, 'scale_y': 1.0, 'scale_z': 1.0,
      'use_tracker': 'True',
    }
    data.update(overrides)
    return self.client.post(reverse('scene_update', args=[self.scene.id]), data=data)

  def test_form_persists_shifted_anchor_with_other_fields(self):
    """The shifted anchor is saved with the form's own fields, keeping the stored footprint."""
    self._commit_glb()
    footprint = self.scene.glb_anchor['footprint_m']

    resp = self._post_scene_form(name='geo_renamed', glb_anchor=json.dumps(self.SHIFTED))

    self.assertEqual(resp.status_code, 302)
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_renamed')
    self.assertAlmostEqual(self.scene.glb_anchor['lat'], 37.391, places=6)
    self.assertAlmostEqual(self.scene.glb_anchor['lng'], -121.969, places=6)
    self.assertAlmostEqual(self.scene.glb_anchor['heading_deg'], 90.0, places=6)
    self.assertEqual(self.scene.glb_anchor['footprint_m'], footprint)

  def test_form_without_anchor_leaves_glb_untouched(self):
    """A plain Save Scene Updates does not move the stored GLB."""
    self._commit_glb()
    before = self.scene.glb_anchor

    resp = self._post_scene_form(name='geo_renamed')

    self.assertEqual(resp.status_code, 302)
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.glb_anchor, before)

  def test_shift_applied_glb_recomputes_pose_over_posted_corners(self):
    """An applied GLB's corners follow the new anchor, not the stale corners the form posted."""
    self._commit_glb()
    with self.captureOnCommitCallbacks(execute=True):
      self._apply_glb()
    self.scene.refresh_from_db()
    stale_corners = self.scene.map_corners_lla

    resp = self._post_scene_form(
      glb_anchor=json.dumps(self.SHIFTED), map_corners_lla=json.dumps(stale_corners)
    )

    self.assertEqual(resp.status_code, 302)
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    self.assertAlmostEqual(self.scene.glb_anchor['lat'], 37.391, places=6)
    self.assertNotEqual(self.scene.map_corners_lla, stale_corners)

  def test_invalid_anchor_json_rerenders_with_error_and_keeps_scene(self):
    """Malformed glb_anchor re-renders the form with an error and saves nothing."""
    self._commit_glb()
    before = self.scene.glb_anchor

    resp = self._post_scene_form(name='geo_renamed', glb_anchor='{not json')

    self.assertEqual(resp.status_code, 200)
    self.assertIn('Invalid GLB anchor', resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_scene')
    self.assertEqual(self.scene.glb_anchor, before)

  def test_out_of_range_anchor_rerenders_with_error_and_keeps_scene(self):
    """A latitude outside [-90, 90] is rejected with the same error as the Save position route."""
    self._commit_glb()
    before = self.scene.glb_anchor
    bad = dict(self.SHIFTED, lat=91.0)

    resp = self._post_scene_form(name='geo_renamed', glb_anchor=json.dumps(bad))

    self.assertEqual(resp.status_code, 200)
    self.assertIn('Invalid anchor', resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_scene')
    self.assertEqual(self.scene.glb_anchor, before)

  def test_anchor_without_stored_glb_is_rejected(self):
    """A shifted anchor with no stored GLB is refused and nothing is saved."""
    resp = self._post_scene_form(name='geo_renamed', glb_anchor=json.dumps(self.SHIFTED))

    self.assertEqual(resp.status_code, 200)
    self.assertIn('No stored GLB to move', resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_scene')
    self.assertFalse(self.scene.glb_anchor)

  def test_staged_glb_is_accepted_with_scene_update(self):
    """Save Scene Updates with a staged GLB stores it, the same as the Accept button."""
    token = self._stage_glb()

    resp = self._post_scene_form(
      name='geo_renamed', glb_token=token, glb_anchor=json.dumps(self.SHIFTED)
    )

    self.assertEqual(resp.status_code, 302)
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_renamed')
    self.assertTrue(self.scene.glb_map)
    self.assertFalse(self.scene.use_glb_map)
    self.assertAlmostEqual(self.scene.glb_anchor['lat'], 37.391, places=6)
    self.assertAlmostEqual(self.scene.glb_anchor['lng'], -121.969, places=6)
    self.assertAlmostEqual(self.scene.glb_anchor['heading_deg'], 90.0, places=6)
    self.assertIn('footprint_m', self.scene.glb_anchor)
    self.assertFalse(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))

  def test_staged_glb_with_unknown_token_is_rejected(self):
    """A staged token with no file is refused and nothing is saved."""
    resp = self._post_scene_form(
      name='geo_renamed', glb_token=str(uuid.uuid4()), glb_anchor=json.dumps(self.SHIFTED)
    )

    self.assertEqual(resp.status_code, 200)
    self.assertIn('Staged GLB not found or expired', resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_scene')
    self.assertFalse(self.scene.glb_map)

  def test_staged_glb_with_invalid_anchor_is_rejected(self):
    """A staged GLB with a malformed anchor is refused and the staged file is kept for retry."""
    token = self._stage_glb()

    resp = self._post_scene_form(
      name='geo_renamed', glb_token=token, glb_anchor='{not json'
    )

    self.assertEqual(resp.status_code, 200)
    self.assertIn('Invalid GLB anchor', resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_scene')
    self.assertFalse(self.scene.glb_map)
    self.assertTrue(os.path.exists(os.path.join(self.staging_dir, f'{token}.glb')))

  def test_staged_glb_on_non_geospatial_scene_is_rejected(self):
    """A staged GLB is not stored when the form switches the scene to another map type."""
    token = self._stage_glb()

    resp = self._post_scene_form(
      name='geo_renamed', map_type='map_upload', glb_token=token, glb_anchor=json.dumps(self.SHIFTED)
    )

    self.assertEqual(resp.status_code, 200)
    self.assertIn('Scene map type must be geospatial_map', resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.name, 'geo_scene')
    self.assertFalse(self.scene.glb_map)

  def test_clearing_map_on_geospatial_scene_is_rejected(self):
    """Ticking Clear on the map of an output_lla scene is refused, not saved as an empty map."""
    resp = self._post_scene_form(**{'map-clear': 'on'})

    self.assertEqual(resp.status_code, 200)
    self.assertIn(MAP_REQUIRED_MSG, resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertEqual(self.scene.map.name, 'old_map.png')

  def test_clearing_map_with_applied_glb_is_rejected_and_keeps_frame(self):
    """Clearing the map while a GLB is applied is refused, so the original frame survives."""
    self._commit_glb()
    with self.captureOnCommitCallbacks(execute=True):
      self._apply_glb()
    self.scene.refresh_from_db()
    frame = self.scene.base_map_corners_lla

    resp = self._post_scene_form(**{'map-clear': 'on'})

    self.assertEqual(resp.status_code, 200)
    self.assertIn(MAP_REQUIRED_MSG, resp.context['form'].non_field_errors())
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)
    self.assertEqual(self.scene.base_map_corners_lla, frame)


class TestGlbApplyOverGlbMap(CommitBaseSetup):
  """A GLB applied over a GLB-type map (e.g. a generated mesh) unapplies back to that map."""

  def setUp(self):
    super().setUp()
    with open(TEST_GLB_FILE, 'rb') as src, open(os.path.join(self.media_root, 'mesh.glb'), 'wb') as dst:
      dst.write(src.read())
    Scene.objects.filter(pk=self.scene.pk).update(map='mesh.glb')
    self.scene.refresh_from_db()
    self._set_frame()

  def test_unapply_restores_the_glb_map_it_replaced(self):
    """Unapply after applying over a mesh brings the mesh back instead of leaving no map."""
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0}}
    with self.captureOnCommitCallbacks(execute=True):
      self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
      self._apply_glb()
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)

    resp = self.client.put(
      reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
      data=json.dumps({'use_glb_map': False}), content_type='application/json'
    )

    self.assertEqual(resp.status_code, 200)
    self.scene.refresh_from_db()
    self.assertFalse(self.scene.use_glb_map)
    self.assertTrue(self.scene.map)
    self.assertTrue(self.scene.map.name.endswith('.glb'))


class TestGenerateMeshGlbOverride(CommitBaseSetup):
  """Generate Mesh asks before replacing an applied GLB map."""

  def _apply_glb_scene(self):
    self._create_old_map()
    self._set_frame()
    token = self._stage_glb()
    body = {'token': token, 'anchor': {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0}}
    with self.captureOnCommitCallbacks(execute=True):
      self.client.post(
        reverse('geospatial_glb', kwargs={'scene_uid': self.scene.id}),
        data=json.dumps(body), content_type='application/json'
      )
    with self.captureOnCommitCallbacks(execute=True):
      self._apply_glb()
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)

  def _generate_mesh(self, data=None):
    return self.client.post(reverse('generate_mesh', kwargs={'pk': self.scene.id}), data or {})

  @patch('manager.mesh_generator.MeshGenerator.startMeshGeneration')
  def test_generate_mesh_without_override_returns_409_and_does_not_start(self, start_mock):
    self._apply_glb_scene()
    resp = self._generate_mesh()
    self.assertEqual(resp.status_code, 409)
    self.assertTrue(json.loads(resp.content)['glb_applied'])
    start_mock.assert_not_called()
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)

  @patch('manager.mesh_generator.MeshGenerator.startMeshGeneration')
  def test_generate_mesh_with_override_starts_and_keeps_glb_until_finalize(self, start_mock):
    start_mock.return_value = {'success': True, 'request_id': 'req-1'}
    self._apply_glb_scene()
    resp = self._generate_mesh({'override_glb': 'true'})
    self.assertEqual(resp.status_code, 200)
    start_mock.assert_called_once()
    self.scene.refresh_from_db()
    self.assertTrue(self.scene.use_glb_map)

  @patch('manager.mesh_generator.MeshGenerator.startMeshGeneration')
  def test_generate_mesh_without_applied_glb_is_not_guarded(self, start_mock):
    start_mock.return_value = {'success': True, 'request_id': 'req-2'}
    resp = self._generate_mesh()
    self.assertEqual(resp.status_code, 200)
    start_mock.assert_called_once()


class TestScenePagesMapImage(TestCase):
  """Scene pages show a map image only when the map file is an image."""

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@intel.com", "pass")
    self.client.force_login(self.user)

  def _scene_with_map(self, map_name):
    scene = Scene.objects.create(name="pages_scene", map_type="geospatial_map")
    Scene.objects.filter(pk=scene.pk).update(map=map_name)
    scene.refresh_from_db()
    return scene

  def test_glb_map_without_thumbnail_is_not_rendered_as_image(self):
    scene = self._scene_with_map("pages_scene.glb")
    for url in (reverse('sceneDetail', args=[scene.id]), reverse('index')):
      resp = self.client.get(url)
      self.assertEqual(resp.status_code, 200)
      self.assertNotContains(resp, f'src="{scene.map.url}"')

  def test_image_map_without_thumbnail_is_rendered(self):
    scene = self._scene_with_map("pages_scene.png")
    for url in (reverse('sceneDetail', args=[scene.id]), reverse('index')):
      resp = self.client.get(url)
      self.assertEqual(resp.status_code, 200)
      self.assertContains(resp, f'src="{scene.map.url}"')


