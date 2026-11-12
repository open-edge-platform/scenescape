# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GL-7: writers of Scene.map must not leave a stale GLB applied.

The xfail tests assert an invariant that holds for either policy the author
has not yet chosen:
  (A) the write auto-unapplies the GLB (use_glb_map becomes False), or
  (B) the write is rejected and Scene.map and use_glb_map are unchanged.
Remove the xfail marker once the policy is implemented.
"""

import json

import pytest
import trimesh
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager import glb_alignment, mapping_store
from manager.models import Scene, SceneSourceMap
from scene_common.earth_lla import localFootprintCornersLLA

pytestmark = pytest.mark.django_db

CORNERS = localFootprintCornersLLA(
  center_lat=37.38689, center_lng=-121.96411, heading_deg=0.0,
  width_m=100.0, height_m=100.0,
).tolist()
ANCHOR = {'lat': 37.39, 'lng': -121.97, 'heading_deg': 45.0,
          'footprint_m': {'width': 10.0, 'height': 10.0}}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, tmp_path, settings):
  settings.MEDIA_ROOT = str(tmp_path / "media")
  monkeypatch.setattr(mapping_store, "sendUpdateCommand", lambda *a, **k: None)
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)
  monkeypatch.setattr("manager.models.sendUpdateCommand", lambda *a, **k: None)


@pytest.fixture
def scene():
  obj = Scene.objects.create(
    name="glb-state", map_type="geospatial_map", output_lla=True,
    map_center_lat=37.38689, map_center_lng=-121.96411)
  Scene.objects.filter(pk=obj.pk).update(map_corners_lla=CORNERS)
  obj.refresh_from_db()
  return obj


@pytest.fixture
def api_client():
  user = User.objects.create_superuser("admin", "a@b.c", "pw")
  token, _ = Token.objects.get_or_create(user=user)
  api = APIClient()
  api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
  return api


@pytest.fixture
def web_client():
  user = User.objects.create_superuser("webadmin", "w@b.c", "pw")
  web = Client()
  web.force_login(user)
  return web


def _glb_bytes(size=1.0):
  return trimesh.creation.box(extents=(size, size, size)).export(file_type="glb")


def _write(field, name, size):
  field.save(name, ContentFile(_glb_bytes(size)), save=False)
  return field.name


def _upload_source(scene, method, size=1.0):
  """Record a per-method mesh the way the Scene PUT path does."""
  name = _write(scene.map, f"{method}.glb", size)
  Scene.objects.filter(pk=scene.pk).update(map=name)
  return mapping_store.record_glb_source_map(scene, method, "tester")


def _apply_glb_state(scene):
  """Put the scene in the GLB-applied state: base snapshot, stored GLB, applied map."""
  base = _write(scene.base_map, "base.glb", 1.0)
  glb = _write(scene.glb_map, "stored.glb", 2.0)
  applied = _write(scene.map, "applied.glb", 3.0)
  Scene.objects.filter(pk=scene.pk).update(
    base_map=base, glb_map=glb, map=applied, use_glb_map=True,
    glb_anchor=ANCHOR, base_map_corners_lla=CORNERS, map_corners_lla=CORNERS)
  scene.refresh_from_db()
  assert scene.use_glb_map is True


def _put_glb(api, scene):
  upload = SimpleUploadedFile("new_api.glb", _glb_bytes(4.0), content_type="model/gltf-binary")
  return api.put(f"/api/v1/scene/{scene.pk}",
                 {"name": scene.name, "map": upload}, format="multipart")


def _post_form(web, scene):
  scene.refresh_from_db()
  data = {
    "name": scene.name,
    "map_type": "geospatial_map",
    "output_lla": "True",
    "map_corners_lla": json.dumps(scene.map_corners_lla),
    "map_center_lat": scene.map_center_lat,
    "map_center_lng": scene.map_center_lng,
    "camera_calibration": scene.camera_calibration,
    "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
    "translation_x": 0.0, "translation_y": 0.0, "translation_z": 0.0,
    "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
    "use_tracker": "True",
    "map": SimpleUploadedFile("new_form.glb", _glb_bytes(5.0), content_type="model/gltf-binary"),
  }
  return web.post(reverse("scene_update", args=[scene.pk]), data=data)


@pytest.mark.xfail(strict=True, reason="GL-7: activation writes Scene.map under an applied GLB (policy pending)")
def test_activate_source_map_while_glb_applied(scene):
  source = _upload_source(scene, "orbslam3")
  _upload_source(scene, "arkit", size=2.0)
  scene.refresh_from_db()
  _apply_glb_state(scene)
  applied_name = scene.map.name

  try:
    mapping_store.activate_source_map(scene, source)
  except (mapping_store.MappingStoreError, glb_alignment.GlbAlignmentError):
    rejected = True
  else:
    rejected = False

  scene.refresh_from_db()
  if rejected:
    assert scene.use_glb_map is True
    assert scene.map.name == applied_name
  else:
    assert scene.use_glb_map is False
    assert scene.map.name == SceneSourceMap.objects.get(pk=source.pk).file.name


@pytest.mark.xfail(strict=True, reason="GL-7: API .glb upload keeps a GLB applied (policy pending)")
def test_api_glb_upload_while_glb_applied(api_client, scene):
  _apply_glb_state(scene)
  before = scene.map.name

  resp = _put_glb(api_client, scene)

  scene.refresh_from_db()
  if resp.status_code == 400:
    assert scene.use_glb_map is True
    assert scene.map.name == before
  else:
    assert resp.status_code == 200, resp.content
    assert scene.use_glb_map is False


@pytest.mark.xfail(strict=True, reason="GL-7: form .glb replacement keeps a GLB applied (policy pending)")
def test_form_glb_upload_while_glb_applied(web_client, scene):
  _apply_glb_state(scene)
  before = scene.map.name

  resp = _post_form(web_client, scene)

  scene.refresh_from_db()
  if resp.status_code == 302:
    assert scene.use_glb_map is False
  else:
    assert scene.use_glb_map is True
    assert scene.map.name == before


def test_api_glb_upload_without_applied_glb_is_plain_map(api_client, scene):
  resp = _put_glb(api_client, scene)

  assert resp.status_code == 200, resp.content
  scene.refresh_from_db()
  assert scene.use_glb_map is False
  assert scene.map.name.endswith(".glb")


def test_form_glb_upload_without_applied_glb_is_plain_map(web_client, scene):
  resp = _post_form(web_client, scene)

  assert resp.status_code == 302
  scene.refresh_from_db()
  assert scene.use_glb_map is False
  assert scene.map.name.endswith(".glb")
