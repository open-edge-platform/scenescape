#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests verifying that scene property updates are reflected in the
scene controller:
  - Scene name changes appear in scenescape/data/scene MQTT topic metadata.
  - Regulated_rate and external_update_rate changes affect the frequency of
    scenescape/regulated/scene and scenescape/external/{scene_id} messages, respectively.
  - Standalone roots (CONTROLLER_PUBLISH_EXTERNAL off by default) do not emit
    DATA_EXTERNAL; remote-child stacks enable --publish-external on the controller.
    """

import json
import threading
import time
import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from tests.functional.common_retrack import RetrackTest
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

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


@pytest.fixture
def demo_scene(params):
  """Provide (helper, rest, scene) for Demo scene tests and restore scene
  properties on teardown."""
  helper = UpdateSceneTest(params)
  rest = helper.make_rest_client()
  scene = helper.get_demo_scene(rest)
  original = {
    "name": scene["name"],
    "regulated_rate": scene.get("regulated_rate", 30),
  }
  yield helper, rest, scene
  def _restore():
    res = rest.updateScene(scene["uid"], original)
    assert res.statusCode == 200, \
      f"Failed to restore Demo scene: {res.statusCode}: {res.errors}"

  helper.await_cmd_database(_restore)
  log.info(f"Restored Demo scene properties: {original}")


@pytest.fixture
def child_scene(params):
  """Provide (helper, rest) with a child scene set up via helper.setup_scenes,
  and tear it down on fixture teardown."""
  helper = UpdateSceneTest(params)
  rest = helper.make_rest_client()
  helper.setup_scenes(rest)
  try:
    yield helper, rest
  finally:
    try:
      helper.teardown_scenes(rest)
    except Exception:
      log.exception("Exception tearing down child scene")
      raise


@pytest.mark.test_name("NEX-T10565")
def test_scene_name_update_reflected_in_data_scene_topic(
    objData, result_recorder, demo_scene):
  """Verify that when a scene name is updated via REST, subsequent
  scenescape/data/scene MQTT messages carry the new name in their metadata.

  Sequence:
    1. Subscribe to data/scene for the Demo scene.
    2. Send detections and confirm baseline messages carry the original name.
    3. Update the scene name via REST, wait for CMD_DATABASE notification.
    4. Send more detections and confirm messages carry the updated name.

  @param    objData            Pytest fixture with detection data.
  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    demo_scene         Fixture yielding (helper, rest, scene) and
                               restoring scene state on teardown.
  """

  helper, rest, scene = demo_scene
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

    helper.publish_data(objData, client)
    updated = helper.wait_for_name(new_name)
    assert updated["name"] == new_name, \
      f"Expected updated name='{new_name}', got '{updated['name']}'"
    assert updated["id"] == scene_uid, \
      f"Scene UID mismatch in updated message: {updated['id']}"

    log.info(f"PASS: data/scene reflects updated scene name='{new_name}'")
    result_recorder.success()

  finally:
    if client is not None:
      client.loopStop()


@pytest.mark.test_name("NEX-T10570")
def test_scene_regulated_rate_update_changes_message_frequency(
    objData, result_recorder, demo_scene):
  """Verify that updating regulated_rate on the Demo scene changes the
  frequency of scenescape/regulated/scene messages.

  Phase 1: regulated_rate = 1 Hz: DATA_REGULATED messages with objects must
  arrive within the 1 Hz band over MEASURE_WINDOW_S seconds.
  Phase 2: regulated_rate = 10 Hz: the count must fall within the 10 Hz band
  and must exceed the Phase 1 count, confirming the rate increase took effect.

  @param    objData            Pytest fixture with detection data.
  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    demo_scene         Fixture yielding (helper, rest, scene) and
                               restoring scene state on teardown.
  """
  helper, rest, scene = demo_scene
  scene_uid = scene["uid"]
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

    def _measure(rate_hz):
      helper.set_regulated_rate(rest, scene_uid, rate_hz)
      time.sleep(0.2)
      with msg_lock:
        reg_msgs.clear()
      t = threading.Thread(
        target=RetrackTest.publish_timed,
        args=(objData, client, RetrackTest.FRAME_RATE, MEASURE_WINDOW_S),
        daemon=True)
      t.start()
      t.join()
      time.sleep(1.0)
      with msg_lock:
        return len(reg_msgs)

    log.info("Phase 1: setting regulated_rate=1 Hz")
    count_1hz = _measure(1)
    max_1hz = int(1 * MEASURE_WINDOW_S * 2)
    min_1hz = int(1 * MEASURE_WINDOW_S * 0.4)
    log.info(f"Phase 1 (1 Hz): {count_1hz} messages (expect {min_1hz}–{max_1hz})")
    assert count_1hz >= min_1hz, \
      f"Too few DATA_REGULATED messages at 1 Hz: {count_1hz} < {min_1hz}"
    assert count_1hz <= max_1hz, \
      f"Too many DATA_REGULATED messages at 1 Hz: {count_1hz} > {max_1hz}"

    log.info("Phase 2: setting regulated_rate=10 Hz")
    count_10hz = _measure(10)
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
    result_recorder.success()

  finally:
    if client is not None:
      client.loopStop()


@pytest.mark.test_name("NEX-T23097")
def test_scene_external_rate_update_changes_message_frequency(
    objData, result_recorder, child_scene):
  """Verify that updating external_update_rate on a child scene changes the
  frequency of scenescape/external/{scene_id} messages.

  Phase 1: external_update_rate = 1 Hz: the count must fall within the 1 Hz
  band and must be less than the Phase 2 count, confirming the rate increase
  took effect.
  Phase 2: external_update_rate = 10 Hz: DATA_EXTERNAL messages with objects
  must arrive within the 10 Hz band over MEASURE_WINDOW_S seconds.

  @param    objData            Pytest fixture with detection data.
  @param    result_recorder    Pytest fixture recording test pass/fail.
  @param    child_scene        Fixture yielding (helper, rest) with a child
                               scene set up and torn down on teardown.
  """
  helper, rest = child_scene
  scene_data = rest.getScene(helper.child_id)
  assert scene_data.statusCode == 200, \
    f"getScene({helper.child_id}) failed: {getattr(scene_data, 'errors', None)}"
  original_ext_rate = scene_data.get("external_update_rate", 30)
  log.info(f"Original external_update_rate={original_ext_rate}")
  client = None

  try:
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

    def _measure(rate_hz):
      helper.set_external_rate(rest, rate_hz)
      time.sleep(0.2)
      with msg_lock:
        ext_msgs.clear()
      t = threading.Thread(
        target=RetrackTest.publish_timed,
        args=(objData, client, RetrackTest.FRAME_RATE, MEASURE_WINDOW_S),
        daemon=True)
      t.start()
      t.join()
      time.sleep(1.0)
      with msg_lock:
        return len(ext_msgs)

    log.info("Phase 1: setting external_update_rate=1 Hz")
    count_1hz = _measure(1)
    max_1hz = int(1 * MEASURE_WINDOW_S * 2)
    min_1hz = int(1 * MEASURE_WINDOW_S * 0.4)
    log.info(f"Phase 1 (1 Hz): {count_1hz} messages (expect {min_1hz}–{max_1hz})")
    assert count_1hz >= min_1hz, \
      f"Too few DATA_EXTERNAL messages at 1 Hz: {count_1hz} < {min_1hz}"
    assert count_1hz <= max_1hz, \
      f"Too many DATA_EXTERNAL messages at 1 Hz: {count_1hz} > {max_1hz}"

    log.info("Phase 2: setting external_update_rate=10 Hz")
    count_10hz = _measure(10)
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
    result_recorder.success()

  finally:
    try:
      helper.set_external_rate(rest, original_ext_rate)
      log.info(f"Restored external_update_rate={original_ext_rate}")
    except Exception as exc:
      log.warning(f"Failed to restore external_update_rate: {exc}")
    if client is not None:
      client.loopStop()


@pytest.mark.test_name("NEX-T23098")
def test_standalone_root_skips_external_when_publish_external_disabled(
    objData, result_recorder, demo_scene):
  """ADR 16: default controller (no --publish-external) does not emit DATA_EXTERNAL
  for a standalone root scene.
  """
  helper, rest, scene = demo_scene
  scene_uid = scene["uid"]
  assert not scene.get("parent"), "Demo must be a standalone root for this test"
  client = None

  try:
    ext_topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=scene_uid, thing_type="+")
    ext_msgs = []
    msg_lock = threading.Lock()

    def _on_ext(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
        if data.get("objects"):
          with msg_lock:
            ext_msgs.append(data)
      except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning(f"Failed to decode external payload: {exc}")

    client = helper.make_client(topics=[ext_topic], on_msg=_on_ext)
    helper.publish_data(objData, client)
    time.sleep(2.0)
    with msg_lock:
      count = len(ext_msgs)
    assert count == 0, (
      f"Standalone root must not publish DATA_EXTERNAL when "
      f"--publish-external is off; got {count} messages")
    log.info("PASS: no DATA_EXTERNAL from standalone root (publish-external disabled)")
    result_recorder.success()

  finally:
    if client is not None:
      client.loopStop()
