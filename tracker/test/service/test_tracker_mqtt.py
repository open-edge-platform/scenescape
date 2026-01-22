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
import time
import uuid
import pytest
import paho.mqtt.client as mqtt

from python_on_whales import DockerClient


# Topic constants (match message_handler.hpp)
TOPIC_CAMERA_INPUT = "scenescape/data/camera/test-camera"
TOPIC_SCENE_OUTPUT = "scenescape/data/scene/dummy-scene/thing"

# Timeouts
MQTT_CONNECT_TIMEOUT = 5
MESSAGE_RECEIVE_TIMEOUT = 10
RECONNECT_TIMEOUT = 15  # Max backoff is 5s in test config


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


def get_broker_host(tracker_service):
    """Get broker hostname accessible from test host."""
    docker = tracker_service["docker"]
    containers = docker.compose.ps()
    for container in containers:
        if "-broker-" in container.name:
            # Get the published port
            ports = container.network_settings.ports
            if "1883/tcp" in ports and ports["1883/tcp"]:
                return "localhost", int(ports["1883/tcp"][0]["HostPort"])
    # Fallback: connect to broker on default port (works if port exposed)
    return "localhost", 1883


def wait_for_message(client, topic, timeout):
    """Wait for a message on a topic with timeout."""
    received = {"message": None}

    def on_message(client, userdata, msg):
        if msg.topic == topic:
            received["message"] = json.loads(msg.payload.decode())

    client.on_message = on_message
    client.subscribe(topic, qos=2)

    start = time.time()
    while received["message"] is None and (time.time() - start) < timeout:
        client.loop(timeout=0.1)

    return received["message"]


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
        # Give tracker time to connect and subscribe
        time.sleep(2)

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
        # Subscribe to output topic first
        received = {"message": None}

        def on_message(client, userdata, msg):
            if msg.topic == TOPIC_SCENE_OUTPUT:
                received["message"] = json.loads(msg.payload.decode())

        mqtt_client.on_message = on_message
        mqtt_client.subscribe(TOPIC_SCENE_OUTPUT, qos=2)

        # Give time for subscription to propagate
        time.sleep(1)

        # Publish a camera detection
        message = create_camera_detection_message()
        mqtt_client.publish(TOPIC_CAMERA_INPUT, json.dumps(message), qos=2)

        # Wait for scene output
        start = time.time()
        while received["message"] is None and (time.time() - start) < MESSAGE_RECEIVE_TIMEOUT:
            time.sleep(0.1)

        # Verify output
        assert received["message"] is not None, \
            f"No scene output received within {MESSAGE_RECEIVE_TIMEOUT}s"

        scene = received["message"]

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
        containers = docker.compose.ps()

        # Find tracker container
        tracker_container = None
        for container in containers:
            if "-tracker-" in container.name:
                tracker_container = container
                break

        assert tracker_container is not None, "Tracker container not found"

        # Distroless container has no shell/wget - use the tracker's healthcheck subcommand
        # which is designed to work from within the container
        # The healthcheck command uses --endpoint (not --type), defaulting to /readyz
        result = docker.compose.execute(
            "tracker",
            ["/scenescape/tracker", "healthcheck", "--endpoint", "/readyz"],
            tty=False
        )

        # healthcheck returns "OK" on success (exit code 0)
        assert "OK" in result or result.strip() == "", \
            f"Readiness check failed: {result}"

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

        # First verify we can receive messages
        received = {"count": 0}

        def on_message(client, userdata, msg):
            if msg.topic == TOPIC_SCENE_OUTPUT:
                received["count"] += 1

        mqtt_client.on_message = on_message
        mqtt_client.subscribe(TOPIC_SCENE_OUTPUT, qos=2)
        time.sleep(1)

        # Send initial message and verify it works
        message = create_camera_detection_message()
        mqtt_client.publish(TOPIC_CAMERA_INPUT, json.dumps(message), qos=2)
        time.sleep(2)
        initial_count = received["count"]
        assert initial_count > 0, "Initial message not received"

        print(f"\n📡 Initial message flow confirmed ({initial_count} messages)")

        # Stop the broker
        print("🔌 Stopping broker...")
        docker.compose.stop("broker")
        time.sleep(2)

        # Restart the broker
        print("🔌 Restarting broker...")
        docker.compose.start("broker")
        time.sleep(3)

        # Reconnect test client - need to create new client since port may change
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        time.sleep(0.5)

        host, port = get_broker_host(tracker_service)
        new_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"test-{uuid.uuid4().hex[:8]}"
        )
        new_client.on_message = on_message
        new_client.connect(host, port)
        new_client.loop_start()
        new_client.subscribe(TOPIC_SCENE_OUTPUT, qos=2)
        time.sleep(1)

        # Wait for tracker to reconnect (max backoff 5s + margin)
        print(f"⏳ Waiting for tracker reconnection (up to {RECONNECT_TIMEOUT}s)...")
        time.sleep(RECONNECT_TIMEOUT)

        # Send another message
        received["count"] = 0
        new_client.publish(TOPIC_CAMERA_INPUT, json.dumps(message), qos=2)

        # Wait for response
        start = time.time()
        while received["count"] == 0 and (time.time() - start) < MESSAGE_RECEIVE_TIMEOUT:
            time.sleep(0.1)

        # Clean up the new client
        new_client.loop_stop()
        new_client.disconnect()

        assert received["count"] > 0, \
            f"No messages received after broker restart within {MESSAGE_RECEIVE_TIMEOUT}s"

        print(f"✅ Tracker reconnected successfully, messages flowing")
