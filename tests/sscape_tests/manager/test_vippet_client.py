# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Manager ViPPET client library (manager.vippet)."""

import json
from unittest.mock import Mock, call

import pytest
import requests

from manager.vippet import (
  VIPPET_URL_ENV,
  PipelineSummary,
  PipelineVariant,
  ViPPETBadRequestError,
  ViPPETClient,
  ViPPETError,
  ViPPETNotFoundError,
  ViPPETUnavailableError,
)
from manager.vippet import client as client_module

BASE_URL = "http://vippet.test:7860/api/v1"
PIPELINE_ID = "vehicle-detection"
PIPELINE_STRING = (
  "filesrc location=/videos/input/sample.mp4 ! decodebin3 ! "
  "gvadetect model=/models/output/yolo/model.xml device=GPU ! "
  "capsfilter caps=\"video/x-raw,width=320\" ! fakesink"
)

CPU_GRAPH = {
  "nodes": [
    {"id": "0", "type": "filesrc", "data": {"location": "/videos/input/sample.mp4"}},
    {"id": "1", "type": "gvadetect", "data": {"device": "CPU"}},
    {"id": "2", "type": "fakesink", "data": {}},
  ],
  "edges": [
    {"id": "0", "source": "0", "target": "1"},
    {"id": "1", "source": "1", "target": "2"},
  ],
}
GPU_GRAPH = {
  "nodes": [
    {"id": "0", "type": "filesrc", "data": {"location": "/videos/input/sample.mp4"}},
    {"id": "1", "type": "gvadetect", "data": {"device": "GPU"}},
    {"id": "2", "type": "fakesink", "data": {}},
  ],
  "edges": [
    {"id": "0", "source": "0", "target": "1"},
    {"id": "1", "source": "1", "target": "2"},
  ],
}
SIMPLE_GRAPH = {"nodes": [{"id": "1", "type": "gvadetect", "data": {}}], "edges": []}


def _variant(variant_id, name, graph):
  return {
    "id": variant_id,
    "name": name,
    "read_only": True,
    "pipeline_graph": graph,
    "pipeline_graph_simple": SIMPLE_GRAPH,
    "created_at": "2026-02-05T14:30:45.123000+00:00",
    "modified_at": "2026-02-05T14:30:45.123000+00:00",
  }


def _pipeline(pipeline_id=PIPELINE_ID, pipeline_type="vision", **overrides):
  pipeline = {
    "id": pipeline_id,
    "name": "Vehicle Detection",
    "description": "Simple vehicle detection pipeline",
    "source": "PREDEFINED",
    "type": pipeline_type,
    "tags": ["detection", "vehicle"],
    "variants": [_variant("cpu", "CPU", CPU_GRAPH), _variant("gpu", "GPU", GPU_GRAPH)],
    "thumbnail": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA",
    "created_at": "2026-02-05T14:30:45.123000+00:00",
    "modified_at": "2026-02-05T14:30:45.123000+00:00",
  }
  pipeline.update(overrides)
  return pipeline


EXPECTED_SUMMARY = PipelineSummary(
  id=PIPELINE_ID,
  name="Vehicle Detection",
  description="Simple vehicle detection pipeline",
  tags=("detection", "vehicle"),
  variants=(PipelineVariant(id="cpu", name="CPU"), PipelineVariant(id="gpu", name="GPU")),
)


def _response(status_code, payload=None, raw=None):
  response = requests.Response()
  response.status_code = status_code
  # pylint: disable-next=protected-access
  response._content = raw if raw is not None else json.dumps(payload).encode()
  return response


def _call(method, path, body=None):
  return call(method, BASE_URL + path, json=body, timeout=10, verify=True)


@pytest.fixture
def session():
  return Mock(spec=requests.Session)


@pytest.fixture
def client(session):
  return ViPPETClient(base_url=BASE_URL + "/", session=session)


class TestConfiguration:
  def test_base_url_argument_strips_trailing_slash(self, session):
    vippet = ViPPETClient(base_url="http://host:7860/api/v1/", session=session)
    assert vippet.base_url == "http://host:7860/api/v1"

  def test_base_url_from_environment(self, monkeypatch, session):
    monkeypatch.setenv(VIPPET_URL_ENV, "https://from-env/api/v1")
    assert ViPPETClient(session=session).base_url == "https://from-env/api/v1"

  def test_base_url_argument_overrides_environment(self, monkeypatch, session):
    monkeypatch.setenv(VIPPET_URL_ENV, "http://from-env/api/v1")
    vippet = ViPPETClient(base_url="http://arg/api/v1", session=session)
    assert vippet.base_url == "http://arg/api/v1"

  @pytest.mark.parametrize("env_value", [None, "", "   "])
  def test_missing_base_url_raises(self, monkeypatch, session, env_value):
    if env_value is None:
      monkeypatch.delenv(VIPPET_URL_ENV, raising=False)
    else:
      monkeypatch.setenv(VIPPET_URL_ENV, env_value)
    with pytest.raises(ValueError, match=VIPPET_URL_ENV):
      ViPPETClient(session=session)

  @pytest.mark.parametrize("url", [
    "vippet:7860/api/v1",
    "ftp://vippet/api/v1",
    "file:///etc/passwd",
    "http://",
    "http://vippet/api/v1?debug=1",
    "http://vippet/api/v1#docs",
  ])
  def test_invalid_base_url_raises(self, session, url):
    with pytest.raises(ValueError, match="ViPPET base URL"):
      ViPPETClient(base_url=url, session=session)

  def test_invalid_base_url_error_does_not_echo_credentials(self, session):
    with pytest.raises(ValueError) as exc_info:
      ViPPETClient(base_url="http://user:s3cret@vippet/api/v1?x=1", session=session)
    assert "s3cret" not in str(exc_info.value)

  def test_timeout_and_verify_are_forwarded(self, session):
    session.request.return_value = _response(200, [])
    vippet = ViPPETClient(base_url=BASE_URL, timeout=2.5, verify="/run/secrets/ca.pem",
                          session=session)
    vippet.get_pipelines()
    session.request.assert_called_once_with(
      "GET", BASE_URL + "/pipelines", json=None, timeout=2.5, verify="/run/secrets/ca.pem")

  def test_context_manager_closes_session(self, session):
    with ViPPETClient(base_url=BASE_URL, session=session) as vippet:
      assert vippet.session is session
    session.close.assert_called_once_with()


class TestGetPipelines:
  def test_returns_vision_summaries_and_hides_time_series(self, client, session):
    session.request.return_value = _response(200, [
      _pipeline(),
      _pipeline(pipeline_id="anomaly-detection", pipeline_type="time_series"),
    ])
    assert client.get_pipelines() == [EXPECTED_SUMMARY]
    assert session.request.call_args_list == [_call("GET", "/pipelines")]

  def test_missing_type_defaults_to_vision(self, client, session):
    pipeline = _pipeline()
    del pipeline["type"]
    session.request.return_value = _response(200, [pipeline])
    assert client.get_pipelines() == [EXPECTED_SUMMARY]

  def test_unknown_type_is_hidden(self, client, session):
    session.request.return_value = _response(200, [_pipeline(pipeline_type="audio")])
    assert client.get_pipelines() == []

  def test_optional_fields_default_to_empty(self, client, session):
    pipeline = _pipeline(description=None)
    del pipeline["tags"]
    session.request.return_value = _response(200, [pipeline])
    summary = client.get_pipelines()[0]
    assert summary.description == ""
    assert summary.tags == ()

  def test_empty_list(self, client, session):
    session.request.return_value = _response(200, [])
    assert client.get_pipelines() == []

  def test_non_list_response_raises(self, client, session):
    session.request.return_value = _response(200, {"pipelines": []})
    with pytest.raises(ViPPETError, match="Expected a list of pipelines"):
      client.get_pipelines()

  @pytest.mark.parametrize("pipeline", [
    "not-an-object",
    _pipeline(id=None),
    _pipeline(name=""),
    _pipeline(description=5),
    _pipeline(tags="detection"),
    _pipeline(tags=["detection", 1]),
    _pipeline(type=1),
    _pipeline(variants=None),
    _pipeline(variants=["cpu"]),
    _pipeline(variants=[{"id": "cpu"}]),
  ])
  def test_malformed_pipeline_raises(self, client, session, pipeline):
    session.request.return_value = _response(200, [pipeline])
    with pytest.raises(ViPPETError):
      client.get_pipelines()


class TestGetPipelineString:
  def test_converts_advanced_graph_of_selected_variant(self, client, session):
    session.request.side_effect = [
      _response(200, _pipeline()),
      _response(200, {"pipeline_description": PIPELINE_STRING}),
    ]
    assert client.get_pipeline_string(PIPELINE_ID, "gpu") == PIPELINE_STRING
    assert session.request.call_args_list == [
      _call("GET", f"/pipelines/{PIPELINE_ID}"),
      _call("POST", "/convert/to-description", GPU_GRAPH),
    ]

  def test_pipeline_string_is_not_logged(self, client, session, monkeypatch):
    log = Mock()
    monkeypatch.setattr(client_module, "log", log)
    session.request.side_effect = [
      _response(200, _pipeline()),
      _response(200, {"pipeline_description": PIPELINE_STRING}),
    ]
    client.get_pipeline_string(PIPELINE_ID, "cpu")
    logged = repr(log.mock_calls)
    assert "gvadetect" not in logged
    assert PIPELINE_ID in logged

  def test_unknown_variant_raises_not_found_without_conversion(self, client, session):
    session.request.return_value = _response(200, _pipeline())
    with pytest.raises(ViPPETNotFoundError, match="npu"):
      client.get_pipeline_string(PIPELINE_ID, "npu")
    assert session.request.call_count == 1

  def test_time_series_pipeline_raises_not_found(self, client, session):
    session.request.return_value = _response(200, _pipeline(pipeline_type="time_series"))
    with pytest.raises(ViPPETNotFoundError, match="not a vision pipeline"):
      client.get_pipeline_string(PIPELINE_ID, "cpu")
    assert session.request.call_count == 1

  def test_unknown_pipeline_raises_not_found(self, client, session):
    message = "Pipeline with id 'missing' not found."
    session.request.return_value = _response(404, {"message": message})
    with pytest.raises(ViPPETNotFoundError) as exc_info:
      client.get_pipeline_string("missing", "cpu")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == message

  def test_conversion_failure_raises_bad_request(self, client, session):
    message = "Invalid graph: circular graph detected or no start nodes found"
    session.request.side_effect = [
      _response(200, _pipeline()),
      _response(400, {"message": message}),
    ]
    with pytest.raises(ViPPETBadRequestError) as exc_info:
      client.get_pipeline_string(PIPELINE_ID, "cpu")
    assert exc_info.value.detail == message

  def test_max_length_id_is_accepted(self, client, session):
    pipeline_id = "p" * client_module.MAX_ID_LENGTH
    session.request.side_effect = [
      _response(200, _pipeline(pipeline_id=pipeline_id)),
      _response(200, {"pipeline_description": PIPELINE_STRING}),
    ]
    assert client.get_pipeline_string(pipeline_id, "cpu") == PIPELINE_STRING
    assert session.request.call_args_list[0] == _call("GET", f"/pipelines/{pipeline_id}")

  @pytest.mark.parametrize("pipeline_id, variant_id", [
    ("", "cpu"),
    (".", "cpu"),
    ("..", "cpu"),
    ("../health", "cpu"),
    ("a/b", "cpu"),
    ("a?b=1", "cpu"),
    ("a%2Fb", "cpu"),
    ("p" * 129, "cpu"),
    (None, "cpu"),
    (PIPELINE_ID, ""),
    (PIPELINE_ID, "c p u"),
    (PIPELINE_ID, 1),
  ])
  def test_invalid_ids_raise_without_request(self, client, session, pipeline_id, variant_id):
    with pytest.raises(ValueError):
      client.get_pipeline_string(pipeline_id, variant_id)
    session.request.assert_not_called()

  @pytest.mark.parametrize("graph", [
    None,
    [],
    {"edges": []},
    {"nodes": [], "edges": None},
  ])
  def test_malformed_variant_graph_raises(self, client, session, graph):
    pipeline = _pipeline(variants=[_variant("cpu", "CPU", graph)])
    session.request.return_value = _response(200, pipeline)
    with pytest.raises(ViPPETError, match="pipeline_graph|nodes|edges"):
      client.get_pipeline_string(PIPELINE_ID, "cpu")
    assert session.request.call_count == 1

  @pytest.mark.parametrize("payload", [
    {},
    [],
    {"pipeline_description": ""},
    {"pipeline_description": "   "},
    {"pipeline_description": 5},
  ])
  def test_invalid_description_response_raises(self, client, session, payload):
    session.request.side_effect = [_response(200, _pipeline()), _response(200, payload)]
    with pytest.raises(ViPPETError):
      client.get_pipeline_string(PIPELINE_ID, "cpu")

  def test_non_object_pipeline_response_raises(self, client, session):
    session.request.return_value = _response(200, [_pipeline()])
    with pytest.raises(ViPPETError, match="Expected pipeline object"):
      client.get_pipeline_string(PIPELINE_ID, "cpu")


class TestErrorMapping:
  @pytest.mark.parametrize("status_code, error_cls", [
    (400, ViPPETBadRequestError),
    (422, ViPPETBadRequestError),
    (404, ViPPETNotFoundError),
    (503, ViPPETUnavailableError),
    (401, ViPPETError),
    (500, ViPPETError),
  ])
  def test_http_errors_are_mapped(self, client, session, status_code, error_cls):
    session.request.return_value = _response(status_code, {"message": "boom"})
    with pytest.raises(ViPPETError) as exc_info:
      client.get_pipelines()
    assert exc_info.type is error_cls
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == "boom"

  def test_initializing_service_raises_unavailable(self, client, session):
    session.request.return_value = _response(
      503, {"message": "Service is initializing. Please wait.", "status": "initializing"})
    with pytest.raises(ViPPETUnavailableError, match="initializing"):
      client.get_pipelines()

  def test_fastapi_validation_detail_is_preserved(self, client, session):
    detail = [{"loc": ["body", "nodes"], "msg": "Field required", "type": "missing"}]
    session.request.return_value = _response(422, {"detail": detail})
    with pytest.raises(ViPPETBadRequestError) as exc_info:
      client.get_pipelines()
    assert exc_info.value.detail == detail

  def test_error_body_without_known_keys_is_returned_whole(self, client, session):
    session.request.return_value = _response(500, {"error": "boom"})
    with pytest.raises(ViPPETError) as exc_info:
      client.get_pipelines()
    assert exc_info.value.detail == {"error": "boom"}

  def test_non_json_error_body_uses_truncated_text(self, client, session):
    session.request.return_value = _response(502, raw=b"x" * 2000)
    with pytest.raises(ViPPETError) as exc_info:
      client.get_pipelines()
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "x" * client_module.MAX_ERROR_DETAIL_LENGTH

  @pytest.mark.parametrize("exc", [
    requests.exceptions.ConnectionError("refused"),
    requests.exceptions.Timeout("timed out"),
  ])
  def test_network_failures_raise_unavailable(self, client, session, exc):
    session.request.side_effect = exc
    with pytest.raises(ViPPETUnavailableError) as exc_info:
      client.get_pipelines()
    assert exc_info.value.status_code is None
    assert exc_info.value.__cause__ is exc

  def test_other_request_failures_raise_base_error(self, client, session):
    session.request.side_effect = requests.exceptions.InvalidURL("bad url")
    with pytest.raises(ViPPETError) as exc_info:
      client.get_pipelines()
    assert exc_info.type is ViPPETError

  def test_invalid_json_success_body_raises(self, client, session):
    session.request.return_value = _response(200, raw=b"<html>not json</html>")
    with pytest.raises(ViPPETError, match="invalid JSON") as exc_info:
      client.get_pipelines()
    assert exc_info.value.status_code == 200
