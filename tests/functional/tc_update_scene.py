#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests verifying that scene property updates are reflected in the
scene controller:
  - Scene name changes appear in scenescape/data/scene MQTT topic metadata.
  - Scene scale changes are acknowledged by the controller and persist."""

import json
import threading
import time

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
import tests.common_test_utils as common
from tests.functional.common_retrack import RetrackTest

DEMO_SCENE_NAME = "Demo"
WAIT_TIMEOUT_S = 30
MEASURE_WINDOW_S = 5   # seconds of continuous publishing per rate phase


class UpdateSceneTest(RetrackTest):

  MAX_WAIT = WAIT_TIMEOUT_S

  def __init__(self, params):
    super().__init__(params)
    self._scene_messages = []
    self._expected_name = None
    self._name_seen = threading.Event()

  def make_rest_client(self):
    rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert rest.authenticate(self.params["user"], self.params["password"]), \
      "REST authentication failed"
    return rest

  def get_demo_scene(self, rest):
    res = rest.getScenes({"name": DEMO_SCENE_NAME})
    assert res.statusCode == 200, f"Failed to fetch scenes: {res.errors}"
    assert res["count"] > 0, f"Demo scene '{DEMO_SCENE_NAME}' not found"
    return res["results"][0]

  def _on_scene_message(self, mqttc, obj, msg):
    """MQTT callback, collect data/scene payloads and signal name matches."""
    try:
      payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
      log.warning(f"Failed to decode data/scene payload: {exc}")
      return
    with self._lock:
      self._scene_messages.append(payload)
      if self._expected_name and payload.get("name") == self._expected_name:
        self._name_seen.set()

  def connect_for_scene(self, scene_id):
    data_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_id, thing_type="+")
    return self.make_client(topics=[data_topic], on_msg=self._on_scene_message)

  def await_cmd_database(self, rest_fn):
    self._await_db_notification(rest_fn)

  def wait_for_name(self, name, timeout=WAIT_TIMEOUT_S):
    """Block until a data/scene message whose ``name`` field equals *name*.

    Checks already-buffered messages first, then waits for incoming ones.

    @param    name       Expected scene name value.
    @param    timeout    Maximum wait time in seconds.
    @return              First matching message payload dict.
    """
    with self._lock:
      for msg in self._scene_messages:
        if msg.get("name") == name:
          return msg
      self._expected_name = name
      self._name_seen.clear()

    assert self._name_seen.wait(timeout), \
      f"Timed out after {timeout}s waiting for data/scene message with name='{name}'"

    with self._lock:
      self._expected_name = None
      for msg in reversed(self._scene_messages):
        if msg.get("name") == name:
          return msg

    raise AssertionError(
      f"data/scene message with name='{name}' not found after event fired")


def test_scene_name_update_reflected_in_data_scene_topic(
    objData, record_xml_attribute, params):
  """Verify that when a scene name is updated via REST, subsequent
  scenescape/data/scene MQTT messages carry the new name in their metadata.

  Sequence:
    1. Subscribe to data/scene for the Demo scene.
    2. Send detections and confirm baseline messages carry the original name.
    3. Update the scene name via REST, wait for CMD_DATABASE notification.
    4. Send more detections and confirm messages carry the updated name.
    5. Restore the original name in the finally block.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T10565"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  helper = UpdateSceneTest(params)
  rest = helper.make_rest_client()
  scene = helper.get_demo_scene(rest)
  scene_uid = scene["uid"]
  original_name = scene["name"]
  new_name = "updated_scene"
  client = None

  try:
    client = helper.connect_for_scene(scene_uid)

    log.info(f"Baseline check for name='{original_name}'")
    helper.publish_data(objData, client)
    baseline = helper.wait_for_name(original_name)
    assert baseline["id"] == scene_uid, \
      f"Unexpected scene UID in baseline message: {baseline['id']}"
    log.info(f"Baseline confirmed: data/scene name='{baseline['name']}'")

    log.info(f"Updating scene name '{original_name}' → '{new_name}'")

    def _update_name():
      res = rest.updateScene(scene_uid, {"name": new_name})
      assert res.statusCode == 200, \
        f"REST update returned {res.statusCode}: {res.errors}"

    helper.await_cmd_database(_update_name)
    log.info("Controller acknowledged name update via CMD_DATABASE")

    # Verify updated name appears in data/scene messages
    helper.publish_data(objData, client)
    updated = helper.wait_for_name(new_name)
    assert updated["name"] == new_name, \
      f"Expected updated name='{new_name}', got '{updated['name']}'"
    assert updated["id"] == scene_uid, \
      f"Scene UID mismatch in updated message: {updated['id']}"

    log.info(f"PASS: data/scene reflects updated scene name='{new_name}'")
    exit_code = 0

  finally:
    try:
      res = rest.updateScene(scene_uid, {"name": original_name})
      if res.statusCode == 200:
        log.info(f"Restored scene name to '{original_name}'")
      else:
        log.error(f"Failed to restore scene name: {res.statusCode}: {res.errors}")
    except Exception as exc:
      log.error(f"Exception restoring scene name: {exc}")
    if client is not None:
      client.loopStop()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_scene_regulated_rate_update_changes_message_frequency(
    objData, record_xml_attribute, params):
  """Verify that updating regulated_rate on the Demo scene changes the
  frequency of scenescape/regulated/scene messages.

  Phase 1: regulated_rate = 1 Hz: DATA_REGULATED messages with objects must
  arrive within the 1 Hz band over MEASURE_WINDOW_S seconds.
  Phase 2: regulated_rate = 10 Hz: the count must fall within the 10 Hz band
  and must exceed the Phase 1 count, confirming the rate increase took effect.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T10570"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  helper = UpdateSceneTest(params)
  rest = helper.make_rest_client()
  scene = helper.get_demo_scene(rest)
  scene_uid = scene["uid"]
  original_rate = scene.get("regulated_rate", 30)
  client = None

  try:
    reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
    reg_msgs = []
    msg_lock = threading.Lock()

    def _on_reg(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
        if data.get("objects"):
          with msg_lock:
            reg_msgs.append(time.time())
      except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning(f"Failed to decode regulated payload: {exc}")

    client = helper.make_client(topics=[reg_topic], on_msg=_on_reg)

    log.info("Phase 1: setting regulated_rate=1 Hz")
    helper.set_regulated_rate(rest, scene_uid, 1)

    send_thread = threading.Thread(
      target=RetrackTest.publish_timed,
      args=(objData, client, RetrackTest.FRAME_RATE, MEASURE_WINDOW_S),
      daemon=True)
    send_thread.start()
    send_thread.join()
    time.sleep(1.0)

    with msg_lock:
      count_1hz = len(reg_msgs)
      reg_msgs.clear()

    max_1hz = int(1 * MEASURE_WINDOW_S * 2)
    min_1hz = int(1 * MEASURE_WINDOW_S * 0.4)
    log.info(f"Phase 1 (1 Hz): {count_1hz} messages (expect {min_1hz}–{max_1hz})")
    assert count_1hz >= min_1hz, \
      f"Too few DATA_REGULATED messages at 1 Hz: {count_1hz} < {min_1hz}"
    assert count_1hz <= max_1hz, \
      f"Too many DATA_REGULATED messages at 1 Hz: {count_1hz} > {max_1hz}"

    log.info("Phase 2: setting regulated_rate=10 Hz")
    helper.set_regulated_rate(rest, scene_uid, 10)

    send_thread = threading.Thread(
      target=RetrackTest.publish_timed,
      args=(objData, client, RetrackTest.FRAME_RATE, MEASURE_WINDOW_S),
      daemon=True)
    send_thread.start()
    send_thread.join()
    time.sleep(1.0)

    with msg_lock:
      count_10hz = len(reg_msgs)

    max_10hz = int(10 * MEASURE_WINDOW_S * 2)
    min_10hz = int(10 * MEASURE_WINDOW_S * 0.4)
    log.info(f"Phase 2 (10 Hz): {count_10hz} messages (expect {min_10hz}–{max_10hz})")
    assert count_10hz >= min_10hz, \
      f"Too few DATA_REGULATED messages at 10 Hz: {count_10hz} < {min_10hz}"
    assert count_10hz <= max_10hz, \
      f"Too many DATA_REGULATED messages at 10 Hz: {count_10hz} > {max_10hz}"

    assert count_10hz > count_1hz, \
      (f"Expected more messages at 10 Hz than at 1 Hz, "
       f"got {count_10hz} (10 Hz) vs {count_1hz} (1 Hz)")

    log.info(
      f"PASS: regulated_rate changes message frequency "
      f"(1 Hz: {count_1hz} msgs, 10 Hz: {count_10hz} msgs over {MEASURE_WINDOW_S}s)")
    exit_code = 0

  finally:
    try:
      helper.set_regulated_rate(rest, scene_uid, original_rate)
      log.info(f"Restored regulated_rate={original_rate}")
    except Exception as exc:
      log.error(f"Failed to restore regulated_rate: {exc}")
    if client is not None:
      client.loopStop()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_scene_external_rate_update_changes_message_frequency(
    objData, record_xml_attribute, params):
  """Verify that updating external_update_rate on a child scene changes the
  frequency of scenescape/external/{scene_id} messages.

  Phase 1: external_update_rate = 1 Hz: the count must fall within the 1 Hz
  band and must be less than the Phase 1 count, confirming the rate decrease
  took effect.
  Phase 2: external_update_rate = 10 Hz: DATA_EXTERNAL messages with objects
  must arrive within the 10 Hz band over MEASURE_WINDOW_S seconds.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T23097"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  helper = UpdateSceneTest(params)
  rest = helper.make_rest_client()
  original_ext_rate = None
  client = None

  try:
    helper.setup_scenes(rest)

    scene_data = rest.getScene(helper.child_id)
    assert scene_data.statusCode == 200, \
      f"getScene({helper.child_id}) failed: {getattr(scene_data, 'errors', None)}"
    original_ext_rate = scene_data.get("external_update_rate", 30)
    log.info(f"Original external_update_rate={original_ext_rate}")

    ext_topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=helper.child_id, thing_type="+")
    ext_msgs = []
    msg_lock = threading.Lock()

    def _on_ext(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
        if data.get("objects"):
          with msg_lock:
            ext_msgs.append(time.time())
      except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning(f"Failed to decode external payload: {exc}")

    client = helper.make_client(topics=[ext_topic], on_msg=_on_ext)

    log.info("Phase 1: setting external_update_rate=10 Hz")
    helper.set_external_rate(rest, 1)

    send_thread = threading.Thread(
      target=RetrackTest.publish_timed,
      args=(objData, client, RetrackTest.FRAME_RATE, MEASURE_WINDOW_S),
      daemon=True)
    send_thread.start()
    send_thread.join()
    time.sleep(1.0)

    with msg_lock:
      count_1hz = len(ext_msgs)
      ext_msgs.clear()

    max_1hz = int(1 * MEASURE_WINDOW_S * 2)
    min_1hz = int(1 * MEASURE_WINDOW_S * 0.4)
    log.info(f"Phase 1 (1 Hz): {count_1hz} messages (expect {min_1hz}–{max_1hz})")
    assert count_1hz >= min_1hz, \
      f"Too few DATA_EXTERNAL messages at 1 Hz: {count_1hz} < {min_1hz}"
    assert count_1hz <= max_1hz, \
      f"Too many DATA_EXTERNAL messages at 1 Hz: {count_1hz} > {max_1hz}"

    log.info("Phase 2: setting external_update_rate=10 Hz")
    helper.set_external_rate(rest, 10)

    send_thread = threading.Thread(
      target=RetrackTest.publish_timed,
      args=(objData, client, RetrackTest.FRAME_RATE, MEASURE_WINDOW_S),
      daemon=True)
    send_thread.start()
    send_thread.join()
    time.sleep(1.0)

    with msg_lock:
      count_10hz = len(ext_msgs)

    max_10hz = int(10 * MEASURE_WINDOW_S * 2)
    min_10hz = int(10 * MEASURE_WINDOW_S * 0.4)
    log.info(f"Phase 2 (10 Hz): {count_10hz} messages (expect {min_10hz}–{max_10hz})")
    assert count_10hz >= min_10hz, \
      f"Too few DATA_EXTERNAL messages at 10 Hz: {count_10hz} < {min_10hz}"
    assert count_10hz <= max_10hz, \
      f"Too many DATA_EXTERNAL messages at 10 Hz: {count_10hz} > {max_10hz}"

    assert count_10hz > count_1hz, \
      (f"Expected more messages at 10 Hz than at 1 Hz, "
       f"got {count_10hz} (10 Hz) vs {count_1hz} (1 Hz)")

    log.info(
      f"PASS: external_update_rate changes message frequency "
      f"(10 Hz: {count_10hz} msgs, 1 Hz: {count_1hz} msgs over {MEASURE_WINDOW_S}s)")
    exit_code = 0

  finally:
    if helper.child_id and original_ext_rate is not None:
      try:
        helper.set_external_rate(rest, original_ext_rate)
        log.info(f"Restored external_update_rate={original_ext_rate}")
      except Exception as exc:
        log.warning(f"Failed to restore external_update_rate: {exc}")
    if client is not None:
      client.loopStop()
    helper.teardown_scenes(rest)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
