# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene archive identity, hierarchy, and credential handling."""

import asyncio
import copy
import json
import secrets
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.api import SceneImportAPIView
from manager.scene_archive import (
  LINK_FIELDS, SceneArchiveSerializer, remote_link_data, validate_archive, walk_scenes,
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
    "remote_credentials": SimpleUploadedFile("credentials.json", json.dumps(credentials).encode()),
  })
  assert serializer.is_valid(), serializer.errors
  assert serializer.validated_data["restore_ids"] is True
  assert serializer.validated_data["remote_credentials"] == credentials


@pytest.mark.parametrize("superuser", [True, False])
def test_import_api_passes_options_only_for_superusers(archive, tmp_path, superuser):
  _, credentials = archive
  archive_path = tmp_path / "scene.zip"
  archive_path.write_bytes(b"zip")
  request = APIRequestFactory().post("/", {
    "zipFile": SimpleUploadedFile("scene.zip", b"zip"),
    "restore_ids": "true",
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
    assert importer.call_args.kwargs == {"restore_ids": True, "remote_credentials": credentials}
  else:
    assert response.status_code == 403
    store.assert_not_called()
    importer.assert_not_called()
