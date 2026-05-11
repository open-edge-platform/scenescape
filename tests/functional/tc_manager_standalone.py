#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Microservices needed for test:
#   * broker
#   * pgserver
#   * web (Manager + REST API)

import time

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient

from tests.functional.common_service import ServiceMqttTest

TEST_SCENE_NAME = "manager-scene"


def test_manager_publishes_cmd_database_on_scene_create(record_xml_attribute, params):
  """! Verify that creating a scene via the REST API causes the Manager to
  publish an 'update' message on the CMD_DATABASE MQTT topic.

  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test connection parameters.
  """
  TEST_NAME = "NEX-T12750"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password']), \
    "REST authentication failed"

  print(f"Testing scene creation triggers CMD_DATABASE 'update' on {db_topic}")

  h = ServiceMqttTest(params)
  created_uid = None
  try:
    h.connect([db_topic])

    res = rest.createScene({'name': TEST_SCENE_NAME})
    assert res.statusCode == 201, f"Failed to create scene: {res.errors}"
    created_uid = res['uid']
    log.info(f"Created scene uid={created_uid}")

    received = h.wait_for_payload("update")
    assert received, (
      f"No CMD_DATABASE 'update' message received on {db_topic} within "
      f"{h.MAX_WAIT}s after scene creation"
    )
    log.info("PASS: CMD_DATABASE 'update' received after scene creation")
  finally:
    h.disconnect()
    if created_uid is not None:
      rest.deleteScene(created_uid)


def test_manager_publishes_cmd_scene_update_on_scene_modify(record_xml_attribute, params,
                                                             scene_uid):
  """! Verify that updating a scene via the REST API causes the Manager to
  publish an 'update' message on the CMD_SCENE_UPDATE MQTT topic for that
  specific scene.

  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test connection parameters.
  @param    scene_uid               UID of the test scene.
  """
  TEST_NAME = "NEX-T12750"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  scene_update_topic = PubSub.formatTopic(PubSub.CMD_SCENE_UPDATE, scene_id=scene_uid)
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password']), \
    "REST authentication failed"

  original_res = rest.getScenes({'id': scene_uid})
  assert original_res['count'] > 0, f"Scene uid={scene_uid} not found"
  original_name = original_res['results'][0]['name']

  h = ServiceMqttTest(params)
  try:
    h.connect([scene_update_topic])

    res = rest.updateScene(scene_uid, {'name': original_name + "-modified"})
    assert res.statusCode == 200, f"Failed to update scene: {res.errors}"
    log.info(f"Updated scene uid={scene_uid}")

    received = h.wait_for_payload("update")
    assert received, (
      f"No CMD_SCENE_UPDATE 'update' message received on {scene_update_topic} "
      f"within {h.MAX_WAIT}s after scene update"
    )
    log.info("PASS: CMD_SCENE_UPDATE 'update' received after scene modification")
  finally:
    h.disconnect()
    rest.updateScene(scene_uid, {'name': original_name})


def test_manager_no_mqtt_on_readonly_request(record_xml_attribute, params, scene_uid):
  """! Verify that a read-only REST request (GET) does NOT trigger any
  CMD_DATABASE or CMD_SCENE_UPDATE MQTT message.

  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test connection parameters.
  @param    scene_uid               UID of the test scene.
  """
  TEST_NAME = "NEX-T12750"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
  scene_update_topic = PubSub.formatTopic(PubSub.CMD_SCENE_UPDATE, scene_id=scene_uid)
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password']), \
    "REST authentication failed"

  h = ServiceMqttTest(params)
  try:
    h.connect([db_topic, scene_update_topic])
    h.clear_messages()

    res = rest.getScenes({'id': scene_uid})
    assert res['count'] > 0, f"GET scene uid={scene_uid} failed"
    log.info(f"GET scene uid={scene_uid} succeeded")

    time.sleep(2)

    assert not h.has_any_message(), (
      "Unexpected MQTT message(s) received on CMD_DATABASE or CMD_SCENE_UPDATE "
      "after a read-only GET request"
    )
    log.info("PASS: no MQTT messages triggered by read-only REST request")
  finally:
    h.disconnect()

def test_manager_publishes_cmd_database_on_scene_delete(record_xml_attribute, params,
                                                         scene_uid):
  """! Verify that deleting a scene via the REST API causes the Manager to
  publish an 'update' message on the CMD_DATABASE MQTT topic. CMD_SCENE_UPDATE
  is not published on delete because the scene no longer exists.

  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test connection parameters.
  @param    scene_uid               UID of the test scene.
  """
  TEST_NAME = "NEX-T12750"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")

  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password']), \
    "REST authentication failed"

  h = ServiceMqttTest(params)
  try:
    h.connect([db_topic])

    res = rest.deleteScene(scene_uid)
    assert res.statusCode == 200, f"Failed to delete scene: {res.errors}"
    log.info(f"Deleted scene uid={scene_uid}")

    received = h.wait_for_payload("update")
    assert received, (
      f"No CMD_DATABASE 'update' message received on {db_topic} "
      f"within {h.MAX_WAIT}s after scene delete"
    )
    log.info("PASS: CMD_DATABASE 'update' received after scene delete")
  finally:
    h.disconnect()
