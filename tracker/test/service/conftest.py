#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration and fixtures for tracker service tests.
"""

import uuid
import pytest
from pathlib import Path
from python_on_whales import DockerClient
from waiting import wait

from utils.certs import generate_test_certificates
from utils.docker import is_tracker_ready


@pytest.fixture(scope="function")
def tls_certs(tmp_path):
  """
  Generate test TLS certificates in a temp directory.

  The docker-compose.yaml uses secrets configured via env vars
  pointing to these certificate files. This fixture is shared by
  both TLS and non-TLS tests - non-TLS tests need valid files for
  Docker Compose secrets even though the certs won't be used.
  """
  certs = generate_test_certificates(tmp_path / "certs")
  yield certs
  # Cleanup handled by tmp_path fixture


@pytest.fixture(scope="function")
def tracker_service(tls_certs):
  """
  Fixture that starts tracker service with broker and OTEL collector.

  Used for tests that need a fully running service (e.g., shutdown tests).

  Yields:
      dict: Contains 'containers' and 'docker' client
  """
  service_dir = Path(__file__).parent
  compose_file = service_dir / "docker-compose.yaml"

  project_name = f"tracker-test-{uuid.uuid4().hex[:8]}"

  env_file = tls_certs.temp_dir / ".env"
  env_file.write_text(
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
  )

  docker = DockerClient(
      compose_files=[compose_file],
      compose_project_name=project_name,
      compose_project_directory=str(service_dir),
      compose_env_files=[str(env_file)],
  )

  try:
    print(f"\nStarting test environment: {project_name}")
    docker.compose.up(detach=True, wait=True)

    yield {"containers": docker.compose.ps(), "docker": docker}

  finally:
    print(f"\nCleaning up: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)


@pytest.fixture(scope="function")
def tracker_service_delayed_broker(tls_certs):
  """
  Fixture that starts services, immediately stops broker, for delayed broker testing.

  Used to test that tracker can connect to a broker that starts after
  the tracker (delayed broker availability).

  Yields:
      dict: Contains 'docker' client (broker stopped after initial startup)
  """
  service_dir = Path(__file__).parent
  compose_file = service_dir / "docker-compose.yaml"

  project_name = f"tracker-delayed-{uuid.uuid4().hex[:8]}"

  # Write .env file in temp directory
  env_file = tls_certs.temp_dir / ".env"
  env_file.write_text(
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
  )

  docker = DockerClient(
      compose_files=[compose_file],
      compose_project_name=project_name,
      compose_project_directory=str(service_dir),
      compose_env_files=[str(env_file)],
  )

  try:
    print(f"\nStarting test environment: {project_name}")
    # Start all services (broker needed for tracker to start due to depends_on)
    docker.compose.up(detach=True, wait=False)

    # Wait for tracker container to exist before stopping broker
    def tracker_container_exists():
      try:
        containers = docker.compose.ps()
        return any("-tracker-" in c.name for c in containers)
      except Exception:
        return False

    wait(tracker_container_exists, timeout_seconds=10, sleep_seconds=0.2)
    print("Stopping broker to simulate delayed availability...")
    docker.compose.stop(services=["broker"])

    yield {"docker": docker}

  finally:
    print(f"\nCleaning up: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)
