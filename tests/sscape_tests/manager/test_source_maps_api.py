# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST surface for per-method source maps and artifacts."""

import hashlib
import io
import json
import zipfile

import pytest
import trimesh
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager import mapping_store
from manager.models import Scene

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, tmp_path, settings):
  settings.MEDIA_ROOT = str(tmp_path / "media")
  monkeypatch.setattr(mapping_store, "sendUpdateCommand", lambda *a, **k: None)
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)


@pytest.fixture
def client():
  user = User.objects.create_superuser("admin", "a@b.c", "pw")
  token, _ = Token.objects.get_or_create(user=user)
  api = APIClient()
  api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
  return api


@pytest.fixture
def scene():
  return Scene.objects.create(name="api-rev")


def _bundle(members):
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w") as archive:
    for name, data in members.items():
      archive.writestr(name, data)
  data = buf.getvalue()
  upload = io.BytesIO(data)
  upload.name = "bundle.zip"
  return upload, hashlib.sha256(data).hexdigest()


def _glb():
  return trimesh.creation.box().export(file_type="glb")


def _put(client, scene, method, members, **extra):
  upload, sha = _bundle(members)
  data = {"bundle": upload, "sha256": sha, **extra}
  return client.put(f"/api/v1/scene/{scene.pk}/mapping-artifacts/{method}",
                    data, format="multipart")


def _put_mesh(client, scene, source=None, name="map.glb", **extra):
  glb = io.BytesIO(_glb())
  glb.name = name
  data = {"name": scene.name, "map": glb, **extra}
  if source:
    data["source"] = source
  return client.put(f"/api/v1/scene/{scene.pk}", data, format="multipart")


def test_artifact_put_list_get_delete(client, scene):
  manifest = {"cameras": [{"id": "c1", "kind": "proposed"}]}
  resp = _put(client, scene, "keyframes",
              {"manifest.json": json.dumps(manifest), "frames.bin": b"x"},
              contributor="handheld-01")
  assert resp.status_code == 200, resp.content
  body = resp.json()
  assert body["manifest"]["cameras"][0]["id"] == "c1"
  assert body["contributor"] == "handheld-01"

  listing = client.get(f"/api/v1/scene/{scene.pk}/mapping-artifacts").json()
  assert [a["method"] for a in listing] == ["keyframes"]
  scene_body = client.get(f"/api/v1/scene/{scene.pk}").json()
  assert [a["method"] for a in scene_body["mapping_artifacts"]] == ["keyframes"]
  # Artifacts never create meshes.
  assert client.get(f"/api/v1/scene/{scene.pk}/maps").json() == {"default": None, "maps": []}

  resp = client.get(f"/api/v1/scene/{scene.pk}/mapping-artifacts/keyframes")
  assert resp.status_code == 200
  assert resp[mapping_store.DIGEST_HEADER] == body["sha256"]
  assert resp.get("Content-Type") == "application/zip"

  resp = _put(client, scene, "orbslam3", {"nope.bin": b"x"})
  assert resp.status_code == 400
  assert resp.json() == {"error": "Failed to store mapping artifact"}


@pytest.mark.parametrize("manifest", [
  '{"contributor": 123}',
  '{"metadata": NaN}',
  '{"metadata": 1e999}',
])
def test_invalid_artifact_metadata_returns_controlled_400(client, scene, manifest, caplog):
  response = _put(client, scene, "keyframes", {"manifest.json": manifest})
  assert response.status_code == 400
  assert response.json() == {"error": "Failed to store mapping artifact"}
  assert "Failed to store mapping artifact" in caplog.text
  assert not scene.mapping_artifacts.exists()


def test_artifact_delete_and_missing_get(client, scene):
  assert _put(client, scene, "keyframes", {"frames.bin": b"x"}).status_code == 200
  assert client.delete(f"/api/v1/scene/{scene.pk}/mapping-artifacts/keyframes").status_code == 204
  assert client.get(f"/api/v1/scene/{scene.pk}/mapping-artifacts/keyframes").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_artifact_writes_require_superuser_but_reads_allow_authenticated(client, scene):
  assert _put(client, scene, "keyframes", {"frames.bin": b"x"}).status_code == 200
  reader = User.objects.create_user("reader")
  token = Token.objects.create(user=reader)
  client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
  url = f"/api/v1/scene/{scene.pk}/mapping-artifacts/keyframes"
  response = client.get(url)
  assert response.status_code == 200
  response.close()
  assert _put(client, scene, "keyframes", {"frames.bin": b"changed"}).status_code == 403
  assert client.delete(url).status_code == 403
  client.credentials()
  assert client.get(url).status_code == 401


def test_artifact_upload_size_limit(client, scene, monkeypatch):
  monkeypatch.setattr("manager.api.MAX_ARTIFACT_BYTES", 1)
  response = _put(client, scene, "keyframes", {"frames.bin": b"x"})
  assert response.status_code == 413
  assert not scene.mapping_artifacts.exists()


@pytest.mark.parametrize("create", [False, True])
def test_zip_map_upload_extracts_glb_and_invalidates_processed_state(client, scene, create):
  if not create:
    assert _put_mesh(client, scene, "rtabmap").status_code == 200
    Scene.objects.filter(pk=scene.pk).update(map_processed="2026-10-28T00:00:00Z")
  upload, _ = _bundle({
    "capture/raw.glb": _glb(),
    "capture/mesh_info.json": b"{}",
    "capture/keyframes/images/0.jpg": b"image",
    "capture/keyframes/depth/0.png": b"depth",
    "capture/keyframes/cameras/0.json": b"{}",
  })
  data = {"name": "zip-created" if create else scene.name, "map": upload}
  url = "/api/v1/scene" if create else f"/api/v1/scene/{scene.pk}"
  response = client.post(url, data, format="multipart")
  assert response.status_code in (200, 201), response.content
  saved = Scene.objects.get(pk=response.json()["uid"])
  assert saved.map.name.endswith(".glb")
  assert saved.map_processed is None
  assert saved.default_source_map.file.name == saved.map.name


def test_non_glb_replacement_resets_map_state(client, scene):
  from PIL import Image
  assert _put_mesh(client, scene, "rtabmap").status_code == 200
  Scene.objects.filter(pk=scene.pk).update(map_processed="2026-10-28T00:00:00Z", translation_x=12)
  upload = io.BytesIO()
  Image.new("RGB", (4, 4)).save(upload, format="PNG")
  upload.seek(0)
  upload.name = "floor.png"
  response = client.post(f"/api/v1/scene/{scene.pk}", {"map": upload}, format="multipart")
  assert response.status_code == 200, response.content
  scene.refresh_from_db()
  assert scene.map.name.endswith(".png")
  assert scene.map_processed is None
  assert scene.translation_x == 0
  assert not scene.thumbnail
  assert scene.default_source_map_id is None


@pytest.mark.parametrize("scale_only", [False, True])
def test_placement_only_save_updates_active_source_map(client, scene, monkeypatch, scale_only):
  assert _put_mesh(client, scene, "rtabmap").status_code == 200
  scene.refresh_from_db()
  source_id = scene.default_source_map_id
  thumbnail_calls = []

  def save_thumbnail(instance):
    thumbnail_calls.append(instance.pk)
    instance.thumbnail = f"edited-{instance.pk}.png"

  monkeypatch.setattr(Scene, "saveThumbnail", save_thumbnail)
  transform = mapping_store.scene_transform(scene)
  edits = {"scale": [2, 3, 4]} if scale_only else {
    "translation": [2, 3, 4], "rotation": [10, 20, 30], "scale": [2, 3, 4],
  }
  transform.update(edits)
  response = client.post(f"/api/v1/scene/{scene.pk}", {
    f"mesh_{key}": value for key, value in edits.items()
  }, format="json")
  assert response.status_code == 200, response.content
  scene.refresh_from_db()
  assert scene.default_source_map_id == source_id
  assert scene.default_source_map.transform == transform
  assert scene.thumbnail.name
  assert scene.default_source_map.thumbnail.name == scene.thumbnail.name
  assert thumbnail_calls
  assert _put_mesh(client, scene, "arkit").status_code == 200
  assert client.post(f"/api/v1/scene/{scene.pk}/maps/rtabmap/activate").status_code == 200
  scene.refresh_from_db()
  assert mapping_store.scene_transform(scene) == transform


def test_mesh_upload_then_list_activate_delete(client, scene):
  resp = _put_mesh(client, scene, "orbslam3", name="handheld.glb")
  assert resp.status_code == 200, resp.content
  assert resp.json()["map_source"] == "orbslam3"
  resp = _put_mesh(client, scene, "arkit", name="phone.glb")
  assert resp.status_code == 200, resp.content
  assert resp.json()["map_source"] == "arkit"

  maps = client.get(f"/api/v1/scene/{scene.pk}/maps").json()
  assert maps["default"] == "arkit"
  assert {m["method"]: m["is_default"] for m in maps["maps"]} == {"orbslam3": False, "arkit": True}
  assert all(m["file"].endswith(".glb") for m in maps["maps"])

  resp = client.post(f"/api/v1/scene/{scene.pk}/maps/orbslam3/activate")
  assert resp.status_code == 200, resp.content
  assert resp.json()["is_default"] is True
  scene_body = client.get(f"/api/v1/scene/{scene.pk}").json()
  assert scene_body["map_source"] == "orbslam3"
  assert scene_body["map"].endswith("handheld.glb")

  assert client.delete(f"/api/v1/scene/{scene.pk}/maps/orbslam3").status_code == 409
  assert client.delete(f"/api/v1/scene/{scene.pk}/maps/arkit").status_code == 204
  assert client.get(f"/api/v1/scene/{scene.pk}/maps/arkit").status_code == 404
  assert client.get(f"/api/v1/scene/{scene.pk}/maps").json()["default"] == "orbslam3"


def test_scene_map_upload_without_source_is_user_method(client, scene):
  resp = _put_mesh(client, scene, "rtabmap")
  assert resp.status_code == 200, resp.content
  assert resp.json()["map_source"] == "rtabmap"

  resp = _put_mesh(client, scene, None, name="plain.glb")
  assert resp.status_code == 200, resp.content
  assert resp.json()["map_source"] == "user"
  maps = client.get(f"/api/v1/scene/{scene.pk}/maps").json()
  assert maps["default"] == "user"
  assert sorted(m["method"] for m in maps["maps"]) == ["rtabmap", "user"]


def test_activation_response_uses_refreshed_source_transform(client, scene, monkeypatch):
  assert _put_mesh(client, scene, "orbslam3").status_code == 200
  source = scene.source_maps.get(method="orbslam3")
  assert _put_mesh(client, scene, "arkit").status_code == 200
  transform = {"translation": [7, 8, 9], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
  scene.source_maps.filter(pk=source.pk).update(transform=transform)
  monkeypatch.setattr("manager.api.source_map_for_method", lambda *args: source)
  response = client.post(f"/api/v1/scene/{scene.pk}/maps/orbslam3/activate")
  assert response.status_code == 200
  assert response.json()["transform"] == transform
  scene.refresh_from_db()
  assert scene.map_processed is None
  assert scene.translation_x == 7


@pytest.mark.parametrize("create", [False, True])
def test_map_upload_preserves_explicit_transform_and_source_map(client, scene, monkeypatch, create):
  def reject_auto_align(self):
    pytest.fail("Explicit mesh placement must bypass auto-alignment")

  monkeypatch.setattr(Scene, "autoAlignSceneMap", reject_auto_align)
  thumbnail_transforms = []
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: thumbnail_transforms.append(
    mapping_store.scene_transform(self)))
  transform = {
    "translation": [1.5, -2.0, 0.75],
    "rotation": [15.0, -20.0, 35.0],
    "scale": [1.5, 2.0, 0.5],
  }
  upload = io.BytesIO(_glb())
  upload.name = "placed.glb"
  data = {"name": "placed-scene" if create else scene.name, "map": upload}
  data.update({f"mesh_{key}": json.dumps(value) for key, value in transform.items()})
  url = "/api/v1/scene" if create else f"/api/v1/scene/{scene.pk}"
  response = client.post(url, data, format="multipart")
  assert response.status_code in (200, 201), response.content
  body = response.json()
  placed_scene = Scene.objects.get(pk=body["uid"])
  assert mapping_store.scene_transform(placed_scene) == transform
  source_map = placed_scene.default_source_map
  assert source_map.transform == transform

  Scene.objects.filter(pk=placed_scene.pk).update(rotation_x=80.0, translation_x=9.0, scale_x=4.0)
  response = client.post(f"/api/v1/scene/{placed_scene.pk}/maps/{source_map.method}/activate")
  assert response.status_code == 200, response.content
  placed_scene.refresh_from_db()
  assert mapping_store.scene_transform(placed_scene) == transform
  assert thumbnail_transforms
  assert all(placement == transform for placement in thumbnail_transforms)


def test_map_upload_scale_only_bypasses_auto_alignment(client, scene, monkeypatch):
  def reject_auto_align(self):
    pytest.fail("Explicit scale must bypass auto-alignment")

  monkeypatch.setattr(Scene, "autoAlignSceneMap", reject_auto_align)
  upload = io.BytesIO(_glb())
  upload.name = "scaled.glb"
  response = client.post(f"/api/v1/scene/{scene.pk}", {
    "map": upload, "mesh_scale": json.dumps([2.0, 3.0, 4.0]),
  }, format="multipart")
  assert response.status_code == 200, response.content
  scene.refresh_from_db()
  assert scene.default_source_map.transform["scale"] == [2.0, 3.0, 4.0]


@pytest.mark.parametrize("field,value", [
  ("skip_auto_align", "true"),
  ("mesh_rotation", "not-json"),
  ("mesh_translation", "[1, 2]"),
  ("mesh_scale", '[1, "invalid", 3]'),
  ("mesh_rotation", "[NaN, 0, 0]"),
  ("mesh_translation", "[Infinity, 0, 0]"),
  ("mesh_scale", "[true, 1, 1]"),
])
def test_invalid_upload_transform_keeps_current_source_map(client, scene, field, value):
  initial = _put_mesh(client, scene, "rtabmap", name="initial.glb")
  assert initial.status_code == 200, initial.content
  scene.refresh_from_db()
  original_map = scene.map.name
  original_source_map = scene.default_source_map_id
  upload = io.BytesIO(_glb())
  upload.name = "invalid.glb"
  response = client.post(f"/api/v1/scene/{scene.pk}", {
    "map": upload, field: value,
  }, format="multipart")
  assert response.status_code == 400, response.content
  scene.refresh_from_db()
  assert scene.map.name == original_map
  assert scene.default_source_map_id == original_source_map


def test_upload_without_placement_still_auto_aligns(client, scene, monkeypatch):
  aligned = []

  def auto_align(self):
    aligned.append(self.pk)
    self.rotation_x = 90.0
    self.translation_x = 2.0

  monkeypatch.setattr(Scene, "autoAlignSceneMap", auto_align)
  upload = io.BytesIO(_glb())
  upload.name = "unaligned.glb"
  response = client.post(f"/api/v1/scene/{scene.pk}", {"map": upload}, format="multipart")
  assert response.status_code == 200, response.content
  assert aligned == [scene.pk]
  scene.refresh_from_db()
  assert scene.default_source_map.transform["rotation"] == [90.0, 0.0, 0.0]
  assert scene.default_source_map.transform["translation"] == [2.0, 0.0, 0.0]
