#!/usr/bin/env python3

# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ('License'). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import os
import time
import json

from tests.ui.browser import Browser
import tests.ui.common_ui_test_utils as common
from scene_common.rest_client import RESTClient

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

GOOD_DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test_media/good_data.txt')
SENSOR_NAME = 'Scene_Sensor_to_be_Deleted'
SENSOR_ID = 'scene_sensor_to_be_deleted'
SENSOR_TYPE_CHOICES = ['entire_scene', 'circle', 'triangle']
VIEWPORT_SIZE = 1200
is_receiving_message = False

def on_connect(mqttc, obj, flags, rc):
  '''! Call back function which subscribes to
  topic scenescape/event/region/Demo/scene_sensor_to_be_deleted/objects

  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    flags     the response sent by the broker
  @param    rc        the connection result
  '''
  print('Connected!')
  return

def on_message(mqttc, obj, msg):
  '''! Call back function for for receiving messages
  @param    mqttc     the mqtt client object
  @param    obj       the private user data
  @param    msg       the instance of MQTTMessage
  '''
  global is_receiving_message
  print('Message received from sensor {}!'.format(SENSOR_NAME))
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

def getSensorUid(rest, sensor_name):
  res = rest.getSensors({'name': sensor_name})
  assert res["results"], f"getSensors REST call hasn't returned any results for {sensor_name}!"
  # Get the uid of the first result
  return res["results"][0]['uid']

def test_sensor_delete_mqtt(params, record_xml_attribute):
  '''! This function creates a sensor from the UI and then deletes
  the sensor. After the sensor deletion, the MQTT server should not
  give any response, else the test fails.
  @returns exit_code 0 on success 1 on failure
  '''
  TEST_NAME = 'NEX-T10432'
  record_xml_attribute('name', TEST_NAME)

  print('Executing: ' + TEST_NAME)
  scene_name = common.TEST_SCENE_NAME
  exit_code = 6

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  try:
    client = PubSub(params['auth'], None, params['rootcert'],
                    params['broker_url'], params['broker_port'])
    client.onConnect = on_connect
    client.onMessage = on_message
    client.connect()

    browser = Browser()
    viewport_dimensions = browser.execute_script("return [window.innerWidth, window.innerHeight];")
    browser.setViewportSize(viewport_dimensions[0], VIEWPORT_SIZE)
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    client.loopStart()

    for sensor_type in SENSOR_TYPE_CHOICES:
      print()
      print('=== Executing test for {} sensor... ==='.format(sensor_type))
      assert common.create_sensor_from_scene(browser, SENSOR_ID, SENSOR_NAME, scene_name)

      if sensor_type == 'circle':
        common.open_scene_manage_sensors_tab(browser)
        assert common.create_circle_sensor(browser)

      elif sensor_type == 'triangle':
        common.open_scene_manage_sensors_tab(browser)
        assert common.create_triangle_sensor(browser)

      sensor_uid = getSensorUid(rest, SENSOR_NAME)
      topic = PubSub.formatTopic(PubSub.EVENT, region_type="region", event_type="objects",
                                 scene_id=common.TEST_SCENE_ID, region_id=sensor_uid)
      client.subscribe(topic, 0)

      print("Events should be received from the sensor...")
      message_received = verify_message_mqtt(client)
      assert message_received, f"The scene hasn't processed any event from the {sensor_type} sensor!"
      exit_code -= 1

      # Delete sensor
      assert common.delete_sensor(browser, SENSOR_NAME)

      print("Events should not be received from the sensor because it was deleted...")
      message_received = verify_message_mqtt(client)
      # Test should fail if scene processed any of the sensors tested
      assert not message_received, f"The scene processed events from the {sensor_type} sensor!"
      exit_code -= 1

      client.unsubscribe(topic)

    client.loopStop()
    assert client.isConnected()
    if exit_code != 0:
      print("Received unexpected message from some sensors!")

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
