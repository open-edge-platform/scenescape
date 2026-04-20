#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import pytest

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
import tests.common_test_utils as common
from scene_common.timestamp import get_iso_time

FRAME_RATE = 10
MAX_WAIT = 10
NUM_PUBLISH_ITERATIONS = 3
parent_id = None
child_id = None
parent_received = []
child_received = []
connected = False


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


def on_message(mqttc, obj, msg):
  """! Call back function for the MQTT client on receiving messages.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    msg       The instance of MQTTMessage.
  @return   None
  """
  global parent_received, child_received, \
      parent_id, child_id

  topic = PubSub.parseTopic(msg.topic)
  real_msg = str(msg.payload.decode("utf-8"))
  data = json.loads(real_msg)

  log.info(f"Received message on topic: {msg.topic}")

  if topic['scene_id'] == parent_id:
    parent_received.append(data)
    obj_count = len(data.get('objects', []))
    log.info(f"Parent received data: {obj_count} objects")

  elif topic['scene_id'] == child_id:
    child_received.append(data)
    obj_count = len(data.get('objects', []))
    log.info(f"Child received data: {obj_count} objects")

  return


def setup_scenes(rest_client):
  """! Function to set up parent scene and link existing Demo scene as child.

  @param    rest_client                 The rest client.
  @return   None
  """
  global parent_id, child_id

  # Create a new parent scene
  parent_scene = rest_client.createScene({'name': "parent"})
  assert parent_scene.statusCode == 201, f"Expected status code 201, got {parent_scene.statusCode}"
  parent_id = parent_scene['uid']
  log.info(f"Parent Scene ID: {parent_id}")

  # Use the existing Demo scene which already has a camera registered
  scenes = rest_client.getScenes({'name': 'Demo'})
  assert scenes['count'] > 0, "Demo scene not found"
  child_scene = scenes['results'][0]
  child_id = child_scene['uid']
  log.info(f"Child Scene (Demo) ID: {child_id}")

  # Link the Demo scene as a child of the parent
  res = rest_client.updateScene(child_id, {
      'parent': parent_id,
  })
  assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"

  res = rest_client.getChildScene({'parent': parent_id})
  assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"


def publish_data(obj_data, client, obj_category="person"):
  """! Publish simulated object detection data to a camera's MQTT topic
  to verify data flow between parent and child scenes.

  @param    obj_data        The object data fixture containing camera id and objects.
  @param    client          The MQTT PubSub client.
  @param    obj_category    The object category to publish (default: "person").
  @return   None
  """
  cam_id = obj_data["id"]
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)

  for iteration in range(NUM_PUBLISH_ITERATIONS):
    for i in range(5):
      obj_data["timestamp"] = get_iso_time()
      obj_data["objects"][obj_category][0]["bounding_box"]["y"] = 100 + \
          (i * 20)
      obj_data["objects"][obj_category][0]["category"] = obj_category
      line = json.dumps(obj_data)

      client.publish(topic, line)
      log.info(
          f"Published object via camera {cam_id}: y={100 + (i * 20)} (iter {iteration})")
      time.sleep(1.0 / FRAME_RATE)

  return


def wait_for_messages(timeout=MAX_WAIT):
  """! Wait for MQTT messages with objects to arrive on parent and/or child topics.
  Returns early once at least one message has been received, and fails on timeout.
  @param    timeout     Maximum time to wait in seconds.
  @return   None
  """
  start = time.time()
  while time.time() - start < timeout:
    # Return as soon as we see any message on parent or child topics
    if parent_received or child_received:
      return
    time.sleep(0.5)
  # If we reach here, no messages were received within the timeout
  assert parent_received or child_received, (
      f"Timed out after {timeout} seconds waiting for MQTT messages "
      "on parent/child scenes"
  )


@pytest.mark.parametrize("parent_scene, child_scene", [
    ("parent", "Demo"),
])
def test_remove_linked_scene(parent_scene, child_scene, objData, record_xml_attribute, params):
  """! Test to verify the unlinking of a child scene from parent scene and validating the data flow.
  """

  global parent_id, child_id, parent_received, child_received, connected
  TEST_NAME = "NEX-T10520"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1

  try:
    rest_client = RESTClient(params['resturl'],
                             rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])
    setup_scenes(rest_client)

    client = PubSub(params["auth"], None, params["rootcert"],
                    params["broker_url"], params["broker_port"])
    client.onConnect = on_connect
    client.onMessage = on_message
    client.connect()
    client.loopStart()

    # Wait for MQTT connection and subscriptions to be established
    start = time.time()
    while not connected and time.time() - start < MAX_WAIT:
      time.sleep(0.5)
    assert connected, "MQTT client failed to connect within timeout"

    log.info("Step 1: Publishing data to child scene while linked to parent")
    parent_received.clear()
    child_received.clear()
    publish_data(objData, client, obj_category="person")
    wait_for_messages()

    assert len(
        child_received) > 0, "Child scene should have received regulated data"
    assert len(
        parent_received) > 0, "Parent scene should have received regulated data"
    log.info(f"Child received {len(child_received)} messages")
    log.info(f"Parent received {len(parent_received)} messages")

    log.info("PASS: Parent scene received data from linked child scene")

    log.info("Step 2: Unlinking child scene from parent scene")
    res = rest_client.deleteChildSceneLink(child_id)
    assert res.statusCode == 200, f"Expected status code 200, got {res.statusCode}"

    log.info("Step 3: Publishing data to child scene after unlinking")
    parent_received.clear()
    child_received.clear()
    publish_data(objData, client, obj_category="person")
    wait_for_messages(timeout=5)

    assert len(
        child_received) > 0, "Child scene should still receive its own data"
    assert len(
        parent_received) == 0, "Parent scene should not receive data from unlinked child scene"

    log.info("PASS: Parent scene did not receive data after child was unlinked")

    exit_code = 0

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
