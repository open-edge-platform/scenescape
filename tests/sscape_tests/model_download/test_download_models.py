# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for model_download/src/download_models.py."""

import json
from urllib import error

import pytest

import download_models as dm


class TestGetJobOutcome:

  def test_completed_without_result_is_completed(self):
    assert dm._get_job_outcome({"status": "completed"}) == "completed"

  def test_completed_with_success_true(self):
    assert dm._get_job_outcome({"status": "completed", "result": {"success": True}}) == "completed"

  def test_completed_with_success_false_is_failed(self):
    assert dm._get_job_outcome({"status": "completed", "result": {"success": False}}) == "failed"

  @pytest.mark.parametrize("status", ["failed", "canceled", "FAILED", "Canceled"])
  def test_failed_or_canceled_status_is_failed(self, status):
    assert dm._get_job_outcome({"status": status}) == "failed"

  @pytest.mark.parametrize("status", ["running", "pending", "", "unknown"])
  def test_in_progress_status_is_pending(self, status):
    assert dm._get_job_outcome({"status": status}) == "pending"

  def test_success_false_without_terminal_status_is_failed(self):
    assert dm._get_job_outcome({"status": "running", "result": {"success": False}}) == "failed"

  def test_non_bool_success_flag_raises(self):
    with pytest.raises(ValueError, match="boolean value"):
      dm._get_job_outcome({"status": "completed", "result": {"success": "yes"}})

  def test_missing_status_key_defaults_to_pending(self):
    assert dm._get_job_outcome({}) == "pending"


class TestGetTrackedJobs:

  def test_filters_to_tracked_ids_only(self):
    body = json.dumps({"jobs": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
    tracked = dm._get_tracked_jobs(body, ["a", "c"])
    assert set(tracked.keys()) == {"a", "c"}

  def test_returns_empty_dict_when_none_tracked(self):
    body = json.dumps({"jobs": [{"id": "z"}]})
    assert dm._get_tracked_jobs(body, ["a"]) == {}

  def test_missing_jobs_key_treated_as_empty_list(self):
    assert dm._get_tracked_jobs(json.dumps({}), ["a"]) == {}

  def test_rejects_non_list_jobs(self):
    with pytest.raises(TypeError, match="jobs must be a list"):
      dm._get_tracked_jobs(json.dumps({"jobs": "nope"}), ["a"])

  def test_rejects_non_dict_job_entry(self):
    with pytest.raises(TypeError, match="must be an object"):
      dm._get_tracked_jobs(json.dumps({"jobs": ["nope"]}), ["a"])

  def test_rejects_job_without_string_id(self):
    with pytest.raises(ValueError, match="string id"):
      dm._get_tracked_jobs(json.dumps({"jobs": [{"id": 123}]}), ["a"])


class TestValidateDownloaderModels:

  def test_accepts_valid_models(self):
    models = [{"name": "m1"}, {"name": "m2", "hub": "omz"}]
    assert dm._validate_downloader_models(models) == models

  def test_rejects_non_list(self):
    with pytest.raises(ValueError, match="JSON array"):
      dm._validate_downloader_models({"name": "m1"})

  def test_rejects_empty_list(self):
    with pytest.raises(ValueError, match="must not be empty"):
      dm._validate_downloader_models([])

  def test_rejects_non_dict_entry(self):
    with pytest.raises(ValueError, match=r"models\[0\] must be an object"):
      dm._validate_downloader_models(["nope"])

  def test_rejects_missing_name(self):
    with pytest.raises(ValueError, match="name must be a non-empty string"):
      dm._validate_downloader_models([{"hub": "omz"}])

  def test_rejects_empty_name(self):
    with pytest.raises(ValueError, match="name must be a non-empty string"):
      dm._validate_downloader_models([{"name": ""}])


class TestExtractDownloaderModels:

  def test_extracts_model_downloader_objects(self):
    config_models = [
      {"model_downloader": {"name": "m1"}},
      {"model_downloader": {"name": "m2"}},
    ]
    result = dm._extract_downloader_models(config_models)
    assert result == [{"name": "m1"}, {"name": "m2"}]

  def test_rejects_non_list(self):
    with pytest.raises(ValueError, match="JSON array"):
      dm._extract_downloader_models("nope")

  def test_rejects_non_dict_entry(self):
    with pytest.raises(ValueError, match=r"models\[0\] must be an object"):
      dm._extract_downloader_models(["nope"])

  def test_rejects_missing_model_downloader(self):
    with pytest.raises(ValueError, match="model_downloader must be an object"):
      dm._extract_downloader_models([{}])


class TestLoadModelsFromConfig:

  def test_loads_valid_config(self, tmp_path):
    config_file = tmp_path / "models.json"
    config_file.write_text(
      json.dumps({"models": [{"model_downloader": {"name": "m1"}}]}),
      encoding="utf-8",
    )
    result = dm._load_models_from_config(str(config_file))
    assert result == [{"name": "m1"}]

  def test_rejects_non_object_top_level(self, tmp_path):
    config_file = tmp_path / "models.json"
    config_file.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
      dm._load_models_from_config(str(config_file))

  def test_missing_file_raises_oserror(self, tmp_path):
    with pytest.raises(OSError):
      dm._load_models_from_config(str(tmp_path / "missing.json"))

  def test_malformed_json_raises(self, tmp_path):
    config_file = tmp_path / "bad.json"
    config_file.write_text("{ not valid json }", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
      dm._load_models_from_config(str(config_file))


class _FakeResponse:
  def __init__(self, body: bytes):
    self._body = body

  def read(self):
    return self._body

  def __enter__(self):
    return self

  def __exit__(self, *exc_info):
    return False


class TestWaitForJobs:

  def test_rejects_empty_job_ids(self):
    with pytest.raises(ValueError, match="No job ids"):
      dm._wait_for_jobs("http://api", [], wait_timeout_s=1)

  def test_returns_when_all_jobs_completed(self, monkeypatch):
    body = json.dumps({"jobs": [{"id": "a", "status": "completed"}]}).encode("utf-8")

    def fake_urlopen(req, timeout=None):
      return _FakeResponse(body)

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    dm._wait_for_jobs("http://api", ["a"], wait_timeout_s=5, poll_interval_s=0.01)

  def test_raises_when_job_fails(self, monkeypatch):
    body = json.dumps({"jobs": [{"id": "a", "status": "failed"}]}).encode("utf-8")

    def fake_urlopen(req, timeout=None):
      return _FakeResponse(body)

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="Download jobs failed"):
      dm._wait_for_jobs("http://api", ["a"], wait_timeout_s=5, poll_interval_s=0.01)

  def test_raises_on_http_error(self, monkeypatch):
    def fake_urlopen(req, timeout=None):
      raise error.HTTPError("http://api", 500, "boom", None, None)

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="status request failed"):
      dm._wait_for_jobs("http://api", ["a"], wait_timeout_s=1, poll_interval_s=0.01)

  def test_raises_on_timeout_when_pending(self, monkeypatch):
    body = json.dumps({"jobs": [{"id": "a", "status": "running"}]}).encode("utf-8")

    def fake_urlopen(req, timeout=None):
      return _FakeResponse(body)

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="Timeout waiting"):
      dm._wait_for_jobs("http://api", ["a"], wait_timeout_s=0.05, poll_interval_s=0.01)


class TestPostDownloadRequest:

  def test_returns_job_ids_on_success(self, monkeypatch):
    body = json.dumps({"job_ids": ["job-1", "job-2"]}).encode("utf-8")

    def fake_urlopen(req, timeout=None):
      return _FakeResponse(body)

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    job_ids = dm._post_download_request(
      "http://api", models=[{"name": "m1"}], parallel_downloads=False, wait_timeout_s=5,
    )
    assert job_ids == ["job-1", "job-2"]

  def test_raises_on_http_error(self, monkeypatch):
    def fake_urlopen(req, timeout=None):
      raise error.HTTPError("http://api", 400, "bad request", None, None)

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="Download request failed"):
      dm._post_download_request(
        "http://api", models=[{"name": "m1"}], parallel_downloads=False, wait_timeout_s=1,
      )

  def test_raises_on_timeout(self, monkeypatch):
    def fake_urlopen(req, timeout=None):
      raise error.URLError("connection refused")

    monkeypatch.setattr(dm.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError):
      dm._post_download_request(
        "http://api", models=[{"name": "m1"}], parallel_downloads=False, wait_timeout_s=0.05,
      )
