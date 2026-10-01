# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST surface for GLB revisions and per-method artifacts."""

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
  monkeypatch.setattr(mapping_store, "_save_revision_thumbnail", lambda revision: None)
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)
  monkeypatch.setenv("MAPPING_METHOD_FILES", "")


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


def test_put_mesh_then_list_activate_delete(client, scene):
  manifest = {"method": "mapanything", "cameras": [{"id": "c1", "kind": "proposed"}]}
  resp = _put(client, scene, "mapanything",
              {"manifest.json": json.dumps(manifest), "mesh.glb": _glb()})
  assert resp.status_code == 200, resp.content
  body = resp.json()
  assert body["manifest"]["cameras"][0]["id"] == "c1"
  rev_id = body["map_revision"]
  assert rev_id

  listing = client.get(f"/api/v1/scene/{scene.pk}/mapping-artifacts").json()
  assert [a["method"] for a in listing] == ["mapanything"]

  revs = client.get(f"/api/v1/scene/{scene.pk}/map-revisions").json()
  assert revs["default"] is None
  assert len(revs["revisions"]) == 1
  assert revs["revisions"][0]["is_default"] is False
  assert revs["revisions"][0]["method"] == "mapanything"
  assert revs["revisions"][0]["file"].endswith(".glb")

  scene_body = client.get(f"/api/v1/scene/{scene.pk}").json()
  assert scene_body.get("map_revision") is None

  resp = client.post(f"/api/v1/scene/{scene.pk}/map-revisions/{rev_id}/activate")
  assert resp.status_code == 200, resp.content
  assert resp.json()["is_default"] is True

  scene_body = client.get(f"/api/v1/scene/{scene.pk}").json()
  assert scene_body["map_revision"] == rev_id
  assert scene_body["map_source"] == "mapanything"
  assert scene_body["map"]

  resp = client.delete(f"/api/v1/scene/{scene.pk}/map-revisions/{rev_id}")
  assert resp.status_code == 409


def test_put_with_activate_flag(client, scene):
  resp = _put(client, scene, "vggt", {"mesh.glb": _glb()}, activate="true")
  assert resp.status_code == 200, resp.content
  scene.refresh_from_db()
  assert str(scene.default_map_revision_id) == resp.json()["map_revision"]


def test_legacy_scene_map_upload_still_becomes_default(client, scene):
  glb = io.BytesIO(_glb())
  glb.name = "user.glb"
  resp = client.put(f"/api/v1/scene/{scene.pk}",
                    {"name": scene.name, "map": glb, "source": "rtabmap"},
                    format="multipart")
  assert resp.status_code == 200, resp.content
  body = resp.json()
  assert body["map_source"] == "rtabmap"
  revs = client.get(f"/api/v1/scene/{scene.pk}/map-revisions").json()
  assert revs["default"] == body["map_revision"]

  glb2 = io.BytesIO(_glb())
  glb2.name = "plain.glb"
  resp = client.put(f"/api/v1/scene/{scene.pk}",
                    {"name": scene.name, "map": glb2}, format="multipart")
  assert resp.status_code == 200, resp.content
  assert resp.json()["map_source"] == "user"
