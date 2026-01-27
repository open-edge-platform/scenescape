#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test helper utilities for tracker service tests.

Provides polling helpers, MQTT utilities, and message collection for
event-driven testing without fixed sleeps.
"""

import json
import uuid
import paho.mqtt.client as mqtt
from waiting import wait, TimeoutExpired


# Default timeouts for polling
DEFAULT_TIMEOUT = 10
POLL_INTERVAL = 0.1


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


def get_broker_host(tracker_service):
  """Get broker hostname accessible from test host."""
  docker = tracker_service["docker"]
  containers = docker.compose.ps()
  for container in containers:
    if "-broker-" in container.name:
      ports = container.network_settings.ports
      if "1883/tcp" in ports and ports["1883/tcp"]:
        return "localhost", int(ports["1883/tcp"][0]["HostPort"])
  return "localhost", 1883


def can_connect_to_broker(tracker_service, timeout=1):
  """Check if broker accepts MQTT connections."""
  try:
    host, port = get_broker_host(tracker_service)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"probe-{uuid.uuid4().hex[:8]}"
    )
    client.connect(host, port, keepalive=10)
    client.disconnect()
    return True
  except Exception:
    return False


def wait_for_broker(tracker_service, timeout=DEFAULT_TIMEOUT):
  """Wait until broker accepts connections."""
  wait(lambda: can_connect_to_broker(tracker_service), timeout_seconds=timeout, sleep_seconds=POLL_INTERVAL)


def create_mqtt_client(tracker_service):
  """Create and connect an MQTT client to the test broker."""
  host, port = get_broker_host(tracker_service)
  client = mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=f"test-{uuid.uuid4().hex[:8]}"
  )
  client.connect(host, port, keepalive=60)
  client.loop_start()
  return client


class MessageCollector:
  """Collects messages from MQTT topics for testing."""

  def __init__(self, client, topic):
    self.messages = []
    self.topic = topic
    self.client = client
    self._original_callback = client.on_message
    client.on_message = self._on_message
    client.subscribe(topic, qos=2)

  def _on_message(self, client, userdata, msg):
    if msg.topic == self.topic:
      self.messages.append(json.loads(msg.payload.decode()))

  def wait_for_message(self, timeout=DEFAULT_TIMEOUT):
    """Wait for at least one message, return first message or None."""
    try:
      wait(lambda: len(self.messages) > 0, timeout_seconds=timeout, sleep_seconds=POLL_INTERVAL)
      return self.messages[0]
    except TimeoutExpired:
      return None

  def clear(self):
    """Clear collected messages."""
    self.messages = []

  def close(self):
    """Restore original callback."""
    self.client.on_message = self._original_callback
