# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the standalone Re-ID service facade."""

from pathlib import Path
import re
from types import SimpleNamespace
from unittest import mock

import grpc
import pytest
from google.protobuf import struct_pb2
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from reid.api import ReIDService
from reid.client import ReIDClient, RPC_METHODS, SERVICE_NAME
from reid.qdrant_adapter import QdrantDatabase
from reid.server import create_server
from reid.vdms_adapter import VDMSDatabase


class FakeAdapter:
  """Capture facade calls without requiring a vector database."""

  def __init__(self):
    self.connected = False
    self.dimensions = None
    self.set_name = "gallery"

  def connect(self, hostname=None):
    self.connected = True

  def findMatches(self, object_type, vectors, set_name=None, **constraints):
    return [{"object_type": object_type, "count": len(vectors),
             "set_name": set_name, "constraints": constraints}]

  def findSchemaMetadata(self, set_name):
    return True, 256, "IP"

  def purgeExpired(self):
    return 2


def test_facade_delegates_baseline_operations():
  service = ReIDService(adapter=FakeAdapter())

  assert service.health()["status"] == "ok"
  result = service.find_matches({
      "object_type": "person",
      "reid_vectors": [[0.1, 0.2]],
      "set_name": "gallery",
      "constraints": {"camera_id": "cam1"},
  })["matches"][0]
  assert result == {"object_type": "person", "count": 1,
                    "set_name": "gallery", "constraints": {"camera_id": "cam1"}}
  assert service.find_schema_metadata({"set_name": "gallery"})["metadata"] == (
      True, 256, "IP")
  assert service.purge_expired() == 2


def test_facade_rejects_missing_query_fields():
  service = ReIDService(adapter=FakeAdapter())

  with pytest.raises(KeyError, match="reid_vectors"):
    service.find_matches({"object_type": "person"})


def test_connect_called_on_init():
  adapter = mock.Mock()
  ReIDService(adapter=adapter)
  adapter.connect.assert_called_once_with()


def test_connect_can_be_skipped():
  adapter = mock.Mock()
  ReIDService(adapter=adapter, connect=False)
  adapter.connect.assert_not_called()


def test_health_reports_disconnected():
  adapter = mock.Mock(spec=["connect", "connected"])
  adapter.connected = False
  health = ReIDService(adapter=adapter).health()
  assert health["status"] == "degraded"
  assert health["connected"] is False


def test_health_reports_connected():
  adapter = mock.Mock(spec=["connect", "connected"])
  adapter.connected = True
  health = ReIDService(adapter=adapter).health()
  assert health["status"] == "ok"
  assert health["connected"] is True


def test_health_uses_vdms_client_state():
  adapter = mock.Mock(spec=["connect", "db"])
  adapter.db.connected = True
  assert ReIDService(adapter=adapter).health()["connected"] is True


QUERY = {"object_type": "person", "reid_vectors": [[1, 0, 0]], "set_name": "gallery"}


def _vdms_response(commands, *args):
  responses = {
      "FindEntity": {"status": 0, "returned": 0},
      "FindDescriptorSet": {"status": 0, "returned": 1, "dimensions": 3, "metric": "IP"},
      "FindDescriptor": {"status": 0, "returned": 1,
                         "entities": [{"uuid": "gid-1", "rvid": "track-1", "_distance": 0.8}]},
      "DeleteExpired": {"status": 0, "deleted": 2},
  }
  return [{name: responses[name]} for command in commands for name in command], []


@pytest.fixture(params=["VDMS", "QDRANT"])
def transport(request):
  """Real gRPC and adapters; only external database clients are mocked."""
  if request.param == "VDMS":
    with mock.patch("reid.vdms_adapter.vdms.vdms"):
      adapter = VDMSDatabase(set_name="gallery", dimensions=3, descriptor_ttl_secs=60)
    backend = adapter.db
    backend.connected = True
    backend.query.side_effect = _vdms_response
  else:
    adapter = QdrantDatabase(set_name="gallery", dimensions=3, descriptor_ttl_secs=60)
    backend = adapter.client = mock.Mock()
    adapter.connected = True
    collection = SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
        vectors=SimpleNamespace(size=3, distance=models.Distance.DOT))))
    backend.get_collection.return_value = collection
    backend.retrieve.return_value = []
    backend.query_points.return_value = SimpleNamespace(points=[SimpleNamespace(
        payload={"uuid": "gid-1", "rvid": "track-1"}, score=0.8)])
  service = ReIDService(adapter=adapter, connect=False)
  server = create_server(service)
  port = server.add_insecure_port("127.0.0.1:0")
  server.start()
  channel = grpc.insecure_channel(f"127.0.0.1:{port}")
  try:
    grpc.channel_ready_future(channel).result(timeout=5)
    yield SimpleNamespace(client=ReIDClient(channel), service=service, backend=backend,
                          adapter=adapter, channel=channel, backend_name=request.param)
  finally:
    channel.close()
    server.stop(0).wait(timeout=5)


def test_transport_baseline_success(transport):
  client = transport.client
  assert client.health()["ready"] is True
  assert client.health()["connected"] is True
  result = client.find_matches(QUERY)
  assert result["matches"][0][0]["uuid"] == "gid-1"
  assert client.find_schema_metadata("gallery")["metadata"] == [True, 3, "IP"]
  assert client.find_schema_metadata()["metadata"] == [True, 3, "IP"]
  result = client.purge_expired()["result"]
  assert result == (2 if transport.backend_name == "VDMS" else None)
  assert client.ingest_stats() == {"enabled": False}
  transport.service.ingest = SimpleNamespace(snapshot=lambda: {
      "counters": {"objects": 3}, "unique_id_counts": {"scene/person": 2}})
  assert client.ingest_stats()["counters"] == {"objects": 3}
  transport.backend.upsert.assert_not_called()
  transport.backend.create_collection.assert_not_called()


def test_transport_l2_accepts_zero_vectors_and_disabled_purge(transport):
  transport.adapter.similarity_metric = "L2"
  transport.adapter.descriptor_ttl_secs = 0
  transport.client.find_matches({**QUERY, "reid_vectors": [[0, 0, 0]]})
  transport.backend.reset_mock()
  assert transport.client.purge_expired() == {"result": 0}
  assert transport.backend.mock_calls == []


@pytest.mark.parametrize("method, payload", [
    ("Health", {"unexpected": True}),
    ("IngestStats", {"unexpected": True}),
    ("PurgeExpired", {"unexpected": True}),
    ("FindSchemaMetadata", {"set_name": 12}),
    ("FindSchemaMetadata", {"set_name": ""}),
    ("FindMatches", {}),
    ("FindMatches", {**QUERY, "object_type": ""}),
    ("FindMatches", {**QUERY, "constraints": []}),
    ("FindMatches", {**QUERY, "constraints": {"k_neighbors": 2}}),
    ("FindMatches", {**QUERY, "constraints": {"reid_vectors": []}}),
    ("FindMatches", {**QUERY, "constraints": {"confidence_threshold": 0}}),
    ("FindMatches", {**QUERY, "k_neighbors": 1.5}),
    ("FindMatches", {**QUERY, "k_neighbors": True}),
    ("FindMatches", {**QUERY, "reid_vectors": []}),
    ("FindMatches", {**QUERY, "reid_vectors": [[1, 2], [3]]}),
    ("FindMatches", {**QUERY, "reid_vectors": [["1", 0, 0]]}),
    ("FindMatches", {**QUERY, "reid_vectors": [[True, False, True]]}),
    ("FindMatches", {**QUERY, "reid_vectors": [[0, 0, 0]]}),
    ("FindMatches", {**QUERY, "reid_vectors": [[1, 2]]}),
])
def test_transport_invalid_request(transport, method, payload):
  transport.backend.reset_mock()
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.call(method, payload)
  assert failure.value.code() == grpc.StatusCode.INVALID_ARGUMENT
  assert transport.backend.mock_calls == []


def _fail_backend(transport):
  error = RuntimeError("private backend diagnostic")
  if transport.backend_name == "VDMS":
    transport.backend.query.side_effect = error
  else:
    for method in ("get_collections", "get_collection", "query_points", "delete"):
      getattr(transport.backend, method).side_effect = error


@pytest.mark.parametrize("method, payload", [
    ("FindMatches", QUERY), ("FindSchemaMetadata", {"set_name": "gallery"}),
    ("PurgeExpired", {}),
])
def test_transport_backend_failure(transport, method, payload):
  _fail_backend(transport)
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.call(method, payload)
  assert failure.value.code() == grpc.StatusCode.UNAVAILABLE
  assert "private" not in failure.value.details()


def test_transport_readiness_outage_and_recovery(transport):
  assert transport.client.health()["ready"] is True
  _fail_backend(transport)
  assert transport.client.health()["ready"] is False
  assert transport.client.health()["status"] == "degraded"
  assert transport.client.ingest_stats() == {"enabled": False}
  if transport.backend_name == "VDMS":
    transport.backend.query.side_effect = _vdms_response
  else:
    transport.backend.get_collections.side_effect = None
  assert transport.client.health()["ready"] is True


def test_transport_missing_schema_is_not_backend_failure(transport):
  if transport.backend_name == "VDMS":
    transport.backend.query.side_effect = None
    transport.backend.query.return_value = ([{"FindDescriptorSet": {"status": 0, "returned": 0}}], [])
  else:
    transport.backend.get_collection.side_effect = UnexpectedResponse(404, "Not Found", b"", {})
  assert transport.client.find_schema_metadata("missing")["metadata"] == [False, None, None]


def test_transport_failed_backend_status_is_not_empty_success(transport):
  if transport.backend_name == "VDMS":
    transport.backend.query.side_effect = None
    transport.backend.query.return_value = ([{"FindDescriptor": {"status": -1}}], [])
  else:
    transport.backend.query_points.side_effect = ValueError("backend decoding failure")
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.find_matches(QUERY)
  assert failure.value.code() == grpc.StatusCode.UNAVAILABLE


@pytest.mark.parametrize("method", ["AddEntry", "EnsureSchema", "DeleteGallery"])
def test_transport_has_no_general_gallery_write_rpc(transport, method):
  call = transport.channel.unary_unary(
      f"/{SERVICE_NAME}/{method}", request_serializer=struct_pb2.Struct.SerializeToString,
      response_deserializer=struct_pb2.Struct.FromString)
  with pytest.raises(grpc.RpcError) as failure:
    call(struct_pb2.Struct(), timeout=5)
  assert failure.value.code() == grpc.StatusCode.UNIMPLEMENTED


def test_proto_declares_exactly_the_client_surface():
  proto = Path(__file__).resolve().parents[3] / "reid/proto/reid.proto"
  methods = re.findall(r"rpc\s+(\w+)\(", proto.read_text())
  assert set(methods) == set(RPC_METHODS)
  assert len(methods) == len(RPC_METHODS)
  register = grpc.method_handlers_generic_handler
  with mock.patch("reid.server.grpc.method_handlers_generic_handler", wraps=register) as registration:
    server = create_server(ReIDService(adapter=FakeAdapter()))
    try:
      assert set(registration.call_args.args[1]) == set(methods)
    finally:
      server.stop(0).wait(timeout=5)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_client_requires_bounded_deadline(timeout):
  with pytest.raises(ValueError, match="finite and positive"):
    ReIDClient(mock.Mock(), timeout=timeout)


def test_transport_internal_error_is_sanitized(transport):
  transport.service.ingest = SimpleNamespace(snapshot=mock.Mock(
      side_effect=RuntimeError("private ingest diagnostic")))
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.ingest_stats()
  assert failure.value.code() == grpc.StatusCode.INTERNAL
  assert "private" not in failure.value.details()


@pytest.mark.parametrize("method, payload", [
    ("FindMatches", QUERY),
    ("FindSchemaMetadata", {"set_name": "gallery"}),
    ("PurgeExpired", {}),
])
def test_transport_no_response_is_backend_failure(transport, method, payload):
  if transport.backend_name == "VDMS":
    transport.backend.query.side_effect = None
    transport.backend.query.return_value = "NOT CONNECTED"
  else:
    transport.backend.get_collection.side_effect = UnexpectedResponse(503, "Unavailable", b"", {})
    transport.backend.query_points.side_effect = OSError("disconnected")
    transport.backend.delete.side_effect = OSError("disconnected")
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.call(method, payload)
  assert failure.value.code() == grpc.StatusCode.UNAVAILABLE
