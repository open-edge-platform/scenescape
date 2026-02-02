#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
import os
import time
import threading

import tests.common_test_utils as common
from scene_common.mqtt import PubSub
from scene_common import log

log.info(f"Environment variables: {os.environ}")
TEST_WAIT_TIME = 20  # seconds
CHECK_INTERVAL = 1   # seconds


scenes = [
    "3bc091c7-e449-46a0-9540-29c499bca18c",
    "302cf49a-97ec-402d-a324-c5077b280b7b"
]

# Tracked state of camera_bounds presence
regulated_has_camera_bounds = False
unregulated_has_camera_bounds = False

# Shared state lock
message_lock = threading.Lock()

def has_valid_camera_bounds(json_data):
  """
  Returns True if camera_bounds exist and contain valid bounding box keys.
  """
  REQUIRED_KEYS = {"x", "y", "width", "height"}
  found = False

  for obj in json_data.get("objects", []):
    camera_bounds = obj.get("camera_bounds")
    if not isinstance(camera_bounds, dict):
      continue

    for camera_name, bbox in camera_bounds.items():
      if isinstance(bbox, dict):
        if REQUIRED_KEYS.issubset(bbox):
          found = True

  return found

def on_connect(mqttc, data, flags, rc):
  global regulated_topic, unregulated_topic
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

    mqttc.subscribe(regulated_topic, 0)
    mqttc.subscribe(unregulated_topic, 0)

    log.info(f"Subscribed to: {regulated_topic}")
    log.info(f"Subscribed to: {unregulated_topic}")

def on_message(mqttc, userdata, msg):
  global regulated_has_camera_bounds, unregulated_has_camera_bounds

  json_data = json.loads(msg.payload.decode())
  topic = str(msg.topic)

  if not has_valid_camera_bounds(json_data):
    return

  with message_lock:
    if topic == regulated_topic:
      regulated_has_camera_bounds = True

    if topic == unregulated_topic:
      unregulated_has_camera_bounds = True

def check_camera_bound_visibility():
  """
  Validate camera_bounds publishing based on visibility_topic policy.
  """
  start_time = time.time()

  while time.time() - start_time < TEST_WAIT_TIME:
    with message_lock:
      if visibility_topic == "regulated":
        if regulated_has_camera_bounds and not unregulated_has_camera_bounds:
          log.info("PASS: camera_bounds for the tracked objects are published only into regulated topic")
          return
      elif visibility_topic == "unregulated":
        if regulated_has_camera_bounds and unregulated_has_camera_bounds:
          log.info("PASS: camera_bounds for the tracked objects are published into both regulated and unregulated topics")
          return
      elif visibility_topic == "none":
        if not regulated_has_camera_bounds and not unregulated_has_camera_bounds:
          log.info("PASS: camera_bounds for the tracked objects are not published into any topic")
          return
      else:
        raise ValueError(f"Unknown visibility_topic: {visibility_topic}")

    log.info(
        f"Waiting for validation "
        f"(visibility={visibility_topic})..."
    )
    time.sleep(CHECK_INTERVAL)

  # Fail conditions
  if visibility_topic == "regulated":
    raise AssertionError(
        "Expected camera_bounds ONLY in regulated topic"
    )

  if visibility_topic == "unregulated":
    raise AssertionError(
        "Expected camera_bounds in BOTH regulated and unregulated topics"
    )

  if visibility_topic == "none":
    raise AssertionError(
        "Expected NO camera_bounds in any topic"
    )

def test_camera_bound_visibility(params, pytestconfig, record_xml_attribute):
  TEST_NAME = "NEX-T10582"
  record_xml_attribute("name", TEST_NAME)

  # Get visibility from the command line argument
  global visibility_topic
  visibility_topic = pytestconfig.getoption('visibility_topic').lower()
  log.info(f"Test parameter visibility_topic: {visibility_topic}")

  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1
  client = None

  try:
    client = PubSub(
        params["auth"],
        None,
        params["rootcert"],
        params["broker_url"]
    )

    client.onConnect = on_connect
    for scene_id in scenes:
      client.addCallback(
          PubSub.formatTopic(
              PubSub.DATA_REGULATED,
              scene_id=scene_id,
              thing_type="person"
          ),
          on_message
      )

      client.addCallback(
          PubSub.formatTopic(
              PubSub.DATA_SCENE,
              scene_id=scene_id,
              thing_type="person"
          ),
          on_message
      )

    client.connect()
    client.loopStart()
    check_camera_bound_visibility()
    exit_code = 0
  finally:
    if client:
      client.loopStop()

    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
