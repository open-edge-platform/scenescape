#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import json
import time
import numpy as np
import pytest

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
from scene_common.transform import CameraPose
from scene_common.geometry import Point
from controller.tools.analytics.library import metrics
from scene_common.timestamp import get_iso_time
import tests.common_test_utils as common

FRAME_RATE = 10
MAX_DELAYS = 3
CHILD_NAME = "Demo"
ERROR = 0.2
DEBUG_MSGS = 5

recent_data = []
parent_translation = {}
cur_parent = None
cur_category = None
pose = None
count = 0
test_cases = [([1., 0., 0.], [0., 0., 0.], CHILD_NAME, "parent", "person")]
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

  if len(recent_data) == 2:
    transform_data(recent_data, parent_translation, cur_category, count, pose)
    count += 1
  return

def verify_linking_children(parent_scene, children, rest_client, pose):
  """! Function to verify the linking mulitple child scenes to a parent

  @param    parent_scene                The current parent scene for test.
  @param    children                    The list of names for child scenes.
  @param    rest_client                 The rest client.
  @param    pose                        The scene pose information.
  @return   None
  """
  log.info("Verifying linking multiple children to parent")
  for child in children:
    child_scene = rest_client.createScene({'name': child})
    res = rest_client.updateScene(child_scene['uid'], {
      'parent': parent_scene['uid'],
      'transform': pose.asDict,
    })
    assert res
    assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"
  return

def verify_circular_linking_fails(parent_scene, children, rest_client):
  """! Function to verify that linking children with a circular dependency fails

  @param    parent_scene                The current parent scene for test.
  @param    children                    The list of names for child scenes.
  @param    rest_client                 The rest client.
  @return   None
  """
  log.info("Verifying linking B->A fails with existing A->B")
  for child in children:
    child_scene = rest_client.getScenes({'name': child})['results'][0]
    res = rest_client.updateScene(parent_scene['uid'], {'parent': child_scene['uid']})
    assert res.statusCode == 400, f"Expected status code 400, got {res.statusCode}"
    assert 'circular dependency' in res.errors[0]

  log.info("Verifying that linking C->A fails with existing A->B->C")
  sub_child = rest_client.createScene({'name': 'sc1'})
  res = rest_client.updateScene(sub_child['uid'], {'parent': child_scene['uid']})
  assert res
  assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"
  res = rest_client.updateScene(parent_scene['uid'], {'parent': sub_child['uid']})
  assert res.statusCode == 400, f"Expected status code 400, got {res.statusCode}"
  assert 'circular dependency' in res.errors[0]
  return

def verify_unique_parent(child_scene, parents, rest_client, pose):
  """! Function to verify the prevention of linking the same child to multiple parent scenes

  @param    child_scene                The current child scene for test.
  @param    parents                    The list of names for parent scenes.
  @param    rest_client                The rest client.
  @param    pose                       The scene pose information.
  @return   None
  """
  log.info("Verifying linking child to multiple parents fails")
  for parent in parents:
    parent_scene = rest_client.createScene({'name': parent})
    res = rest_client.updateScene(child_scene['uid'], {
      'parent': parent_scene['uid'],
      'transform': pose.asDict,
    })
    assert res.statusCode == 400, f"Expected status code 400, got {res.statusCode}"
    assert 'already exists' in res.errors[0]
  return

def transform_data(data, parent_translation, cur_category, count, pose):
  """! Function to calculate expected parent data
  by transforming child data

  @param    data                     The capture parent and child data.
  @param    parent_translation       Dict to store expected and predicted location of parent data.
  @param    cur_category             The current object category.
  @param    count                    Iter used for debugging.
  @param    pose                     The scene pose information.
  @return   None
  """

  if data[0]['category'] == cur_category and \
    data[1]['category'] == cur_category:
    expected_translation = Point(data[0]["translation"])
    expected_translation = np.hstack([expected_translation.asNumpyCartesian, [1]])
    expected_translation = np.matmul(pose.pose_mat, expected_translation)[:3]

    parent_translation['expected_x'].append(expected_translation[0])
    parent_translation['expected_y'].append(expected_translation[1])
    parent_translation['predicted_x'].append(data[1]["translation"][0])
    parent_translation['predicted_y'].append(data[1]["translation"][1])

    if count < DEBUG_MSGS:
      log.info('expected parent translation: ({},{})'.format(round(expected_translation[0], 2), \
                                                             round(expected_translation[1], 2)))
      log.info('actual parent translation: ({},{})'.format(round(data[1]['translation'][0], 2), \
                                                           round(data[1]['translation'][1], 2)))
  return

def calculate_mse(parent_translation):
  """! Function to calulcate mse based on expected and predicted object location
  @param    parent_translation           Dict of expected and actual object locations.
  @return   mse                          Dict containing mse.
  """
  assert len(parent_translation['expected_x']) == len(parent_translation['expected_y'])
  assert len(parent_translation['predicted_x']) == len(parent_translation['predicted_y'])

  length = [parent_translation['expected_x'].index(i) for i in parent_translation['expected_x']]
  expected = metrics.Track(parent_translation['expected_x'],\
                           parent_translation['expected_y'], None, length, None)
  predicted = metrics.Track(parent_translation['predicted_x'],\
                            parent_translation['predicted_y'], None, length, None)
  mse = metrics.getMSE(expected, predicted)
  return mse

def publish_data(obj_data, obj_location, client, obj_cat):
  """! Function to publish data to mqtt topic based on object category
  @param    obj_data                   Pytest fixture defining object data such as ID, etc.
  @param    obj_location               Pytest fixture defining the objects location.
  @param    client                     The mqtt client.
  @param    obj_cat                    The object category.
  """
  for y_loc in obj_location:
    cam_id = obj_data["id"]
    obj_data["timestamp"] = get_iso_time()
    obj_data["objects"][obj_cat][0]["bounding_box"]["y"] = y_loc
    obj_data["objects"][obj_cat][0]["category"] = obj_cat
    line = json.dumps(obj_data)

    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
    client.publish(topic, line)
    time.sleep(1/FRAME_RATE)
  return

@pytest.mark.parametrize("translation,rotation,child,parent,obj_cat", test_cases)
def test_child_scenes(objData, obj_location, record_xml_attribute, \
                                             translation, \
                                             rotation, \
                                             child, \
                                             parent, \
                                             obj_cat, \
                                             params):
  """! This function creates and updates the child scene. It also verifies that
  the data received from the parent is correct after applying different transforms based on the test
  cases provided above.
  @param    objData                 Pytest fixture defining object data such as ID, etc.
  @param    obj_location            Pytest fixture defining the objects location.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    translation             The ranslation of the child scene.
  @param    rotation                The rotation of the child scene.
  @param    parent                  The name of the parent.
  @param    child                   The name of the child.
  @param    obj_cat                 The object category.
  @param    params                  Dict of test parameters.
  @return   exit_code               Indicates test success or failure.
  """
  global parent_translation,\
  cur_parent, cur_category, count, parent_id, child_id

  parent_translation = {
    'expected_x':  [],
    'expected_y':  [],
    'predicted_x': [],
    'predicted_y': []
  }

  transform = {
    "translation": translation,
    "rotation": rotation,
    "scale": [1., 1., 1.],
  }

  cur_parent = parent
  cur_category = obj_cat
  children = ['c1', 'c2', 'c3']
  parents = ['p1', 'p2', 'p3']
  exit_code = 1
  mse = None

  TEST_NAME = "NEX-T10439"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  pose = CameraPose(transform, None)
  client = PubSub(params["auth"], None, params["rootcert"],
                  params["broker_url"], params["broker_port"], userdata=pose)
  client.onConnect = on_connect
  client.onMessage = on_message
  client.connect()

  map_image = "/workspace/sample_data/HazardZoneSceneLarge.png"
  assert os.path.exists(map_image)

  try:
    rest_client = RESTClient(params['resturl'],
                             rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])
    with open(map_image, "rb") as f:
      map_data = f.read()
    parent_scene = rest_client.createScene({'name': parent, 'map': (map_image, map_data)})
    parent_id = parent_scene['uid']
    log.info("Parent scene:", parent, parent_scene)
    assert parent_scene
    scenes = rest_client.getScenes({'name': child})
    assert scenes['results']
    child_scene = scenes['results'][0]
    child_id = child_scene['uid']
    result = rest_client.updateScene(child_scene['uid'], {
      'parent': parent_scene['uid'],
      'transform': pose.asDict,
    })
    assert result

    client.loopStart()
    publish_data(objData, obj_location, client, obj_cat)
    mse = calculate_mse(parent_translation)

    assert mse is not None
    log.info("MSE: ", round(mse["euclidean_mse"], 2))
    assert mse["euclidean_mse"] <= ERROR, f"The MSE is not within limit (max: {ERROR})!"

    verify_unique_parent(child_scene, parents, rest_client, pose)
    verify_linking_children(parent_scene, children, rest_client, pose)
    verify_circular_linking_fails(parent_scene, children, rest_client)
    res = rest_client.deleteScene(parent_scene['uid'])
    res = rest_client.getScenes({'name': child})
    assert res['results'][0]
    exit_code = 0

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
