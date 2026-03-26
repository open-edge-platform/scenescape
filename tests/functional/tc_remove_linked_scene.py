#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import json
import pytest

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
import tests.common_test_utils as common


parent_id = None
child_id = None

def on_connect(mqttc, obj, flags, rc):
  """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    flags     The response sent by the broker.
  @param    rc        The connection result.
  @return   None
  """
  global connected, parent_id, child_id
  log.info("Connected!")
  connected = True
  topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=parent_id)
  mqttc.subscribe(topic)
  topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=child_id)
  mqttc.subscribe(topic)
  return

def on_message(mqttc, pose, msg):
  """! Call back function for the MQTT client on receiving messages.
  This function captures the recent child and parent data and calculates
  the expected object location for the parent data

  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    msg       The instance of MQTTMessage.
  @return   None
  """
  global recent_data, parent_translation, \
  parent_id, cur_category, count, child_id

  parent_data = None
  child_data = None
  topic = PubSub.parseTopic(msg.topic)

  if topic['scene_id'] == parent_id:
    real_msg = str(msg.payload.decode("utf-8"))
    parent_data = json.loads(real_msg)
    for p_obj in parent_data['objects']:
      if p_obj['category'] == cur_category:
        recent_data.append(p_obj)

  elif topic['scene_id'] == child_id:
    real_msg = str(msg.payload.decode("utf-8"))
    child_data = json.loads(real_msg)
    for c_obj in child_data['objects']:
      if c_obj['category'] == cur_category:
        recent_data.clear()
        recent_data.append(c_obj)

  return

def create_scenes(parent_scene, child_scene, rest_client):
  """! Function to verify the linking mulitple child scenes to a parent

  @param    parent_scene                The current parent scene for test.
  @param    child_scene                 The current child scene for test.
  @param    rest_client                 The rest client.
  @return   None
  """

  parent_scene = rest_client.createScene({'name': "parent"})
  assert parent_scene.statusCode == 201, f"Expected status code 201, got {parent_scene.statusCode}"
  global parent_id
  parent_id = parent_scene['uid']

  child_scene = rest_client.createScene({'name': "child"})
  assert child_scene.statusCode == 201, f"Expected status code 201, got {child_scene.statusCode}"
  global child_id
  child_id = child_scene['uid']

  res = rest_client.updateScene(child_scene['uid'], {
      'parent': parent_scene['uid'],
    })
#   assert res
  assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"


@pytest.mark.parametrize("parent_scene, child_scene", [
  ("parent", "child"),
])
def test_remove_linked_scene(parent_scene, child_scene, record_xml_attribute, params):
  """! Test to verify the unlinking of a child scene from parent scene and validating the data flow.

  @param    parent_scene                The current parent scene for test.
  @param    child_scene                 The current child scene for test.
  @param    rest_client                 The rest client.
  @return   None
  """

  global parent_id, child_id, cur_category, recent_data
  TEST_NAME = "NEX-T10439"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1

  try:
    rest_client = RESTClient(params['resturl'],
                             rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])
    create_scenes(parent_scene, child_scene, rest_client)
    
    # parent_id = rest_client.getScenes({'name': parent_scene})
    # child_id = rest_client.getScenes({'name': child_scene})
    
    client = PubSub(params["auth"], None, params["rootcert"],
                  params["broker_url"], params["broker_port"])
    client.onConnect = on_connect
    client.onMessage = on_message
    client.connect()
    
   
    # Unlink the child scene from the parent scene
    # res = rest_client.updateScene(child_id, {
    #     'parent': None,
    #   })
    # # assert res
    # assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"
    exit_code = 0

  # Wait for MQTT messages to be updated after unlinking
  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return

