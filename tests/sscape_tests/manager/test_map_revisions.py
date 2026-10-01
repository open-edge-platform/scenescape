# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GLB revisions: every method's mesh is a revision; Scene.map mirrors the default."""

import hashlib
import io
import json
import os
import zipfile
from unittest.mock import patch

import pytest
import trimesh
from django.core.files.base import ContentFile

from manager import mapping_store
from manager.models import Scene, SceneMapRevision, SceneMappingArtifact

pytestmark = pytest.mark.django_db


def _glb_bytes(size=1.0):
  return trimesh.creation.box(extents=(size, size, size)).export(file_type="glb")


def _zip(path, members):
  with zipfile.ZipFile(path, "w") as archive:
    for name, data in members.items():
      archive.writestr(name, data)
  return hashlib.sha256(open(path, "rb").read()).hexdigest()


@pytest.fixture(autouse=True)
def _quiet_side_effects(monkeypatch, tmp_path, settings):
  settings.MEDIA_ROOT = str(tmp_path / "media")
  monkeypatch.setattr(mapping_store, "sendUpdateCommand", lambda *a, **k: None)
  monkeypatch.setattr(mapping_store, "_save_revision_thumbnail", lambda revision: None)
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)
  monkeypatch.setenv("MAPPING_METHOD_FILES", "")


@pytest.fixture
def scene():
  return Scene.objects.create(name="rev-test")


def _store(scene, method, tmp_path, members, **kw):
  path = tmp_path / f"{method}.zip"
  sha = _zip(path, members)
  return mapping_store.store_artifact(
    scene, method, str(path), sha, kw.pop("fiducials", None),
    kw.pop("contributor", "tester"), kw.pop("map_revision_id", None), **kw)


def test_artifact_mesh_becomes_candidate_revision_not_default(scene, tmp_path):
  manifest = {"method": "mapanything", "contributor": "mapping-service",
              "mesh": {"file": "mesh.glb", "transform": {"translation": [1, 2, 3]}},
              "cameras": [{"id": "cam1", "kind": "proposed"}]}
  artifact = _store(scene, "mapanything", tmp_path, {
    "manifest.json": json.dumps(manifest), "mesh.glb": _glb_bytes()})

  scene.refresh_from_db()
  rev = artifact.map_revision
  assert rev is not None and rev.method == "mapanything"
  assert rev.transform["translation"] == [1.0, 2.0, 3.0]
  assert rev.transform["scale"] == [1.0, 1.0, 1.0]
  assert os.path.isfile(rev.file.path)
  assert artifact.manifest["cameras"][0]["id"] == "cam1"
  assert scene.default_map_revision_id is None
  assert not scene.map


def test_activate_mirrors_revision_into_scene_map(scene, tmp_path):
  artifact = _store(scene, "mapanything", tmp_path, {
    "manifest.json": json.dumps({"mesh": {"transform": {"rotation": [90, 0, 0]}}}),
    "mesh.glb": _glb_bytes()})
  rev = artifact.map_revision

  mapping_store.activate_revision(scene, rev)

  scene.refresh_from_db()
  assert scene.default_map_revision_id == rev.id
  assert scene.map.name == rev.file.name
  assert (scene.rotation_x, scene.rotation_y, scene.rotation_z) == (90.0, 0.0, 0.0)
  assert scene.map_contributor == "tester"
  assert scene.map_processed is not None


def test_store_with_activate_sets_default_in_one_call(scene, tmp_path):
  artifact = _store(scene, "vggt", tmp_path, {"mesh.glb": _glb_bytes()}, activate=True)
  scene.refresh_from_db()
  assert scene.default_map_revision_id == artifact.map_revision_id
  assert scene.map.name == artifact.map_revision.file.name


def test_zip_without_mesh_links_nothing(scene, tmp_path):
  artifact = _store(scene, "rtabmap", tmp_path, {"rtabmap.db": b"x"})
  assert artifact.map_revision is None
  assert SceneMapRevision.objects.filter(scene=scene).count() == 0


def test_legacy_glb_upload_is_user_method_and_default(scene):
  scene.map.save("legacy.glb", ContentFile(_glb_bytes()), save=False)
  Scene.objects.filter(pk=scene.pk).update(map=scene.map.name)

  rev = mapping_store.record_glb_revision(scene, None, "alice")

  scene.refresh_from_db()
  assert rev.method == "user"
  assert rev.file.name == scene.map.name
  assert scene.default_map_revision_id == rev.id


def test_manifest_fiducials_used_when_form_field_absent(scene, tmp_path):
  fid = [{"type": "apriltag", "family": "tag36h11", "id": "7", "size_m": 0.16,
          "t": [0, 0, 0]}]
  artifact = _store(scene, "orbslam3", tmp_path, {
    "manifest.json": json.dumps({"fiducials": fid}), "orbslam3.osa": b"x"})
  assert artifact.fiducials[0]["id"] == "7"


def test_eviction_is_per_method_and_protects_default(scene, tmp_path, monkeypatch):
  monkeypatch.setenv("MAPPING_HISTORY_DEPTH", "1")
  first = _store(scene, "mapanything", tmp_path, {"mesh.glb": _glb_bytes(1.0)}, activate=True)
  default_rev = first.map_revision
  (tmp_path / "mapanything.zip").unlink()
  _store(scene, "mapanything", tmp_path, {"mesh.glb": _glb_bytes(2.0)})
  _store(scene, "vggt", tmp_path, {"mesh.glb": _glb_bytes(3.0)})

  ids = set(SceneMapRevision.objects.filter(scene=scene).values_list("id", flat=True))
  # default (old mapanything), newest mapanything, newest vggt all survive
  assert default_rev.id in ids
  assert SceneMapRevision.objects.filter(scene=scene, method="mapanything").count() == 2
  assert SceneMapRevision.objects.filter(scene=scene, method="vggt").count() == 1
  scene.refresh_from_db()
  assert scene.default_map_revision_id == default_rev.id


def test_delete_revision_refuses_default_and_removes_its_artifact(scene, tmp_path):
  artifact = _store(scene, "mapanything", tmp_path, {"mesh.glb": _glb_bytes()}, activate=True)
  rev = artifact.map_revision
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    mapping_store.delete_revision(scene, rev)
  assert exc.value.status == 409

  # Once another revision is default, rejecting this candidate deletes the
  # revision and the artifact that produced it.
  other = _store(scene, "vggt", tmp_path, {"mesh.glb": _glb_bytes(2.0)}, activate=True)
  mapping_store.delete_revision(scene, rev)
  assert not SceneMapRevision.objects.filter(pk=rev.pk).exists()
  assert not SceneMappingArtifact.objects.filter(pk=artifact.pk).exists()
  assert SceneMappingArtifact.objects.filter(scene=scene, method="vggt", head=True).exists()
  scene.refresh_from_db()
  assert scene.default_map_revision_id == other.map_revision_id


def test_bad_manifest_json_is_rejected(scene, tmp_path):
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    _store(scene, "mapanything", tmp_path, {"manifest.json": b"{not json"})
  assert exc.value.status == 400
