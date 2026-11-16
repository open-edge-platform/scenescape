#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for the Manager service standalone MQTT event flow.

Covers:
  - Creating a scene via REST publishes 'update' on CMD_DATABASE.
  - Updating a scene via REST publishes 'update' on CMD_SCENE_UPDATE.
  - Read-only REST requests publish no MQTT messages.
  - Deleting a scene via REST publishes 'update' on CMD_DATABASE.
"""

import time
import pytest

from scene_common.mqtt import PubSub

from tests.functional.common_service import ServiceMqttTest
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_SCENE_NAME = "manager-scene"


def _create_scene(rest, name=TEST_SCENE_NAME):
  res = rest.createScene({'name': name})
  assert res.statusCode == 201, f"Failed to create scene: {res.errors}"
  created_uid = res['uid']
  log.info(f"Created scene uid={created_uid}")
  return created_uid


@pytest.fixture
def mqtt_tester(params):
  """Provide a ServiceMqttTest and disconnect it on teardown."""
  h = ServiceMqttTest(params)
  try:
    yield h
  finally:
    h.disconnect()


@pytest.mark.test_name("NEX-T12750")
def test_manager_publishes_cmd_database_on_scene_create(
    result_recorder, rest, mqtt_tester):
  """! Verify that creating a scene via the REST API causes the Manager to
  publish an 'update' message on the CMD_DATABASE MQTT topic.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    rest               Authenticated RESTClient fixture.
  @param    mqtt_tester        ServiceMqttTest fixture.
  """
  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
  log.info(f"Testing scene creation triggers CMD_DATABASE 'update' on {db_topic}")

  created_uid = None
  try:
    mqtt_tester.connect([db_topic])
    created_uid = _create_scene(rest, TEST_SCENE_NAME)

    received = mqtt_tester.wait_for_payload("update")
    assert received, (
      f"No CMD_DATABASE 'update' message received on {db_topic} within "
      f"{mqtt_tester.MAX_WAIT_S}s after scene creation"
    )
    log.info("PASS: CMD_DATABASE 'update' received after scene creation")
    result_recorder.success()
  finally:
    if created_uid is not None:
      try:
        rest.deleteScene(created_uid)
      except Exception as exc:
        log.warning(f"Failed to delete scene uid={created_uid}: {exc}")


@pytest.mark.test_name("NEX-T22790")
def test_manager_publishes_cmd_scene_update_on_scene_update(
    result_recorder, rest, scene_uid, mqtt_tester):
  """! Verify that updating a scene via the REST API causes the Manager to
  publish an 'update' message on the CMD_SCENE_UPDATE MQTT topic for that
  specific scene.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    rest               Authenticated RESTClient fixture.
  @param    scene_uid          UID of the test scene.
  @param    mqtt_tester        ServiceMqttTest fixture.
  """
  scene_update_topic = PubSub.formatTopic(
    PubSub.CMD_SCENE_UPDATE, scene_id=scene_uid)

  original_res = rest.getScenes({'id': scene_uid})
  assert original_res['count'] > 0, f"Scene uid={scene_uid} not found"
  original_name = original_res['results'][0]['name']

  try:
    mqtt_tester.connect([scene_update_topic])

    res = rest.updateScene(scene_uid, {'name': original_name + "-modified"})
    assert res.statusCode == 200, f"Failed to update scene: {res.errors}"
    log.info(f"Updated scene uid={scene_uid}")

    received = mqtt_tester.wait_for_payload("update")
    assert received, (
      f"No CMD_SCENE_UPDATE 'update' message received on {scene_update_topic} "
      f"within {mqtt_tester.MAX_WAIT_S}s after scene update"
    )
    log.info("PASS: CMD_SCENE_UPDATE 'update' received after scene modification")
    result_recorder.success()
  finally:
    try:
      rest.updateScene(scene_uid, {'name': original_name})
    except Exception as exc:
      log.warning(f"Failed to restore scene name: {exc}")


@pytest.mark.test_name("NEX-T22791")
def test_manager_no_mqtt_on_readonly_request(
    result_recorder, rest, scene_uid, mqtt_tester):
  """! Verify that a read-only REST request (GET) does NOT trigger any
  CMD_DATABASE or CMD_SCENE_UPDATE MQTT message.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    rest               Authenticated RESTClient fixture.
  @param    scene_uid          UID of the test scene.
  @param    mqtt_tester        ServiceMqttTest fixture.
  """
  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
  scene_update_topic = PubSub.formatTopic(
    PubSub.CMD_SCENE_UPDATE, scene_id=scene_uid)

  mqtt_tester.connect([db_topic, scene_update_topic])
  mqtt_tester.clear_messages()

  res = rest.getScenes({'id': scene_uid})
  assert res['count'] > 0, f"GET scene uid={scene_uid} failed"
  log.info(f"GET scene uid={scene_uid} succeeded")

  time.sleep(2)

  assert not mqtt_tester.has_any_message(), (
    "Unexpected MQTT message(s) received on CMD_DATABASE or CMD_SCENE_UPDATE "
    "after a read-only GET request"
  )
  log.info("PASS: no MQTT messages triggered by read-only REST request")
  result_recorder.success()


@pytest.mark.test_name("NEX-T22792")
def test_manager_publishes_cmd_database_on_scene_delete(
    result_recorder, rest, mqtt_tester):
  """! Verify that deleting a scene via the REST API causes the Manager to
  publish an 'update' message on the CMD_DATABASE MQTT topic.

  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    rest               Authenticated RESTClient fixture.
  @param    mqtt_tester        ServiceMqttTest fixture.
  """
  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)

  created_uid = None
  try:
    mqtt_tester.connect([db_topic])
    created_uid = _create_scene(rest, TEST_SCENE_NAME)
    res = rest.deleteScene(created_uid)
    assert res.statusCode == 200, f"Failed to delete scene: {res.errors}"
    log.info(f"Deleted scene uid={created_uid}")
    created_uid = None

    received = mqtt_tester.wait_for_payload("update")
    assert received, (
      f"No CMD_DATABASE 'update' message received on {db_topic} "
      f"within {mqtt_tester.MAX_WAIT_S}s after scene delete"
    )
    log.info("PASS: CMD_DATABASE 'update' received after scene delete")
    result_recorder.success()
  finally:
    if created_uid is not None:
      try:
        rest.deleteScene(created_uid)
      except Exception as exc:
        log.warning(f"Failed to delete scene uid={created_uid}: {exc}")
