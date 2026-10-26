# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""gRPC entry point for the standalone Re-ID service skeleton."""

import json
import hmac
import os
from concurrent import futures

import grpc
from google.protobuf import json_format
from google.protobuf import struct_pb2

from scene_common import log
from reid.api import CollectionSchemaConflictError, PoiNotFoundError, ReIDService, validate_request
from reid.client import SERVICE_NAME
from reid.ingest import build_from_env
from reid.reid_registry import create_reid_database


def _decode(request):
  return json_format.MessageToDict(request, preserving_proto_field_name=True)


def _encode(value):
  message = struct_pb2.Struct()
  json_format.ParseDict(_json_safe(value), message)
  return message


def _json_safe(value):
  if isinstance(value, dict):
    return {str(key): _json_safe(item) for key, item in value.items()}
  if isinstance(value, (list, tuple)):
    return [_json_safe(item) for item in value]
  if hasattr(value, "tolist"):
    return _json_safe(value.tolist())
  if isinstance(value, (str, int, float, bool)) or value is None:
    return value
  return json.loads(json.dumps(value, default=str))


def _authorize_token(token, action):
  def authorize(context):
    authorization = dict(context.invocation_metadata()).get("authorization", "")
    scheme, separator, supplied_token = authorization.partition(" ")
    if (not token or scheme.lower() != "bearer" or not separator or
        not hmac.compare_digest(supplied_token, token)):
      context.abort(grpc.StatusCode.PERMISSION_DENIED, f"{action} is not authorized")
  return authorize


def _handler(function, authorize=None):
  def call(request, context):
    if authorize is not None:
      authorize(context)
    try:
      return _encode(function(_decode(request)))
    except (KeyError, TypeError, ValueError):
      context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid ReID request")
    except CollectionSchemaConflictError as error:
      context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(error))
    except PoiNotFoundError as error:
      context.abort(grpc.StatusCode.NOT_FOUND, str(error))
    except ConnectionError:
      context.abort(grpc.StatusCode.UNAVAILABLE, "ReID backend unavailable")
    except Exception:
      context.abort(grpc.StatusCode.INTERNAL, "ReID operation failed")

  return grpc.unary_unary_rpc_method_handler(
      call,
      request_deserializer=struct_pb2.Struct.FromString,
      response_serializer=struct_pb2.Struct.SerializeToString,
  )


def _empty_request(function):
  def call(request):
    validate_request(request, set())
    return function()
  return call


def create_server(service=None, workers=4, collection_create_token=None, poi_write_token=None):
  """Create a gRPC server using the baseline Re-ID API methods."""
  service = service or ReIDService()
  if collection_create_token is None:
    collection_create_token = os.getenv("REID_COLLECTION_CREATE_TOKEN", "")
  if poi_write_token is None:
    poi_write_token = os.getenv("REID_POI_WRITE_TOKEN", "")
  server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))
  handlers = {
      "Health": _handler(_empty_request(service.health)),
      "FindMatches": _handler(service.find_matches),
      "FindSchemaMetadata": _handler(service.find_schema_metadata),
      "PurgeExpired": _handler(_empty_request(lambda: {"result": service.purge_expired()})),
      "IngestStats": _handler(_empty_request(service.ingest_stats)),
      "CreateCollection": _handler(
        service.create_collection, authorize=_authorize_token(collection_create_token, "Collection creation")),
      "EnrollPoi": _handler(
        service.enroll_poi, authorize=_authorize_token(poi_write_token, "POI enrollment")),
      "AppendPoiEmbeddings": _handler(
        service.append_poi_embeddings, authorize=_authorize_token(poi_write_token, "POI enrollment")),
  }
  server.add_generic_rpc_handlers((
      grpc.method_handlers_generic_handler(SERVICE_NAME, handlers),
  ))
  return server


def main():
  """Start the Re-ID gRPC server and, when enabled, the Tracker-stream ingest."""
  port = int(os.getenv("REID_SERVICE_PORT", "50051"))
  # Each (scene, category) matcher gets its own adapter/connection, as each
  # Controller UUIDManager does today.
  ingest = build_from_env(lambda: create_reid_database(None, dimensions=None))
  service = ReIDService(ingest=ingest)
  log.info(f"ReID backend {service.adapter.__class__.__name__}: {service.health()}")
  server = create_server(service)
  server.add_insecure_port(f"[::]:{port}")
  server.start()
  log.info(f"reid-service gRPC listening on :{port}")
  try:
    server.wait_for_termination()
  finally:
    if ingest is not None:
      ingest.stop()


if __name__ == "__main__":
  main()
