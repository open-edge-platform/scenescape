#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests validating retrack behaviour when a child scene is linked
to a parent scene via the scene hierarchy.

Retrack semantics:
  - retrack=True  : objects from the child scene are fed into the parent's
                    tracker, the parent assigns new tracking IDs.
  - retrack=False : objects bypass the parent tracker and are merged as
                    already-tracked, original child IDs are preserved.
"""

import json
import queue
import threading
import time

import pytest
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
import tests.common_test_utils as common
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

from tests.functional.common_retrack import RetrackTest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

@pytest.mark.test_name("NEX-T21491")
def test_scene_retrack_disabled_objects_propagate_to_parent(
    objData, params):
  """! Positive test: with retrack=False, objects from the child scene still
  appear on the parent regulated topic.  They bypass the parent tracker and
  are merged as already-tracked objects.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21491"
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, False)
    client = h.make_client()

    h.reset()

    h.publish_data(objData, client, obj_category="person")
    h.wait_for_messages(require_parent=True, require_child=True)

    assert len(h.parent_received) > 0, \
      "Parent scene should receive objects when retrack=False"
    assert len(h.child_received) > 0, \
      "Child scene should publish regulated data"

    log.info("PASS: parent received %d messages with retrack=False" %
             len(h.parent_received))
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


@pytest.mark.test_name("NEX-T21492")
def test_scene_retrack_disabled_preserves_child_object_ids(
    objData, params):
  """! Positive test: with retrack=False, object IDs published on the parent's
  regulated topic match the IDs from the child scene.  This verifies that
  objects bypass the parent tracker and keep their original IDs.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21492"
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, False)
    client = h.make_client()

    h.reset()

    h.publish_data(objData, client, obj_category="person")
    h.wait_for_messages(require_parent=True, require_child=True)

    parent_snap, child_snap = h.snapshot_received()
    parent_ids = RetrackTest.collect_object_ids(parent_snap)
    child_ids = RetrackTest.collect_object_ids(child_snap)

    log.info(f"Parent IDs: {parent_ids}")
    log.info(f"Child IDs:  {child_ids}")

    assert parent_ids, "No object IDs collected from parent"
    assert child_ids, "No object IDs collected from child"
    shared = parent_ids & child_ids
    assert shared, \
      ("retrack=False: expected parent IDs to overlap with child IDs, "
       f"parent={parent_ids}, child={child_ids}")

    log.info(f"PASS: shared IDs between child and parent: {shared}")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


@pytest.mark.test_name("NEX-T21493")
def test_scene_retrack_enabled_assigns_new_ids_to_child_objects(
    objData, params):
  """! Positive test: with retrack=True, the parent tracker assigns its own
  tracking IDs to objects received from the child scene.  The IDs seen on
  the parent regulated topic must not match the child's IDs.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21493"
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)
    client = h.make_client()

    h.reset()

    h.publish_data(objData, client, obj_category="person")
    h.wait_for_messages(require_parent=True, require_child=True)

    parent_snap, child_snap = h.snapshot_received()
    parent_ids = RetrackTest.collect_object_ids(parent_snap)
    child_ids = RetrackTest.collect_object_ids(child_snap)

    log.info(f"Parent IDs: {parent_ids}")
    log.info(f"Child IDs:  {child_ids}")

    assert parent_ids, "No object IDs collected from parent"
    assert child_ids, "No object IDs collected from child"
    shared = parent_ids & child_ids
    assert not shared, \
      ("retrack=True: expected parent IDs to be distinct from child IDs "
       f"(parent re-tracks), shared={shared}")

    log.info("PASS: parent IDs are distinct from child IDs with retrack=True")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


@pytest.mark.test_name("NEX-T21494")
def test_scene_retrack_toggle_changes_id_behaviour(
    objData, params):
  """! Positive test: with continuous object publishing, toggling retrack
  from True to False causes the parent to switch from assigning new tracking
  IDs to preserving the child's original IDs.  Phase 1 (retrack=True): parent
  IDs must differ from child IDs.  Phase 2 (retrack=False): parent IDs must
  overlap with child IDs.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21494"
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  send_thread = None
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)
    client = h.make_client()

    # Publish continuously through both phases; daemon so it is killed if the
    # test fails before join().  Five MAX_WAIT windows covers both observation
    # phases plus the CMD_DATABASE round-trip for the retrack toggle.
    total_duration = int(h.MAX_WAIT * 5)
    send_thread = threading.Thread(
      target=h.publish_timed,
      args=(objData, client, RetrackTest.FRAME_RATE, total_duration),
      daemon=True)
    send_thread.start()

    # ---- Phase 1: retrack=True – parent assigns new IDs ----
    log.info("Phase 1: retrack=True")
    h.reset()
    h.wait_for_messages(require_parent=True, require_child=True)

    parent_snap, child_snap = h.snapshot_received()
    phase1_parent_ids = RetrackTest.collect_object_ids(parent_snap)
    phase1_child_ids = RetrackTest.collect_object_ids(child_snap)
    shared_phase1 = phase1_parent_ids & phase1_child_ids
    assert not shared_phase1, \
      ("Phase 1 (retrack=True): expected parent IDs to differ from child IDs, "
       f"shared={shared_phase1}")
    log.info(
      f"Phase 1: parent IDs differ from child IDs – "
      f"{len(phase1_parent_ids)} parent, {len(phase1_child_ids)} child")

    # ---- Phase 2: switch to retrack=False – child IDs preserved ----
    log.info("Phase 2: switching to retrack=False")
    h.set_retrack(rest_client, False)
    h.reset()

    h.wait_for_messages(require_parent=True, require_child=True)

    parent_snap, child_snap = h.snapshot_received()
    phase2_parent_ids = RetrackTest.collect_object_ids(parent_snap)
    phase2_child_ids = RetrackTest.collect_object_ids(child_snap)
    shared_phase2 = phase2_parent_ids & phase2_child_ids
    assert shared_phase2, \
      ("Phase 2 (retrack=False): expected parent and child to share IDs, "
       f"parent={phase2_parent_ids}, child={phase2_child_ids}")
    log.info(f"Phase 2 shared IDs: {shared_phase2}")

    log.info("PASS: retrack toggle correctly changes ID assignment behaviour")
    exit_code = 0

  finally:
    if send_thread is not None:
      send_thread.join(timeout=1)  # daemon thread; brief grace period before teardown
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


@pytest.mark.test_name("NEX-T21707")
def test_external_topic_payload_has_required_fields(objData, params):
  """! Verify that DATA_EXTERNAL messages published for a child scene contain
  the required top-level fields (id, timestamp, name, objects) and that each
  object entry contains id, translation (three finite floats), and type.
  bounding_box is a camera-space concept and must NOT appear on scene-space
  external topics.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21707"
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1
  ext_client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)

    ext_queue = queue.Queue()

    def _on_ext_msg(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
        if data.get("objects"):
          ext_queue.put(data)
      except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    ext_topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=h.child_id, thing_type="+")
    ext_client = h.make_client([ext_topic], _on_ext_msg)

    send_thread = threading.Thread(
      target=h.publish_data, args=(objData, ext_client), daemon=True)
    send_thread.start()

    try:
      msg = ext_queue.get(timeout=h.MAX_WAIT)
    except queue.Empty:
      msg = None
    send_thread.join()

    assert msg is not None, \
      f"No DATA_EXTERNAL messages with objects received within {h.MAX_WAIT}s"
    assert "id" in msg, "DATA_EXTERNAL message missing 'id'"
    assert "timestamp" in msg, "DATA_EXTERNAL message missing 'timestamp'"
    assert "name" in msg, "DATA_EXTERNAL message missing 'name'"
    assert "objects" in msg, "DATA_EXTERNAL message missing 'objects'"
    assert isinstance(msg["objects"], list) and len(msg["objects"]) > 0, \
      "'objects' field must be a non-empty list"

    for obj in msg["objects"]:
      assert "id" in obj, "Object missing 'id'"
      assert "type" in obj, "Object missing 'type'"
      assert "translation" in obj, "Object missing 'translation'"
      RetrackTest.assert_valid_translation(obj["translation"], "DATA_EXTERNAL object")
      assert "bounding_box" not in obj, \
        "DATA_EXTERNAL object must not contain 'bounding_box' (scene-space topic)"

    log.info(
      f"PASS: DATA_EXTERNAL payload schema correct "
      f"({len(msg['objects'])} object(s) validated)")
    exit_code = 0

  finally:
    if ext_client is not None:
      ext_client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


@pytest.mark.test_name("NEX-T21708")
def test_external_topic_translations_reach_parent_regulated(
    objData, params):
  """! Verify that object translations from DATA_EXTERNAL (child scene space)
  reach the parent regulated topic after the coordinate transform.  With
  retrack=False, object IDs are preserved across the hierarchy, allowing
  direct cross-topic matching by ID.  For each matched pair both the child
  external and parent regulated translation must be a list of three finite
  numeric values, confirming the transform pipeline ran without producing NaN
  or Inf.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21708"
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1
  sub_client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, False)

    ext_queue = queue.Queue()    # object dicts from DATA_EXTERNAL (child space)
    parent_queue = queue.Queue() # object dicts from parent DATA_REGULATED

    ext_topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=h.child_id, thing_type="+")
    parent_reg_topic = PubSub.formatTopic(
      PubSub.DATA_REGULATED, scene_id=h.parent_id)

    def _on_dual_msg(mqttc, obj, msg):
      topic = PubSub.parseTopic(msg.topic)
      if topic is None:
        return
      try:
        data = json.loads(msg.payload.decode("utf-8"))
      except (json.JSONDecodeError, UnicodeDecodeError):
        return
      if topic.get("_topic_id") == PubSub.DATA_EXTERNAL:
        for o in data.get("objects", []):
          if "id" in o and "translation" in o:
            ext_queue.put(o)
      elif topic.get("_topic_id") == PubSub.DATA_REGULATED:
        if topic.get("scene_id") == h.parent_id:
          for o in data.get("objects", []):
            if "id" in o and "translation" in o:
              parent_queue.put(o)

    sub_client = h.make_client([ext_topic, parent_reg_topic], _on_dual_msg)

    send_thread = threading.Thread(
      target=h.publish_data, args=(objData, sub_client), daemon=True)
    send_thread.start()

    start = time.time()
    while time.time() - start < h.MAX_WAIT:
      if not ext_queue.empty() and not parent_queue.empty():
        break
      time.sleep(0.5)
    send_thread.join()

    external_objs = []
    while True:
      try:
        external_objs.append(ext_queue.get_nowait())
      except queue.Empty:
        break
    parent_objs = []
    while True:
      try:
        parent_objs.append(parent_queue.get_nowait())
      except queue.Empty:
        break

    assert external_objs, \
      f"No DATA_EXTERNAL objects received within {h.MAX_WAIT}s"
    assert parent_objs, \
      f"No parent DATA_REGULATED objects received within {h.MAX_WAIT}s"

    external_by_id = {o["id"]: o for o in external_objs}
    parent_by_id = {o["id"]: o for o in parent_objs}
    matched = set(external_by_id) & set(parent_by_id)

    assert matched, (
      "No object IDs matched between DATA_EXTERNAL and parent DATA_REGULATED, "
      f"external={set(external_by_id)}, parent={set(parent_by_id)}")

    for oid in matched:
      RetrackTest.assert_valid_translation(
        external_by_id[oid]["translation"], f"DATA_EXTERNAL obj {oid}")
      RetrackTest.assert_valid_translation(
        parent_by_id[oid]["translation"], f"parent DATA_REGULATED obj {oid}")

    log.info(
      f"PASS: {len(matched)} object(s) with finite translations matched "
      f"across DATA_EXTERNAL and parent DATA_REGULATED")
    exit_code = 0

  finally:
    if sub_client is not None:
      sub_client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


@pytest.mark.test_name("NEX-T21709")
def test_external_update_rate_limits_publish_frequency(
    objData, params):
  """! Verify that the external_update_rate scene setting limits the frequency
  at which DATA_EXTERNAL messages are published.  The child scene rate is set
  to 1 Hz, camera detections are sent at FRAME_RATE for measure_window seconds.
  At most target_rate * measure_window * 2 DATA_EXTERNAL messages (2x tolerance
  for timer jitter) must arrive, and at least 1 must arrive to confirm the path
  is active.

  @param    objData                 Pytest fixture: object payload template.
  @param    params                  Dict of functional-test parameters.
  """
  TEST_NAME = "NEX-T21709"
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1
  ext_client = None
  rest_client = None
  default_rate = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)

    scene_data = rest_client.getScene(h.child_id)
    assert scene_data.statusCode == 200, \
      f"getScene({h.child_id}) failed: {getattr(scene_data, 'errors', None)}"
    default_rate = scene_data.get('external_update_rate', 30)
    log.info(f"Original external_update_rate={default_rate}")

    target_rate = 1   # Hz - well below the default 30 Hz
    h.set_external_rate(rest_client, target_rate)

    ext_queue = queue.Queue()

    def _on_ext_msg(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
        if data.get("objects"):
          ext_queue.put((time.time(), data))
      except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    ext_topic = PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=h.child_id, thing_type="+")
    ext_client = h.make_client([ext_topic], _on_ext_msg)

    measure_window = 5   # seconds of continuous input

    send_thread = threading.Thread(
      target=h.publish_timed,
      args=(objData, ext_client, RetrackTest.FRAME_RATE, measure_window),
      daemon=True)
    send_thread.start()
    send_thread.join()

    # Allow a brief settling period for in-flight messages
    time.sleep(1.0)

    external_msgs = []
    while True:
      try:
        external_msgs.append(ext_queue.get_nowait())
      except queue.Empty:
        break
    count = len(external_msgs)
    max_expected = int(target_rate * measure_window * 2)
    log.info(
      f"DATA_EXTERNAL messages received: {count} "
      f"(target_rate={target_rate} Hz, window={measure_window}s, "
      f"max_expected={max_expected})")

    assert count >= 1, \
      "At least one DATA_EXTERNAL message must arrive to confirm the path is active"
    assert count <= max_expected, (
      f"Rate limiting failed: received {count} messages in {measure_window}s "
      f"at {target_rate} Hz limit (expected <= {max_expected})")

    log.info(
      f"PASS: external_update_rate={target_rate} Hz correctly "
      f"limited DATA_EXTERNAL to {count} messages over {measure_window}s")
    exit_code = 0

  finally:
    if ext_client is not None:
      ext_client.loopStop()
    if rest_client is not None:
      if h.child_id and default_rate is not None:
        try:
          h.set_external_rate(rest_client, default_rate)
          log.info(f"[TEARDOWN] Restored external_update_rate={default_rate}")
        except Exception as exc:
          log.warning(f"[TEARDOWN] Failed to restore external_update_rate: {exc}")
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
