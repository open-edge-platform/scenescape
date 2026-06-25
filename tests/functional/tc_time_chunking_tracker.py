#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time

import tests.common_test_utils as common
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time

TEST_NAME = "NEX-TIMECHUNK-TRACKER"
WAIT_TIMEOUT_SECS = 30.0
PUBLISH_INTERVAL_SECS = 0.05


def test_time_chunking_tracker_functional(params, objData, record_xml_attribute):
  """Verify scene tracking output is produced with time chunking enabled."""
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  ready_condition = threading.Condition()
  received_scene_payloads = []

  def on_scene_message(_mqttc, _userdata, message):
    payload = json.loads(message.payload.decode("utf-8"))
    with ready_condition:
      received_scene_payloads.append(payload)
      ready_condition.notify()

  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"])
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])

  try:
    auth = rest.authenticate(params["user"], params["password"])
    assert auth, auth.errors

    scenes = rest.getScenes({"name": params["scene_name"]})["results"]
    assert scenes and len(scenes) > 0, f"Scene '{params['scene_name']}' not found"
    scene_uid = scenes[0]["uid"]

    cameras = scenes[0].get("cameras", [])
    assert cameras and len(cameras) > 0, "No cameras available in test scene"
    camera_id = cameras[0]["uid"]

    wait_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_uid, thing_type="person")
    publish_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)

    client.addCallback(wait_topic, on_scene_message)
    client.connect()
    client.loopStart()

    with ready_condition:
      start = time.time()
      while time.time() - start < WAIT_TIMEOUT_SECS and not received_scene_payloads:
        objData["id"] = camera_id
        objData["timestamp"] = get_iso_time()
        client.publish(publish_topic, json.dumps(objData))
        ready_condition.wait(PUBLISH_INTERVAL_SECS)

    assert received_scene_payloads, "No scene tracking output received with time chunking enabled"
    exit_code = 0
  finally:
    client.loopStop()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
