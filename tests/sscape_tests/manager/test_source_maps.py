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
from django.db import transaction

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


@pytest.mark.parametrize("writer", ["form", "generated"])
def test_non_serializer_map_replacement_clears_stale_default(scene, writer):
  from django.core.files.uploadedfile import SimpleUploadedFile
  from manager.forms import SceneUpdateForm
  from manager.mesh_generator import MeshGenerator
  source = _upload_mesh(scene, "orbslam3")
  scene = Scene.objects.get(pk=scene.pk)
  if writer == "form":
    from django.forms.models import model_to_dict
    data = model_to_dict(scene)
    data["name"] = scene.name
    form = SceneUpdateForm(data=data, files={
      "map": SimpleUploadedFile("form.glb", _glb_bytes(2))}, instance=scene)
    assert form.is_valid(), form.errors
    form.save()
  else:
    generator = MeshGenerator.__new__(MeshGenerator)
    generator._saveMeshToScene(scene, trimesh.creation.box(extents=(2, 2, 2)), align=False)
  scene.refresh_from_db()
  assert scene.map.name != source.file.name
  assert scene.default_source_map_id is None
  assert SceneSourceMap.objects.filter(pk=source.pk).exists()


def test_non_map_model_save_preserves_default_source(scene):
  source = _upload_mesh(scene, "orbslam3")
  scene = Scene.objects.get(pk=scene.pk)
  scene.name = "renamed"
  scene.save(send_update_command=False)
  scene.refresh_from_db()
  assert scene.default_source_map_id == source.pk


def test_polycam_data_replacement_clears_stale_default(scene, tmp_path):
  source = _upload_mesh(scene, "orbslam3")
  scene = Scene.objects.get(pk=scene.pk)
  archive_path = tmp_path / "capture.zip"
  _zip(archive_path, {"capture/raw.glb": _glb_bytes(2)})
  scene.polycam_data = ContentFile(archive_path.read_bytes(), name="capture.zip")
  scene.save(send_update_command=False)
  scene.refresh_from_db()
  assert scene.map.name != source.file.name
  assert scene.default_source_map_id is None


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
  assert scene.map_processed is None


def test_activation_uses_fresh_source_and_scene_state(scene):
  source = _upload_mesh(scene, "orbslam3", contributor="")
  _upload_mesh(scene, "arkit")
  SceneSourceMap.objects.filter(pk=source.pk).update(
    transform={"translation": [4, 5, 6], "rotation": [0, 0, 0], "scale": [2, 2, 2]})
  Scene.objects.filter(pk=scene.pk).update(map_contributor="latest", map_processed="2026-10-28T00:00:00Z")
  activated = mapping_store.activate_source_map(scene, source)
  scene.refresh_from_db()
  assert activated.transform["translation"] == [4, 5, 6]
  assert scene.translation_x == 4
  assert scene.scale_x == 2
  assert scene.map_contributor == "latest"
  assert scene.map_processed is None


def test_activation_rejects_replaced_source(scene):
  source = _upload_mesh(scene, "orbslam3")
  replacement = _upload_mesh(scene, "orbslam3", 2)
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    mapping_store.activate_source_map(scene, source)
  assert exc.value.status == 404
  scene.refresh_from_db()
  assert scene.default_source_map_id == replacement.pk


def test_source_switches_cleanup_only_unreferenced_thumbnails(
    scene, monkeypatch, django_capture_on_commit_callbacks):
  first = _upload_mesh(scene, "orbslam3")
  second = _upload_mesh(scene, "arkit")
  def thumbnail(instance):
    instance.thumbnail.save("switch.png", ContentFile(b"thumbnail"), save=False)
  monkeypatch.setattr(Scene, "saveThumbnail", thumbnail)
  with django_capture_on_commit_callbacks(execute=True):
    mapping_store.activate_source_map(scene, first)
  scene.refresh_from_db()
  retained = scene.thumbnail.path
  with django_capture_on_commit_callbacks(execute=True):
    mapping_store.activate_source_map(scene, second)
    mapping_store.activate_source_map(scene, first)
  scene.refresh_from_db()
  intermediate = scene.thumbnail.path
  with django_capture_on_commit_callbacks(execute=True):
    mapping_store.activate_source_map(scene, second)
    assert os.path.exists(intermediate)
  assert not os.path.exists(intermediate)
  assert os.path.exists(retained)
  scene.refresh_from_db()
  before_rollback = scene.thumbnail.path
  with django_capture_on_commit_callbacks(execute=True):
    with pytest.raises(RuntimeError):
      with transaction.atomic():
        mapping_store.activate_source_map(scene, first)
        raise RuntimeError("rollback")
  assert os.path.exists(before_rollback)

def test_placement_edit_cleans_up_replaced_source_thumbnail(
    scene, django_capture_on_commit_callbacks):
  source = _upload_mesh(scene, "orbslam3")
  scene.thumbnail.save("old.png", ContentFile(b"old thumbnail"), save=False)
  old_thumbnail = scene.thumbnail.name
  source.thumbnail.name = old_thumbnail
  source.save(update_fields=["thumbnail"])
  scene.thumbnail.save("new.png", ContentFile(b"new thumbnail"), save=False)
  Scene.objects.filter(pk=scene.pk).update(thumbnail=scene.thumbnail.name)

  with django_capture_on_commit_callbacks(execute=True):
    mapping_store.update_active_source_map(scene)

  assert not scene.thumbnail.storage.exists(old_thumbnail)
  assert scene.thumbnail.storage.exists(scene.thumbnail.name)
  source.refresh_from_db()
  assert source.thumbnail.name == scene.thumbnail.name


@pytest.mark.django_db(transaction=True)
def test_repeated_activation_commits_keep_only_referenced_thumbnails(scene, monkeypatch, settings):
  from pathlib import Path
  first = _upload_mesh(scene, "orbslam3")
  second = _upload_mesh(scene, "arkit")
  def thumbnail(instance):
    instance.thumbnail.save("switch.png", ContentFile(b"thumbnail"), save=False)
  monkeypatch.setattr(Scene, "saveThumbnail", thumbnail)
  for source in [first, second] * 4:
    mapping_store.activate_source_map(scene, source)
  scene.refresh_from_db()
  referenced = {source.thumbnail.name for source in SceneSourceMap.objects.filter(scene=scene)}
  referenced.add(scene.thumbnail.name)
  files = {str(path.relative_to(settings.MEDIA_ROOT))
           for path in Path(settings.MEDIA_ROOT).rglob("*.png")}
  assert files == referenced
  assert len(files) == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("change", ["delete", "replace", "placement"])
def test_activation_conflicts_with_concurrent_source_change(scene, change):
  from concurrent.futures import ThreadPoolExecutor
  from django.db import connection, connections
  if connection.vendor != "postgresql":
    pytest.skip("Requires PostgreSQL row locking")
  source = _upload_mesh(scene, "orbslam3")
  _upload_mesh(scene, "arkit")

  def activate():
    try:
      return mapping_store.activate_source_map(scene, source)
    finally:
      connections.close_all()

  with ThreadPoolExecutor(max_workers=1) as pool:
    with transaction.atomic():
      mapping_store._lock_scene(scene.pk, nowait=False)
      if change == "delete":
        mapping_store.delete_source_map(scene, source)
      elif change == "replace":
        _upload_mesh(scene, "orbslam3", 2)
      else:
        SceneSourceMap.objects.filter(pk=source.pk).update(
          transform={"translation": [7, 8, 9]})
      with pytest.raises(mapping_store.MappingConflict):
        pool.submit(activate).result(timeout=10)
  if change == "placement":
    mapping_store.activate_source_map(scene, source)
    scene.refresh_from_db()
    assert scene.translation_x == 7
  else:
    with pytest.raises(mapping_store.MappingStoreError) as exc:
      mapping_store.activate_source_map(scene, source)
    assert exc.value.status == 404


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


def test_delete_source_map_checks_default_after_lock(scene):
  source_map = _upload_mesh(scene, "orbslam3")
  _upload_mesh(scene, "arkit")
  stale_scene = Scene.objects.get(pk=scene.pk)
  mapping_store.activate_source_map(scene, source_map)
  with pytest.raises(mapping_store.MappingStoreError, match="Cannot delete the default"):
    mapping_store.delete_source_map(stale_scene, source_map)
  assert SceneSourceMap.objects.filter(pk=source_map.pk).exists()
  assert os.path.isfile(source_map.file.path)


def test_delete_source_map_rejects_replaced_row(scene):
  source_map = _upload_mesh(scene, "orbslam3")
  _upload_mesh(scene, "orbslam3", 2.0)
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    mapping_store.delete_source_map(scene, source_map)
  assert exc.value.status == 404


@pytest.mark.parametrize("limit,value,members", [
  ("MAX_ARTIFACT_BYTES", 1, {"frames.bin": b"x"}),
  ("MAX_ARCHIVE_MEMBERS", 1, {"a": b"x", "b": b"x"}),
  ("MAX_MEMBER_BYTES", 1, {"frames.bin": b"xx"}),
  ("MAX_EXPANDED_BYTES", 2, {"a": b"xx", "b": b"x"}),
  ("MAX_MANIFEST_BYTES", 1, {"manifest.json": b"{}"}),
])
def test_artifact_limits_are_checked_before_decompression(scene, tmp_path, monkeypatch, limit, value, members):
  monkeypatch.setattr(mapping_store, limit, value)
  path = tmp_path / "keyframes.zip"
  sha = _zip(path, members)
  with patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("Must reject before reading")):
    with pytest.raises(mapping_store.MappingStoreError, match="exceeds"):
      mapping_store.store_artifact(scene, "keyframes", str(path), sha, None, "tester")
  assert not SceneMappingArtifact.objects.filter(scene=scene).exists()


def test_artifact_accepts_size_boundaries_and_checks_crc(scene, tmp_path, monkeypatch):
  path = tmp_path / "keyframes.zip"
  _zip(path, {"frames.bin": b"xy"})
  monkeypatch.setattr(mapping_store, "MAX_ARTIFACT_BYTES", path.stat().st_size)
  monkeypatch.setattr(mapping_store, "MAX_ARCHIVE_MEMBERS", 1)
  monkeypatch.setattr(mapping_store, "MAX_MEMBER_BYTES", 2)
  monkeypatch.setattr(mapping_store, "MAX_EXPANDED_BYTES", 2)
  mapping_store.validate_artifact_zip(path, "keyframes")
  data = path.read_bytes()
  path.write_bytes(data.replace(b"xy", b"xz", 1))
  with pytest.raises(mapping_store.ValidationError, match="Invalid"):
    mapping_store.validate_artifact_zip(path, "keyframes")


def test_corrupt_deflate_stream_is_a_validation_error(tmp_path):
  path = tmp_path / "corrupt.zip"
  with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("frames.bin", b"x" * 1000)
    info = archive.getinfo("frames.bin")
  content = bytearray(path.read_bytes())
  content[info.header_offset + 30 + len(info.filename)] = 0x07
  path.write_bytes(content)
  with pytest.raises(mapping_store.ValidationError, match="Invalid"):
    mapping_store.validate_artifact_zip(path, "keyframes")


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
  from pathlib import Path
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  old_zip = first.bundle.path
  files_before = set(Path(old_zip).parent.iterdir())
  with django_capture_on_commit_callbacks(execute=True):
    with patch.object(SceneMappingArtifact, "save", side_effect=RuntimeError("write failed")):
      with pytest.raises(RuntimeError, match="write failed"):
        _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"b"})
  assert SceneMappingArtifact.objects.filter(pk=first.pk).exists()
  assert os.path.isfile(old_zip)
  assert set(Path(old_zip).parent.iterdir()) == files_before


@pytest.mark.django_db(transaction=True)
def test_artifact_store_rejects_enclosing_transaction_before_writing(scene, tmp_path):
  from pathlib import Path
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  files_before = set(Path(first.bundle.path).parent.iterdir())
  with transaction.atomic():
    with pytest.raises(RuntimeError, match="durable atomic block"):
      _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"b"})
  assert SceneMappingArtifact.objects.get(pk=first.pk).sha256 == first.sha256
  assert set(Path(first.bundle.path).parent.iterdir()) == files_before


@pytest.mark.django_db(transaction=True)
def test_commit_failure_removes_new_artifact_file_and_preserves_old(scene, tmp_path):
  from pathlib import Path
  from django.db import connection
  first = _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"a"})
  files_before = set(Path(first.bundle.path).parent.iterdir())
  with patch.object(connection, "commit", side_effect=mapping_store.OperationalError("commit failed")):
    with pytest.raises(mapping_store.MappingConflict):
      _store(scene, "orbslam3", tmp_path, {"orbslam3.osa": b"b"})
  assert SceneMappingArtifact.objects.filter(pk=first.pk).exists()
  assert set(Path(first.bundle.path).parent.iterdir()) == files_before


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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10 ** 400])
@pytest.mark.parametrize("field", ["size_m", "t", "q"])
def test_fiducial_numbers_must_be_finite(value, field):
  fiducial = {"type": "apriltag", "family": "tag36h11", "id": "7",
              "size_m": 0.16, "t": [0, 0, 0]}
  fiducial[field] = value if field == "size_m" else [value] * (3 if field == "t" else 4)
  with pytest.raises(mapping_store.ValidationError, match="finite"):
    mapping_store.parse_fiducials([fiducial])


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_json_rejected_anywhere_in_manifest(scene, tmp_path, literal):
  first = _store(scene, "keyframes", tmp_path, {"frames.bin": b"old"})
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    _store(scene, "keyframes", tmp_path, {
      "manifest.json": '{"metadata": {"nested": [' + literal + ']}}'})
  assert exc.value.status == 400
  assert SceneMappingArtifact.objects.filter(pk=first.pk).exists()
  assert os.path.isfile(first.bundle.path)
  with pytest.raises(mapping_store.ValidationError, match="finite"):
    mapping_store.parse_fiducials('[' + literal + ']')


@pytest.mark.parametrize("contributor", [123, False, [], {}])
def test_manifest_contributor_requires_string_before_replacement(scene, tmp_path, contributor):
  first = _store(scene, "keyframes", tmp_path, {"frames.bin": b"old"})
  with pytest.raises(mapping_store.MappingStoreError) as exc:
    _store(scene, "keyframes", tmp_path, {
      "manifest.json": json.dumps({"contributor": contributor})}, contributor="")
  assert exc.value.status == 400
  assert SceneMappingArtifact.objects.filter(pk=first.pk).exists()
  assert os.path.isfile(first.bundle.path)


def test_form_contributor_overrides_manifest_and_is_truncated(scene, tmp_path):
  artifact = _store(scene, "keyframes", tmp_path, {
    "manifest.json": json.dumps({"contributor": 123})}, contributor="a" * 201)
  assert artifact.contributor == "a" * 200


@pytest.mark.parametrize("queryset", [False, True])
def test_scene_cascade_cleans_all_mapping_files_after_commit(
    scene, tmp_path, django_capture_on_commit_callbacks, queryset):
  first = _upload_mesh(scene, "orbslam3")
  first.thumbnail.save("old.png", ContentFile(b"thumbnail"), save=True)
  second = _upload_mesh(scene, "arkit")
  artifact = _store(scene, "keyframes", tmp_path, {"frames.bin": b"x"})
  scene.thumbnail = first.thumbnail.name
  Scene.objects.filter(pk=scene.pk).update(thumbnail=scene.thumbnail.name)
  paths = [first.file.path, first.thumbnail.path, second.file.path, artifact.bundle.path]
  with django_capture_on_commit_callbacks(execute=True):
    if queryset:
      Scene.objects.filter(pk=scene.pk).delete()
    else:
      scene.delete()
    assert all(os.path.isfile(path) for path in paths)
  assert all(not os.path.exists(path) for path in paths)


def test_mapping_deletions_preserve_files_on_rollback(
    scene, tmp_path, django_capture_on_commit_callbacks):
  source = _upload_mesh(scene, "orbslam3")
  artifact = _store(scene, "keyframes", tmp_path, {"frames.bin": b"x"})
  with django_capture_on_commit_callbacks(execute=True):
    with pytest.raises(RuntimeError):
      with transaction.atomic():
        scene.delete()
        raise RuntimeError("rollback")
  assert os.path.isfile(source.file.path)
  assert os.path.isfile(artifact.bundle.path)
  assert SceneSourceMap.objects.filter(pk=source.pk).exists()
  assert SceneMappingArtifact.objects.filter(pk=artifact.pk).exists()


def test_shared_mapping_files_survive_until_last_reference_deleted(
    scene, django_capture_on_commit_callbacks):
  source = _upload_mesh(scene, "orbslam3")
  source.thumbnail.save("shared.png", ContentFile(b"thumbnail"), save=True)
  other = Scene.objects.create(name="sharing")
  shared = SceneSourceMap.objects.create(
    scene=other, method="arkit", file=source.file.name, thumbnail=source.thumbnail.name,
    sha256=source.sha256)
  paths = [source.file.path, source.thumbnail.path]
  with django_capture_on_commit_callbacks(execute=True):
    scene.delete()
  assert all(os.path.isfile(path) for path in paths)
  with django_capture_on_commit_callbacks(execute=True):
    shared.delete()
  assert all(not os.path.exists(path) for path in paths)


def test_explicit_artifact_delete_is_deferred_and_rollback_safe(
    scene, tmp_path, django_capture_on_commit_callbacks):
  artifact = _store(scene, "keyframes", tmp_path, {"frames.bin": b"x"})
  path = artifact.bundle.path
  with django_capture_on_commit_callbacks(execute=True):
    with pytest.raises(RuntimeError):
      with transaction.atomic():
        mapping_store.delete_artifact(scene, "keyframes")
        raise RuntimeError("rollback")
  assert SceneMappingArtifact.objects.filter(pk=artifact.pk).exists()
  assert os.path.isfile(path)
  with django_capture_on_commit_callbacks(execute=True):
    mapping_store.delete_artifact(scene, "keyframes")
    assert os.path.isfile(path)
  assert not os.path.exists(path)
