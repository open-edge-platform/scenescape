#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests validating retrack behaviour when a child scene is linked
to a parent scene via the scene hierarchy.

Retrack semantics:
  - retrack=True  : objects from the child scene are fed into the parent's
                    tracker; the parent assigns new tracking IDs.
  - retrack=False : objects bypass the parent tracker and are merged as
                    already-tracked; original child IDs are preserved.
"""

import json
import threading
import time

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
import tests.common_test_utils as common
from scene_common.timestamp import get_iso_time

FRAME_RATE = 10
MAX_WAIT = 60
NUM_PUBLISH_ITERATIONS = 5

parent_id = None
child_id = None

parent_received = []
child_received = []
connected = False

def on_connect(mqttc, obj, flags, rc):
  """! Callback for MQTT client on connection.  Subscribes to regulated data
  topics for both the parent and child scenes.

  @param    mqttc   The MQTT client object.
  @param    obj     Private user data (unused).
  @param    flags   Response flags from broker.
  @param    rc      Connection result code.
  """
  global connected, parent_id, child_id
  if rc == 0:
    log.info("MQTT connected (rc=%d)" % rc)
    connected = True
    mqttc.subscribe(PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=parent_id))
    mqttc.subscribe(PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=child_id))
  else:
    log.error("MQTT connection failed (rc=%d)" % rc)
  return


def on_message(mqttc, obj, msg):
  """! Callback for incoming MQTT messages.  Appends decoded payloads to the
  appropriate receive buffer based on scene_id.

  @param    mqttc   The MQTT client object.
  @param    obj     Private user data (unused).
  @param    msg     The MQTTMessage instance.
  """
  global parent_received, child_received, parent_id, child_id

  topic = PubSub.parseTopic(msg.topic)
  if topic is None:
    return

  data = json.loads(msg.payload.decode("utf-8"))

  if topic.get('scene_id') == parent_id:
    obj_count = len(data.get('objects', []))
    if obj_count > 0:
      log.info(f"Parent regulated: {obj_count} objects")
      parent_received.append(data)

  elif topic.get('scene_id') == child_id:
    obj_count = len(data.get('objects', []))
    if obj_count > 0:
      log.info(f"Child regulated: {obj_count} objects")
      child_received.append(data)

  return


def _setup_scenes(rest_client):
  """! Create a fresh parent scene and link the existing Demo scene as child
  with retrack=True (default).

  @param    rest_client     An authenticated RESTClient instance.
  """
  global parent_id, child_id

  parent_scene = rest_client.createScene({'name': "retrack_parent"})
  assert parent_scene.statusCode == 201, \
    f"Failed to create parent scene: {parent_scene.statusCode}"
  parent_id = parent_scene['uid']
  log.info(f"Created parent scene: {parent_id}")

  scenes = rest_client.getScenes({'name': 'Demo'})
  assert scenes['count'] > 0, "Demo scene not found – required for retrack tests"
  child_scene = scenes['results'][0]
  child_id = child_scene['uid']
  log.info(f"Using Demo as child scene: {child_id}")

  res = rest_client.updateScene(child_id, {'parent': parent_id})
  assert res.statusCode == 200, \
    f"Failed to link child to parent: {res.statusCode}"

  child_links = rest_client.getChildScene({'parent': parent_id})
  assert child_links.statusCode == 200 and child_links['count'] == 1, \
    "Child-parent link not found after linking"
  return


def _set_retrack(rest_client, value, params):
  """! Update the retrack flag on the child scene link and wait for the
  CMD_DATABASE command to be published by the model, confirming the scene
  controller (cache manager) has been notified of the change.

  @param    rest_client     An authenticated RESTClient instance.
  @param    value           Boolean value for the retrack field.
  @param    params          Dict of connection parameters used to subscribe to
                            the CMD_DATABASE confirmation topic.
  """
  db_update_received = threading.Event()
  subscribed = threading.Event()
  db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)

  def _on_db_update(mqttc, obj, msg):
    log.info(f"CMD_DATABASE received on {msg.topic}")
    db_update_received.set()

  def _on_connected(mqttc, obj, flags, rc):
    if rc == 0:
      mqttc.addCallback(db_topic, _on_db_update)
      subscribed.set()

  tmp_client = PubSub(params["auth"], None, params["rootcert"],
                      params["broker_url"], params["broker_port"])
  tmp_client.onConnect = _on_connected
  tmp_client.connect()
  tmp_client.loopStart()

  log.info("Waiting for MQTT client to connect and subscribe to CMD_DATABASE topic...")
  assert subscribed.wait(MAX_WAIT), \
    "Temporary MQTT client failed to connect and subscribe within timeout"

  try:
    res = rest_client.updateChildScene(child_id, {'retrack': value})
    assert res.statusCode == 200, \
      f"Failed to set retrack={value}: {res.statusCode}"
    log.info(f"Set retrack={value} on child scene {child_id}")

    verify = rest_client.getChildScene({'parent': parent_id})
    assert verify.statusCode == 200, \
      f"Failed to read back child scene link after setting retrack={value}"
    actual = verify['results'][0]['retrack']
    log.info(f"Verify child link retrack value: {actual}")
    assert actual == value, \
      f"retrack mismatch: expected {value}, got {actual}"

    assert db_update_received.wait(MAX_WAIT), \
      f"Timed out waiting for CMD_DATABASE on {db_topic}"

  finally:
    tmp_client.loopStop()

  return

def _publish_data(obj_data, client, obj_category="person"):
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

def _wait_for_messages(timeout=MAX_WAIT, require_parent=True, require_child=True):
  """! Block until at least one message with objects has arrived on the
  expected topics, or timeout expires.

  @param    timeout         Maximum seconds to wait.
  @param    require_parent  Assert that parent received objects if True.
  @param    require_child   Assert that child received objects if True.
  """
  start = time.time()
  while time.time() - start < timeout:
    parent_ok = (not require_parent) or len(parent_received) > 0
    child_ok = (not require_child) or len(child_received) > 0
    if parent_ok and child_ok:
      return
    time.sleep(0.5)

  if require_parent:
    assert len(parent_received) > 0, \
      f"Timed out after {timeout}s: no objects on parent regulated topic"
  if require_child:
    assert len(child_received) > 0, \
      f"Timed out after {timeout}s: no objects on child regulated topic"
  return


def _collect_object_ids(messages):
  """! Return the set of object id values from a list of regulated messages.

  @param    messages  List of decoded regulated-data message dicts.
  @return             Set of id strings found in 'objects' lists.
  """
  ids = set()
  for msg in messages:
    for obj in msg.get('objects', []):
      if 'id' in obj:
        ids.add(obj['id'])
  return ids


def _make_client(params):
  """! Create and start an MQTT PubSub client with the module callbacks.

  @param    params  Dict of connection parameters from the conftest fixture.
  @return           Connected PubSub instance.
  """
  global connected
  connected = False
  client = PubSub(params["auth"], None, params["rootcert"],
                  params["broker_url"], params["broker_port"])
  client.onConnect = on_connect
  client.onMessage = on_message
  client.connect()
  client.loopStart()
  return client


def _wait_for_connect(timeout=MAX_WAIT):
  """! Poll until the MQTT client reports it is connected, or timeout.

  @param    timeout  Maximum seconds to wait.
  """
  start = time.time()
  while not connected and time.time() - start < timeout:
    time.sleep(0.5)
  assert connected, "MQTT client failed to connect within timeout"
  return

def _teardown_scenes(rest_client):
  """Remove created scenes and unlink child."""
  # Unlink child from parent
  if child_id and parent_id:
    res = rest_client.deleteChildSceneLink(child_id)
    log.info(f"[TEARDOWN] Unlinked child uid={child_id}: {res.statusCode}")

  # Delete parent scene (child Demo is not deleted – it is a fixture scene)
  if parent_id:
    res = rest_client.deleteScene(parent_id)
    log.info(f"[TEARDOWN] Deleted parent scene uid={parent_id}: {res.statusCode}")


def test_scene_retrack_enabled_objects_propagate_to_parent(
    objData, record_xml_attribute, params):
  """! Positive test: with retrack=True (default), objects from a child scene
  appear on the parent scene's regulated topic after the parent tracker has
  had enough frames to produce reliable tracks.

  @param    objData                 Pytest fixture: object payload template.
  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test parameters.
  """
  global parent_id, child_id
  global parent_received, child_received, connected

  TEST_NAME = "NEX-T10536"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    _setup_scenes(rest_client)

    _set_retrack(rest_client, True, params)

    client = _make_client(params)
    _wait_for_connect()

    parent_received.clear()
    child_received.clear()

    _publish_data(objData, client, obj_category="person")
    _wait_for_messages(require_parent=True, require_child=True)

    assert len(parent_received) > 0, \
      "Parent scene should receive objects when retrack=True"
    assert len(child_received) > 0, \
      "Child scene should publish regulated data"

    log.info("PASS: parent received %d messages with retrack=True" %
             len(parent_received))
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_scene_retrack_disabled_objects_propagate_to_parent(
    objData, record_xml_attribute, params):
  """! Positive test: with retrack=False, objects from the child scene still
  appear on the parent regulated topic.  They bypass the parent tracker and
  are merged as already-tracked objects.

  @param    objData                 Pytest fixture: object payload template.
  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test parameters.
  """
  global parent_id, child_id
  global parent_received, child_received, connected

  TEST_NAME = "NEX-T21491"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    _setup_scenes(rest_client)
    _set_retrack(rest_client, False, params)

    client = _make_client(params)
    _wait_for_connect()

    parent_received.clear()
    child_received.clear()

    _publish_data(objData, client, obj_category="person")
    _wait_for_messages(require_parent=True, require_child=True)

    assert len(parent_received) > 0, \
      "Parent scene should receive objects when retrack=False"
    assert len(child_received) > 0, \
      "Child scene should publish regulated data"

    log.info("PASS: parent received %d messages with retrack=False" %
             len(parent_received))
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_scene_retrack_disabled_preserves_child_object_ids(
    objData, record_xml_attribute, params):
  """! Positive test: with retrack=False, object IDs published on the parent's
  regulated topic match the IDs from the child scene.  This verifies that
  objects bypass the parent tracker and keep their original IDs.

  @param    objData                 Pytest fixture: object payload template.
  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test parameters.
  """
  global parent_id, child_id
  global parent_received, child_received, connected

  TEST_NAME = "NEX-T21492"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    _setup_scenes(rest_client)
    _set_retrack(rest_client, False, params)

    client = _make_client(params)
    _wait_for_connect()

    parent_received.clear()
    child_received.clear()

    _publish_data(objData, client, obj_category="person")
    _wait_for_messages(require_parent=True, require_child=True)

    parent_ids = _collect_object_ids(parent_received)
    child_ids = _collect_object_ids(child_received)

    log.info(f"Parent IDs: {parent_ids}")
    log.info(f"Child IDs:  {child_ids}")

    assert parent_ids, "No object IDs collected from parent"
    assert child_ids, "No object IDs collected from child"
    shared = parent_ids & child_ids
    assert shared, \
      ("retrack=False: expected parent IDs to overlap with child IDs; "
       f"parent={parent_ids}, child={child_ids}")

    log.info(f"PASS: shared IDs between child and parent: {shared}")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_scene_retrack_enabled_assigns_new_ids_to_child_objects(
    objData, record_xml_attribute, params):
  """! Positive test: with retrack=True, the parent tracker assigns its own
  tracking IDs to objects received from the child scene.  The IDs seen on
  the parent regulated topic must not match the child's IDs.

  @param    objData                 Pytest fixture: object payload template.
  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test parameters.
  """
  global parent_id, child_id
  global parent_received, child_received, connected

  TEST_NAME = "NEX-T21493"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    _setup_scenes(rest_client)
    _set_retrack(rest_client, True, params)

    client = _make_client(params)
    _wait_for_connect()

    parent_received.clear()
    child_received.clear()

    _publish_data(objData, client, obj_category="person")
    _wait_for_messages(require_parent=True, require_child=True)

    parent_ids = _collect_object_ids(parent_received)
    child_ids = _collect_object_ids(child_received)

    log.info(f"Parent IDs: {parent_ids}")
    log.info(f"Child IDs:  {child_ids}")

    assert parent_ids, "No object IDs collected from parent"
    assert child_ids, "No object IDs collected from child"
    shared = parent_ids & child_ids
    assert not shared, \
      ("retrack=True: expected parent IDs to be distinct from child IDs "
       f"(parent re-tracks); shared={shared}")

    log.info("PASS: parent IDs are distinct from child IDs with retrack=True")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_scene_retrack_toggle_changes_id_behaviour(
    objData, record_xml_attribute, params):
  """! Positive test: toggling retrack from False to True causes the parent
  to stop preserving child IDs and switch to assigning new tracking IDs.

  @param    objData                 Pytest fixture: object payload template.
  @param    record_xml_attribute    Pytest fixture for XML result tagging.
  @param    params                  Dict of functional-test parameters.
  """
  global parent_id, child_id
  global parent_received, child_received, connected

  TEST_NAME = "NEX-T21494"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    _setup_scenes(rest_client)
    _set_retrack(rest_client, False, params)

    client = _make_client(params)
    _wait_for_connect()

    # ---- Phase 1: retrack=False – IDs should be shared ----
    log.info("Phase 1: retrack=False")
    parent_received.clear()
    child_received.clear()

    _publish_data(objData, client, obj_category="person")
    _wait_for_messages(require_parent=True, require_child=True)

    phase1_parent_ids = _collect_object_ids(parent_received)
    phase1_child_ids = _collect_object_ids(child_received)
    shared_phase1 = phase1_parent_ids & phase1_child_ids
    assert shared_phase1, \
      ("Phase 1 (retrack=False): expected parent and child to share IDs; "
       f"parent={phase1_parent_ids}, child={phase1_child_ids}")
    log.info(f"Phase 1 shared IDs: {shared_phase1}")

    # ---- Phase 2: switch to retrack=True – IDs should diverge ----
    log.info("Phase 2: switching to retrack=True")
    _set_retrack(rest_client, True, params)
    parent_received.clear()
    child_received.clear()

    _publish_data(objData, client, obj_category="person")
    _wait_for_messages(require_parent=True, require_child=True)

    phase2_parent_ids = _collect_object_ids(parent_received)
    phase2_child_ids = _collect_object_ids(child_received)
    shared_phase2 = phase2_parent_ids & phase2_child_ids
    assert not shared_phase2, \
      ("Phase 2 (retrack=True): expected parent IDs to differ from child IDs; "
       f"shared={shared_phase2}")
    log.info("Phase 2: parent IDs differ from child IDs as expected")

    log.info("PASS: retrack toggle correctly changes ID assignment behaviour")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
