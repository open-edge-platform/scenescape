#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
API scene loading service tests for tracker.

Tests the full dynamic scene loading path via mock Manager REST API:
- Auth file reading and authentication
- Scene fetching with token-based authorization
- API flat format -> schema nested format transformation
- Schema validation and scene registration
- MQTT subscriptions based on API-loaded cameras
"""

import json
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from waiting import wait

from utils.docker import (
    get_container_logs,
    is_tracker_ready,
    DEFAULT_TIMEOUT,
    POLL_INTERVAL,
)

# Expected camera/scene from test-scenes-api.json (same UIDs as config/scenes.json)
EXPECTED_SCENE_UID = "302cf49a-97ec-402d-a324-c5077b280b7b"
EXPECTED_CAMERA_UIDS = ["atag-qcam1", "atag-qcam2", "camera1", "camera2"]
TOPIC_CAMERA_INPUT = "scenescape/data/camera/atag-qcam1"
TOPIC_SCENE_OUTPUT = f"scenescape/data/scene/{EXPECTED_SCENE_UID}/thing"


def test_api_scene_loading(tracker_service_api):
  """
  Test that tracker loads scenes from mock Manager API and becomes ready.

  Verifies the full API path:
  1. Tracker reads auth file (test-auth.json)
  2. POSTs to mock-manager /api/v1/auth -> gets token
  3. GETs /api/v1/scenes with token -> gets scenes in flat API format
  4. Transforms flat format to nested schema format
  5. Validates against scene.schema.json
  6. Registers scenes and subscribes to camera topics
  7. Becomes ready (healthcheck passes)
  """
  docker = tracker_service_api["docker"]

  # Tracker should already be ready (fixture waits for readiness)
  assert is_tracker_ready(docker), "Tracker should be ready after API scene loading"

  # Verify logs confirm API loading path was used
  logs = get_container_logs(docker, "tracker")
  assert "Authenticated with Manager API" in logs, \
      f"Expected auth log. Got:\n{logs[-500:]}"
  assert "Fetched scenes from Manager API" in logs, \
      f"Expected fetch log. Got:\n{logs[-500:]}"
  assert "Loaded 2 scenes from Manager API" in logs, \
      f"Expected '2 scenes' log. Got:\n{logs[-500:]}"
  assert "Loaded 2 scenes with 4 cameras" in logs, \
      f"Expected '4 cameras' log. Got:\n{logs[-500:]}"

  # Verify subscriptions for all cameras from API-loaded scenes
  for camera_uid in EXPECTED_CAMERA_UIDS:
    expected_topic = f"scenescape/data/camera/{camera_uid}"
    assert expected_topic in logs, \
        f"Expected subscription to {expected_topic}. Got:\n{logs[-500:]}"

  print("\nAPI scene loading verified: auth -> fetch -> transform -> subscribe")


def test_api_scene_message_flow(tracker_service_api):
  """
  Test end-to-end message flow with API-loaded scenes.

  Verifies that scenes loaded via the API path produce the same
  functional behavior as file-loaded scenes: camera detections
  are processed and scene output is published.
  """
  docker = tracker_service_api["docker"]

  assert is_tracker_ready(docker), "Tracker should be ready"

  # Connect to broker from host (non-TLS, port 1883)
  containers = docker.compose.ps()
  broker_port = 1883
  for container in containers:
    if "-broker-" in container.name:
      ports = container.network_settings.ports
      if "1883/tcp" in ports and ports["1883/tcp"]:
        broker_port = int(ports["1883/tcp"][0]["HostPort"])
        break

  received_messages = []

  def on_message(client, userdata, msg):
    received_messages.append(json.loads(msg.payload.decode()))

  client = mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=f"test-api-{uuid.uuid4().hex[:8]}"
  )
  client.on_message = on_message
  client.connect("localhost", broker_port, keepalive=60)
  client.loop_start()

  try:
    # Subscribe to scene output
    client.subscribe(TOPIC_SCENE_OUTPUT, qos=1)

    # Send multiple detections with current timestamps (tracking pipeline
    # drops stale messages via max_lag_s and needs repeated detections
    # before RobotVision produces reliable tracks)
    for i in range(5):
      timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
      detection = {
          "id": "atag-qcam1",
          "timestamp": timestamp,
          "objects": {
              "thing": [
                  {
                      "id": 1,
                      "bounding_box_px": {"x": 100, "y": 50, "width": 80, "height": 200}
                  }
              ]
          }
      }
      result = client.publish(TOPIC_CAMERA_INPUT, json.dumps(detection), qos=1)
      result.wait_for_publish()
      if i < 4:
        time.sleep(0.067)  # ~15 FPS

    # Wait for scene output
    wait(
        lambda: len(received_messages) > 0,
        timeout_seconds=DEFAULT_TIMEOUT,
        sleep_seconds=POLL_INTERVAL
    )

    assert len(received_messages) > 0, "Should receive scene output from API-loaded scene"
    print(f"\nAPI message flow verified: received {len(received_messages)} scene output(s)")

  finally:
    client.loop_stop()
    client.disconnect()
