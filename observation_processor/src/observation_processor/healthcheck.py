# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Container HEALTHCHECK probe: queries grpc.health.v1 process liveness."""

import os
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc


def main():
  port = os.getenv("OBSERVATION_PROCESSOR_SERVICE_PORT", "50052")
  try:
    with grpc.insecure_channel(f"localhost:{port}") as channel:
      response = health_pb2_grpc.HealthStub(channel).Check(
          health_pb2.HealthCheckRequest(service=""), timeout=3)
  except grpc.RpcError:
    sys.exit(1)
  if response.status != health_pb2.HealthCheckResponse.SERVING:
    sys.exit(1)


if __name__ == "__main__":
  main()
