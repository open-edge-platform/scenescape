# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backend-neutral client for the baseline ReID gRPC contract."""

import math

from google.protobuf import json_format, struct_pb2


SERVICE_NAME = "scenescape.reid.ReIDService"
RPC_METHODS = ("Health", "FindMatches", "FindSchemaMetadata", "PurgeExpired", "IngestStats")


class ReIDClient:
  """Use a caller-owned gRPC channel; every call has a finite deadline."""

  def __init__(self, channel, timeout=5.0):
    if not math.isfinite(timeout) or timeout <= 0:
      raise ValueError("timeout must be finite and positive")
    self.timeout = timeout
    self._methods = {
        name: channel.unary_unary(
            f"/{SERVICE_NAME}/{name}",
            request_serializer=struct_pb2.Struct.SerializeToString,
            response_deserializer=struct_pb2.Struct.FromString,
        ) for name in RPC_METHODS
    }

  def call(self, method, request=None):
    """Call a declared method and preserve grpc.RpcError status codes."""
    message = struct_pb2.Struct()
    json_format.ParseDict({} if request is None else request, message)
    response = self._methods[method](message, timeout=self.timeout)
    return json_format.MessageToDict(response, preserving_proto_field_name=True)

  def health(self):
    """Return process health and current backend readiness."""
    return self.call("Health")

  def find_matches(self, request):
    """Query matching without enrolling descriptors."""
    return self.call("FindMatches", request)

  def find_schema_metadata(self, set_name=None):
    """Read the configured or explicitly named descriptor-set metadata."""
    request = {} if set_name is None else {"set_name": set_name}
    return self.call("FindSchemaMetadata", request)

  def purge_expired(self):
    """Trigger TTL reclaim; this is not a general-gallery write interface."""
    return self.call("PurgeExpired")

  def ingest_stats(self):
    """Read live-loop counters, or enabled=false when ingest is disabled."""
    return self.call("IngestStats")
