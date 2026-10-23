# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Manager DLSPS 2.0 REST adapter (manager.dlsps)."""

import json
import uuid
from unittest.mock import Mock

import pytest
import requests

from manager.dlsps import (
  DEFAULT_DLSPS_URL,
  DLSPS_URL_ENV,
  DLSPSBadRequestError,
  DLSPSClient,
  DLSPSConflictError,
  DLSPSError,
  DLSPSNotFoundError,
  DLSPSUnavailableError,
  PipelineState,
  PipelineStatus,
  PipelineSummary,
  RestartConfig,
  StartPipelineRequest,
)

BASE_URL = "http://dlsps.test:8080"
INSTANCE_ID = "3f1c0d2e-8a4b-4d6c-9e1f-2a3b4c5d6e7f"
OTHER_INSTANCE_ID = "9b2e7a10-4c3d-4f5e-8a6b-1c2d3e4f5a6b"
PIPELINE = "videotestsrc num-buffers=300 ! videoconvert ! fakesink"

RUNNING_STATUS = {
  "id": INSTANCE_ID,
  "state": "RUNNING",
  "avg_fps": 29.87,
  "frame_fps": 30.02,
  "frame_interval": 1.023,
  "start_time": 1791366000.123,
  "first_frame_time": 1791366000.456,
  "elapsed_time": 42.51,
  "message": "",
}

ERROR_STATUS = {
  "id": OTHER_INSTANCE_ID,
  "state": "ERROR",
  "avg_fps": 0.0,
  "frame_fps": 0.0,
  "frame_interval": 0.0,
  "start_time": None,
  "first_frame_time": None,
  "elapsed_time": None,
  "message": "validation failed: no element \"badelement\"",
}


def _response(status_code, payload=None, raw=None):
  response = requests.Response()
  response.status_code = status_code
  # pylint: disable-next=protected-access
  response._content = raw if raw is not None else json.dumps(payload).encode()
  return response


@pytest.fixture
def session():
  return Mock(spec=requests.Session)


@pytest.fixture
def client(session):
  return DLSPSClient(base_url=BASE_URL + "/", session=session)


def _assert_request(session, method, path, body=None):
  session.request.assert_called_once_with(
    method, BASE_URL + path, json=body, timeout=10, verify=True)


class TestConfiguration:
  def test_base_url_argument_strips_trailing_slash(self, session):
    assert DLSPSClient(base_url="http://host:1234/", session=session).base_url == "http://host:1234"

  def test_base_url_from_environment(self, monkeypatch, session):
    monkeypatch.setenv(DLSPS_URL_ENV, "http://from-env:8080")
    assert DLSPSClient(session=session).base_url == "http://from-env:8080"

  def test_base_url_argument_overrides_environment(self, monkeypatch, session):
    monkeypatch.setenv(DLSPS_URL_ENV, "http://from-env:8080")
    assert DLSPSClient(base_url=BASE_URL, session=session).base_url == BASE_URL

  def test_base_url_default(self, monkeypatch, session):
    monkeypatch.delenv(DLSPS_URL_ENV, raising=False)
    assert DLSPSClient(session=session).base_url == DEFAULT_DLSPS_URL

  def test_timeout_and_verify_are_forwarded(self, session):
    session.request.return_value = _response(200, [])
    DLSPSClient(base_url=BASE_URL, timeout=3, verify="/certs/ca.pem",
                session=session).list_pipeline_statuses()
    session.request.assert_called_once_with(
      "GET", BASE_URL + "/pipelines/status", json=None, timeout=3, verify="/certs/ca.pem")

  def test_context_manager_closes_session(self, session):
    with DLSPSClient(base_url=BASE_URL, session=session):
      pass
    session.close.assert_called_once()


class TestCreatePipeline:
  def test_sends_default_body_and_returns_instance_id(self, client, session):
    session.request.return_value = _response(200, {"instance_id": INSTANCE_ID})

    assert client.create_pipeline(PIPELINE) == INSTANCE_ID
    _assert_request(session, "POST", "/pipelines", {
      "pipeline": PIPELINE,
      "validate_pipeline": True,
      "warmup_frames": 0,
    })

  def test_sends_all_optional_fields(self, client, session):
    session.request.return_value = _response(200, {"instance_id": INSTANCE_ID})

    client.create_pipeline(PIPELINE, validate_pipeline=False, cpu_cores=[0, 2],
                           warmup_frames=10,
                           restart_config=RestartConfig(enabled=True, max_attempts=3,
                                                        backoff_seconds=5))
    _assert_request(session, "POST", "/pipelines", {
      "pipeline": PIPELINE,
      "validate_pipeline": False,
      "warmup_frames": 10,
      "cpu_cores": [0, 2],
      "restart_config": {"enabled": True, "max_attempts": 3, "backoff_seconds": 5},
    })

  def test_pipeline_string_is_sent_verbatim(self, client, session):
    pipeline = "  filesrc location=/tmp/a b.mp4 ! decodebin3 ! fakesink  "
    session.request.return_value = _response(200, {"instance_id": INSTANCE_ID})

    client.create_pipeline(pipeline)
    assert session.request.call_args.kwargs["json"]["pipeline"] == pipeline

  @pytest.mark.parametrize("kwargs", [
    {"pipeline": ""},
    {"pipeline": "   \n"},
    {"pipeline": None},
    {"pipeline": 123},
    {"pipeline": PIPELINE, "validate_pipeline": "yes"},
    {"pipeline": PIPELINE, "warmup_frames": -1},
    {"pipeline": PIPELINE, "warmup_frames": 1.5},
    {"pipeline": PIPELINE, "warmup_frames": True},
    {"pipeline": PIPELINE, "cpu_cores": [-1]},
    {"pipeline": PIPELINE, "cpu_cores": ["0"]},
    {"pipeline": PIPELINE, "cpu_cores": [True]},
    {"pipeline": PIPELINE, "cpu_cores": "0,1"},
    {"pipeline": PIPELINE, "cpu_cores": 3},
    {"pipeline": PIPELINE, "restart_config": {"enabled": True}},
  ])
  def test_invalid_arguments_raise_without_request(self, client, session, kwargs):
    pipeline = kwargs.pop("pipeline")
    with pytest.raises(ValueError):
      client.create_pipeline(pipeline, **kwargs)
    session.request.assert_not_called()

  @pytest.mark.parametrize("payload", [{}, {"instance_id": ""}, {"instance_id": 5}, ["x"]])
  def test_missing_instance_id_in_response_raises(self, client, session, payload):
    session.request.return_value = _response(200, payload)
    with pytest.raises(DLSPSError, match="instance_id"):
      client.create_pipeline(PIPELINE)


class TestRequestSchemas:
  def test_restart_config_defaults(self):
    assert RestartConfig(enabled=True).to_dict() == {
      "enabled": True, "max_attempts": 5, "backoff_seconds": 30}

  @pytest.mark.parametrize("kwargs", [
    {"enabled": "true"},
    {"enabled": True, "max_attempts": 0},
    {"enabled": True, "backoff_seconds": -1},
    {"enabled": True, "max_attempts": 2.0},
  ])
  def test_restart_config_rejects_invalid_values(self, kwargs):
    with pytest.raises(ValueError):
      RestartConfig(**kwargs)

  def test_start_request_normalizes_cpu_cores_to_tuple(self):
    request = StartPipelineRequest(pipeline=PIPELINE, cpu_cores=[1, 3])
    assert request.cpu_cores == (1, 3)
    assert request.to_dict()["cpu_cores"] == [1, 3]


class TestGetPipeline:
  def test_returns_summary_for_inline_pipeline(self, client, session):
    payload = dict(RUNNING_STATUS, type="GStreamer", launch_command=PIPELINE,
                   name=None, version=None, request=None)
    session.request.return_value = _response(200, payload)

    summary = client.get_pipeline(INSTANCE_ID)

    _assert_request(session, "GET", f"/pipelines/{INSTANCE_ID}")
    assert isinstance(summary, PipelineSummary)
    assert summary.id == INSTANCE_ID
    assert summary.state is PipelineState.RUNNING
    assert summary.avg_fps == pytest.approx(29.87)
    assert summary.launch_command == PIPELINE
    assert summary.type == "GStreamer"
    assert summary.name is None and summary.version is None and summary.request is None

  def test_returns_summary_for_named_pipeline(self, client, session):
    request = {"source": {"uri": "file:///videos/a.avi", "type": "uri"}}
    payload = dict(RUNNING_STATUS, type="GStreamer", launch_command=PIPELINE,
                   name="user_defined_pipelines", version="pallet", request=request)
    session.request.return_value = _response(200, payload)

    summary = client.get_pipeline(INSTANCE_ID)
    assert summary.name == "user_defined_pipelines"
    assert summary.version == "pallet"
    assert summary.request == request

  def test_rejects_non_object_request_field(self, client, session):
    session.request.return_value = _response(200, dict(RUNNING_STATUS, request="oops"))
    with pytest.raises(DLSPSError, match="request"):
      client.get_pipeline(INSTANCE_ID)


class TestPipelineStatus:
  def test_get_pipeline_status(self, client, session):
    session.request.return_value = _response(200, RUNNING_STATUS)

    status = client.get_pipeline_status(INSTANCE_ID)

    _assert_request(session, "GET", f"/pipelines/{INSTANCE_ID}/status")
    assert status == PipelineStatus(
      id=INSTANCE_ID, state=PipelineState.RUNNING, avg_fps=29.87, frame_fps=30.02,
      frame_interval=1.023, start_time=1791366000.123, first_frame_time=1791366000.456,
      elapsed_time=42.51, message="")

  def test_list_pipeline_statuses(self, client, session):
    session.request.return_value = _response(200, [RUNNING_STATUS, ERROR_STATUS])

    statuses = client.list_pipeline_statuses()

    _assert_request(session, "GET", "/pipelines/status")
    assert [s.state for s in statuses] == [PipelineState.RUNNING, PipelineState.ERROR]
    assert statuses[1].start_time is None
    assert statuses[1].elapsed_time is None
    assert "badelement" in statuses[1].message

  def test_list_pipeline_statuses_empty(self, client, session):
    session.request.return_value = _response(200, [])
    assert client.list_pipeline_statuses() == []

  def test_list_pipeline_statuses_rejects_non_list(self, client, session):
    session.request.return_value = _response(200, {"id": INSTANCE_ID})
    with pytest.raises(DLSPSError, match="list"):
      client.list_pipeline_statuses()

  def test_unknown_fields_are_ignored(self, client, session):
    session.request.return_value = _response(200, dict(RUNNING_STATUS, new_field=1))
    assert client.get_pipeline_status(INSTANCE_ID).state is PipelineState.RUNNING

  def test_missing_optional_metrics_use_defaults(self, client, session):
    session.request.return_value = _response(200, {"id": INSTANCE_ID, "state": "QUEUED"})
    status = client.get_pipeline_status(INSTANCE_ID)
    assert status.avg_fps == 0.0
    assert status.start_time is None
    assert status.message == ""

  @pytest.mark.parametrize("payload", [
    dict(RUNNING_STATUS, state="PAUSED"),
    dict(RUNNING_STATUS, state=None),
    {k: v for k, v in RUNNING_STATUS.items() if k != "id"},
    dict(RUNNING_STATUS, avg_fps="fast"),
    dict(RUNNING_STATUS, start_time=True),
    dict(RUNNING_STATUS, message=1),
    [RUNNING_STATUS],
  ])
  def test_malformed_status_raises(self, client, session, payload):
    session.request.return_value = _response(200, payload)
    with pytest.raises(DLSPSError):
      client.get_pipeline_status(INSTANCE_ID)


class TestDeletePipeline:
  def test_delete_pipeline(self, client, session):
    session.request.return_value = _response(200, {"instance_id": INSTANCE_ID})

    assert client.delete_pipeline(INSTANCE_ID) == INSTANCE_ID
    _assert_request(session, "DELETE", f"/pipelines/{INSTANCE_ID}")

  def test_delete_non_running_pipeline_raises_conflict(self, client, session):
    detail = f"Instance '{INSTANCE_ID}' is not running (state: COMPLETED)"
    session.request.return_value = _response(409, {"detail": detail})

    with pytest.raises(DLSPSConflictError) as exc_info:
      client.delete_pipeline(INSTANCE_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == detail


class TestInstanceIdValidation:
  @pytest.mark.parametrize("instance_id", [INSTANCE_ID.upper(), uuid.UUID(INSTANCE_ID)])
  def test_instance_id_is_normalized(self, client, session, instance_id):
    session.request.return_value = _response(200, RUNNING_STATUS)
    client.get_pipeline_status(instance_id)
    _assert_request(session, "GET", f"/pipelines/{INSTANCE_ID}/status")

  @pytest.mark.parametrize("method", ["get_pipeline", "get_pipeline_status", "delete_pipeline"])
  @pytest.mark.parametrize("instance_id", ["", "abc", "../status", f"{INSTANCE_ID}/x", None, 42])
  def test_invalid_instance_id_raises_without_request(self, client, session, method,
                                                      instance_id):
    with pytest.raises(ValueError):
      getattr(client, method)(instance_id)
    session.request.assert_not_called()


class TestErrorMapping:
  @pytest.mark.parametrize("status_code, error_cls", [
    (400, DLSPSBadRequestError),
    (422, DLSPSBadRequestError),
    (404, DLSPSNotFoundError),
    (409, DLSPSConflictError),
    (503, DLSPSUnavailableError),
    (500, DLSPSError),
  ])
  def test_http_errors_are_mapped(self, client, session, status_code, error_cls):
    session.request.return_value = _response(status_code, {"detail": "boom"})

    with pytest.raises(error_cls) as exc_info:
      client.get_pipeline(INSTANCE_ID)
    assert type(exc_info.value) is error_cls
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == "boom"

  def test_validation_error_detail_list_is_preserved(self, client, session):
    detail = [{"loc": ["body", "pipeline"], "msg": "Field required", "type": "missing"}]
    session.request.return_value = _response(422, {"detail": detail})

    with pytest.raises(DLSPSBadRequestError) as exc_info:
      client.create_pipeline(PIPELINE)
    assert exc_info.value.detail == detail

  def test_non_json_error_body_uses_truncated_text(self, client, session):
    session.request.return_value = _response(502, raw=b"<html>" + b"x" * 2000)

    with pytest.raises(DLSPSError) as exc_info:
      client.get_pipeline(INSTANCE_ID)
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail.startswith("<html>")
    assert len(exc_info.value.detail) == 512

  @pytest.mark.parametrize("exc", [
    requests.exceptions.ConnectionError("refused"),
    requests.exceptions.ConnectTimeout("connect timeout"),
    requests.exceptions.ReadTimeout("read timeout"),
  ])
  def test_network_failures_raise_unavailable(self, client, session, exc):
    session.request.side_effect = exc

    with pytest.raises(DLSPSUnavailableError) as exc_info:
      client.list_pipeline_statuses()
    assert exc_info.value.status_code is None
    assert exc_info.value.__cause__ is exc

  def test_other_request_failures_raise_base_error(self, client, session):
    session.request.side_effect = requests.exceptions.InvalidURL("bad url")

    with pytest.raises(DLSPSError) as exc_info:
      client.list_pipeline_statuses()
    assert type(exc_info.value) is DLSPSError

  def test_invalid_json_success_body_raises(self, client, session):
    session.request.return_value = _response(200, raw=b"not json")

    with pytest.raises(DLSPSError, match="invalid JSON"):
      client.get_pipeline_status(INSTANCE_ID)
