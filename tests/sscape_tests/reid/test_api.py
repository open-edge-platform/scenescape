# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the standalone Re-ID service facade."""

from pathlib import Path
import json
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
from scene_common.reid_constants import SCHEMA_MARKER_COLLECTION, SCHEMA_NAME


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
    return True, 2, "IP"

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
      True, 2, "IP")
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
  if commands[0].get("FindEntity", {}).get("class") == "VD:DESCSET":
    responses["FindEntity"] = {"status": 0, "returned": 1, "dimensions": 3, "metric": "IP"}
  return [{name: responses[name]} for command in commands for name in command], []


def _configure_vdms_schema_backend(backend):
  schemas = {"gallery": (3, "IP")}
  markers = {"gallery": {"set_name": "gallery", "dimensions": 3, "metric": "IP"}}
  records = []

  def query(commands, *args):
    responses = []
    for command in commands:
      operation, values = next(iter(command.items()))
      if operation == "FindEntity":
        if values.get("class") == "VD:DESCSET":
          set_name = values["constraints"]["VD:name"][1]
          schema = schemas.get(set_name)
          response = {"status": 0, "returned": int(schema is not None)}
          if schema:
            response["entities"] = [{"VD:name": set_name, "VD:dimensions": schema[0]}]
        else:
          set_filter = values.get("constraints", {}).get("set_name")
          set_name = set_filter[1] if set_filter else None
          marker = markers.get(set_name) if set_name else None
          response = {"status": 0, "returned": int(marker is not None)}
          if marker is not None:
            response["entities"] = [marker]
      elif operation == "FindDescriptorSet":
        schema = schemas.get(values.get("set"))
        response = {"status": 0, "returned": int(schema is not None)}
        if schema:
          response.update({"dimensions": schema[0], "metric": schema[1]})
      elif operation == "AddDescriptorSet":
        set_name = values["name"]
        if set_name in schemas:
          response = {"status": 1, "returned": 0}
        else:
          schemas[set_name] = (values["dimensions"], values["metric"])
          response = {"status": 0, "returned": 1}
      elif operation == "AddEntity":
        properties = values["properties"]
        markers[properties["set_name"]] = properties.copy()
        response = {"status": 0, "returned": 1}
      elif operation == "FindDescriptor":
        constraints = values.get("constraints", {})
        requested = values.get("results", {}).get("list", [])
        poi_id = constraints.get("uuid", [None, None])[1]
        if "persist" in requested:
          entities = [record for record in records if record.get("uuid") == poi_id]
          entities = [{key: value for key, value in entity.items() if key in requested}
                      for entity in entities]
        else:
          entities = [{"uuid": "gid-1", "rvid": "track-1", "_distance": 0.8}]
        response = {"status": 0, "returned": len(entities), "entities": entities}
      elif operation == "AddDescriptor":
        records.append(values["properties"].copy())
        response = {"status": 0, "returned": 1}
      elif operation == "DeleteExpired":
        response = {"status": 0, "deleted": 2}
      else:
        raise AssertionError(f"Unexpected VDMS operation: {operation}")
      responses.append({operation: response})
    return responses, []

  backend.query.side_effect = query
  return schemas, markers, records


def _configure_qdrant_schema_backend(backend):
  schemas = {
    "gallery": (3, models.Distance.DOT),
    SCHEMA_MARKER_COLLECTION: (1, models.Distance.EUCLID),
  }
  markers = {"gallery": {"set_name": "gallery", "dimensions": 3, "metric": "IP"}}
  records = []
  point_ids = {}

  def get_collection(name):
    if name not in schemas:
      raise UnexpectedResponse(404, "Not Found", b"", {})
    size, distance = schemas[name]
    return SimpleNamespace(
      config=SimpleNamespace(params=SimpleNamespace(
        vectors=SimpleNamespace(size=size, distance=distance))),
      payload_schema={},
    )

  def create_collection(collection_name, vectors_config):
    schemas[collection_name] = (vectors_config.size, vectors_config.distance)

  def upsert(collection_name, points, wait=True):
    for point in points:
      if collection_name == SCHEMA_MARKER_COLLECTION:
        markers[point.payload["set_name"]] = point.payload.copy()
        point_ids[str(point.id)] = point.payload["set_name"]
      else:
        records.append(SimpleNamespace(id=point.id, payload=point.payload.copy()))

  def retrieve(collection_name, ids, with_payload=True):
    payloads = [markers[point_ids[point_id]] for point_id in ids if point_id in point_ids]
    return [SimpleNamespace(payload=payload) for payload in payloads]

  def scroll(collection_name, **kwargs):
    return records, None

  backend.get_collections.return_value = SimpleNamespace(collections=[])
  backend.get_collection.side_effect = get_collection
  backend.create_collection.side_effect = create_collection
  backend.create_payload_index.return_value = None
  backend.upsert.side_effect = upsert
  backend.retrieve.side_effect = retrieve
  backend.scroll.side_effect = scroll
  backend.delete.return_value = None
  return schemas, markers, records


@pytest.fixture(params=["VDMS", "QDRANT"])
def transport(request):
  """Real gRPC and adapters; only external database clients are mocked."""
  if request.param == "VDMS":
    with mock.patch("reid.vdms_adapter.vdms.vdms"):
      adapter = VDMSDatabase(set_name="gallery", dimensions=3, descriptor_ttl_secs=60)
    backend = adapter.db
    backend.connected = True
    schemas, markers, records = _configure_vdms_schema_backend(backend)

    def collection_factory(collection_name, metric):
      declared = VDMSDatabase(set_name=collection_name, similarity_metric=metric,
                              dimensions=None, descriptor_ttl_secs=0)
      declared.db = backend
      return declared
  else:
    adapter = QdrantDatabase(set_name="gallery", dimensions=3, descriptor_ttl_secs=60)
    backend = adapter.client = mock.Mock()
    adapter.connected = True
    schemas, markers, records = _configure_qdrant_schema_backend(backend)

    def collection_factory(collection_name, metric):
      declared = QdrantDatabase(set_name=collection_name, similarity_metric=metric,
                                dimensions=None, descriptor_ttl_secs=0)
      declared.client = backend
      declared.connected = True
      return declared
    backend.query_points.return_value = SimpleNamespace(points=[SimpleNamespace(
        payload={"uuid": "gid-1", "rvid": "track-1"}, score=0.8)])
  service = ReIDService(adapter=adapter, connect=False, collection_factory=collection_factory)
  server = create_server(service, collection_create_token="transport-create-token",
                         poi_write_token="transport-poi-write-token")
  port = server.add_insecure_port("127.0.0.1:0")
  server.start()
  channel = grpc.insecure_channel(f"127.0.0.1:{port}")
  try:
    grpc.channel_ready_future(channel).result(timeout=5)
    yield SimpleNamespace(client=ReIDClient(channel), service=service, backend=backend,
                          adapter=adapter, channel=channel, backend_name=request.param,
                          schemas=schemas, markers=markers, records=records)
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
    ("CreateCollection", {"collection_name": "poi_invalid"}),
    ("CreateCollection", {"collection_name": "poi_invalid", "dimensions": True, "metric": "IP"}),
    ("CreateCollection", {"collection_name": "poi_invalid", "dimensions": 3, "metric": "cosine"}),
    ("CreateCollection", {"collection_name": "gallery ", "dimensions": 3, "metric": "IP"}),
    ("CreateCollection", {"collection_name": "gallery", "dimensions": 3, "metric": "IP"}),
    ("CreateCollection", {"collection_name": SCHEMA_NAME, "dimensions": 3, "metric": "IP"}),
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
    metadata = (("authorization", "Bearer transport-create-token"),) if method == "CreateCollection" else None
    transport.client.call(method, payload, metadata=metadata)
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
    transport.backend.query.return_value = ([{"FindEntity": {"status": 0, "returned": 0}}], [])
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


def test_transport_create_collection_requires_authorization(transport):
  request = {"collection_name": "poi_unauthorized", "dimensions": 3, "metric": "IP"}
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.call("CreateCollection", request)
  assert failure.value.code() == grpc.StatusCode.PERMISSION_DENIED
  assert "poi_unauthorized" not in transport.schemas


def test_transport_create_collection_is_idempotent_for_compatible_schema(transport):
  client = transport.client
  first = client.create_collection("poi_person", 3, "IP", "transport-create-token")
  second = client.create_collection("poi_person", 3, "IP", "transport-create-token")
  assert first == {"collection_name": "poi_person", "dimensions": 3, "metric": "IP", "created": True}
  assert second == {"collection_name": "poi_person", "dimensions": 3, "metric": "IP", "created": False}
  assert transport.schemas["poi_person"] == (
    3, "IP" if transport.backend_name == "VDMS" else models.Distance.DOT)


@pytest.mark.parametrize("dimensions, metric", [(4, "IP"), (3, "L2")])
def test_transport_create_collection_rejects_incompatible_schema(transport, dimensions, metric):
  token = "transport-create-token"
  transport.client.create_collection("poi_person", 3, "IP", token)
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.create_collection("poi_person", dimensions, metric, token)
  assert failure.value.code() == grpc.StatusCode.FAILED_PRECONDITION
  assert "poi_person" in failure.value.details()
  assert transport.schemas["poi_person"] == (
    3, "IP" if transport.backend_name == "VDMS" else models.Distance.DOT)


def _record_payload(transport, record):
  return record if transport.backend_name == "VDMS" else record.payload


def _declare_test_poi_collection(transport):
  return transport.client.create_collection(
    "poi_person", 3, "IP", "transport-create-token")


def test_transport_enrolls_and_appends_poi_vectors_with_audit(transport):
  _declare_test_poi_collection(transport)
  authorization = "transport-poi-write-token"
  created = transport.client.enroll_poi(
    "poi_person", "person", [[1, 0, 0], [0, 1, 0]], "high", "red jacket", "alice", authorization)
  poi_id = created["poi_id"]
  assert created["vector_count"] == 2
  records = [_record_payload(transport, record) for record in transport.records]
  assert len(records) == 2
  for record in records:
    assert record["uuid"] == poi_id
    assert "rvid" not in record
    assert json.loads(record["persist"])["poi_id"] == poi_id
    audit = json.loads(record["poi_enrollment_audit"])
    assert audit["action"] == "enroll"
    assert audit["enrolled_by"] == "alice", audit
    assert len(audit["vector_sha256"]) == 2

  appended = transport.client.append_poi_embeddings(
    "poi_person", poi_id, [[0, 0, 1]], "bob", authorization)
  assert appended == {"poi_id": poi_id, "collection_name": "poi_person", "vector_count": 1}
  records = [_record_payload(transport, record) for record in transport.records]
  assert len(records) == 3
  append_audit = json.loads(records[-1]["poi_enrollment_audit"])
  assert append_audit["action"] == "append_embeddings"
  assert append_audit["enrolled_by"] == "bob"
  assert len(append_audit["vector_sha256"]) == 1


@pytest.mark.parametrize("method", ["EnrollPoi", "AppendPoiEmbeddings"])
def test_transport_poi_writes_require_separate_writer_token(transport, method):
  _declare_test_poi_collection(transport)
  request = {"collection_name": "poi_person", "object_type": "person",
             "reid_vectors": [[1, 0, 0]], "severity": "high", "notes": "",
             "enrolled_by": "alice", "poi_id": "p1"}
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.call(method, request)
  assert failure.value.code() == grpc.StatusCode.PERMISSION_DENIED
  assert transport.records == []


def test_transport_append_requires_existing_poi(transport):
  _declare_test_poi_collection(transport)
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.append_poi_embeddings(
      "poi_person", "missing-poi", [[1, 0, 0]], "alice", "transport-poi-write-token")
  assert failure.value.code() == grpc.StatusCode.NOT_FOUND


def test_transport_poi_write_failure_returns_no_poi_id(transport):
  _declare_test_poi_collection(transport)
  if transport.backend_name == "VDMS":
    original = transport.backend.query.side_effect

    def fail_add(commands, *args):
      if any("AddDescriptor" in command for command in commands):
        raise RuntimeError("write failed")
      return original(commands, *args)

    transport.backend.query.side_effect = fail_add
  else:
    transport.backend.upsert.side_effect = RuntimeError("write failed")
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.enroll_poi(
      "poi_person", "person", [[1, 0, 0]], "high", "notes", "alice",
      "transport-poi-write-token")
  assert failure.value.code() == grpc.StatusCode.UNAVAILABLE
  assert "poi_id" not in failure.value.details()


def test_transport_infers_query_dimensions_without_configured_model(transport):
  """Production adapters start without dimensions; schema lookup must validate width."""
  transport.adapter.dimensions = None
  assert transport.client.find_matches(QUERY)["matches"][0][0]["uuid"] == "gid-1"
  transport.backend.reset_mock()
  with pytest.raises(grpc.RpcError) as failure:
    transport.client.find_matches({**QUERY, "reid_vectors": [[1, 2]]})
  assert failure.value.code() == grpc.StatusCode.INVALID_ARGUMENT
  assert transport.backend.mock_calls == []


def test_transport_validates_override_schema_dimensions(transport):
  transport.adapter.dimensions = None
  with mock.patch.object(transport.adapter, "findSchemaMetadata",
                         return_value=(True, 4, "IP")) as metadata:
    with pytest.raises(grpc.RpcError) as failure:
      transport.client.find_matches({**QUERY, "set_name": "other"})
    assert failure.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    metadata.assert_called_once_with("other")
    assert transport.client.find_matches(
        {**QUERY, "set_name": "other", "reid_vectors": [[1, 2, 3, 4]]})["matches"]
    metadata.assert_called_once()


def test_transport_missing_gallery_returns_empty_matches_without_search(transport):
  with mock.patch.object(transport.adapter, "findSchemaMetadata",
                         return_value=(False, None, None)), \
       mock.patch.object(transport.adapter, "findMatches") as search:
    result = transport.client.find_matches({**QUERY, "reid_vectors": [[1, 0, 0], [0, 1, 0]]})
    assert result == {"matches": [[], []]}
    search.assert_not_called()


def test_transport_missing_dimensions_is_unavailable_not_unvalidated_query(transport):
  transport.adapter.dimensions = None
  with mock.patch.object(transport.adapter, "findSchemaMetadata",
                         return_value=(True, None, None)), \
       mock.patch.object(transport.adapter, "findMatches") as search:
    with pytest.raises(grpc.RpcError) as failure:
      transport.client.find_matches(QUERY)
    assert failure.value.code() == grpc.StatusCode.UNAVAILABLE
    search.assert_not_called()


def test_schema_cache_expires_and_does_not_cache_absence(monkeypatch):
  now = [0.0]
  monkeypatch.setattr("reid.api.time.monotonic", lambda: now[0])
  adapter = FakeAdapter()
  adapter.findSchemaMetadata = mock.Mock(side_effect=[
      (False, None, None), (True, 2, "IP"), (True, 3, "IP")])
  service = ReIDService(adapter=adapter)
  query = {"object_type": "person", "reid_vectors": [[1, 0]]}
  assert service.find_matches(query) == {"matches": [[]]}
  assert service.find_matches(query)["matches"]
  assert service.find_matches(query)["matches"]
  assert adapter.findSchemaMetadata.call_count == 2
  now[0] = 30.0
  with pytest.raises(ValueError, match="dimensions"):
    service.find_matches(query)
  assert adapter.findSchemaMetadata.call_count == 3


@pytest.mark.parametrize("info", [
    "DescriptorSet Not Found!", "Set Not Found", "Not Found!",
    "Descriptors Not Found", "Descriptor Not Found in graph!",
])
def test_transport_vdms_documented_empty_status_is_success(transport, info):
  if transport.backend_name != "VDMS":
    pytest.skip("VDMS-specific response codes")
  original = _vdms_response

  def respond(commands, *args):
    if "FindDescriptor" in commands[0]:
      return [{"FindDescriptor": {"status": -1, "info": info}} for _ in commands], []
    return original(commands, *args)

  transport.backend.query.side_effect = respond
  assert transport.client.find_matches(QUERY) == {"matches": [[]]}


def test_vdms_missing_set_transaction_returns_one_empty_result_per_vector():
  with mock.patch("reid.vdms_adapter.vdms.vdms"):
    adapter = VDMSDatabase(dimensions=3)
  adapter.raise_on_backend_error = True
  command = {"FindDescriptor": {"set": adapter.set_name}}
  adapter.db.query.return_value = ([{
      "FailedCommand": command, "status": -1, "info": "DescriptorSet Not Found!",
  }], [])
  responses, _ = adapter.sendQuery([command, command], [b"one", b"two"])
  assert len(responses) == 2
  assert all(item["status"] == -1 for item in responses)


@pytest.mark.parametrize("responses", [
    [], [{"FindDescriptor": {"status": 0}}, {"FindDescriptor": {"status": 0}}],
    [{"FindDescriptor": {"status": -1, "info": "Blob (required) is null or size invalid"}}],
    [{"FindDescriptor": {"status": -1, "info": "Internal Server Error"}}],
    [{"FailedCommand": "Transaction", "status": -1, "info": "bad query"}],
    [{"FindDescriptor": {"info": "Not Found!"}}],
])
def test_vdms_strict_query_rejects_failures_and_incomplete_responses(responses):
  with mock.patch("reid.vdms_adapter.vdms.vdms"):
    adapter = VDMSDatabase()
  adapter.raise_on_backend_error = True
  adapter.db.query.return_value = (responses, [])
  with pytest.raises(ConnectionError):
    adapter.sendQuery([{"FindDescriptor": {"set": adapter.set_name}}])


def test_vdms_empty_lookup_status_does_not_hide_write_failure():
  with mock.patch("reid.vdms_adapter.vdms.vdms"):
    adapter = VDMSDatabase()
  adapter.raise_on_backend_error = True
  adapter.db.query.return_value = ([{
      "AddDescriptor": {"status": -1, "info": "DescriptorSet Not Found!"},
  }], [])
  with pytest.raises(ConnectionError):
    adapter.sendQuery([{"AddDescriptor": {"set": adapter.set_name}}])


def test_vdms_readiness_reconnects_with_rate_limiting(monkeypatch):
  now = [0.0]
  monkeypatch.setattr("reid.vdms_adapter.time.monotonic", lambda: now[0])
  with mock.patch("reid.vdms_adapter.vdms.vdms"):
    adapter = VDMSDatabase()
  adapter.raise_on_backend_error = True
  adapter.db.connected = False
  adapter.db.connect.side_effect = OSError("offline")
  adapter.db.query.return_value = "NOT CONNECTED"
  adapter.connect()
  assert adapter.backendAvailable() is False
  adapter.db.connect.assert_called_once()
  now[0] = 5.0
  assert adapter.backendAvailable() is False
  assert adapter.db.connect.call_count == 2
  assert adapter.backendAvailable() is False
  assert adapter.db.connect.call_count == 2
  now[0] = 10.0
  def reconnect(*args, **kwargs):
    adapter.db.connected = True
    adapter.db.query.return_value = ([{"FindEntity": {"status": 0, "returned": 0}}], [])
  adapter.db.connect.side_effect = reconnect
  assert adapter.backendAvailable() is True
  assert adapter.db.connect.call_count == 3
  assert adapter.backendAvailable() is True
  assert adapter.db.connect.call_count == 3
  query = adapter.db.query.call_args.args[0]
  assert query == [{"FindEntity": {"class": "ReidSchemaMarker",
                                 "results": {"list": ["set_name"]}}}]


def test_vdms_readiness_reconnects_stale_active_socket():
  with mock.patch("reid.vdms_adapter.vdms.vdms"):
    adapter = VDMSDatabase()
  adapter.db.connected = True
  adapter.db.query.side_effect = [
      ConnectionResetError("restarted"), ([{"FindEntity": {"status": 0, "returned": 0}}], []),
  ]
  assert adapter.backendAvailable() is True
  # Discard the failed stream first, then reset the client before reconnecting.
  assert adapter.db.disconnect.call_count == 2
  adapter.db.connect.assert_called_once()
