# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GL-7: writers of Scene.map must not leave a stale GLB applied.

The xfail tests assert an invariant that holds for either policy the author
has not yet chosen:
  (A) the write auto-unapplies the GLB (use_glb_map becomes False), or
  (B) the write is rejected and Scene.map and use_glb_map are unchanged.
Remove the xfail marker once the policy is implemented.
"""

import io
import json
import uuid

import pytest
import trimesh
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager import glb_staging, glb_state, mapping_store
from manager.models import Scene, SceneSourceMap
from manager.serializers import SceneSerializer
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


def _post_form(web, scene, map_file=True, **extra):
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
  }
  if map_file:
    data["map"] = SimpleUploadedFile("new_form.glb", _glb_bytes(5.0), content_type="model/gltf-binary")
  data.update(extra)
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
  except (mapping_store.MappingStoreError, glb_staging.GlbAlignmentError):
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


def _png_bytes():
  buf = io.BytesIO()
  Image.new("RGB", (4, 4)).save(buf, format="PNG")
  return buf.getvalue()


def _store_glb(scene):
  glb = _write(scene.glb_map, "stored.glb", 2.0)
  Scene.objects.filter(pk=scene.pk).update(glb_map=glb, glb_anchor=ANCHOR)
  scene.refresh_from_db()


def _set_map(scene, name, content):
  scene.map.save(name, ContentFile(content), save=False)
  Scene.objects.filter(pk=scene.pk).update(map=scene.map.name)
  scene.refresh_from_db()


def _clear_base_map(scene):
  Scene.objects.filter(pk=scene.pk).update(base_map=None, base_scale=None, base_map_corners_lla=None)
  scene.refresh_from_db()


def test_apply_rejects_scene_with_empty_map(scene):
  _store_glb(scene)

  with pytest.raises(glb_staging.GlbAlignmentError) as err:
    glb_state.apply_glb_map(scene)

  assert err.value.status == 400
  assert "flat base map" in err.value.message
  scene.refresh_from_db()
  assert scene.use_glb_map is False


def test_apply_rejects_generated_glb_as_base_map(scene):
  _store_glb(scene)
  _set_map(scene, "mesh.glb", _glb_bytes(1.0))

  with pytest.raises(glb_staging.GlbAlignmentError) as err:
    glb_state.apply_glb_map(scene)

  assert err.value.status == 400
  scene.refresh_from_db()
  assert scene.use_glb_map is False


def test_apply_succeeds_over_flat_map(scene):
  _store_glb(scene)
  _set_map(scene, "flat.png", _png_bytes())

  glb_state.apply_glb_map(scene)

  scene.refresh_from_db()
  assert scene.use_glb_map is True
  assert scene.base_map.name.endswith(".png")


def test_apply_new_glb_applies_over_flat_map(scene):
  _store_glb(scene)
  _set_map(scene, "flat.png", _png_bytes())

  glb_state.apply_new_glb(scene)

  scene.refresh_from_db()
  assert scene.use_glb_map is True


def test_apply_new_glb_keeps_glb_unapplied_without_flat_map(scene):
  _store_glb(scene)

  glb_state.apply_new_glb(scene)

  scene.refresh_from_db()
  assert scene.glb_map
  assert scene.use_glb_map is False


def test_form_glb_commit_applies_new_glb_by_default(web_client, scene):
  _set_map(scene, "flat.png", _png_bytes())
  token = glb_staging.stage_glb(
    SimpleUploadedFile("stored.glb", _glb_bytes(2.0), content_type="model/gltf-binary"))

  resp = _post_form(web_client, scene, map_file=False, glb_token=token,
                    glb_anchor=json.dumps({"lat": 37.39, "lng": -121.97, "heading_deg": 45.0}))

  assert resp.status_code == 302, resp.content
  scene.refresh_from_db()
  assert scene.glb_map
  assert scene.use_glb_map is True


def test_commit_applied_scene_rejects_missing_base_map(scene):
  _apply_glb_state(scene)
  _clear_base_map(scene)

  with pytest.raises(glb_staging.GlbAlignmentError) as err:
    glb_state.commit_glb(scene, str(uuid.uuid4()), {"lat": 37.39, "lng": -121.97, "heading_deg": 45.0})

  assert err.value.status == 400
  assert "flat base map" in err.value.message


def test_commit_unapplied_scene_without_base_map_stores_glb(scene):
  upload = SimpleUploadedFile("stored.glb", _glb_bytes(2.0), content_type="model/gltf-binary")
  token = glb_staging.stage_glb(upload)

  glb_state.commit_glb(scene, token, {"lat": 37.39, "lng": -121.97, "heading_deg": 45.0})

  scene.refresh_from_db()
  assert scene.glb_map
  assert scene.use_glb_map is False


def test_move_and_remove_work_on_applied_scene_without_base_map(scene):
  _apply_glb_state(scene)
  _clear_base_map(scene)

  glb_state.move_glb_anchor(scene, {"lat": 37.3895, "lng": -121.9705, "heading_deg": 30.0})
  scene.refresh_from_db()
  assert scene.glb_anchor["lat"] == 37.3895

  glb_state.remove_glb_map(scene)
  scene.refresh_from_db()
  assert not scene.glb_map
  assert scene.use_glb_map is False


def test_scene_serializer_exposes_base_map_and_scale(scene):
  _apply_glb_state(scene)
  Scene.objects.filter(pk=scene.pk).update(base_scale=12.5)
  scene.refresh_from_db()

  data = SceneSerializer(scene).data

  assert data["base_map"].endswith("base.glb")
  assert data["base_scale"] == 12.5


def test_scene_serializer_omits_empty_base_map(scene):
  data = SceneSerializer(scene).data

  assert "base_map" not in data
  assert "base_scale" not in data


def test_scene_serializer_ignores_base_map_on_write(scene):
  _apply_glb_state(scene)
  before = scene.base_map.name

  serializer = SceneSerializer(
    scene, data={"name": scene.name, "base_map": "evil.png", "base_scale": 99.0}, partial=True)

  assert serializer.is_valid(), serializer.errors
  assert "base_map" not in serializer.validated_data
  assert "base_scale" not in serializer.validated_data
  scene.refresh_from_db()
  assert scene.base_map.name == before
