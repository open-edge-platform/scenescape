#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MQTT service tests for tracker.

Tests tracker's MQTT functionality including:
- Connection resilience (broker unavailability and reconnection)
- mTLS connection with client certificate authentication
- Message flow over encrypted connection
- Certificate enforcement (rejection of invalid certs)
"""

import json
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
from pathlib import Path
from python_on_whales import DockerClient
from waiting import wait, TimeoutExpired

from utils.docker import (
    wait_for_readiness,
    is_tracker_ready,
    DEFAULT_TIMEOUT,
    POLL_INTERVAL,
)
from utils.schema import validate_camera_input, validate_scene_output


# Topic constants (match message_handler.hpp)
TOPIC_CAMERA_INPUT = "scenescape/data/camera/test-camera"
TOPIC_SCENE_OUTPUT = "scenescape/data/scene/dummy-scene/thing"


def get_tls_broker_host(docker):
  """Get TLS broker hostname accessible from test host."""
  containers = docker.compose.ps()
  for container in containers:
    if "-broker-" in container.name:
      ports = container.network_settings.ports
      if "8883/tcp" in ports and ports["8883/tcp"]:
        return "localhost", int(ports["8883/tcp"][0]["HostPort"])
  return "localhost", 8883


def get_container_logs(docker, service):
  """Get container logs for debugging."""
  try:
    return docker.compose.logs(service)
  except Exception as e:
    return f"Failed to get logs: {e}"


def create_camera_detection_message():
  """Create a valid camera detection message matching camera-data.schema.json."""
  return {
      "id": "test-camera",
      "timestamp": "2026-01-27T10:30:00.000Z",
      "objects": {
          "thing": [
              {
                  "id": 1,
                  "bounding_box_px": {"x": 100, "y": 50, "width": 80, "height": 200}
              }
          ]
      }
  }


@pytest.fixture(scope="function")
def tls_tracker_service(tls_certs):
  """
  Fixture that starts tracker service with TLS-enabled MQTT broker.

  Uses docker-compose.yaml configured for TLS mode via environment variables.
  """
  service_dir = Path(__file__).parent
  compose_path = service_dir / "docker-compose.yaml"
  project_name = f"tracker-tls-{uuid.uuid4().hex[:8]}"

  env_file = tls_certs.temp_dir / ".env"
  env_file.write_text(
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
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
    print(f"\nStarting TLS test environment: {project_name}")
    docker.compose.up(detach=True, wait=False)

    try:
      wait_for_readiness(docker, timeout=30)
    except TimeoutExpired:
      print("\nTracker failed to become ready. Logs:")
      print("--- Tracker logs ---")
      print(get_container_logs(docker, "tracker"))
      print("--- Broker logs ---")
      print(get_container_logs(docker, "broker"))
      raise

    yield {"docker": docker, "certs": tls_certs}

  finally:
    print(f"\nCleaning up TLS environment: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)


def test_mqtt_connection_resilience(tracker_service_delayed_broker):
  """
  Test tracker MQTT connection lifecycle and resilience.

  Phases:
  1. Tracker NOT ready (broker stopped by fixture)
  2. Start broker → tracker becomes ready
  3. Stop broker → tracker becomes not ready
  4. Restart broker → tracker reconnects
  """
  docker = tracker_service_delayed_broker["docker"]

  # Phase 1: Verify tracker is NOT ready (broker stopped by fixture)
  time.sleep(2)  # Give tracker time to detect broker is gone
  assert not is_tracker_ready(docker), \
      "Tracker should NOT be ready without broker"
  print("\nPhase 1: Tracker correctly reports not ready (no broker)")

  # Phase 2: Start broker, verify tracker connects
  print("Phase 2: Starting broker...")
  docker.compose.start(services=["broker"])
  wait_for_readiness(docker, timeout=15)
  print("Phase 2: Tracker connected to broker")

  # Phase 3: Stop broker, verify tracker becomes not ready
  print("Phase 3: Stopping broker...")
  docker.compose.stop(services=["broker"])
  wait(lambda: not is_tracker_ready(docker), timeout_seconds=10, sleep_seconds=0.2)
  print("Phase 3: Tracker detected broker disconnect")

  # Phase 4: Restart broker, verify tracker reconnects
  print("Phase 4: Restarting broker...")
  docker.compose.start(services=["broker"])
  wait_for_readiness(docker, timeout=15)
  print("Phase 4: Tracker reconnected to broker")

  print("\nAll connection resilience phases passed")


def test_mqtt_message_flow(tls_tracker_service):
  """
  Test mTLS connection, message flow, and certificate enforcement.

  Phases:
  1. Verify mTLS connection (tracker ready)
  2. Verify message flow over TLS with schema validation
  3. Verify broker rejects connections without valid client cert
  """
  docker = tls_tracker_service["docker"]
  certs = tls_tracker_service["certs"]
  host, port = get_tls_broker_host(docker)

  # Phase 1: Verify mTLS connection
  assert is_tracker_ready(docker), "Tracker should be ready with mTLS"
  print("\nPhase 1: Tracker connected with mTLS")

  # Phase 2: Verify message flow over TLS
  received_messages = []

  def on_message(client, userdata, msg):
    received_messages.append(json.loads(msg.payload.decode()))

  client = mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=f"test-tls-{uuid.uuid4().hex[:8]}"
  )
  client.tls_set(
      ca_certs=str(certs.ca.cert_path),
      certfile=str(certs.client.cert_path),
      keyfile=str(certs.client.key_path),
  )
  client.on_message = on_message
  client.connect(host, port, keepalive=60)
  client.loop_start()

  try:
    client.subscribe(TOPIC_SCENE_OUTPUT, qos=1)
    time.sleep(0.5)  # Wait for subscription

    detection = create_camera_detection_message()
    validate_camera_input(detection)  # Validate input against schema
    result = client.publish(TOPIC_CAMERA_INPUT, json.dumps(detection), qos=1)
    result.wait_for_publish()

    wait(
        lambda: len(received_messages) > 0,
        timeout_seconds=DEFAULT_TIMEOUT,
        sleep_seconds=POLL_INTERVAL
    )

    validate_scene_output(received_messages[0])  # Validate output against schema
    print("Phase 2: Message flow verified over TLS")
  finally:
    client.loop_stop()
    client.disconnect()

  # Phase 3: Verify mTLS enforcement (reject invalid cert)
  invalid_client = mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=f"test-no-cert-{uuid.uuid4().hex[:8]}"
  )
  invalid_client.tls_set(ca_certs=str(certs.ca.cert_path))  # No client cert

  connection_failed = False

  def on_connect(client, userdata, flags, rc, properties):
    nonlocal connection_failed
    if rc != 0:
      connection_failed = True

  def on_disconnect(client, userdata, disconnect_flags, rc, properties):
    nonlocal connection_failed
    connection_failed = True

  invalid_client.on_connect = on_connect
  invalid_client.on_disconnect = on_disconnect

  try:
    invalid_client.connect(host, port, keepalive=5)
    invalid_client.loop_start()
    time.sleep(3)  # Give time for connection attempt
    invalid_client.loop_stop()
  except Exception:
    connection_failed = True

  assert connection_failed, "Connection without client cert should fail"
  print("Phase 3: mTLS correctly rejected connection without client certificate")

  print("\nAll mTLS phases passed")
