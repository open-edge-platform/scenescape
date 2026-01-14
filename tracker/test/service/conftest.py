#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for tracker service tests.
"""

import os
import uuid
import pytest
from python_on_whales import DockerClient


@pytest.fixture(scope="function")
def tracker_service():
  """
  Fixture that starts tracker service with broker and OTEL collector.

  Yields:
      dict: Contains 'containers' and 'docker' client
  """
  project_name = f"tracker-test-{uuid.uuid4().hex[:8]}"
  docker = DockerClient(
      compose_files=["docker-compose.test.yml"],
      compose_project_name=project_name,
      compose_project_directory=os.path.dirname(__file__)
  )

  try:
    print(f"\n🚀 Starting test environment: {project_name}")
    docker.compose.up(detach=True, wait=True)

    yield {"containers": docker.compose.ps(), "docker": docker}

  finally:
    print(f"\n🧹 Cleaning up: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)
