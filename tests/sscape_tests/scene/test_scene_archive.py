# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene archive identity, hierarchy, and credential handling."""

import asyncio
import copy
import io
import json
import secrets
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.api import ManageThing, SceneImportAPIView
from manager.models import ChildScene, Scene
from manager.scene_archive import (
  LINK_FIELDS, SceneArchiveSerializer, matching_scene, remote_link_data, validate_archive,
  validate_existing_link, walk_scenes,
)
from manager.scene_import import ImportScene
from manager.serializers import SceneImportSerializer
from scene_common.rest_client import RESTResult


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_archive_map_packaging():
  result = subprocess.run(
    ["node", "--test", str(Path(__file__).with_name("test_scene_archive_maps.mjs"))],
    capture_output=True, text=True, timeout=30,
  )
  assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def archive(tmp_path):
  def make_scene(name):
    uid = str(uuid4())
    filename = f"{uid}.png"
    (tmp_path / filename).write_bytes(b"map")
    return {"uid": uid, "name": name, "scale": 100, "map_file": filename, "archive_version": 2}
  root = make_scene("Parent")
  child = make_scene("Local")
  child["link"] = {"child_type": "local", "retrack": False, "transform_type": "matrix", "transform4": 7}
  root["children"] = [child]
  remote_id = str(uuid4())
  root["remote_children"] = [{
    "child_type": "remote", "remote_child_id": remote_id, "child_name": "Remote",
    "host_name": "remote.example", "retrack": False, "transform_type": "matrix", "transform4": 12,
  }]
  credentials = {remote_id: {"mqtt_username": secrets.token_hex(8), "mqtt_password": secrets.token_hex(16)}}
  return root, credentials


@pytest.fixture
def no_existing_scenes():
  with patch("manager.scene_archive.Scene.objects") as scenes, \
       patch("manager.scene_archive.ChildScene.objects") as links, \
       patch("rest_framework.validators.qs_exists", return_value=False):
    scenes.filter.return_value.exists.return_value = False
    links.filter.return_value.exists.return_value = False
    yield scenes, links


def test_validate_mixed_hierarchy(archive, tmp_path, no_existing_scenes):
  scene, credentials = archive
  validate_archive(scene, str(tmp_path), True, credentials)


def test_legacy_local_only_archive_remains_supported(archive, tmp_path, no_existing_scenes):
  scene, _ = archive
  scene.pop("remote_children")
  for node in walk_scenes(scene):
    node.pop("archive_version")
    (tmp_path / node.pop("map_file")).rename(tmp_path / f"{node['name']}.png")
  validate_archive(scene, str(tmp_path), False, {})


@pytest.mark.parametrize("problem", [
  "credentials", "map", "uuid", "legacy", "remote_duplicate", "local_uuid_duplicate", "transform",
])
def test_preflight_rejects_invalid_hierarchy(archive, tmp_path, no_existing_scenes, problem):
  scene, credentials = archive
  scenes, _ = no_existing_scenes
  if problem == "credentials":
    credentials = {}
  elif problem == "map":
    scene["children"][0]["map_file"] = "missing.png"
  elif problem == "uuid":
    scenes.filter.return_value.exists.side_effect = [False, True]
  elif problem == "legacy":
    scene["children"] = [{"name": "Old remote reference"}]
  elif problem == "remote_duplicate":
    scene["remote_children"] *= 2
  elif problem == "transform":
    scene["children"][0]["link"]["transform4"] = "not-a-number"
  else:
    scene["children"][0]["uid"] = scene["uid"]
  with pytest.raises(ValueError):
    validate_archive(scene, str(tmp_path), True, credentials)


def test_remote_link_allowlist_excludes_archive_credentials(archive):
  scene, credentials = archive
  link = scene["remote_children"][0]
  original = copy.deepcopy(link)
  link["mqtt_password"] = "ignored-archive-value"
  link["cached_rois"] = [{"name": "stale"}]
  data = remote_link_data(link, credentials)
  assert data["mqtt_password"] == credentials[link["remote_child_id"]]["mqtt_password"]
  assert data["transform4"] == original["transform4"]
  assert data["retrack"] is False
  assert "cached_rois" not in data


def test_remote_export_has_no_secrets_or_caches(archive):
  scene, credentials = archive
  link = SimpleNamespace(**{key: 1 for key in LINK_FIELDS})
  for key, value in scene["remote_children"][0].items():
    setattr(link, key, value)
  link.mqtt_password = next(iter(credentials.values()))["mqtt_password"]
  link.cached_rois = [{"name": "cache"}]
  instance = MagicMock()
  instance.children.filter.return_value = [link]
  with patch("manager.serializers.SceneSerializer.to_representation", return_value={"uid": scene["uid"]}):
    exported = SceneArchiveSerializer().to_representation(instance)
  reference = exported["remote_children"][0]
  assert reference["remote_child_id"] == link.remote_child_id
  assert reference["transform4"] == link.transform4
  assert "mqtt_password" not in reference
  assert "cached_rois" not in reference


@pytest.mark.parametrize("restore_ids", [False, True])
def test_scene_creation_identity_is_opt_in(archive, tmp_path, restore_ids):
  scene, _ = archive
  importer = ImportScene.__new__(ImportScene)
  importer.restore_ids = restore_ids
  with patch("manager.scene_import.SceneSerializer") as serializer:
    serializer.return_value.save.return_value.pk = UUID(scene["uid"])
    result = importer.createSceneMap(scene, str(tmp_path / scene["map_file"]))
  assert not result.errors
  expected = {"id": UUID(scene["uid"])} if restore_ids else {}
  serializer.return_value.save.assert_called_once_with(**expected)


def test_import_mixed_hierarchy_restores_links(archive, tmp_path, no_existing_scenes):
  scene, credentials = archive
  original = copy.deepcopy(scene)
  (tmp_path / "archive.json").write_text(json.dumps(scene))
  importer = ImportScene.__new__(ImportScene)
  importer.extract_dir = str(tmp_path)
  importer.badZipfile = False
  importer.restore_ids = True
  importer.reuse_existing = False
  importer.remote_credentials = credentials
  importer.rest = MagicMock()
  success = RESTResult(201)
  importer.rest.updateScene.return_value = success
  importer.rest.createChildScene.return_value = success

  def create(data, path):
    result = RESTResult(201)
    result["uid"] = data["uid"]
    return result

  with patch.object(importer, "createSceneMap", side_effect=create):
    summary = asyncio.run(importer.loadScene())
  assert summary["scene"] is None
  calls = [call.args[0] for call in importer.rest.createChildScene.call_args_list]
  remote, local = calls
  assert remote["parent"] == scene["uid"]
  assert remote["remote_child_id"] == scene["remote_children"][0]["remote_child_id"]
  assert remote["transform4"] == 12
  assert remote["mqtt_password"] == next(iter(credentials.values()))["mqtt_password"]
  assert local["parent"] == scene["uid"]
  assert local["child"] == scene["children"][0]["uid"]
  assert local["transform4"] == 7
  assert local["retrack"] is False
  assert scene == original


def test_missing_credentials_fails_before_scene_creation(archive, tmp_path, no_existing_scenes):
  scene, _ = archive
  (tmp_path / "archive.json").write_text(json.dumps(scene))
  importer = ImportScene.__new__(ImportScene)
  importer.extract_dir = str(tmp_path)
  importer.badZipfile = False
  importer.restore_ids = False
  importer.reuse_existing = False
  importer.remote_credentials = {}
  with patch.object(importer, "createSceneMap") as create:
    summary = asyncio.run(importer.loadScene())
  assert "Missing MQTT credentials" in str(summary["scene"])
  create.assert_not_called()


@pytest.mark.parametrize("content", [b"not-json", b"[]", b'{"bad-uuid": {}}'])
def test_import_options_reject_invalid_credentials(content):
  serializer = SceneImportSerializer(data={
    "zipFile": SimpleUploadedFile("scene.zip", b"zip"),
    "remote_credentials": SimpleUploadedFile("credentials.json", content),
  })
  assert not serializer.is_valid()
  assert "remote_credentials" in serializer.errors


def test_import_options_parse_restore_and_credentials(archive):
  _, credentials = archive
  serializer = SceneImportSerializer(data={
    "zipFile": SimpleUploadedFile("scene.zip", b"zip"),
    "restore_ids": "true",
    "reuse_existing": "true",
    "remote_credentials": SimpleUploadedFile("credentials.json", json.dumps(credentials).encode()),
  })
  assert serializer.is_valid(), serializer.errors
  assert serializer.validated_data["restore_ids"] is True
  assert serializer.validated_data["reuse_existing"] is True
  assert serializer.validated_data["remote_credentials"] == credentials


@pytest.mark.parametrize("superuser", [True, False])
def test_import_api_passes_options_only_for_superusers(archive, tmp_path, superuser):
  _, credentials = archive
  archive_path = tmp_path / "scene.zip"
  archive_path.write_bytes(b"zip")
  request = APIRequestFactory().post("/", {
    "zipFile": SimpleUploadedFile("scene.zip", b"zip"),
    "restore_ids": "true",
    "reuse_existing": "true",
    "remote_credentials": SimpleUploadedFile("credentials.json", json.dumps(credentials).encode()),
  }, format="multipart")
  user = SimpleNamespace(is_authenticated=True, is_superuser=superuser)
  force_authenticate(request, user=user, token=SimpleNamespace(key=secrets.token_hex(16)))
  with patch("manager.api.SceneImport.objects.create") as store, \
       patch("manager.api.ImportScene") as importer:
    store.return_value.zipFile.path = str(archive_path)
    importer.return_value.loadScene = AsyncMock(return_value={"scene": None})
    response = SceneImportAPIView.as_view()(request)
  if superuser:
    assert response.status_code == 201
    assert importer.call_args.kwargs == {
      "restore_ids": True, "remote_credentials": credentials, "reuse_existing": True,
    }
  else:
    assert response.status_code == 403
    store.assert_not_called()
    importer.assert_not_called()


@pytest.mark.parametrize("restore_ids", [False, True])
def test_reuse_identity_rejects_mismatched_names_or_restore_uuid(restore_ids):
  scene_id = uuid4()
  node = {"name": "Child", "uid": str(scene_id)}
  existing = SimpleNamespace(pk=uuid4())
  with patch("manager.scene_archive.Scene.objects") as scenes:
    scenes.filter.return_value.first.side_effect = [None, existing]
    with pytest.raises(ValueError, match="different scene"):
      matching_scene(node, restore_ids)
  with patch("manager.scene_archive.Scene.objects") as scenes:
    scenes.filter.return_value.first.side_effect = [existing, None]
    if restore_ids:
      with pytest.raises(ValueError, match="does not match"):
        matching_scene(node, True)
    else:
      assert matching_scene(node, False) is existing


@pytest.mark.parametrize("conflict", ["parent", "transform", "retrack", "credentials"])
def test_reuse_never_overwrites_conflicting_links(conflict):
  parent_id = uuid4()
  credentials = {"mqtt_username": secrets.token_hex(8), "mqtt_password": secrets.token_hex(16)}
  data = {
    "child_type": "remote", "parent_id": parent_id, "remote_child_id": uuid4(),
    "host_name": "remote.example", "child_name": "Remote", **credentials,
  }
  existing = ChildScene(**data)
  validate_existing_link(existing, data, parent_id)
  if conflict == "parent":
    existing.parent_id = uuid4()
  elif conflict == "transform":
    existing.transform4 = 7
  elif conflict == "retrack":
    existing.retrack = False
  else:
    existing.mqtt_password = secrets.token_hex(16)
  with pytest.raises(ValueError):
    validate_existing_link(existing, data, parent_id)


def test_resource_exception_summary_is_json_serializable():
  importer = ImportScene.__new__(ImportScene)
  create = MagicMock(side_effect=requests.ConnectionError("transport failed"))
  created, errors = asyncio.run(importer.bulk_create([{"name": "Resource"}], "scene-id", create))
  assert created is None
  rendered = JSONRenderer().render({"regions": errors})
  assert b"ConnectionError" in rendered
  assert b"transport failed" not in rendered


@pytest.fixture
def hierarchy_import(tmp_path, transactional_db, settings, archive):
  """Exercise the actual ORM and REST views with only network transport replaced."""
  settings.MEDIA_ROOT = str(tmp_path / "media")
  scene, credentials = archive
  for index in range(2):
    child = copy.deepcopy(scene["children"][0])
    child.update({"name": f"Child {index}", "uid": str(uuid4())})
    child["map_file"] = child["uid"] + ".png"
    scene["children"].append(child)
  image = io.BytesIO()
  Image.new("RGB", (10, 10)).save(image, format="PNG")

  def rest_call(kind, data, uid=None):
    request = APIRequestFactory().post("/", data, format="json")
    force_authenticate(request, user=SimpleNamespace(is_authenticated=True, is_superuser=True))
    response = ManageThing.as_view()(request, thing_type=kind, uid=uid)
    result = RESTResult(response.status_code, errors=response.data if response.status_code >= 400 else None)
    if not result.errors:
      result.update(response.data)
    return result

  def make_importer(node, restore_ids=False, reuse_existing=True):
    path = tmp_path / f"{uuid4()}.zip"
    with zipfile.ZipFile(path, "w") as output:
      output.writestr("scene.json", json.dumps(node))
      for descendant in walk_scenes(node):
        output.writestr(descendant["map_file"], image.getvalue())
    importer = ImportScene(str(path), "", restore_ids=restore_ids,
                           remote_credentials=credentials, reuse_existing=reuse_existing)
    importer.rest = MagicMock()
    importer.rest.updateScene.side_effect = lambda uid, data: rest_call("scene", data, uid)
    importer.rest.createChildScene.side_effect = lambda data: rest_call("child", data)
    return importer
  return scene, make_importer


def assert_import_success(importer):
  summary = asyncio.run(importer.loadScene())
  assert not any(summary[key] for key in (
    "scene", "cameras", "regions", "tripwires", "sensors", "calibration_markers",
  )), summary


@pytest.mark.parametrize("order", ["children_first", "parent_first"])
@pytest.mark.parametrize("restore_ids", [False, True])
def test_reuse_import_order_is_independent(hierarchy_import, order, restore_ids):
  scene, make_importer = hierarchy_import
  nodes = [*scene["children"], scene] if order == "children_first" else [scene, *scene["children"]]
  for node in nodes:
    assert_import_success(make_importer(node, restore_ids))
  assert Scene.objects.count() == 4
  parent = Scene.objects.get(name=scene["name"])
  assert parent.children.filter(child_type="local").count() == 3
  assert parent.children.filter(child_type="remote").count() == 1
  for child in scene["children"]:
    link = ChildScene.objects.get(child__name=child["name"])
    assert link.parent_id == parent.pk
    assert link.transform4 == 7
    assert link.retrack is False
  existing = Scene.objects.get(name=scene["children"][0]["name"])
  Scene.objects.filter(pk=existing.pk).update(scale=23)
  before_maps = dict(Scene.objects.values_list("name", "map"))
  retry = make_importer(scene, restore_ids)
  assert_import_success(retry)
  retry.rest.updateScene.assert_not_called()
  retry.rest.createCamera.assert_not_called()
  existing.refresh_from_db()
  assert existing.scale == 23
  assert dict(Scene.objects.values_list("name", "map")) == before_maps
  assert ChildScene.objects.count() == 4


def test_reuse_retry_restores_all_links_after_second_child_failure(hierarchy_import):
  scene, make_importer = hierarchy_import
  importer = make_importer(scene)
  create_link = importer.rest.createChildScene.side_effect

  def fail_second_child(data):
    if data.get("child") and Scene.objects.get(pk=data["child"]).name == scene["children"][1]["name"]:
      raise requests.ConnectionError("unavailable")
    return create_link(data)

  importer.rest.createChildScene.side_effect = fail_second_child
  summary = asyncio.run(importer.loadScene())
  assert "Cannot contact child-link API" in str(summary["scene"])
  JSONRenderer().render(summary)
  assert Scene.objects.count() == 3
  assert ChildScene.objects.filter(child_type="local").count() == 1
  assert_import_success(make_importer(scene))
  assert Scene.objects.count() == 4
  assert ChildScene.objects.filter(child_type="local").count() == 3


@pytest.mark.parametrize("conflict", ["parent", "transform"])
def test_reuse_conflicts_fail_preflight_without_writes(hierarchy_import, conflict):
  scene, make_importer = hierarchy_import
  assert_import_success(make_importer(scene))
  link = ChildScene.objects.get(child__name=scene["children"][0]["name"])
  if conflict == "parent":
    other = Scene.objects.create(name="Other parent")
    ChildScene.objects.filter(pk=link.pk).update(parent=other)
  else:
    ChildScene.objects.filter(pk=link.pk).update(transform4=99)
  scene["children"].append({
    "name": "Must not be created", "uid": str(uuid4()), "map_file": "new.png", "scale": 100,
  })
  summary = asyncio.run(make_importer(scene).loadScene())
  assert summary["scene"]
  assert not Scene.objects.filter(name="Must not be created").exists()
