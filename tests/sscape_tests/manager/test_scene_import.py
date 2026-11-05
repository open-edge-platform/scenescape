# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for camera handling in manager.scene_import.ImportScene."""

import asyncio
from unittest.mock import MagicMock

import pytest
import requests

from manager import scene_import
from manager.scene_import import (
  DEFAULT_IMPORT_REST_TIMEOUT_S, IMPORT_REST_TIMEOUT_ENV_VAR, ImportScene, get_import_rest_timeout,
)
from scene_common.rest_client import RESTResult

SCENE_ID = "scene-uid"
PIPELINE = "videotestsrc ! appsink"


def make_importer():
  importer = ImportScene.__new__(ImportScene)
  importer.rest = MagicMock()
  return importer


def ok_result(**content):
  result = RESTResult(statusCode=200)
  result.update(content)
  return result


def test_build_camera_items_keeps_camera_pipeline():
  importer = make_importer()
  data = {"cameras": [{
    "uid": "cam1", "name": "Cam 1",
    "use_camera_pipeline": True, "camera_pipeline": PIPELINE,
  }]}

  item = importer.build_camera_items(data)[0]

  assert item["use_camera_pipeline"] is True
  assert item["camera_pipeline"] == PIPELINE


def test_build_camera_items_omits_absent_camera_pipeline():
  importer = make_importer()
  data = {"cameras": [{"uid": "cam1", "name": "Cam 1"}]}

  item = importer.build_camera_items(data)[0]

  assert "camera_pipeline" not in item


def test_relink_sends_camera_pipeline_to_orphaned_camera():
  importer = make_importer()
  importer.rest.getCameras.return_value = ok_result(
    results=[{"uid": "local-cam", "name": "Cam 1"}])
  importer.rest.updateCamera.return_value = ok_result(uid="local-cam", scene=SCENE_ID)
  items = importer.build_camera_items({"cameras": [{
    "uid": "cam1", "name": "Cam 1",
    "use_camera_pipeline": True, "camera_pipeline": PIPELINE,
  }]})

  to_create, relinked, errors = asyncio.run(
    importer.relink_orphaned_cameras(items, SCENE_ID))

  assert not to_create
  assert not errors
  assert relinked == [{"uid": "local-cam", "scene": SCENE_ID}]
  uid, payload = importer.rest.updateCamera.call_args.args
  assert uid == "local-cam"
  assert payload["camera_pipeline"] == PIPELINE
  assert "sensor_id" not in payload


def test_relink_lookup_failure_is_reported_per_camera():
  importer = make_importer()
  importer.rest.getCameras.side_effect = [
    requests.exceptions.ConnectionError("connection refused"),
    ok_result(results=[]),
  ]
  items = [{"name": "Cam 1"}, {"name": "Cam 2"}]

  to_create, relinked, errors = asyncio.run(
    importer.relink_orphaned_cameras(items, SCENE_ID))

  assert len(errors) == 1
  error, item = errors[0]
  assert isinstance(error, requests.exceptions.ConnectionError)
  assert item["name"] == "Cam 1"
  assert [i["name"] for i in to_create] == ["Cam 2"]
  assert not relinked
  importer.rest.updateCamera.assert_not_called()


def test_relink_skips_camera_owned_by_another_scene():
  importer = make_importer()
  importer.rest.getCameras.return_value = ok_result(
    results=[{"uid": "other", "name": "Cam 1", "scene": "other-scene"}])

  to_create, relinked, errors = asyncio.run(
    importer.relink_orphaned_cameras([{"name": "Cam 1"}], SCENE_ID))

  assert [i["name"] for i in to_create] == ["Cam 1"]
  assert not relinked
  assert not errors
  importer.rest.updateCamera.assert_not_called()


@pytest.mark.parametrize("raw, expected", [
  (None, DEFAULT_IMPORT_REST_TIMEOUT_S),
  ("", DEFAULT_IMPORT_REST_TIMEOUT_S),
  ("900", 900),
  (" 45 ", 45),
  ("0", DEFAULT_IMPORT_REST_TIMEOUT_S),
  ("-5", DEFAULT_IMPORT_REST_TIMEOUT_S),
  ("soon", DEFAULT_IMPORT_REST_TIMEOUT_S),
  ("1.5", DEFAULT_IMPORT_REST_TIMEOUT_S),
])
def test_get_import_rest_timeout(monkeypatch, raw, expected):
  if raw is None:
    monkeypatch.delenv(IMPORT_REST_TIMEOUT_ENV_VAR, raising=False)
  else:
    monkeypatch.setenv(IMPORT_REST_TIMEOUT_ENV_VAR, raw)

  assert get_import_rest_timeout() == expected


def test_import_rest_client_uses_import_timeout(monkeypatch):
  """The internal REST client must outlast slow GLB processing, not use RESTClient's 10 s."""
  rest_client = MagicMock()
  monkeypatch.setattr(scene_import, "RESTClient", rest_client)
  monkeypatch.setattr(ImportScene, "extractZip", lambda self: None)
  monkeypatch.setenv(IMPORT_REST_TIMEOUT_ENV_VAR, "900")

  ImportScene("/tmp/scene.zip", "token")

  assert rest_client.call_args.kwargs["timeout"] == 900


def test_scene_settings_timeout_is_reported_not_raised():
  importer = make_importer()
  importer.rest.updateScene.side_effect = requests.exceptions.ReadTimeout("read timed out")
  summary = {}

  asyncio.run(importer.populate_scene(
    {"name": "Big", "mesh_translation": [1, 2, 3], "cameras": [{"uid": "cam1"}]},
    SCENE_ID, summary))

  assert summary["scene"] == {"scene": ["Scene settings update failed (ReadTimeout)"]}
  importer.rest.createCamera.assert_not_called()


def test_scene_settings_update_success_continues_import():
  importer = make_importer()
  importer.rest.updateScene.return_value = ok_result(uid=SCENE_ID)
  importer.rest.getCameras.return_value = ok_result(results=[])
  importer.rest.createCamera.return_value = ok_result(uid="cam1")
  summary = {}

  asyncio.run(importer.populate_scene(
    {"name": "Big", "mesh_translation": [1, 2, 3], "cameras": [{"uid": "cam1", "name": "Cam 1"}]},
    SCENE_ID, summary))

  assert summary["scene"] is None
  assert summary["cameras_created"] == [{"uid": "cam1"}]
