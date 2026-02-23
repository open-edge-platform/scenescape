#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading

import tests.common_test_utils as common
from scene_common.mqtt import PubSub
from scene_common import log


test_wait_time = 20  # seconds
check_interval = 1   # seconds

scenes = [
    "3bc091c7-e449-46a0-9540-29c499bca18c",
    "302cf49a-97ec-402d-a324-c5077b280b7b"
]


class CameraBounds:
  def __init__(self):
    self.regulated_topics = set()
    self.unregulated_topics = set()
    self.regulated_has_camera_bounds = False
    self.unregulated_has_camera_bounds = False
    self.message_lock = threading.Lock()
    self.visibility_topic = None

  def has_valid_camera_bounds(self, json_data):
    """
    Returns True if camera_bounds exist and contain valid bounding box keys.
    """
    required_keys = {"x", "y", "width", "height"}
    found = False

    for obj in json_data.get("objects", []):
      camera_bounds = obj.get("camera_bounds")
      if not isinstance(camera_bounds, dict):
        continue

      for _, bbox in camera_bounds.items():
        if isinstance(bbox, dict):
          if required_keys.issubset(bbox):
            found = True

    return found

  def on_connect(self, mqttc, _data, _flags, _rc):
    log.info("Connected to MQTT broker")
    for scene_id in scenes:
      regulated_topic = PubSub.formatTopic(
          PubSub.DATA_REGULATED,
          scene_id=scene_id,
          thing_type="person"
      )

      unregulated_topic = PubSub.formatTopic(
          PubSub.DATA_SCENE,
          scene_id=scene_id,
          thing_type="person"
      )

      self.regulated_topics.add(regulated_topic)
      self.unregulated_topics.add(unregulated_topic)

      mqttc.subscribe(regulated_topic, 0)
      mqttc.subscribe(unregulated_topic, 0)

      log.info(f"Subscribed to: {regulated_topic}")
      log.info(f"Subscribed to: {unregulated_topic}")

  def on_message(self, _mqttc, _userdata, msg):
    json_data = json.loads(msg.payload.decode())
    topic = str(msg.topic)

    if not self.has_valid_camera_bounds(json_data):
      return

    with self.message_lock:
      if topic in self.regulated_topics:
        self.regulated_has_camera_bounds = True

      if topic in self.unregulated_topics:
        self.unregulated_has_camera_bounds = True

  def run(self, params, visibility_topic, test_name):
    self.visibility_topic = visibility_topic.lower()
    log.info(f"Test parameter visibility_topic: {self.visibility_topic}")
    log.info(f"Executing: {test_name}")

    exit_code = 1
    client = None

    try:
      client = PubSub(
          params["auth"],
          None,
          params["rootcert"],
          params["broker_url"]
      )

      client.onConnect = self.on_connect
      for scene_id in scenes:
        client.addCallback(
            PubSub.formatTopic(
                PubSub.DATA_REGULATED,
                scene_id=scene_id,
                thing_type="person"
            ),
            self.on_message
        )

        client.addCallback(
            PubSub.formatTopic(
                PubSub.DATA_SCENE,
                scene_id=scene_id,
                thing_type="person"
            ),
            self.on_message
        )

      client.connect()
      client.loopStart()
      self.check_camera_bound_visibility()
      exit_code = 0
    finally:
      if client:
        client.loopStop()

      common.record_test_result(test_name, exit_code)

    return exit_code


def test_camera_bound_visibility(
        params, pytestconfig, record_xml_attribute, test_name):
  record_xml_attribute("name", test_name)

  visibility_topic = pytestconfig.getoption('visibility_topic')
  test = CameraBounds()
  exit_code = test.run(params, visibility_topic, test_name)

  assert exit_code == 0
  return exit_code
