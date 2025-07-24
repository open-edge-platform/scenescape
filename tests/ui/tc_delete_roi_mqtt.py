#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import time
import json
from tests.ui.browser import Browser
import tests.ui.common_ui_test_utils as common
from scene_common.rest_client import RESTClient

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

ROI_DATA_PATH = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "test_media/roi_data.txt")
# Constant for a ROI polygon (triangle) at coordinate (50, -200)
ROI_NAME = "Polygon"
ROI_ORIGIN_X = -50
ROI_ORIGIN_Y = -200

message_received = False

def eventReceived(mqttc, obj, msg):
  """! Call back function for receiving messages
  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    msg       the instance of MQTTMessage
  """
  global message_received
  print("Message received from ROI!")
  message_received = True
  return

def getRegionUid(rest, re_name):
  res = rest.getRegions({'name': re_name})
  assert res["results"], f"getRegions REST call hasn't returned any results for {re_name}!"
  # Get the uid of the first result
  return res["results"][0]['uid']

def test_roi_mqtt(params, record_xml_attribute):
  """! Test the deletion of ROI and verify that the deleted ROI is not publishing any data to MQTT.
  @param    params                  List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  TEST_NAME = "NEX-T10430"
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)

  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  try:
    client = PubSub(params['auth'], None, params['rootcert'],
                    params['broker_url'], params['broker_port'])
    client.connect()
    client.loopStart()

    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    print("Creating ROI...")

    # Create ROI
    assert common.create_roi(browser, ROI_NAME, ROI_ORIGIN_X, ROI_ORIGIN_Y)
    assert common.verify_roi(browser, [ROI_NAME])

    # Subscribe the newly created tripwire
    re_uid = getRegionUid(rest, ROI_NAME)
    topic = PubSub.formatTopic(PubSub.EVENT, region_type="region", event_type="objects",
                               scene_id=common.TEST_SCENE_ID, region_id=re_uid)
    client.addCallback(topic, eventReceived)

    # Delete ROI
    assert common.delete_roi(browser, ROI_NAME)
    assert not common.verify_roi(browser, [ROI_NAME])

    current_line = 0
    data = open(ROI_DATA_PATH, "r")
    data_path_lines = data.readlines()

    for line in data_path_lines:
      if line.startswith("#"):
        pass
      else:
        jdata = json.loads(line.strip())
        camera_id = jdata["id"]
        jdata['timestamp'] = get_iso_time()
        line = json.dumps(jdata)

        print('Sending frame {} id {}'.format(current_line, camera_id))
        client.publish(PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
                        line.strip())
        time.sleep(1/10)
        current_line += 1

    client.loopStop()
    data.close()

    # Check MQTT messages to verify that the deleted ROI is no longer publishing
    global message_received

    if client.isConnected():
      if message_received == False:
        exit_code = 0
      else:
        print("Still receiving message from ROI!")
    else:
      print("Failed to connect!")

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
