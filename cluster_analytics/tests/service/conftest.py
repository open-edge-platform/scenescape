#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration and fixtures for cluster analytics component tests.
"""

import sys
import uuid
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from python_on_whales import DockerClient
from waiting import wait
import paho.mqtt.client as mqtt


SUBSCRIBE_TOPIC = "scenescape/analytics/clusters/#"
READINESS_LOG_PATTERN = "Subscribed to"
DEFAULT_TIMEOUT = 30
POLL_INTERVAL = 0.5


def _get_broker_port(docker):
  """Return the host-mapped port for mosquitto port 1883."""
  containers = docker.compose.ps()
  for container in containers:
    if "broker" in container.name:
      ports = container.network_settings.ports
      port_key = "1883/tcp"
      if port_key in ports and ports[port_key]:
        return int(ports[port_key][0]["HostPort"])
  return 1883


def _is_service_ready(docker):
  """Return True when cluster-analytics has subscribed to DATA_REGULATED."""
  try:
    logs = docker.compose.logs(services=["cluster-analytics"])
    return READINESS_LOG_PATTERN in logs
  except Exception:
    return False


@pytest.fixture(scope="function")
def cluster_analytics_service():
  """Start broker + cluster-analytics via docker-compose, yield helpers, tear down."""
  service_dir = Path(__file__).parent
  project_name = f"ca-test-{uuid.uuid4().hex[:8]}"

  docker = DockerClient(
    compose_files=[service_dir / "docker-compose.yaml"],
    compose_project_name=project_name,
    compose_project_directory=str(service_dir),
  )

  try:
    docker.compose.up(detach=True, wait=False)
    wait(
      lambda: _is_service_ready(docker),
      timeout_seconds=DEFAULT_TIMEOUT,
      sleep_seconds=POLL_INTERVAL,
    )
    broker_port = _get_broker_port(docker)
    yield {"docker": docker, "broker_port": broker_port}
  finally:
    docker.compose.down(remove_orphans=True, volumes=True)


@pytest.fixture
def mqtt_client(cluster_analytics_service):
  """Return a connected paho MQTT client subscribed to analytics/clusters/#."""
  port = cluster_analytics_service["broker_port"]

  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
  client.connect("localhost", port, keepalive=10)
  client.subscribe(SUBSCRIBE_TOPIC, qos=1)
  client.loop_start()

  yield client

  client.loop_stop()
  client.disconnect()
