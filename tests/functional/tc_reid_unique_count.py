#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import tests.common_test_utils as common
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log

TEST_WAIT_TIME = 150
connected = False
detection_count = {}
count_transitions = {}

def on_connect(mqttc, data, flags, rc):
  """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    flags     The response sent by the broker.
  @param    rc        The connection result.
  """
  global connected
  global detection_count
  connected = True
  log.info("Connected to MQTT Broker")
  for sc_uid in detection_count:
    topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person")
    mqttc.subscribe(topic, 0)
    log.info("Subscribed to the topic {}".format(topic))
  return

def on_scene_message(mqttc, condlock, msg):
  global detection_count
  global count_transitions
  real_msg = str(msg.payload.decode("utf-8"))
  json_data = json.loads(real_msg)

  for scene in detection_count:
    if json_data['id'] == scene:
      previous = detection_count[scene]["current"]
      # If the unique count somehow decremented, raise an error
      if previous > json_data['unique_detection_count']:
        detection_count[scene]["error"] = True
      detection_count[scene]["current"] = json_data['unique_detection_count']

      if previous != json_data['unique_detection_count']:
        event = {
          "timestamp": json_data.get("timestamp", "unknown"),
          "from": previous,
          "to": json_data['unique_detection_count']
        }
        count_transitions[scene].append(event)
        log.info(
          f"Transition for {scene}: {previous} -> {json_data['unique_detection_count']} "
          f"at {event['timestamp']}"
        )
  return

def check_unique_detections():
  """! Verify if more than expected unique detections aren't found.
  @return  BOOL       True for the expected behaviour.
  """
  interval = 10  # seconds
  start_time = time.time()
  minima = {scene: max(detection_count[scene].get("minimum", 1), 1) for scene in detection_count}

  while time.time() - start_time < TEST_WAIT_TIME:
    time.sleep(interval)
    log.info(f"Status after {int(time.time() - start_time)} / {TEST_WAIT_TIME} sec")

    for scene in detection_count:
      current = detection_count[scene]["current"]
      maximum = detection_count[scene]["maximum"]

      if current <= maximum:
        log.info(f"-> Detections for {scene} of: {current} (max: {maximum})")
      else:
        log.error(f"-> Detections for {scene} is greater than the maximum: {current} (max: {maximum})!")
        return False

      if detection_count[scene]["error"]:
        log.error(f"The unique detection counter for {scene} somehow got decremented!")
        return False

  for scene in detection_count:
    current = detection_count[scene]["current"]
    minimum = minima[scene]

    if current < minimum:
      log.error(
        f"The unique detection counter for {scene} is below minimum: "
        f"{current} (min: {minimum})!"
      )
      return False

  return True

def run_test(test_name, test_desc, scene_config, params):
  """! Generic test runner for RE-ID unique count tests.
  @param    test_name       The test identifier (e.g., "NEX-T10539").
  @param    test_desc       The test description.
  @param    scene_config    Dict of scene_id -> {error, current, maximum}.
  @param    params          Dict of test parameters.
  @return   exit_code       Indicates test success or failure.
  """
  global detection_count
  global count_transitions
  detection_count = scene_config
  count_transitions = {scene: [] for scene in detection_count}
  exit_code = 1

  try:
    client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"])
    rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
    res = rest.authenticate(params['user'], params['password'])
    assert res, (res.errors)

    client.onConnect = on_connect
    for sc_uid in detection_count:
      client.addCallback(PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person"), on_scene_message)
    client.connect()
    client.loopStart()

    assert check_unique_detections()

    for scene in detection_count:
      if count_transitions[scene]:
        log.info(f"Transition history for {scene}: {count_transitions[scene]}")
      else:
        log.info(f"No transitions observed for {scene}; final count: {detection_count[scene]['current']}")

    client.loopStop()
    exit_code = 0

  finally:
    common.record_test_result(test_name, exit_code)

  assert exit_code == 0
  return exit_code

def test_reid_unique_count(params, record_xml_attribute):
  """! Tests the unique count for each scene when RE-ID is enabled.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10539"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  log.info("Test the unique count for each scene when RE-ID is enabled.")

  scene_config = {
    "3bc091c7-e449-46a0-9540-29c499bca18c": {
      "error": False,
      "current": 0,
      "minimum": 2,
      "maximum": 10
    },
    "302cf49a-97ec-402d-a324-c5077b280b7b": {
      "error": False,
      "current": 0,
      "minimum": 3,
      "maximum": 6
    }
  }

  return run_test(TEST_NAME, "Test the unique count for each scene when RE-ID is enabled.", scene_config, params)
