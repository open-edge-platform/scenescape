#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MQTT service tests for tracker.

Tests tracker's MQTT functionality including:
- Connection resilience (broker unavailability and reconnection)
- mTLS connection with client certificate authentication
- Message flow over encrypted connection
"""

import json
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import pytest
from pathlib import Path
from python_on_whales import DockerClient
from waiting import wait, TimeoutExpired

from utils.docker import (
    wait_for_readiness,
    is_tracker_ready,
    get_broker_host,
    get_container_logs,
    DEFAULT_TIMEOUT,
    POLL_INTERVAL,
)
from utils.schema import validate_camera_input, validate_scene_output


# Topic constants (match config/tracker.json scene and camera)
TOPIC_CAMERA_INPUT = "scenescape/data/camera/atag-qcam1"
TOPIC_SCENE_OUTPUT = "scenescape/data/scene/302cf49a-97ec-402d-a324-c5077b280b7b/thing"


def create_camera_detection_message(timestamp=None, object_id=1, bbox=None):
  """Create a valid camera detection message matching camera-data.schema.json."""
  # Use current timestamp to avoid lag detection dropping the message
  if timestamp is None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
  if bbox is None:
    bbox = {"x": 100, "y": 50, "width": 80, "height": 200}
  return {
      "id": "atag-qcam1",
      "timestamp": timestamp,
      "objects": {
          "thing": [
              {
                  "id": object_id,
                  "bounding_box_px": bbox
              }
          ]
      }
  }


def send_detection_sequence(client, count=5, interval_ms=67):
  """
  Send a sequence of detections to build tracker confidence.

  RobotVision requires multiple consistent detections before a track
  becomes "reliable". This sends detections at the configured FPS rate.

  Args:
      client: Connected MQTT client
      count: Number of detections to send (default 5)
      interval_ms: Milliseconds between detections (default 67ms = ~15 FPS)

  Returns:
      List of timestamps sent
  """
  import time
  timestamps = []
  for i in range(count):
    detection = create_camera_detection_message(object_id=1)
    validate_camera_input(detection)
    result = client.publish(TOPIC_CAMERA_INPUT, json.dumps(detection), qos=1)
    result.wait_for_publish()
    timestamps.append(detection["timestamp"])
    if i < count - 1:
      time.sleep(interval_ms / 1000.0)
  return timestamps


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
      f"TRACKER_SCENES_SOURCE=file\n"
  )

  docker = DockerClient(
      compose_files=[compose_path],
      compose_project_name=project_name,
      compose_project_directory=str(service_dir),
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
  wait(lambda: not is_tracker_ready(docker), timeout_seconds=5, sleep_seconds=0.2)
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
  Test mTLS connection and message flow.

  Phases:
  1. Verify mTLS connection (tracker ready)
  2. Verify message flow over TLS with schema validation
  """
  docker = tls_tracker_service["docker"]
  certs = tls_tracker_service["certs"]
  host, port = get_broker_host(docker, port=8883)

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

    # Send multiple detections to ensure message flow (tracking needs repeated detections)
    send_detection_sequence(client, count=5, interval_ms=67)

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

  print("\nAll mTLS phases passed")


def test_tracking_produces_reliable_tracks(tls_tracker_service):
  """
  Test RobotVision tracking produces reliable tracks after multiple detections.

  RobotVision's Kalman filter requires multiple consistent detections before
  a track becomes "reliable". This test sends a sequence of detections and
  validates the output track format.

  Validates:
  - Track id is a UUID string (mapped from RobotVision integer ID)
  - Track has required fields: translation, velocity, size, rotation
  - Output passes schema validation (UUID string id enforced)
  """
  docker = tls_tracker_service["docker"]
  certs = tls_tracker_service["certs"]
  host, port = get_broker_host(docker, port=8883)

  assert is_tracker_ready(docker), "Tracker should be ready"
  print("\nTracker ready, starting tracking test")

  received_messages = []

  def on_message(client, userdata, msg):
    received_messages.append(json.loads(msg.payload.decode()))

  client = mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=f"test-tracking-{uuid.uuid4().hex[:8]}"
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

    # Send detection sequence to build tracker confidence
    # With max_unreliable_time_s=1.0 at 15fps, tracks need 15+ frames to become reliable.
    # 20 detections at 67ms = ~1.3s, producing ~20 frames which exceeds the threshold.
    print("Sending detection sequence...")
    send_detection_sequence(client, count=20, interval_ms=67)

    # Wait for messages with tracks (may take a few chunks for reliability)
    def has_tracks():
      for msg in received_messages:
        if msg.get("objects") and len(msg["objects"]) > 0:
          return True
      return False

    wait(
        has_tracks,
        timeout_seconds=10,
        sleep_seconds=POLL_INTERVAL
    )

    # Find a message with tracks
    track_message = None
    for msg in received_messages:
      if msg.get("objects") and len(msg["objects"]) > 0:
        track_message = msg
        break

    assert track_message is not None, "Should have received message with tracks"
    print(f"Received {len(received_messages)} messages, found tracks")

    # Validate against schema (enforces UUID string id)
    validate_scene_output(track_message)
    print("Schema validation passed")

    # Additional type assertions
    track = track_message["objects"][0]
    assert isinstance(track["id"], str), f"Track id should be str, got {type(track['id'])}"
    parsed_uuid = uuid.UUID(track["id"])  # Raises ValueError if not valid UUID
    assert parsed_uuid.version == 4, f"Track id should be UUID v4, got version {parsed_uuid.version}"
    assert track["category"] == "thing", f"Category should be 'thing', got {track['category']}"
    assert len(track["translation"]) == 3, "Translation should have 3 elements"
    assert len(track["velocity"]) == 3, "Velocity should have 3 elements"
    assert len(track["size"]) == 3, "Size should have 3 elements"
    assert len(track["rotation"]) == 4, "Rotation should have 4 elements (quaternion)"

    print(f"Track validated: id={track['id']}, position={track['translation']}")
    print("\nTracking test passed")

  finally:
    client.loop_stop()
    client.disconnect()
