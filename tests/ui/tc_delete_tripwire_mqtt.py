#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import time
import json
import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser, By
from scene_common.rest_client import RESTClient

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

GOOD_DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "test_media/good_data.txt")
TW_NAME = "Tripwire_to_be_Deleted"
OBJECT_CATEGORY = "custom_object"
is_receiving_message = False

def on_connect(mqttc, obj, flags, rc):
  """! Call back which subscribes to topic
  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    flags     the response sent by the broker
  @param    rc        the connection result
  """
  print("Connected!")
  return

def eventReceived(pahoClient, userdata, message):
  """! Call back fuction for for receiving messages
  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    msg       the instance of MQTTMessage
  """
  global is_receiving_message
  print('Message received from Tripwire!')
  is_receiving_message = True
  return

def verify_message_mqtt(client):
  global is_receiving_message
  is_receiving_message = False
  current_line = 0
  data = open(GOOD_DATA_PATH, 'r')
  g_data = data.readlines()

  for line in g_data:
    if line.startswith( '#' ):
      pass
    else:
      jdata = json.loads(line.strip())
      camera_id = jdata['id']
      jdata['timestamp'] = get_iso_time()
      line = json.dumps(jdata)

      print('Sending frame {} id {}'.format(current_line, camera_id))
      client.publish(PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
                      line.strip())

      time.sleep(1/10)
      current_line += 1

  data.close()
  return is_receiving_message

def getTripwireUid(rest, tw_name):
  res = rest.getTripwires({'name': tw_name})
  assert res["results"], f"getTripwires REST call hasn't returned any results for {tw_name}!"
  # Get the uid of the first result
  return res["results"][0]['uid']

def test_create_and_delete_tripwire_mqtt(params, record_xml_attribute):
  """! This function creates Trip wire horizontally and the data is published
  such that the object (category ["custom_person"]) moves vertically across the
  tripwrire triggerring event data. The tripwire is deleted and the object data
  is published to the mqtt server and awaiting for the response. The MQTT server
  should not give any response else the test fails.

  @returns exit_code 0 on success, non-zero on failure
  """
  TEST_NAME = "NEX-T10431"
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)

  exit_code = 2

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  try:
    browser = Browser()
    client = PubSub(params['auth'], None, params['rootcert'],
                    params['broker_url'], params['broker_port'])
    client.connect()
    client.loopStart()

    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)
    print("Logged in")

    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    assert common.create_tripwire(browser, TW_NAME)

    # Subscribe the newly created tripwire
    tw_uid = getTripwireUid(rest, TW_NAME)
    topic = PubSub.formatTopic(PubSub.EVENT, event_type="+", region_type="tripwire",
                              scene_id=common.TEST_SCENE_ID, region_id=tw_uid)
    client.addCallback(topic, eventReceived)

    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    assert common.verify_tripwire_persistence(browser, TW_NAME)

    # Modify the tripwire and verify that it has the same UUID
    assert common.modify_tripwire(browser)
    assert common.verify_tripwire_persistence(browser, TW_NAME)

    tw_uid_check = getTripwireUid(rest, TW_NAME)
    assert tw_uid_check == tw_uid, f"The tripwire UUID after the modification doesn't match!" \
      " Before: {tw_uid} - After: {tw_uid_check}"
    print("Events should be received from the sensor...")
    message_received = verify_message_mqtt(client)
    assert message_received, "The scene hasn't processed any event from the tripwire!"
    exit_code -= 1

    # Deleting the tripwire and click on save tripwire and region button
    common.delete_tripwire(browser, tw_uid)
    # Make sure that the tripwire does not exist
    assert not common.verify_tripwire_persistence(browser, TW_NAME)
    print("Events should not be received from the tripwire because it was deleted...")
    message_received = verify_message_mqtt(client)
    # Test should fail if scene processed any of the sensors tested
    assert not message_received, "The scene processed events from the tripwire!"
    exit_code -= 1

    client.loopStop()
    assert client.isConnected()
    if exit_code != 0:
      print("Received unexpected message from the tripwire!")
    browser.close()

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
