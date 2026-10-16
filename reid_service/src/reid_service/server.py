# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""gRPC entry point for the standalone Re-ID service skeleton."""

import json
import os
from concurrent import futures

import grpc
from google.protobuf import json_format
from google.protobuf import struct_pb2

from scene_common import log
from reid_service.api import ReIDService
from reid_service.ingest import build_from_env
from reid_service.reid_registry import create_reid_database


SERVICE_NAME = "scenescape.reid.ReIDService"


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


def _handler(function):
  def call(request, context):
    try:
      return _encode(function(_decode(request)))
    except (KeyError, TypeError, ValueError) as error:
      context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
    except Exception as error:
      context.abort(grpc.StatusCode.INTERNAL, str(error))

  return grpc.unary_unary_rpc_method_handler(
    call,
    request_deserializer=struct_pb2.Struct.FromString,
    response_serializer=struct_pb2.Struct.SerializeToString,
  )


def create_server(service=None, workers=4):
  """Create a gRPC server using the baseline Re-ID API methods."""
  service = service or ReIDService()
  server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))
  handlers = {
    "Health": _handler(lambda request: service.health()),
    "FindMatches": _handler(service.find_matches),
    "FindSchemaMetadata": _handler(service.find_schema_metadata),
    "PurgeExpired": _handler(lambda request: {"result": service.purge_expired()}),
    "IngestStats": _handler(lambda request: service.ingest_stats()),
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
