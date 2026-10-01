# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""keyframes artifact → mapping service job → candidate mesh + proposed cameras."""

import base64
import hashlib
import io
import json
import zipfile
from unittest.mock import patch

import numpy as np
import pytest
import trimesh
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager import mapping_store
from manager.models import Scene, SceneMappingArtifact

pytestmark = pytest.mark.django_db

_JPEG = base64.b64decode(
  "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////"
  "/////////////////////////////////////////////////////////wgALCAABAAEBAREA"
  "/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, tmp_path, settings):
  settings.MEDIA_ROOT = str(tmp_path / "media")
  monkeypatch.setattr(mapping_store, "sendUpdateCommand", lambda *a, **k: None)
  monkeypatch.setattr(mapping_store, "_save_revision_thumbnail", lambda revision: None)
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)
  monkeypatch.setenv("MAPPING_METHOD_FILES", "")
  monkeypatch.setenv("MAPPING_METHOD", "mapanything")


@pytest.fixture
def client():
  user = User.objects.create_superuser("admin", "a@b.c", "pw")
  token, _ = Token.objects.get_or_create(user=user)
  api = APIClient()
  api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
  return api


@pytest.fixture
def scene():
  return Scene.objects.create(name="kf-scene")


def _keyframes_zip(n=3):
  cams = []
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w") as archive:
    for i in range(n):
      name = f"frames/{i:06d}.jpg"
      archive.writestr(name, _JPEG)
      cams.append({"id": f"kf{i:06d}", "kind": "observed", "file": name,
                   "translation": [float(i), 0.0, 1.5],
                   "quaternion_xyzw": [0.0, 0.7071, 0.0, 0.7071],
                   "intrinsics": {"width": 640, "height": 480, "fx": 600, "fy": 600, "cx": 320, "cy": 240}})
    manifest = {"version": 1, "method": "keyframes", "contributor": "handheld-01", "cameras": cams}
    archive.writestr("manifest.json", json.dumps(manifest))
  data = buf.getvalue()
  up = io.BytesIO(data)
  up.name = "keyframes.zip"
  return up, hashlib.sha256(data).hexdigest()


def _fake_result(cam_ids):
  glb = base64.b64encode(trimesh.creation.box().export(file_type="glb")).decode()
  return {
    "success": True, "state": "complete",
    "result": {
      "success": True, "glb_data": glb, "processing_time": 4.2,
      "camera_poses": [{"camera_id": c, "rotation": [0, 0, 0, 1],
                        "translation": [i, 0, 1.5]} for i, c in enumerate(cam_ids)],
      "intrinsics": [{"camera_id": c, "K": [[600, 0, 320], [0, 600, 240], [0, 0, 1]]} for c in cam_ids],
    },
  }


def test_keyframes_upload_then_reconstruct_yields_candidate(client, scene):
  up, sha = _keyframes_zip()
  resp = client.put(f"/api/v1/scene/{scene.pk}/mapping-artifacts/keyframes",
                    {"bundle": up, "sha256": sha}, format="multipart")
  assert resp.status_code == 200, resp.content
  assert resp.json()["map_revision"] is None
  assert len(resp.json()["manifest"]["cameras"]) == 3

  submitted = {}

  def fake_start(images, order, locations, mesh_type="mesh", uploaded_map=None,
                 camera_intrinsics_order=None):
    submitted["order"] = list(order)
    submitted["locations"] = list(locations)
    submitted["intrinsics"] = list(camera_intrinsics_order or [])
    submitted["n_images"] = len(images)
    return {"success": True, "request_id": "abc123", "state": "processing"}

  with patch("manager.mesh_generator.MappingServiceClient.startReconstructMesh", side_effect=fake_start), \
       patch("manager.mesh_generator.MappingServiceClient.checkHealth", return_value={"available": True, "models": {}}):
    resp = client.post(f"/api/v1/scene/{scene.pk}/reconstruct", {"max_images": 2}, format="json")
  assert resp.status_code == 202, resp.content
  assert resp.json()["request_id"] == "abc123"
  assert resp.json()["method"] == "mapanything"
  assert submitted["n_images"] == 2 and len(submitted["order"]) == 2
  # Manifest and service both use xyzw; passed through unchanged.
  assert submitted["locations"][0]["rotation"] == [0.0, 0.7071, 0.0, 0.7071]
  # Intrinsics priors go along, in pixels of the uploaded (uncropped) image.
  assert submitted["intrinsics"][0] == {"fx": 600.0, "fy": 600.0, "cx": 320.0, "cy": 240.0,
                                        "width": 640, "height": 480}
  assert resp.json()["priors"] == {"poses": 2, "intrinsics": 2}

  with patch("manager.mesh_generator.MappingServiceClient.getReconstructionStatus",
             return_value=_fake_result(submitted["order"])):
    resp = client.get(f"/api/v1/scene/{scene.pk}/reconstruct/abc123")
  assert resp.status_code == 200, resp.content
  body = resp.json()
  assert body["finalized"] is True
  art = body["artifact"]
  assert art["method"] == "mapanything"
  assert art["map_revision"]
  cams = art["manifest"]["cameras"]
  assert len(cams) == 2 and all(c["kind"] == "proposed" for c in cams)
  assert cams[0]["intrinsics"]["fx"] == 600.0
  assert art["manifest"]["source"]["request_id"] == "abc123"

  # Candidate only: default map unchanged, both artifacts live.
  scene.refresh_from_db()
  assert scene.default_map_revision_id is None
  assert not scene.map
  methods = sorted(SceneMappingArtifact.objects.filter(scene=scene, head=True).values_list("method", flat=True))
  assert methods == ["keyframes", "mapanything"]

  # Polling again is idempotent — no second artifact.
  with patch("manager.mesh_generator.MappingServiceClient.getReconstructionStatus",
             return_value=_fake_result(submitted["order"])):
    resp = client.get(f"/api/v1/scene/{scene.pk}/reconstruct/abc123")
  assert resp.json()["artifact"]["id"] == art["id"]
  assert SceneMappingArtifact.objects.filter(scene=scene, method="mapanything").count() == 1

  # And the user can now adopt it.
  resp = client.post(f"/api/v1/scene/{scene.pk}/map-revisions/{art['map_revision']}/activate")
  assert resp.status_code == 200, resp.content
  scene.refresh_from_db()
  assert str(scene.default_map_revision_id) == art["map_revision"]


def test_reconstruct_without_keyframes_is_409(client, scene):
  with patch("manager.mesh_generator.MappingServiceClient.checkHealth", return_value={}):
    resp = client.post(f"/api/v1/scene/{scene.pk}/reconstruct", {}, format="json")
  assert resp.status_code == 409
  assert "keyframes" in resp.json()["error"]


def test_client_keeps_priors_index_aligned_with_unposed_cameras():
  """Scene cameras have no pose/intrinsics; their slots must still be sent so
  the handheld frames after them keep the right priors."""
  from manager.mesh_generator import MappingServiceClient
  captured = {}

  class _Resp:
    status_code = 200
    content = b"{}"
    def json(self):
      return {"success": True, "request_id": "r", "processing_time": 0.1}

  def fake_post(url, data=None, files=None, **kw):
    captured["files"] = files
    return _Resp()

  client = MappingServiceClient()
  ids = ["kf0", "axis-01", "kf1"]
  images = {c: {"filename": f"{c}.jpg", "data": base64.b64encode(_JPEG).decode()} for c in ids}
  locs = [{"translation": [0, 0, 0], "rotation": [0, 0, 0, 1]}, None,
          {"translation": [1, 0, 0], "rotation": [0, 0, 0, 1]}]
  intr = [{"fx": 500, "fy": 500, "cx": 320, "cy": 240, "width": 640, "height": 480}, None,
          {"fx": 500, "fy": 500, "cx": 320, "cy": 240}]
  with patch("manager.mesh_generator.requests.post", side_effect=fake_post):
    client.startReconstructMesh(images, ids, locs, camera_intrinsics_order=intr)

  fields = [(k, v[1]) for k, v in captured["files"] if k != "images"]
  cam_ids = [v for k, v in fields if k == "camera_ids"]
  sent_locs = [v for k, v in fields if k == "camera_locations"]
  sent_intr = [v for k, v in fields if k == "camera_intrinsics"]
  assert cam_ids == ids
  assert len(sent_locs) == 3 and len(sent_intr) == 3
  assert sent_locs[1] == "" and sent_intr[1] == ""          # scene camera: empty slots
  assert json.loads(sent_locs[2])["translation"] == [1, 0, 0]  # kf1 still gets its own pose
  assert json.loads(sent_intr[0])["width"] == 640


def test_job_puts_a_posed_view_first():
  """MapAnything drops all pose priors if view 0 has none."""
  from manager.mesh_generator import MeshGenerator
  order, locs, intr = MeshGenerator._posedViewFirst(
    ["cam", "kf0", "kf1"], [None, {"t": 0}, {"t": 1}], [None, {"fx": 1}, {"fx": 2}])
  assert order == ["kf0", "cam", "kf1"]
  assert locs[0] == {"t": 0} and locs[1] is None and locs[2] == {"t": 1}
  assert intr == [{"fx": 1}, None, {"fx": 2}]
  # Already posed first, or no poses at all: untouched.
  assert MeshGenerator._posedViewFirst(["a", "b"], [{"t": 0}, None], [None, None])[0] == ["a", "b"]
  assert MeshGenerator._posedViewFirst(["a", "b"], [None, None], [None, None])[0] == ["a", "b"]
