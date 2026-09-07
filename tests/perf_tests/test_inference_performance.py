#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time
import pytest
from scene_common.mqtt import PubSub
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import INFERENCE_PERF

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=INFERENCE_PERF,
  auth=AUTH_CONTROLLER,
  require_password=False,
)

TEST_NAME="NEX-T10412"
NUM_MESSAGES = 1000
FPS_THRESHOLD = 10
CAMERA_TOPICS = {
  "camera1": PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id="camera1"),
  "camera2": PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id="camera2"),
}
COLLECTION_TIMEOUT = 300


class _FPSCollector:
  """Collects FPS (rate) values from MQTT messages for a single camera."""

  def __init__(self, camera_name, target_count):
    self.camera_name = camera_name
    self.rates = []
    self.target_count = target_count
    self.done = threading.Event()

  def on_message(self, _client, _userdata, message):
    if self.done.is_set():
      return
    try:
      payload = json.loads(message.payload.decode("utf-8"))
      rate = payload.get("rate")
      if rate is not None:
        self.rates.append(float(rate))
        if len(self.rates) >= self.target_count:
          self.done.set()
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
      log.debug("Skipping malformed message for %s: %s", self.camera_name, exc)

  @property
  def average_fps(self):
    if not self.rates:
      return 0.0
    return sum(self.rates) / len(self.rates)

  @property
  def average_fps_rounded(self):
    """Round to nearest integer, matching the original bash implementation."""
    return round(self.average_fps)


@pytest.mark.test_name("NEX-T10412")
def test_inference_performance(scenescape_env, request):
  """NEX-T10412: verify DLStreamer inference FPS meets threshold."""
  auth = request.config.getoption("auth")
  rootcert = request.config.getoption("rootcert")
  broker_url = request.config.getoption("broker_url")
  broker_port = int(request.config.getoption("broker_port"))

  pubsub = PubSub(auth, None, rootcert, broker_url, port=broker_port)

  collectors = {}
  for camera_name, topic in CAMERA_TOPICS.items():
    collector = _FPSCollector(camera_name, NUM_MESSAGES)
    collectors[camera_name] = collector
    pubsub.addCallback(topic, collector.on_message)

  connected = threading.Event()

  def on_connect(_client, _userdata, _flags, rc):
    if rc == 0:
      log.info("Connected to MQTT broker")
      for topic in CAMERA_TOPICS.values():
        pubsub.subscribe(topic)
        log.info("Subscribed to %s", topic)
      connected.set()

  pubsub.onConnect = on_connect
  pubsub.connect()
  pubsub.loopStart()

  try:
    assert connected.wait(timeout=30), "Failed to connect to MQTT broker"

    log.info(
      "Collecting %d messages per camera (timeout %ds)...",
      NUM_MESSAGES, COLLECTION_TIMEOUT,
    )

    deadline = time.monotonic() + COLLECTION_TIMEOUT
    for camera_name, collector in collectors.items():
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        break
      collector.done.wait(timeout=remaining)

    for camera_name, collector in collectors.items():
      count = len(collector.rates)
      log.info(
        "%s: collected %d/%d messages, avg FPS: %.2f (rounded: %d)",
        camera_name, count, NUM_MESSAGES,
        collector.average_fps,
        collector.average_fps_rounded,
      )
      assert count >= NUM_MESSAGES, (
        f"{camera_name}: only received {count}/{NUM_MESSAGES} messages "
        f"within {COLLECTION_TIMEOUT}s"
      )
      assert collector.average_fps_rounded >= FPS_THRESHOLD, (
        f"{camera_name}: avg FPS {collector.average_fps:.2f} "
        f"(rounded: {collector.average_fps_rounded}) "
        f"is below threshold {FPS_THRESHOLD}"
      )
  finally:
    pubsub.loopStop()
    pubsub.disconnect()
