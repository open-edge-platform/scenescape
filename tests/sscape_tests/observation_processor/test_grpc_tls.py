# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""TLS binding helpers for the Observation Processor gRPC server."""

import subprocess
from pathlib import Path

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from observation_processor import grpc_tls
from observation_processor.server import create_server


def _write_self_signed(tmp_path: Path):
  key_path = tmp_path / "server.key"
  cert_path = tmp_path / "server.crt"
  subprocess.run([
    "openssl", "req", "-x509", "-newkey", "ec",
    "-pkeyopt", "ec_paramgen_curve:secp384r1", "-nodes",
    "-keyout", str(key_path), "-out", str(cert_path), "-days", "1",
    "-subj", f"/CN={grpc_tls.DEFAULT_SSL_TARGET_NAME}",
    "-addext", f"subjectAltName=DNS:{grpc_tls.DEFAULT_SSL_TARGET_NAME}",
  ], check=True, capture_output=True)
  return cert_path, key_path


def test_insecure_bind_when_requested(monkeypatch):
  monkeypatch.setenv("OBSERVATION_PROCESSOR_INSECURE", "1")
  server, _ = create_server()
  port = grpc_tls.bind_server_port(server, 0)
  server.start()
  try:
    with grpc_tls.create_channel(f"localhost:{port}") as channel:
      status = health_pb2_grpc.HealthStub(channel).Check(
        health_pb2.HealthCheckRequest(service=""), timeout=3)
    assert status.status == health_pb2.HealthCheckResponse.SERVING
  finally:
    server.stop(0)


def test_tls_bind_serves_secure_clients(tmp_path, monkeypatch):
  monkeypatch.delenv("OBSERVATION_PROCESSOR_INSECURE", raising=False)
  cert_path, key_path = _write_self_signed(tmp_path)
  server, _ = create_server()
  port = grpc_tls.bind_server_port(server, 0, insecure=False,
                                   cert=str(cert_path), key=str(key_path))
  server.start()
  try:
    with grpc_tls.create_channel(
        f"localhost:{port}", rootcert=str(cert_path), insecure=False) as channel:
      status = health_pb2_grpc.HealthStub(channel).Check(
        health_pb2.HealthCheckRequest(service=""), timeout=3)
    assert status.status == health_pb2.HealthCheckResponse.SERVING
    channel = grpc.insecure_channel(f"localhost:{port}")
    try:
      with pytest.raises(grpc.RpcError):
        health_pb2_grpc.HealthStub(channel).Check(
          health_pb2.HealthCheckRequest(service=""), timeout=1)
    finally:
      channel.close()
  finally:
    server.stop(0)
