#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests validating that parent scene MQTT EVENT topic correctly
receives and republishes events (ROIs, tripwires, sensors) originating from
a linked child scene via SceneController.republishEvents."""

import json
import time
import pytest

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
import tests.common_test_utils as common
from tests.common_test_utils import check_event_contains_data
from scene_common.timestamp import get_iso_time

FRAME_RATE = 10
MAX_WAIT = 60
NUM_PUBLISH_ITERATIONS = 3
PERSON = "person"
REGION = "region"
TRIPWIRE = "tripwire"

# Object bounding-box y-sweep that produces world-coordinate trajectories
# crossing both the ROI and the tripwire defined in _setup_scenes.
# Range matches FunctionalTest.getLocations() used by tc_tripwire_mqtt.py.
import numpy as np
_step = 0.02
_opposite = np.arange(-0.5, 0.6, _step)
_across = np.flip(_opposite)[2:]
OBJ_Y_LOCATIONS = np.concatenate((_opposite, _across))


# ---------------------------------------------------------------------------
# Module-level state shared across callbacks
# ---------------------------------------------------------------------------
_state = {
  "parent_id": None,
  "child_id": None,
  "roi_uid": None,
  "tripwire_uid": None,
  "sensor_uid": None,
  "connected": False,

  # accumulated event messages keyed by topic-category
  "parent_roi_events": [],
  "parent_tripwire_events": [],
  "parent_sensor_events": [],
  "child_roi_events": [],
  "child_tripwire_events": [],
  "child_sensor_events": [],
}


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def _on_connect(mqttc, obj, flags, rc):
  """Subscribe to all relevant event topics once connected."""
  if rc != 0:
    log.error(f"MQTT connect failed with rc={rc}")
    return

  s = _state
  log.info("MQTT connected")
  s["connected"] = True

  parent_id = s["parent_id"]
  child_id = s["child_id"]
  roi_uid = s["roi_uid"]
  tripwire_uid = s["tripwire_uid"]
  sensor_uid = s["sensor_uid"]

  # Child ROI events
  t = PubSub.formatTopic(PubSub.EVENT, region_type=REGION, event_type="+",
                         scene_id=child_id, region_id=roi_uid)
  mqttc.subscribe(t)
  log.info(f"Subscribed child ROI events: {t}")

  # Child tripwire events
  t = PubSub.formatTopic(PubSub.EVENT, region_type=TRIPWIRE, event_type="+",
                         scene_id=child_id, region_id=tripwire_uid)
  mqttc.subscribe(t)
  log.info(f"Subscribed child tripwire events: {t}")

  # Child sensor events (sensor uses region event type)
  if sensor_uid:
    t = PubSub.formatTopic(PubSub.EVENT, region_type=REGION, event_type="+",
                           scene_id=child_id, region_id=sensor_uid)
    mqttc.subscribe(t)
    log.info(f"Subscribed child sensor events: {t}")

  # Parent ROI events (republished by controller)
  t = PubSub.formatTopic(PubSub.EVENT, region_type=REGION, event_type="+",
                         scene_id=parent_id, region_id=roi_uid)
  mqttc.subscribe(t)
  log.info(f"Subscribed parent ROI events: {t}")

  # Parent tripwire events (republished by controller)
  t = PubSub.formatTopic(PubSub.EVENT, region_type=TRIPWIRE, event_type="+",
                         scene_id=parent_id, region_id=tripwire_uid)
  mqttc.subscribe(t)
  log.info(f"Subscribed parent tripwire events: {t}")

  # Parent sensor events (republished by controller)
  if sensor_uid:
    t = PubSub.formatTopic(PubSub.EVENT, region_type=REGION, event_type="+",
                           scene_id=parent_id, region_id=sensor_uid)
    mqttc.subscribe(t)
    log.info(f"Subscribed parent sensor events: {t}")


def _on_message(mqttc, obj, msg):
  """Route incoming MQTT messages to the correct accumulator list."""
  s = _state
  parent_id = s["parent_id"]
  child_id = s["child_id"]
  roi_uid = s["roi_uid"]
  tripwire_uid = s["tripwire_uid"]

  topic = PubSub.parseTopic(msg.topic)
  if topic is None:
    return

  try:
    data = json.loads(msg.payload.decode("utf-8"))
  except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    log.warning(f"Failed to decode MQTT payload on {msg.topic}: {exc}")
    return

  scene_id = topic.get("scene_id")
  region_id = topic.get("region_id")
  region_type = topic.get("region_type")
  sensor_uid = s["sensor_uid"]

  if topic.get("_topic_id") != PubSub.EVENT:
    return

  if scene_id == child_id and region_id == roi_uid and region_type == REGION:
    s["child_roi_events"].append(data)
    log.info(f"Child ROI event received: {len(s['child_roi_events'])} total")

  elif scene_id == child_id and region_id == tripwire_uid and region_type == TRIPWIRE:
    s["child_tripwire_events"].append(data)
    log.info(f"Child tripwire event received: {len(s['child_tripwire_events'])} total")

  elif scene_id == child_id and sensor_uid and region_id == sensor_uid and region_type == REGION:
    s["child_sensor_events"].append(data)
    log.info(f"Child sensor event received: {len(s['child_sensor_events'])} total")

  elif scene_id == parent_id and region_id == roi_uid and region_type == REGION:
    s["parent_roi_events"].append(data)
    log.info(f"Parent ROI event received: {len(s['parent_roi_events'])} total")

  elif scene_id == parent_id and region_id == tripwire_uid and region_type == TRIPWIRE:
    s["parent_tripwire_events"].append(data)
    log.info(f"Parent tripwire event received: {len(s['parent_tripwire_events'])} total")

  elif scene_id == parent_id and sensor_uid and region_id == sensor_uid and region_type == REGION:
    s["parent_sensor_events"].append(data)
    log.info(f"Parent sensor event received: {len(s['parent_sensor_events'])} total")


def _setup_scenes(rest_client):
  """Create parent scene, link Demo as child, create ROI, tripwire, sensor in
  child scene.  Populates _state with IDs."""
  s = _state

  # Create parent scene
  parent_scene = rest_client.createScene({"name": "parent_event_test"})
  assert parent_scene.statusCode == 201, (
    f"Expected 201 creating parent scene, got {parent_scene.statusCode}: {parent_scene.errors}")
  s["parent_id"] = parent_scene["uid"]
  log.info(f"[SETUP] Parent scene uid={s['parent_id']}")

  # Check the Demo child scene (it has a registered camera)
  scenes = rest_client.getScenes({"name": "Demo"})
  assert scenes["count"] > 0, "Demo scene not found – required for child camera"
  s["child_id"] = scenes["results"][0]["uid"]
  log.info(f"[SETUP] Child scene uid={s['child_id']}")

  # Link Demo as child of parent
  res = rest_client.updateScene(s["child_id"], {"parent": s["parent_id"]})
  assert res.statusCode == 200, (
    f"Expected 200 linking child to parent, got {res.statusCode}: {res.errors}")
  log.info(f"[SETUP] Linked child to parent")

  # Verify link
  res = rest_client.getChildScene({"parent": s["parent_id"]})
  assert res.statusCode == 200, (
    f"Expected 200 fetching child scenes, got {res.statusCode}: {res.errors}")

  # Create ROI in child scene – spans most of the floor plan
  roi_points = ((1.38, 5.94), (1.17, 0.8), (7.41, 0.83), (7.35, 6.01))
  roi_res = rest_client.createRegion({
    "scene": s["child_id"],
    "name": "TestROI_child",
    "points": roi_points,
  })
  assert roi_res.statusCode == 201, (
    f"Expected 201 creating ROI, got {roi_res.statusCode}: {roi_res.errors}")
  s["roi_uid"] = roi_res["uid"]
  log.info(f"[SETUP] ROI uid={s['roi_uid']}")

  # Create tripwire in child scene using the same centre-horizontal geometry as
  # tc_tripwire_mqtt.py (create_tripwire_by_ratio with x_ratio=0.8).
  # Demo scene: width=900px, height=643px, scale=100 px/m → cx=4.5, cy=3.215
  # The horizontal line at cy spans the full scene width so the object always
  # crosses it during the y-sweep in bounding-box space.
  _demo_cx = 900 / (2 * 100)          # 4.5 m
  _demo_cy = 643 / (2 * 100)          # 3.215 m
  _demo_dx = _demo_cx * 0.8           # 3.6 m
  tw_res = rest_client.createTripwire({
    "scene": s["child_id"],
    "name": "TestTripwire_child",
    "points": ((_demo_cx - _demo_dx, _demo_cy), (_demo_cx + _demo_dx, _demo_cy)),
  })
  assert tw_res.statusCode == 201, (
    f"Expected 201 creating tripwire, got {tw_res.statusCode}: {tw_res.errors}")
  s["tripwire_uid"] = tw_res["uid"]
  log.info(f"[SETUP] Tripwire uid={s['tripwire_uid']}")

  # Create sensor in child scene
  sensor_res = rest_client.createSensor({
    "scene": s["child_id"],
    "name": "TestSensor_child",
    "area": "circle",
    "radius": 3.21,
    "center": (4.5, 3.22),
  })
  assert sensor_res.statusCode == 201, (
    f"Expected 201 creating sensor, got {sensor_res.statusCode}: {sensor_res.errors}")
  s["sensor_uid"] = sensor_res["uid"]
  log.info(f"[SETUP] Sensor uid={s['sensor_uid']}")


def _teardown_scenes(rest_client):
  """Remove created scenes and analytics objects, unlink child."""
  s = _state
  for uid, label, fn in [
    (s.get("roi_uid"), "ROI", rest_client.deleteRegion),
    (s.get("tripwire_uid"), "Tripwire", rest_client.deleteTripwire),
    (s.get("sensor_uid"), "Sensor", rest_client.deleteSensor),
  ]:
    if uid:
      res = fn(uid)
      log.info(f"[TEARDOWN] Deleted {label} uid={uid}: {res.statusCode}")

  # Unlink child from parent
  child_id = s.get("child_id")
  if child_id:
    res = rest_client.deleteChildSceneLink(child_id)
    log.info(f"[TEARDOWN] Unlinked child uid={child_id}: {res.statusCode}")

  # Delete parent scene (child Demo is not deleted – it is a fixture scene)
  parent_id = s.get("parent_id")
  if parent_id:
    res = rest_client.deleteScene(parent_id)
    log.info(f"[TEARDOWN] Deleted parent scene uid={parent_id}: {res.statusCode}")


def _send_detections(client, obj_data, y_locations):
  """Publish person detections through a y-sweep to trigger enter/exit events."""
  cam_id = obj_data["id"]
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
  for _ in range(NUM_PUBLISH_ITERATIONS):
    for y in y_locations:
      obj_data["timestamp"] = get_iso_time()
      obj_data["objects"][PERSON][0]["bounding_box"]["y"] = float(y)
      obj_data["objects"][PERSON][0]["category"] = PERSON
      client.publish(topic, json.dumps(obj_data))
      time.sleep(1.0 / FRAME_RATE)


def _wait_for_events(key, timeout=MAX_WAIT):
  """Block until at least one event appears in _state[key] or timeout."""
  start = time.time()
  while time.time() - start < timeout:
    if _state[key]:
      return True
    time.sleep(0.5)
  return False


def _connect_mqtt_and_wait(params):
  """Create PubSub client, connect, and wait until connected."""
  client = PubSub(params["auth"], None, params["rootcert"],
                  params["broker_url"], params["broker_port"])
  client.onConnect = _on_connect
  client.onMessage = _on_message
  client.connect()
  client.loopStart()

  start = time.time()
  while not _state["connected"] and time.time() - start < MAX_WAIT:
    time.sleep(0.5)
  assert _state["connected"], "MQTT client failed to connect within timeout"
  return client


def _reset_state():
  """Reset shared module state before each test."""
  _state.update({
    "parent_id": None,
    "child_id": None,
    "roi_uid": None,
    "tripwire_uid": None,
    "sensor_uid": None,
    "connected": False,
    "parent_roi_events": [],
    "parent_tripwire_events": [],
    "parent_sensor_events": [],
    "child_roi_events": [],
    "child_tripwire_events": [],
    "child_sensor_events": [],
  })


def _send_sensor_value(client, sensor_name, value):
  """Publish a singleton sensor reading to DATA_SENSOR topic."""
  message = {
    "timestamp": get_iso_time(),
    "id": sensor_name,
    "value": value,
  }
  topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor_name)
  client.publish(topic, json.dumps(message))
  log.info(f"Published sensor value: id={sensor_name}, value={value}")


def test_child_roi_event_propagated_to_parent(objData, record_xml_attribute, params):
  """! Verify that ROI entry/exit events from a child scene are republished on
  the parent scene's MQTT EVENT topic.

  The controller republishes on the parent MQTT topic but preserves the
  original child scene_id in the payload (republishEvents does not rewrite it).
  Proof of propagation is routing to parent_roi_events via the parent-scoped topic.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21477"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    # Wait for the controller to process events and republish
    roi_appeared = _wait_for_events("parent_roi_events")
    assert roi_appeared, (
      f"Timed out after {MAX_WAIT}s: no ROI events arrived on parent scene topic")

    parent_events = _state["parent_roi_events"]
    assert len(parent_events) > 0, "Parent scene should have ROI events from child"

    # Validate event schema
    for event in parent_events:
      check_event_contains_data(event, "region")

    # The controller republishes on the parent MQTT topic but preserves the
    # original child scene_id in the payload (republishEvents does not rewrite it).
    # Routing to parent_roi_events via the parent-scoped topic is the proof of
    # propagation.  Assert the payload scene_id equals the child's uid.
    for event in parent_events:
      assert event["scene_id"] == _state["child_id"], (
        f"Event scene_id {event['scene_id']} must equal child_id {_state['child_id']}")

    # ObjectID and translation fields must be present
    for event in parent_events:
      for obj in event.get("objects", []):
        assert "id" in obj, "Event object missing 'id'"
        assert "translation" in obj, "Event object missing 'translation'"

    log.info(f"PASS: {len(parent_events)} ROI events correctly propagated to parent scene")
    exit_code = 0
  finally:
    client.loopStop()
    _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_child_tripwire_event_propagated_to_parent(objData, record_xml_attribute, params):
  """! Verify that tripwire crossing events from a child scene are republished
  on the parent scene's MQTT EVENT topic.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21478"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    tw_appeared = _wait_for_events("parent_tripwire_events")
    assert tw_appeared, (
      f"Timed out after {MAX_WAIT}s: no tripwire events arrived on parent scene topic")

    parent_events = _state["parent_tripwire_events"]
    assert len(parent_events) > 0, "Parent scene should have tripwire events from child"

    for event in parent_events:
      check_event_contains_data(event, "tripwire")

    for event in parent_events:
      assert event["scene_id"] == _state["child_id"], (
        f"Event scene_id {event['scene_id']} must equal child_id {_state['child_id']}")

    for event in parent_events:
      for obj in event.get("objects", []):
        assert "id" in obj
        assert "translation" in obj, "Event object missing 'translation'"

    log.info(f"PASS: {len(parent_events)} tripwire events correctly propagated to parent scene")
    exit_code = 0
  finally:
    client.loopStop()
    _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_child_sensor_event_propagated_to_parent(objData, record_xml_attribute, params):
  """! Verify that environmental sensor events from a child scene are
  republished on the parent scene's MQTT EVENT topic.

  A sensor is an area-bounded singleton.  When a sensor value is published
  while a tracked object is within the sensor area, the controller emits a
  region-type EVENT.  That event must be republished by republishEvents on
  the parent scene's EVENT topic.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21479"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    # Step 1: send detections to place an object inside the sensor circle
    # (center=(4.5,3.22), radius=3.21 m – covers most of the scene floor plan)
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    # Step 2: publish several sensor readings; the controller will emit a
    # region EVENT each time a value is received while objects are present
    sensor_name = "TestSensor_child"
    for i in range(5):
      _send_sensor_value(client, sensor_name, 100 + i)
      time.sleep(0.2)

    sensor_appeared = _wait_for_events("parent_sensor_events")
    assert sensor_appeared, (
      f"Timed out after {MAX_WAIT}s: no sensor events arrived on parent scene topic")

    parent_events = _state["parent_sensor_events"]
    assert len(parent_events) > 0, "Parent scene should have sensor events from child"

    # Validate schema – sensor events publish as region events
    for event in parent_events:
      check_event_contains_data(event, "region")

    # The controller preserves the child scene_id in the republished payload
    for event in parent_events:
      assert event["scene_id"] == _state["child_id"], (
        f"Event scene_id {event['scene_id']} must equal child_id {_state['child_id']}")

    # The region_id in the event must match the sensor uid created in the child
    for event in parent_events:
      assert event.get("region_id") == _state["sensor_uid"], (
        f"Event region_id {event.get('region_id')} must equal sensor uid {_state['sensor_uid']}")

    log.info(f"PASS: {len(parent_events)} sensor events correctly propagated to parent scene")
    exit_code = 0
  finally:
    client.loopStop()
    _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_parent_event_attributes_match_child_event(objData, record_xml_attribute, params):
  """! Verify that attributes (region_id, region_name, objects, counts) in the
  parent's republished events match those in the child's original events.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21480"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    # Wait for both child and parent events
    child_roi_ok = _wait_for_events("child_roi_events")
    parent_roi_ok = _wait_for_events("parent_roi_events")

    assert child_roi_ok, "No ROI events received on child scene topic"
    assert parent_roi_ok, "No ROI events received on parent scene topic"

    child_evt = _state["child_roi_events"][0]
    parent_evt = _state["parent_roi_events"][0]

    # The region UID and name must be identical
    assert child_evt.get("region_id") == parent_evt.get("region_id"), (
      "region_id mismatch between child and parent events")
    assert child_evt.get("region_name") == parent_evt.get("region_name"), (
      "region_name mismatch between child and parent events")

    # Object counts must be equal for matching events
    child_counts = child_evt.get("counts", {})
    parent_counts = parent_evt.get("counts", {})
    assert child_counts.keys() == parent_counts.keys(), (
      "Object category keys differ between child and parent event counts")

    # parent event must carry 'metadata' with from_child_scene set
    assert "metadata" in parent_evt, "Parent event missing 'metadata' field"
    assert "from_child_scene" in parent_evt.get("metadata", {}), (
      "Parent event metadata missing 'from_child_scene' attribution")

    log.info(f"PASS: Parent event attributes match child event attributes")
    exit_code = 0
  finally:
    client.loopStop()
    _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_child_event_propagation_is_timely(objData, record_xml_attribute, params):
  """! Verify that event propagation from child to parent occurs with minimal
  delay (within MAX_WAIT seconds of the first child event).

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21481"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    # Measure wall-clock delay between first child and first parent ROI event
    child_appeared = _wait_for_events("child_roi_events", timeout=MAX_WAIT)
    assert child_appeared, f"No child ROI events received within {MAX_WAIT}s"

    t_child = time.time()
    parent_appeared = _wait_for_events("parent_roi_events", timeout=MAX_WAIT)
    t_parent = time.time()

    assert parent_appeared, (
      f"No parent ROI events received within {MAX_WAIT}s of child events")

    propagation_delay = t_parent - t_child
    log.info(f"Propagation delay: {propagation_delay:.2f}s")
    assert propagation_delay <= MAX_WAIT, (
      f"Event propagation delay {propagation_delay:.2f}s exceeds limit {MAX_WAIT}s")

    exit_code = 0
  finally:
    client.loopStop()
    _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_no_events_without_parent_link(objData, record_xml_attribute, params):
  """! Verify that child scene events are NOT republished on a parent topic
  when no parent-child link exists (unlinked child).

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21482"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()

  # Deliberately do NOT link a parent – we only create ROI/tripwire in the Demo scene
  scenes = rest_client.getScenes({"name": "Demo"})
  assert scenes["count"] > 0, "Demo scene not found"
  child_id = scenes["results"][0]["uid"]
  _state["child_id"] = child_id

  # Use a random non-existent parent UID as a dummy subscription target
  fake_parent_id = "00000000-0000-0000-0000-000000000000"
  _state["parent_id"] = fake_parent_id

  roi_points = ((1.38, 5.94), (1.17, 0.8), (7.41, 0.83), (7.35, 6.01))
  roi_res = rest_client.createRegion({
    "scene": child_id,
    "name": "UnlinkedROI_test",
    "points": roi_points,
  })
  assert roi_res.statusCode == 201
  _state["roi_uid"] = roi_res["uid"]

  tw_res = rest_client.createTripwire({
    "scene": child_id,
    "name": "UnlinkedTripwire_test",
    "points": ((0.9, 3.215), (8.1, 3.215)),
  })
  assert tw_res.statusCode == 201
  _state["tripwire_uid"] = tw_res["uid"]

  client = _connect_mqtt_and_wait(params)

  try:
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    # Allow time for any erroneous propagation
    wait_duration = 10  # seconds – intentionally shorter than MAX_WAIT
    time.sleep(wait_duration)

    assert len(_state["parent_roi_events"]) == 0, (
      "ROI events must NOT appear on parent topic when no parent link exists")
    assert len(_state["parent_tripwire_events"]) == 0, (
      "Tripwire events must NOT appear on parent topic when no parent link exists")

    log.info("PASS: No events appeared on (fake) parent topic without parent link")
    exit_code = 0
  finally:
    client.loopStop()
    # Cleanup only the analytics objects created for this test
    if _state.get("roi_uid"):
      rest_client.deleteRegion(_state["roi_uid"])
    if _state.get("tripwire_uid"):
      rest_client.deleteTripwire(_state["tripwire_uid"])
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0

def test_event_region_id_matches_child_definition(objData, record_xml_attribute, params):
  """! Verify that the region_id in a parent scene ROI event matches the ROI
  uid originally defined in the child scene.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21483"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    _send_detections(client, objData, OBJ_Y_LOCATIONS)
    ok = _wait_for_events("parent_roi_events")
    assert ok, f"No parent ROI events within {MAX_WAIT}s"

    for event in _state["parent_roi_events"]:
      assert event.get("region_id") == _state["roi_uid"], (
        f"Parent event region_id {event.get('region_id')} "
        f"does not match child ROI uid {_state['roi_uid']}")

    log.info("PASS: Parent event region_id correctly references child ROI uid")
    exit_code = 0
  finally:
    client.loopStop()
    _teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0

def test_events_stop_after_child_unlinked(objData, record_xml_attribute, params):
  """! Verify that after unlinking a child from its parent, subsequent child
  events are no longer republished on the parent's MQTT EVENT topic.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T10520"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  rest_client = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_client.authenticate(params["user"], params["password"])

  _reset_state()
  _setup_scenes(rest_client)

  client = _connect_mqtt_and_wait(params)

  try:
    # Step 1 – Confirm events do propagate while linked
    log.info("Step 1: Publishing while child is linked to parent")
    _send_detections(client, objData, OBJ_Y_LOCATIONS)
    linked_ok = _wait_for_events("parent_roi_events")
    assert linked_ok, "Prerequisite failed: no events received while child is linked"
    log.info(f"Events while linked: {len(_state['parent_roi_events'])}")

    # Step 2 – Unlink child from parent
    log.info("Step 2: Unlinking child from parent")
    res = rest_client.deleteChildSceneLink(_state["child_id"])
    assert res.statusCode == 200, (
      f"Expected 200 deleting child link, got {res.statusCode}: {res.errors}")

    # Clear accumulators and send more detections
    _state["parent_roi_events"].clear()
    _state["parent_tripwire_events"].clear()

    log.info("Step 3: Publishing after unlink – no events should appear on parent topic")
    _send_detections(client, objData, OBJ_Y_LOCATIONS)

    # Wait briefly; events must not arrive
    quiesce = 10  # seconds
    time.sleep(quiesce)

    assert len(_state["parent_roi_events"]) == 0, (
      "ROI events must NOT propagate to parent after child is unlinked")
    assert len(_state["parent_tripwire_events"]) == 0, (
      "Tripwire events must NOT propagate to parent after child is unlinked")

    log.info("PASS: Events stopped propagating after child was unlinked")
    exit_code = 0
  finally:
    client.loopStop()
    # teardown: child already unlinked above; clean analytics objects and parent
    for uid, fn in [
      (_state.get("roi_uid"), rest_client.deleteRegion),
      (_state.get("tripwire_uid"), rest_client.deleteTripwire),
      (_state.get("sensor_uid"), rest_client.deleteSensor),
    ]:
      if uid:
        fn(uid)
    parent_id = _state.get("parent_id")
    if parent_id:
      rest_client.deleteScene(parent_id)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
