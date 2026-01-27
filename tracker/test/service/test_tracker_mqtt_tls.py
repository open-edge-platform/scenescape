#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
TLS MQTT service tests for tracker.

Validates MQTT TLS functionality including:
- CA-only TLS connection (server verification)
- mTLS connection (mutual authentication)
- Certificate rejection scenarios

Uses the same docker-compose.yaml as non-TLS tests but configures it
for TLS mode via environment variables. Certificates are generated
dynamically and mounted via Docker Compose secrets.
"""

import json
import os
import time
import uuid
import pytest
import paho.mqtt.client as mqtt

from pathlib import Path
from python_on_whales import DockerClient
from waiting import wait, TimeoutExpired

from tls_utils import generate_test_certificates
from helpers import DEFAULT_TIMEOUT, POLL_INTERVAL


def is_tracker_ready(docker):
  """Check if tracker /readyz endpoint returns healthy."""
  try:
    result = docker.compose.execute(
        "tracker",
        ["/scenescape/tracker", "healthcheck", "--endpoint", "/readyz"],
        tty=False
    )
    return "OK" in result or result.strip() == ""
  except Exception:
    return False


def wait_for_readiness(docker, timeout=DEFAULT_TIMEOUT):
  """Wait until tracker /readyz returns 200."""
  wait(lambda: is_tracker_ready(docker), timeout_seconds=timeout, sleep_seconds=POLL_INTERVAL)


def get_tls_broker_host(docker):
  """Get TLS broker hostname accessible from test host."""
  containers = docker.compose.ps()
  for container in containers:
    if "-broker-" in container.name:
      ports = container.network_settings.ports
      if "8883/tcp" in ports and ports["8883/tcp"]:
        return "localhost", int(ports["8883/tcp"][0]["HostPort"])
  return "localhost", 8883


def get_tracker_logs(docker):
  """Get tracker container logs for debugging."""
  try:
    return docker.compose.logs("tracker")
  except Exception as e:
    return f"Failed to get logs: {e}"


def get_broker_logs(docker):
  """Get broker container logs for debugging."""
  try:
    return docker.compose.logs("broker")
  except Exception as e:
    return f"Failed to get logs: {e}"


@pytest.fixture(scope="function")
def tls_tracker_service(tls_certs):
  """
  Fixture that starts tracker service with TLS-enabled MQTT broker.

  Uses the same docker-compose.yaml as non-TLS tests but configures
  TLS mode via environment variables for secrets and tracker config.
  """
  service_dir = Path(__file__).parent
  compose_path = service_dir / "docker-compose.yaml"
  project_name = f"tracker-tls-test-{uuid.uuid4().hex[:8]}"

  # Write .env file in temp directory (auto-cleaned by tmp_path fixture)
  env_file = tls_certs.temp_dir / ".env"
  env_file.write_text(
      # Secrets file paths for compose
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
      # Tracker TLS config (paths inside container)
      f"TRACKER_MQTT_PORT=8883\n"
      f"TRACKER_MQTT_INSECURE=false\n"
      f"TRACKER_MQTT_TLS_CA_CERT=/run/secrets/ca_cert\n"
      f"TRACKER_MQTT_TLS_CLIENT_CERT=/run/secrets/client_cert\n"
      f"TRACKER_MQTT_TLS_CLIENT_KEY=/run/secrets/client_key\n"
  )

  docker = DockerClient(
      compose_files=[compose_path],
      compose_project_name=project_name,
      compose_env_files=[str(env_file)],
  )

  try:
    print(f"\n🔐 Starting TLS test environment: {project_name}")

    docker.compose.up(
        detach=True,
        wait=False,  # Don't wait, we'll do custom health check
    )

    # Wait for tracker to become ready
    try:
      wait_for_readiness(docker, timeout=30)
    except TimeoutExpired:
      # Print logs for debugging
      print("\n❌ Tracker failed to become ready. Logs:")
      print("--- Tracker logs ---")
      print(get_tracker_logs(docker))
      print("--- Broker logs ---")
      print(get_broker_logs(docker))
      raise

    yield {
        "docker": docker,
        "certs": tls_certs,
    }

  finally:
    print(f"\n🧹 Cleaning up TLS environment: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)


class TestTrackerMqttTls:
  """Test suite for MQTT TLS functionality."""

  def test_tracker_connects_with_mtls(self, tls_tracker_service):
    """
    Test that tracker connects to broker using mTLS.

    Verifies:
    - Tracker becomes ready with TLS configuration
    - Connection uses client certificate authentication
    """
    docker = tls_tracker_service["docker"]

    # If we got here, the fixture already verified readiness
    # which means TLS connection succeeded
    assert is_tracker_ready(docker), "Tracker should be ready with mTLS"

    print("\n✅ Tracker connected successfully with mTLS")

  def test_tls_message_flow(self, tls_tracker_service):
    """
    Test that messages flow correctly over TLS connection.

    Verifies:
    - Can publish detection message over TLS
    - Tracker processes and publishes output over TLS
    """
    docker = tls_tracker_service["docker"]
    certs = tls_tracker_service["certs"]

    host, port = get_tls_broker_host(docker)

    # Create TLS-enabled MQTT client
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"test-tls-{uuid.uuid4().hex[:8]}"
    )

    # Configure TLS
    client.tls_set(
        ca_certs=str(certs.ca.cert_path),
        certfile=str(certs.client.cert_path),
        keyfile=str(certs.client.key_path),
    )

    # Collect output messages
    received_messages = []

    def on_message(client, userdata, msg):
      received_messages.append(msg)

    client.on_message = on_message
    client.connect(host, port, keepalive=60)
    client.loop_start()

    try:
      # Subscribe to output topic
      client.subscribe("scenescape/data/scene/#", qos=1)

      # Wait for subscription to be established
      time.sleep(0.5)

      # Publish test detection
      detection = {
          "id": "test-camera",
          "timestamp": "2026-01-27T10:30:00.000Z",
          "objects": {
              "thing": [
                  {"id": 1, "bounding_box_px": {"x": 100, "y": 50, "width": 80, "height": 200}}
              ]
          }
      }

      result = client.publish(
          "scenescape/data/camera/test-camera",
          json.dumps(detection),
          qos=1
      )
      result.wait_for_publish()

      # Wait for output message
      try:
        wait(
            lambda: len(received_messages) > 0,
            timeout_seconds=DEFAULT_TIMEOUT,
            sleep_seconds=POLL_INTERVAL
        )
      except TimeoutExpired:
        pytest.fail("Did not receive output message over TLS")

      assert len(received_messages) > 0, "Should receive at least one message"
      print(f"\n✅ Message flow verified over TLS ({len(received_messages)} messages)")

    finally:
      client.loop_stop()
      client.disconnect()

  def test_tls_rejects_invalid_client_cert(self, tls_tracker_service):
    """
    Test that broker rejects connections with invalid client certificate.

    Verifies:
    - mTLS enforcement works correctly
    - Invalid certificates are rejected
    """
    docker = tls_tracker_service["docker"]
    certs = tls_tracker_service["certs"]

    host, port = get_tls_broker_host(docker)

    # Try to connect WITHOUT client certificate (should fail)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"test-no-cert-{uuid.uuid4().hex[:8]}"
    )

    # Configure TLS with CA only (no client cert)
    client.tls_set(
        ca_certs=str(certs.ca.cert_path),
    )

    connection_failed = False

    def on_connect(client, userdata, flags, rc, properties):
      nonlocal connection_failed
      if rc != 0:
        connection_failed = True

    def on_disconnect(client, userdata, disconnect_flags, rc, properties):
      nonlocal connection_failed
      connection_failed = True

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
      client.connect(host, port, keepalive=5)
      client.loop_start()
      time.sleep(3)  # Give time for connection attempt
      client.loop_stop()
    except Exception:
      connection_failed = True

    assert connection_failed, "Connection without client cert should fail"
    print("\n✅ mTLS correctly rejected connection without client certificate")
