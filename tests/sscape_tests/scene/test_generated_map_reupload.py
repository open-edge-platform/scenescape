# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A generated map re-uploaded through the REST API keeps its horizontal orientation."""

import io

import numpy as np
import pytest
import trimesh
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager import mapping_store
from manager.mesh_generator import MeshGenerator
from manager.models import Scene
from scene_common.glb_top_view import getMeshSize
from scene_common.mesh_util import extractMeshFromGLB

pytestmark = pytest.mark.django_db

FLOOR_EXTENTS = (4.0, 3.0, 1.0)


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch, tmp_path, settings):
  settings.MEDIA_ROOT = str(tmp_path / "media")
  monkeypatch.setattr(mapping_store, "sendUpdateCommand", lambda *a, **k: None)
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)
  monkeypatch.setattr(Scene, "sendUpdateCommand", lambda self, *a, **k: None, raising=False)


@pytest.fixture
def client():
  user = User.objects.create_superuser("admin", "a@b.c", "pw")
  token, _ = Token.objects.get_or_create(user=user)
  api = APIClient()
  api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
  return api


def _generate_map():
  box = trimesh.creation.box(extents=FLOOR_EXTENTS)
  box.apply_translation(box.extents / 2)
  # Stale values from an earlier upload must be replaced by the generated-map transform
  scene = Scene.objects.create(name="generated", rotation_z=15.0, translation_x=5.0)
  MeshGenerator()._saveMeshToScene(scene, box)
  scene.refresh_from_db()
  with open(scene.map.path, "rb") as f:
    return scene, f.read()


def _assert_horizontal_map(scene):
  assert [scene.rotation_x, scene.rotation_y, scene.rotation_z] == [90, 0, 0]
  assert [scene.translation_x, scene.translation_y, scene.translation_z] == pytest.approx([0, 0, 0], abs=1e-4)
  mesh, _ = extractMeshFromGLB(scene.map.path, rotation=np.array([scene.rotation_x, scene.rotation_y, scene.rotation_z]))
  assert getMeshSize(mesh) == pytest.approx(FLOOR_EXTENTS, abs=1e-4)
  assert mesh.get_axis_aligned_bounding_box().min_bound.numpy() == pytest.approx((0, 0, 0), abs=1e-4)


def test_generated_map_is_horizontal():
  scene, _ = _generate_map()

  _assert_horizontal_map(scene)


def test_reuploading_generated_map_through_api_keeps_it_horizontal(client):
  _, glb_bytes = _generate_map()
  other = Scene.objects.create(name="reuploaded")

  upload = io.BytesIO(glb_bytes)
  upload.name = "generated_mesh.glb"
  resp = client.put(f"/api/v1/scene/{other.pk}", {"name": other.name, "map": upload}, format="multipart")
  assert resp.status_code == 200, resp.content

  body = client.get(f"/api/v1/scene/{other.pk}").json()
  assert body["mesh_rotation"] == [90, 0, 0]
  assert body["mesh_translation"] == pytest.approx([0, 0, 0], abs=1e-4)

  other.refresh_from_db()
  _assert_horizontal_map(other)
