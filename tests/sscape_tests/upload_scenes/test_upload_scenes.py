# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for tools/upload_scenes/uploader.py."""

import json
import zipfile
from unittest.mock import MagicMock

import pytest
import requests

import uploader
from uploader import (
  RESOURCE_KEYS, SceneScapeClient, parse_auth, read_scene_from_zip,
  upload_all, upload_assets, upload_calibration_markers, upload_one,
  upload_scene, wait_for_database,
)


class TestParseAuth:
  def test_user_password_string(self):
    assert parse_auth("alice:secret") == ("alice", "secret")

  def test_auth_file(self, tmp_path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"user": "alice", "password": "secret"}))
    assert parse_auth(str(auth_file)) == ("alice", "secret")

  def test_missing_colon_raises(self):
    with pytest.raises(ValueError):
      parse_auth("no-colon-here")

  def test_empty_user_raises(self):
    with pytest.raises(ValueError):
      parse_auth(":secret")

  def test_auth_file_missing_password_key_raises(self, tmp_path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"user": "alice"}))
    with pytest.raises(KeyError):
      parse_auth(str(auth_file))


class TestReadSceneFromZip:
  def test_valid_scene(self, scene_zip):
    zip_path = scene_zip({"name": "Demo"})
    assert read_scene_from_zip(str(zip_path)) == {"name": "Demo"}

  def test_zero_json_files(self, scene_zip):
    zip_path = scene_zip(None, extra_files={"readme.txt": "hi"})
    assert read_scene_from_zip(str(zip_path)) is None

  def test_two_json_files(self, scene_zip):
    zip_path = scene_zip({"name": "Demo"}, extra_files={"extra.json": "{}"})
    assert read_scene_from_zip(str(zip_path)) is None

  def test_corrupt_zip(self, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert read_scene_from_zip(str(bad)) is None

  def test_missing_file(self, tmp_path):
    assert read_scene_from_zip(str(tmp_path / "missing.zip")) is None

  def test_json_not_a_dict(self, tmp_path):
    zip_path = tmp_path / "scene.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
      archive.writestr("scene.json", json.dumps([1, 2, 3]))
    assert read_scene_from_zip(str(zip_path)) is None

  def test_missing_name(self, tmp_path):
    zip_path = tmp_path / "scene.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
      archive.writestr("scene.json", json.dumps({"assets": []}))
    assert read_scene_from_zip(str(zip_path)) is None

  def test_non_string_name(self, tmp_path):
    zip_path = tmp_path / "scene.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
      archive.writestr("scene.json", json.dumps({"name": 123}))
    assert read_scene_from_zip(str(zip_path)) is None


class TestSceneScapeClientRequest:
  def test_url_trailing_slash_stripped(self):
    client = SceneScapeClient("http://host/api/v1/", True)
    assert client.url == "http://host/api/v1"

  def test_request_raises_on_http_error(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.raise_for_status.side_effect = requests.HTTPError("500")
    with pytest.raises(requests.HTTPError):
      client._request("GET", "/scenes")


class TestSceneScapeClientAuthenticate:
  def test_authenticate_sets_token_header(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.json.return_value = {"token": "abc123"}
    client.authenticate("user", "pw")
    client.session.headers.__setitem__.assert_called_once_with("Authorization", "Token abc123")


class TestIsDatabaseReady:
  def test_true_when_ready(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.get.return_value.ok = True
    client.session.get.return_value.json.return_value = {"databaseReady": True}
    assert client.is_database_ready() is True

  def test_false_when_not_ok(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.get.return_value.ok = False
    assert client.is_database_ready() is False

  def test_false_when_flag_missing(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.get.return_value.ok = True
    client.session.get.return_value.json.return_value = {}
    assert client.is_database_ready() is False


class TestSceneUidAndAssetExists:
  def test_scene_uid_hit(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.json.return_value = {"results": [{"uid": "abc"}]}
    assert client.scene_uid("Demo") == "abc"

  def test_scene_uid_miss(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.json.return_value = {"results": []}
    assert client.scene_uid("Demo") is None

  def test_asset_exists_true(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.json.return_value = {"results": [{"name": "a"}]}
    assert client.asset_exists("a") is True

  def test_asset_exists_false(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.json.return_value = {"results": []}
    assert client.asset_exists("a") is False


class TestCalibrationMarkerExists:
  def test_true_when_found(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    assert client.calibration_marker_exists("uid_1") is True

  def test_false_on_404(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    error = requests.HTTPError("404")
    error.response = MagicMock(status_code=404)
    client.session.request.return_value.raise_for_status.side_effect = error
    assert client.calibration_marker_exists("uid_1") is False

  def test_reraises_on_other_error(self):
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    error = requests.HTTPError("500")
    error.response = MagicMock(status_code=500)
    client.session.request.return_value.raise_for_status.side_effect = error
    with pytest.raises(requests.HTTPError):
      client.calibration_marker_exists("uid_1")


class TestImportScene:
  def test_posts_multipart_zip(self, tmp_path):
    zip_path = tmp_path / "scene.zip"
    zip_path.write_bytes(b"fake zip contents")
    client = SceneScapeClient("http://host", True)
    client.session = MagicMock()
    client.session.request.return_value.json.return_value = {"scene": None}
    result = client.import_scene(str(zip_path))
    assert result == {"scene": None}
    _, kwargs = client.session.request.call_args
    name, _, content_type = kwargs["files"]["zipFile"]
    assert name == "scene.zip"
    assert content_type == "application/zip"


class TestWaitForDatabase:
  def test_ready_immediately(self, fake_client, monkeypatch):
    fake_client.is_database_ready.return_value = True
    monkeypatch.setattr(uploader.time, "sleep", MagicMock())
    assert wait_for_database(fake_client, 10) is True
    fake_client.is_database_ready.assert_called_once()
    uploader.time.sleep.assert_not_called()

  def test_retries_after_request_exception(self, fake_client, monkeypatch):
    fake_client.is_database_ready.side_effect = [requests.ConnectionError("down"), True]
    monkeypatch.setattr(uploader.time, "monotonic", MagicMock(return_value=0))
    monkeypatch.setattr(uploader.time, "sleep", MagicMock())
    assert wait_for_database(fake_client, 10) is True
    assert fake_client.is_database_ready.call_count == 2
    uploader.time.sleep.assert_called_once_with(uploader.POLL_INTERVAL_SECONDS)

  def test_timeout_returns_false(self, fake_client, monkeypatch):
    fake_client.is_database_ready.return_value = False
    monkeypatch.setattr(uploader.time, "monotonic", MagicMock(side_effect=[0, 10]))
    monkeypatch.setattr(uploader.time, "sleep", MagicMock())
    assert wait_for_database(fake_client, 10) is False
    uploader.time.sleep.assert_not_called()


class TestUploadAssets:
  def test_creates_missing_assets_only(self, fake_client):
    fake_client.asset_exists.side_effect = [False, True]
    scene = {"name": "Demo", "assets": [{"name": "a"}, {"name": "b"}]}
    assert upload_assets(fake_client, scene) is True
    fake_client.create_asset.assert_called_once_with({"name": "a"})

  def test_no_assets(self, fake_client):
    assert upload_assets(fake_client, {"name": "Demo"}) is True
    fake_client.create_asset.assert_not_called()

  def test_asset_without_name_fails(self, fake_client):
    scene = {"name": "Demo", "assets": [{}]}
    assert upload_assets(fake_client, scene) is False
    fake_client.create_asset.assert_not_called()


class TestUploadCalibrationMarkers:
  def test_no_markers_short_circuits(self, fake_client):
    assert upload_calibration_markers(fake_client, {"name": "Demo"}) is True
    fake_client.scene_uid.assert_not_called()

  def test_scene_not_found_fails(self, fake_client):
    fake_client.scene_uid.return_value = None
    scene = {"name": "Demo", "calibration_markers": [{"apriltag_id": 1, "dims": 0.2}]}
    assert upload_calibration_markers(fake_client, scene) is False

  def test_creates_missing_marker(self, fake_client):
    fake_client.scene_uid.return_value = "uid123"
    fake_client.calibration_marker_exists.return_value = False
    scene = {"name": "Demo", "calibration_markers": [{"apriltag_id": 7, "dims": 0.2}]}
    assert upload_calibration_markers(fake_client, scene) is True
    fake_client.create_calibration_marker.assert_called_once_with({
      "marker_id": "uid123_7",
      "apriltag_id": "7",
      "dims": 0.2,
      "scene": "uid123",
    })

  def test_skips_existing_marker(self, fake_client):
    fake_client.scene_uid.return_value = "uid123"
    fake_client.calibration_marker_exists.return_value = True
    scene = {"name": "Demo", "calibration_markers": [{"apriltag_id": 7, "dims": 0.2}]}
    assert upload_calibration_markers(fake_client, scene) is True
    fake_client.create_calibration_marker.assert_not_called()


class TestUploadScene:
  def test_clean_summary_succeeds(self, fake_client):
    fake_client.import_scene.return_value = {}
    assert upload_scene(fake_client, {"name": "Demo"}, "demo.zip") is True

  def test_scene_error_fails(self, fake_client):
    fake_client.import_scene.return_value = {"scene": "boom"}
    assert upload_scene(fake_client, {"name": "Demo"}, "demo.zip") is False

  @pytest.mark.parametrize("key", RESOURCE_KEYS)
  def test_resource_error_fails(self, fake_client, key):
    fake_client.import_scene.return_value = {key: "boom"}
    assert upload_scene(fake_client, {"name": "Demo"}, "demo.zip") is False


class TestUploadOne:
  def test_new_scene_uploads_and_returns_uid(self, fake_client, scene_zip):
    zip_path = scene_zip({"name": "Demo"})
    fake_client.scene_uid.side_effect = [None, "new-uid"]
    fake_client.import_scene.return_value = {}
    result = upload_one(fake_client, str(zip_path))
    assert result == "new-uid"
    fake_client.import_scene.assert_called_once_with(str(zip_path))

  def test_existing_scene_reconciles_without_reimport(self, fake_client, scene_zip):
    zip_path = scene_zip({"name": "Demo"})
    fake_client.scene_uid.return_value = "existing-uid"
    result = upload_one(fake_client, str(zip_path))
    assert result == "existing-uid"
    fake_client.import_scene.assert_not_called()

  def test_unreadable_zip_returns_none(self, fake_client, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert upload_one(fake_client, str(bad)) is None
    fake_client.scene_uid.assert_not_called()

  def test_asset_failure_returns_none(self, fake_client, scene_zip):
    zip_path = scene_zip({"name": "Demo", "assets": [{}]})
    fake_client.scene_uid.return_value = None
    assert upload_one(fake_client, str(zip_path)) is None
    fake_client.import_scene.assert_not_called()

  def test_marker_failure_returns_none(self, fake_client, scene_zip):
    zip_path = scene_zip({
      "name": "Demo",
      "calibration_markers": [{"apriltag_id": 1, "dims": 0.2}],
    })
    fake_client.scene_uid.return_value = None
    fake_client.import_scene.return_value = {}
    assert upload_one(fake_client, str(zip_path)) is None


class TestUploadAll:
  def test_all_succeed_returns_zero_failures(self, fake_client, scene_zip):
    zip1 = scene_zip({"name": "Demo1"}, filename="a.zip")
    zip2 = scene_zip({"name": "Demo2"}, filename="b.zip")
    fake_client.scene_uid.return_value = "uid"
    assert upload_all(fake_client, [str(zip1), str(zip2)]) == 0

  def test_counts_failures(self, fake_client, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert upload_all(fake_client, [str(bad)]) == 1

  def test_request_exception_counted_and_continues(self, fake_client, scene_zip):
    zip1 = scene_zip({"name": "Demo1"}, filename="a.zip")
    zip2 = scene_zip({"name": "Demo2"}, filename="b.zip")
    fake_client.scene_uid.side_effect = [
      requests.ConnectionError("down"),
      None, "uid-b",
    ]
    result = upload_all(fake_client, [str(zip1), str(zip2)])
    assert result == 1
