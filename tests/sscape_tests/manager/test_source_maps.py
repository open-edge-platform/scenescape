# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-method source maps: one current mesh and one artifact zip per method; Scene.map mirrors the default."""

import hashlib
import os
import json
import zipfile
from unittest.mock import patch

import pytest
import trimesh
from django.core.files.base import ContentFile

from manager import mapping_store
from manager.models import Scene, SceneMappingArtifact, SceneSourceMap

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
  monkeypatch.setattr(Scene, "saveThumbnail", lambda self: None)


@pytest.fixture
def scene():
  return Scene.objects.create(name="source-map-test")


def _store(scene, method, tmp_path, members, **kw):
  path = tmp_path / f"{method}.zip"
  if path.exists():
    path.unlink()
  sha = _zip(path, members)
  return mapping_store.store_artifact(
    scene, method, str(path), sha, kw.pop("fiducials", None),
    kw.pop("contributor", "tester"))


def _upload_mesh(scene, method, size=1.0, contributor="tester"):
  """Mesh upload as the Scene PUT path does it: Scene.map first, then record."""
  scene.map.save(f"{method}.glb", ContentFile(_glb_bytes(size)), save=False)
  Scene.objects.filter(pk=scene.pk).update(map=scene.map.name)
  return mapping_store.record_glb_source_map(scene, method, contributor)


def _source_map(scene, method):
  return SceneSourceMap.objects.filter(scene=scene, method=method).first()


def test_direct_glb_upload_is_user_method_and_default(scene):
  source_map = _upload_mesh(scene, None, contributor="alice")

  scene.refresh_from_db()
  assert source_map.method == "user"
  assert source_map.file.name == scene.map.name
  assert source_map.contributor == "alice"
  assert scene.default_source_map_id == source_map.id


def test_mesh_upload_replaces_only_its_method(scene):
  first = _upload_mesh(scene, "orbslam3", 1.0)
  other = _upload_mesh(scene, "arkit", 2.0)
  replacement = _upload_mesh(scene, "orbslam3", 3.0)

  assert replacement.id != first.id
  assert not SceneSourceMap.objects.filter(pk=first.id).exists()
  assert SceneSourceMap.objects.filter(pk=other.id).exists()
  assert SceneSourceMap.objects.filter(scene=scene, method="orbslam3").count() == 1
  scene.refresh_from_db()
  assert scene.default_source_map_id == replacement.id
  assert scene.map.name == replacement.file.name


def test_activate_mirrors_source_map_into_scene_map(scene):
  first = _upload_mesh(scene, "orbslam3", contributor="handheld")
  Scene.objects.filter(pk=scene.pk).update(rotation_x=90.0)
  scene.refresh_from_db()
  SceneSourceMap.objects.filter(pk=first.pk).update(
    transform={"translation": [1, 2, 3], "rotation": [90, 0, 0], "scale": [1, 1, 1]})
  first.refresh_from_db()
  _upload_mesh(scene, "arkit", contributor="phone")

  mapping_store.activate_source_map(scene, first)

  scene.refresh_from_db()
  assert scene.default_source_map_id == first.id
  assert scene.map.name == first.file.name
  assert (scene.translation_x, scene.translation_y, scene.translation_z) == (1.0, 2.0, 3.0)
  assert (scene.rotation_x, scene.rotation_y, scene.rotation_z) == (90.0, 0.0, 0.0)
  assert scene.map_contributor == "handheld"
  assert scene.map_processed is not None


def test_delete_source_map_refuses_default_and_removes_its_artifact(scene, tmp_path):
  _upload_mesh(scene, "orbslam3")
  artifact = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"x"})
  source_map = _source_map(scene, "orbslam3")
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    mapping_store.delete_source_map(scene, source_map)
  assert exc.value.status == 409

  _upload_mesh(scene, "arkit")
  mapping_store.delete_source_map(scene, source_map)
  assert not SceneSourceMap.objects.filter(pk=source_map.pk).exists()
  assert not SceneMappingArtifact.objects.filter(pk=artifact.pk).exists()
  scene.refresh_from_db()
  assert scene.default_source_map_id == _source_map(scene, "arkit").id


def test_mesh_upload_keeps_methods_artifact(scene, tmp_path):
  artifact = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"x"})
  _upload_mesh(scene, "orbslam3")
  _upload_mesh(scene, "orbslam3", 2.0)
  # The resume zip belongs to the method, not to a particular mesh.
  assert SceneMappingArtifact.objects.filter(pk=artifact.pk).exists()


def test_artifact_replacement_is_per_method(scene, tmp_path):
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  other = _store(scene, "arkit", tmp_path, {"arworldmap.bin": b"b"})
  replacement = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"c"})

  assert not SceneMappingArtifact.objects.filter(pk=first.pk).exists()
  assert SceneMappingArtifact.objects.filter(pk=other.pk).exists()
  assert SceneMappingArtifact.objects.get(scene=scene, method="orbslam3").pk == replacement.pk
  assert SceneSourceMap.objects.filter(scene=scene).count() == 0


def test_artifact_replacement_removes_old_zip_after_commit(scene, tmp_path, django_capture_on_commit_callbacks):
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  old_zip = first.bundle.path
  with django_capture_on_commit_callbacks(execute=True):
    replacement = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"b"})
    assert os.path.isfile(old_zip)
  assert not os.path.exists(old_zip)
  assert os.path.isfile(replacement.bundle.path)


def test_failed_artifact_replacement_keeps_row_and_file(scene, tmp_path, django_capture_on_commit_callbacks):
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  old_zip = first.bundle.path
  with django_capture_on_commit_callbacks(execute=True):
    with patch.object(SceneMappingArtifact, "save", side_effect=RuntimeError("write failed")):
      with pytest.raises(RuntimeError, match="write failed"):
        _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"b"})
  assert SceneMappingArtifact.objects.filter(pk=first.pk).exists()
  assert os.path.isfile(old_zip)


def test_invalid_artifact_preserves_existing_set(scene, tmp_path):
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    _store(scene, "orbslam3", tmp_path, {"manifest.json": "not-json", "orbslam3.osa": b"b"})
  assert exc.value.status == 400
  assert SceneMappingArtifact.objects.filter(pk=first.pk).exists()


def test_required_member_is_enforced_for_known_methods(scene, tmp_path):
  with pytest.raises(mapping_store.MappingStoreError, match="must contain orbslam3.osa"):
    _store(scene, "orbslam3", tmp_path, {"other.bin": b"a"})
  with pytest.raises(mapping_store.MappingStoreError, match="is empty"):
    _store(scene, "rtabmap", tmp_path, {"rtabmap.db": b""})
  assert _store(scene, "keyframes", tmp_path, {"anything.bin": b"a"}).method == "keyframes"


def test_manifest_fiducials_and_contributor_used_when_form_fields_absent(scene, tmp_path):
  fid = [{"type": "apriltag", "family": "tag36h11", "id": "7", "size_m": 0.16,
          "t": [0, 0, 0]}]
  manifest = {"fiducials": fid, "contributor": "handheld-01",
              "cameras": [{"id": "cam1", "kind": "proposed"}]}
  artifact = _store(scene, "keyframes", tmp_path, {
    "manifest.json": json.dumps(manifest), "frames.bin": b"x"}, contributor="")
  assert artifact.fiducials[0]["id"] == "7"
  assert artifact.contributor == "handheld-01"
  assert artifact.manifest["cameras"][0]["id"] == "cam1"


def test_delete_artifact_keeps_methods_mesh(scene, tmp_path):
  _upload_mesh(scene, "rtabmap")
  _store(scene, "rtabmap", tmp_path, {"rtabmap.db": b"x"})
  assert mapping_store.delete_artifact(scene, "rtabmap") is True
  assert not SceneMappingArtifact.objects.filter(scene=scene, method="rtabmap").exists()
  assert _source_map(scene, "rtabmap") is not None
  assert mapping_store.delete_artifact(scene, "rtabmap") is False
