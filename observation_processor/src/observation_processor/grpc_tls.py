# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""TLS helpers for the Observation Processor gRPC server and clients."""

import os

import grpc

DEFAULT_CERT = "/run/secrets/certs/scenescape-observation-processor.crt"
DEFAULT_KEY = "/run/secrets/certs/scenescape-observation-processor.key"
DEFAULT_ROOTCERT = "/run/secrets/certs/scenescape-ca.pem"
DEFAULT_SSL_TARGET_NAME = "observation-processor.scenescape.intel.com"


def insecure_requested() -> bool:
  """True when plaintext gRPC is explicitly requested for local development."""
  return os.getenv("OBSERVATION_PROCESSOR_INSECURE", "").strip().lower() in (
    "1", "true", "yes", "on")


def _path(env_name: str, default: str) -> str:
  return os.getenv(env_name, default)


def server_credentials(cert=None, key=None):
  """Build server TLS credentials from the service certificate and private key."""
  cert_path = cert or _path("OBSERVATION_PROCESSOR_CERT", DEFAULT_CERT)
  key_path = key or _path("OBSERVATION_PROCESSOR_KEY", DEFAULT_KEY)
  with open(key_path, "rb") as handle:
    private_key = handle.read()
  with open(cert_path, "rb") as handle:
    certificate_chain = handle.read()
  return grpc.ssl_server_credentials(((private_key, certificate_chain),))


def client_credentials(rootcert=None):
  """Build client TLS credentials that trust the SceneScape CA."""
  root_path = rootcert or _path("OBSERVATION_PROCESSOR_ROOTCERT", DEFAULT_ROOTCERT)
  with open(root_path, "rb") as handle:
    return grpc.ssl_channel_credentials(handle.read())


def bind_server_port(server, port, insecure=None, cert=None, key=None):
  """Bind the gRPC server to ``port`` with TLS unless insecure mode is requested."""
  address = f"[::]:{port}"
  if insecure if insecure is not None else insecure_requested():
    return server.add_insecure_port(address)
  return server.add_secure_port(address, server_credentials(cert=cert, key=key))


def create_channel(target, rootcert=None, insecure=None, ssl_target_name=None):
  """Open a client channel, using TLS by default."""
  if insecure if insecure is not None else insecure_requested():
    return grpc.insecure_channel(target)
  credentials = client_credentials(rootcert=rootcert)
  target_name = ssl_target_name or _path(
    "OBSERVATION_PROCESSOR_SSL_TARGET_NAME", DEFAULT_SSL_TARGET_NAME)
  options = (("grpc.ssl_target_name_override", target_name),)
  return grpc.secure_channel(target, credentials, options=options)
