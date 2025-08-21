#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import tests.common_test_utils as common
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log

TEST_WAIT_TIME = 5 * 60  # 10 minutes in seconds

connected = False
detection_count = {
  "3bc091c7-e449-46a0-9540-29c499bca18c": {
    "error": False,
    "current": 0,
    "maximum": 120
  },
  "302cf49a-97ec-402d-a324-c5077b280b7b": {
    "error": False,
    "current": 0,
    "maximum": 60
  }
}

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
  real_msg = str(msg.payload.decode("utf-8"))
  json_data = json.loads(real_msg)

  for scene in detection_count:
    if json_data['id'] == scene:
      # If the unique count somehow decremented, raise an error
      if detection_count[scene]["current"] > json_data['unique_detection_count']:
        detection_count[scene]["error"] = True
      detection_count[scene]["current"] = json_data['unique_detection_count']
  return

def check_unique_detections():
  """! Verify if more than expected unique detections aren't found.
  @return  BOOL       True for the expected behaviour.
  """
  interval = 10  # seconds
  start_time = time.time()

  while time.time() - start_time < TEST_WAIT_TIME:
    time.sleep(interval)
    log.info(f"Status after {int(time.time() - start_time)} / {TEST_WAIT_TIME} sec")

    for scene in detection_count:
      if detection_count[scene]["current"] <= detection_count[scene]["maximum"]:
        log.info(f"-> Detections for {scene} of: {detection_count[scene]['current']} (max: {detection_count[scene]['maximum']})")
      else:
        log.error(f"-> Detections for {scene} is greater than the maximum: {detection_count[scene]['current']} (max: {detection_count[scene]['maximum']})!")
        return False

      if detection_count[scene]["error"]:
        log.error(f"The unique detection counter for {scene} somehow got decremented!")
        return False

  for scene in detection_count:
    if detection_count[scene]["current"] <= 0:
      log.error(f"The unique detection counter for {scene} shouldn't be 0!")
      return False

  return True

def test_reid_unique_count(params, record_xml_attribute):
  """! Tests the unique count for each scene when RE-ID is enabled.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10539"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME )
  log.info("Test the unique count for each scene when RE-ID is enabled.")
  exit_code = 1

  try:
    client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"])
    rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
    res = rest.authenticate(params['user'], params['password'])
    assert res, (res.errors)

    client.onConnect=on_connect
    for sc_uid in detection_count:
      client.addCallback(PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=sc_uid, thing_type="person"), on_scene_message)
    client.connect()
    client.loopStart()

    assert check_unique_detections()

    client.loopStop()
    exit_code = 0

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
