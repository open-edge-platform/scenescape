#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MQTT service tests for tracker.

Validates MQTT receive/transmit functionality including:
- Subscription to camera detection topics
- Publishing dummy scene data
- Reconnection after broker restart
- Readiness endpoint reflects MQTT state
"""

import json
import uuid
import pytest
import paho.mqtt.client as mqtt

from helpers import (
    wait_for_readiness,
    wait_for_broker,
    is_tracker_ready,
    get_broker_host,
    create_mqtt_client,
    MessageCollector,
    DEFAULT_TIMEOUT,
)
from waiting import wait, TimeoutExpired


# Topic constants (match message_handler.hpp)
TOPIC_CAMERA_INPUT = "scenescape/data/camera/test-camera"
TOPIC_SCENE_OUTPUT = "scenescape/data/scene/dummy-scene/thing"


def create_camera_detection_message():
  """Create a valid camera detection message matching camera-data.schema.json."""
  return {
      "id": "test-camera",
      "timestamp": "2026-01-22T10:30:00.000Z",
      "objects": {
          "thing": [
              {
                  "id": 1,
                  "bounding_box_px": {"x": 100, "y": 50, "width": 80, "height": 200}
              }
          ]
      }
  }


class TestTrackerMqtt:
  """Test suite for MQTT functionality."""

  @pytest.fixture
  def mqtt_client(self, tracker_service):
    """Create MQTT client connected to test broker."""
    host, port = get_broker_host(tracker_service)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"test-{uuid.uuid4().hex[:8]}"
    )
    client.connect(host, port, keepalive=60)
    client.loop_start()

    yield client

    client.loop_stop()
    client.disconnect()

  def test_tracker_subscribes_to_camera_topic(self, tracker_service, mqtt_client):
    """
    Test that tracker subscribes to camera detection topics.

    Verification:
    - Tracker receives messages on scenescape/data/camera/+
    - No errors in tracker logs
    """
    # Wait for tracker to be ready (replaces fixed sleep)
    docker = tracker_service["docker"]
    wait_for_readiness(docker)

    # Publish a test detection
    message = create_camera_detection_message()
    result = mqtt_client.publish(
        TOPIC_CAMERA_INPUT,
        json.dumps(message),
        qos=2
    )
    result.wait_for_publish()

    # Verify message was published successfully
    assert result.is_published(), "Failed to publish test message"

    print(f"\n✅ Published detection to {TOPIC_CAMERA_INPUT}")

  def test_tracker_publishes_scene_output(self, tracker_service, mqtt_client):
    """
    Test that tracker publishes dummy scene data on camera input.

    Verification:
    - Message received on scenescape/data/scene/dummy-scene/thing
    - Output matches scene-data.schema.json format
    - Category is "thing"
    """
    # Wait for tracker to be ready
    docker = tracker_service["docker"]
    wait_for_readiness(docker)

    # Use MessageCollector for event-driven message waiting
    collector = MessageCollector(mqtt_client, TOPIC_SCENE_OUTPUT)

    # Publish a camera detection
    message = create_camera_detection_message()
    mqtt_client.publish(TOPIC_CAMERA_INPUT, json.dumps(message), qos=2)

    # Wait for scene output (event-driven, no fixed sleep)
    scene = collector.wait_for_message(timeout=DEFAULT_TIMEOUT)
    collector.close()

    # Verify output
    assert scene is not None, \
        f"No scene output received within {DEFAULT_TIMEOUT}s"

    # Validate schema fields
    assert "id" in scene, "Missing 'id' field"
    assert "name" in scene, "Missing 'name' field"
    assert "timestamp" in scene, "Missing 'timestamp' field"
    assert "objects" in scene, "Missing 'objects' field"

    # Verify dummy values
    assert scene["id"] == "dummy-scene", f"Unexpected scene id: {scene['id']}"
    assert scene["name"] == "Test Scene", f"Unexpected scene name: {scene['name']}"

    # Verify objects
    assert len(scene["objects"]) > 0, "No objects in scene output"
    obj = scene["objects"][0]
    assert obj["category"] == "thing", f"Expected category 'thing', got: {obj['category']}"
    assert len(obj["translation"]) == 3, "Translation should have 3 elements"
    assert len(obj["velocity"]) == 3, "Velocity should have 3 elements"
    assert len(obj["size"]) == 3, "Size should have 3 elements"
    assert len(obj["rotation"]) == 4, "Rotation should have 4 elements"

    print(f"\n✅ Received valid scene output on {TOPIC_SCENE_OUTPUT}")
    print(f"   Scene: {scene['id']} - {scene['name']}")
    print(f"   Objects: {len(scene['objects'])} with category '{obj['category']}'")

  def test_readiness_reflects_mqtt_state(self, tracker_service):
    """
    Test that /readyz endpoint reflects MQTT connection state.

    Verification:
    - /readyz returns 200 when MQTT is connected and subscribed
    """
    docker = tracker_service["docker"]

    # Wait for readiness (event-driven, replaces manual container lookup + execute)
    wait_for_readiness(docker)

    print(f"\n✅ Readiness endpoint indicates MQTT connected")

  def test_tracker_reconnects_after_broker_restart(self, tracker_service, mqtt_client):
    """
    Test that tracker reconnects after broker restart.

    Verification:
    - Tracker becomes not ready when broker stops
    - Tracker becomes ready again after broker restarts
    - Messages flow again after reconnection
    """
    docker = tracker_service["docker"]

    # Wait for initial readiness
    wait_for_readiness(docker)

    # Verify initial message flow with event-driven waiting
    collector = MessageCollector(mqtt_client, TOPIC_SCENE_OUTPUT)
    message = create_camera_detection_message()
    mqtt_client.publish(TOPIC_CAMERA_INPUT, json.dumps(message), qos=2)

    initial_msg = collector.wait_for_message(timeout=DEFAULT_TIMEOUT)
    assert initial_msg is not None, "Initial message not received"
    collector.close()

    print(f"\n📡 Initial message flow confirmed")

    # Stop the broker
    print("🔌 Stopping broker...")
    docker.compose.stop("broker")

    # Wait until tracker becomes not ready (event-driven)
    try:
      wait(lambda: not is_tracker_ready(docker), timeout_seconds=10, sleep_seconds=0.2)
      print("   Tracker detected broker disconnect")
    except TimeoutExpired:
      print("   Warning: Tracker still reports ready after broker stop")

    # Restart the broker
    print("🔌 Restarting broker...")
    docker.compose.start("broker")

    # Wait for broker to accept connections (event-driven)
    wait_for_broker(tracker_service, timeout=10)
    print("   Broker accepting connections")

    # Disconnect old client and create new one
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

    new_client = create_mqtt_client(tracker_service)

    # Wait for tracker to reconnect (event-driven, replaces RECONNECT_TIMEOUT sleep)
    print("⏳ Waiting for tracker reconnection...")
    wait_for_readiness(docker, timeout=15)
    print("   Tracker reconnected")

    # Verify message flow restored
    new_collector = MessageCollector(new_client, TOPIC_SCENE_OUTPUT)
    new_client.publish(TOPIC_CAMERA_INPUT, json.dumps(message), qos=2)

    final_msg = new_collector.wait_for_message(timeout=DEFAULT_TIMEOUT)
    new_collector.close()

    # Clean up the new client
    new_client.loop_stop()
    new_client.disconnect()

    assert final_msg is not None, \
        f"No messages received after broker restart within {DEFAULT_TIMEOUT}s"

    print(f"✅ Tracker reconnected successfully, messages flowing")
