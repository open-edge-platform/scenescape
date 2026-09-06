#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MQTT smoke: Tracker-shaped DATA_SCENE → Analytics region events.

Uses ANALYTICS_MQTT (no Scene Controller) so coverage is not redundant with
FULL_STACK camera→Controller→Analytics child-event tests. Injects a minimal
Tracker envelope on data/scene and asserts Analytics emits ROI events.
"""

import json
import threading
import time

import tests.common_test_utils as common
from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.functional.event_asserts import (
  assert_event_objects_have_visibility,
  check_event_contains_data,
)
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import ANALYTICS_MQTT

SCENESCAPE_SPEC = FuncTestSpec(
  profile=ANALYTICS_MQTT,
  auth=AUTH_CONTROLLER,
)

EVENT_WAIT = 20
CONNECT_WAIT = 10
GEOMETRY_SETTLE = 3


def test_analytics_emits_roi_event_for_tracker_shaped_scene_data(
    record_xml_attribute, params):
  """! Analytics accepts Tracker DATA_SCENE envelopes and emits region events.

  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21483"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"])

  scenes = rest.getScenes({"name": "Demo"})
  assert scenes["count"] > 0, "Demo scene required"
  scene_id = scenes["results"][0]["uid"]

  roi = rest.createRegion({
    "scene": scene_id,
    "name": "TrackerShapeROI",
    "points": ((1.38, 5.94), (1.17, 0.8), (7.41, 0.83), (7.35, 6.01)),
  })
  assert roi.statusCode == 201, f"ROI create failed: {roi.statusCode} {roi.errors}"
  roi_uid = roi["uid"]

  events = []
  connected = threading.Event()

  def on_connect(client, userdata, flags, rc):
    if rc == 0:
      connected.set()
      topic = PubSub.formatTopic(
        PubSub.EVENT, region_type="region", event_type="+",
        scene_id=scene_id, region_id=roi_uid)
      client.subscribe(topic)

  def on_message(client, userdata, msg):
    try:
      events.append(json.loads(msg.payload.decode("utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError):
      return

  client = PubSub(params["auth"], None, params["rootcert"],
                  params["broker_url"], params["broker_port"])
  client.onConnect = on_connect
  client.onMessage = on_message
  client.connect()
  client.loopStart()

  try:
    assert connected.wait(CONNECT_WAIT), "MQTT connect timeout"
    client.publish(PubSub.formatTopic(PubSub.CMD_DATABASE), "update", qos=1)
    time.sleep(GEOMETRY_SETTLE)

    scene_topic = PubSub.formatTopic(
      PubSub.DATA_SCENE, scene_id=scene_id, thing_type="person")
    # Tracker-shaped envelope: category (not type), UUID ids, no Controller metrics.
    payload = {
      "id": scene_id,
      "name": "Demo",
      "timestamp": get_iso_time(),
      "objects": [
        {
          "id": "8cce2bc7-51fc-4a6e-8c5d-a73ac72d3eb2",
          "category": "person",
          "translation": [4.5, 3.2, 0.0],
          "velocity": [0.0, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
          "rotation": [0, 0, 0, 1],
        }
      ],
    }
    # Publish enough frames for Analytics reliability gate (publishedLocations > 3).
    for _ in range(6):
      payload["timestamp"] = get_iso_time()
      client.publish(scene_topic, json.dumps(payload))
      time.sleep(0.15)

    deadline = time.time() + EVENT_WAIT
    while time.time() < deadline and not events:
      time.sleep(0.5)

    assert events, f"No ROI events within {EVENT_WAIT}s for Tracker-shaped DATA_SCENE"
    assert events[0].get("region_id") == roi_uid
    check_event_contains_data(events[0], "region")
    assert_event_objects_have_visibility(events[0])
    log.info(f"PASS: {len(events)} ROI event(s) from Tracker-shaped scene data")
    exit_code = 0
  finally:
    client.loopStop()
    rest.deleteRegion(roi_uid)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
