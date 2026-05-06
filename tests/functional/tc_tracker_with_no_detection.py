#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional test: tracker drops tracked objects to zero when the camera
sends an empty detection list after a period of active tracking.

Sequence:
  1. Publish non-empty detections until DATA_REGULATED confirms at least one
     tracked object.
  2. Publish empty detections (objects: {}) continuously for
     EMPTY_SEND_DURATION seconds.
  3. Assert that a subsequent DATA_REGULATED message arrives with an empty
     objects list, confirming the tracker cleared all tracks.
"""

import copy
import json
import threading
import time

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from scene_common import log
import tests.common_test_utils as common

from tests.functional.common_retrack import RetrackTest

MAX_WAIT = 10

EMPTY_SEND_DURATION = 5


def test_tracker_objects_drop_to_zero_with_empty_detections(
    objData, record_xml_attribute, params):
  """! Verify that the tracker drops all tracked objects to zero when the
  camera sends an empty detection list after a period of active tracking.

  Phase 1: Non-empty detections are published via
  RetrackTest.publish_data() until DATA_REGULATED confirms at least one
  tracked object.

  Phase 2: Empty detections (objects: {}) are published at
  RetrackTest.FRAME_RATE Hz for EMPTY_SEND_DURATION seconds. 
  A DATA_REGULATED message with an empty objects list must arrive within
  MAX_WAIT seconds, confirming the tracker cleared all tracks.

  @param    objData                 Pytest fixture: object payload template.
  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test parameters.
  """

  TEST_NAME = "NEX-T10544"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1
  client = None
  rest_client = None

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    scenes = rest_client.getScenes({'name': params['scene_name']})
    assert scenes['count'] > 0, \
      f"Scene '{params['scene_name']}' not found"
    scene_id = scenes['results'][0]['uid']
    log.info(f"Using scene '{params['scene_name']}' uid={scene_id}")

    reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_id)
    cam_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=objData['id'])

    regulated_msgs = []
    _lock = threading.Lock()
    connected_event = threading.Event()

    def _on_connect(mqttc, obj, flags, rc):
      if rc == 0:
        mqttc.subscribe(reg_topic)
        log.info(f"Subscribed to DATA_REGULATED: {reg_topic}")
        connected_event.set()

    def _on_message(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode('utf-8'))
        with _lock:
          regulated_msgs.append(data)
      except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning(f"Failed to decode regulated payload on {msg.topic}: {exc}")

    client = PubSub(params['auth'], None, params['rootcert'],
                    params['broker_url'], params['broker_port'])
    client.onConnect = _on_connect
    client.onMessage = _on_message
    client.connect()
    client.loopStart()
    assert connected_event.wait(MAX_WAIT), \
      "MQTT client failed to connect and subscribe within timeout"

    log.info("Publishing non-empty detections to prime the tracker")
    RetrackTest.publish_data(objData, client)

    start = time.time()
    non_empty = False
    while time.time() - start < MAX_WAIT:
      with _lock:
        for msg in regulated_msgs:
          if len(msg.get('objects', [])) > 0:
            non_empty = True
            break
      if non_empty:
        break
      time.sleep(0.2)

    assert non_empty, \
      f"No DATA_REGULATED message with objects received within {MAX_WAIT}s"

    expected_count = sum(len(v) for v in objData['objects'].values())
    with _lock:
      tracked_objects = max(len(m.get('objects', [])) for m in regulated_msgs)
    assert tracked_objects == expected_count, \
      (f"Tracker object count {tracked_objects} != "
       f"Sent detection count {expected_count}")
    log.info(
      f"PASS: tracker object count matches sent detections "
      f"(count={tracked_objects})")

    log.info(
      f"Publishing empty detections for {EMPTY_SEND_DURATION}s "
      f"to drain the tracker")
    with _lock:
      regulated_msgs.clear()

    empty_data = copy.copy(objData)
    empty_data['objects'] = {}
    end = time.time() + EMPTY_SEND_DURATION
    while time.time() < end:
      empty_data['timestamp'] = get_iso_time()
      client.publish(cam_topic, json.dumps(empty_data))
      time.sleep(1.0 / RetrackTest.FRAME_RATE)

    start = time.time()
    empty_seen = False
    while time.time() - start < MAX_WAIT:
      with _lock:
        for msg in regulated_msgs:
          if len(msg.get('objects', [])) == 0:
            empty_seen = True
            break
      if empty_seen:
        break
      time.sleep(0.2)

    assert empty_seen, (
      f"Tracker did not report an empty objects list within "
      f"{MAX_WAIT}s after {EMPTY_SEND_DURATION}s of empty detections")
    log.info(
      "PASS: tracker objects dropped to zero after receiving empty detections")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
