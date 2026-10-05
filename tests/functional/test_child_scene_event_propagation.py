#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests validating that parent scene MQTT EVENT topic correctly
receives and republishes events (ROIs, tripwires, sensors) originating from
a linked child scene via Analytics event republish to the parent."""

import json
import threading
import time

import pytest

from tests.functional.event_asserts import (
  assert_event_objects_have_visibility,
  check_event_contains_data,
)
from tests.functional.common_child import (
  ChildSceneTest,
  EVENT_WAIT,
  NEGATIVE_OBSERVE,
  PROPAGATION_LIMIT,
)
from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)


@pytest.mark.test_name("NEX-T21477")
def test_child_roi_event_propagated_to_parent(objData, params, result_recorder):
  """! Verify that ROI entry/exit events from a child scene are republished on
  the parent scene's MQTT EVENT topic.

  Analytics republishes ROI region-entry/exit EVENT messages
  generated in a linked child scene onto the parent scene's MQTT EVENT topic,
  preserving the original child scene_id and event schema.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    roi_appeared = helper.wait_for_events("parent_roi_events")
    assert roi_appeared, (
      f"Timed out after {EVENT_WAIT}s: no ROI events arrived on parent scene topic")

    parent_events = helper.parent_roi_events
    assert len(parent_events) > 0, "Parent scene should have ROI events from child"

    # Validate event schema
    for event in parent_events:
      check_event_contains_data(event, "region")
      assert_event_objects_have_visibility(event)

    # Analytics republishes on the parent MQTT topic but preserves the
    # original child scene_id in the payload. Routing to parent_roi_events
    # via the parent-scoped topic is the proof of propagation.
    for event in parent_events:
      assert event["scene_id"] == helper.child_id, (
        f"Event scene_id {event['scene_id']} must equal child_id {helper.child_id}")

    # ObjectID and translation fields must be present
    for event in parent_events:
      for obj in event.get("objects", []):
        assert "id" in obj, "Event object missing 'id'"
        assert "translation" in obj, "Event object missing 'translation'"

    log.info(f"PASS: {len(parent_events)} ROI events correctly propagated to parent scene")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T21478")
def test_child_tripwire_event_propagated_to_parent(objData, params, result_recorder):
  """! Verify that tripwire crossing events from a child scene are republished
  on the parent scene's MQTT EVENT topic.

  Analytics republishes tripwire-crossing EVENT messages
  generated in a linked child scene onto the parent scene's MQTT EVENT topic,
  preserving the original child scene_id and event schema.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    # Tripwire crossings need the y-sweep to reach the centre line and enough
    # frames for the analytics reliability gate — wait for child first, then
    # confirm parent republish.
    child_tw = helper.wait_for_events("child_tripwire_events")
    assert child_tw, (
      f"Timed out after {EVENT_WAIT}s: no tripwire events on child scene topic")

    tw_appeared = helper.wait_for_events(
      "parent_tripwire_events", timeout=PROPAGATION_LIMIT)
    assert tw_appeared, (
      f"Timed out after {PROPAGATION_LIMIT}s: no tripwire events arrived on "
      "parent scene topic after child events")

    parent_events = helper.parent_tripwire_events
    assert len(parent_events) > 0, "Parent scene should have tripwire events from child"

    for event in parent_events:
      check_event_contains_data(event, "tripwire")
      assert_event_objects_have_visibility(event)

    for event in parent_events:
      assert event["scene_id"] == helper.child_id, (
        f"Event scene_id {event['scene_id']} must equal child_id {helper.child_id}")

    for event in parent_events:
      for obj in event.get("objects", []):
        assert "id" in obj, "Event object missing 'id'"
        assert "translation" in obj, "Event object missing 'translation'"

    log.info(f"PASS: {len(parent_events)} tripwire events correctly propagated to parent scene")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T21479")
def test_child_sensor_event_propagated_to_parent(objData, params, result_recorder):
  """! Verify that environmental sensor events from a child scene are
  republished on the parent scene's MQTT EVENT topic.

  A sensor is an area-bounded singleton.  When a sensor value is published
  while a tracked object is within the sensor area, Analytics emits a
  region-type EVENT.  That event must be republished on the parent scene's
  EVENT topic.

  Analytics republishes region-type EVENT messages triggered by
  an environmental singleton sensor in a linked child scene onto the parent
  scene's MQTT EVENT topic, with region_id matching the child sensor uid.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    # Wait until Analytics has processed the child scene (ROI event) before
    # publishing sensor readings.
    obj_tracked = helper.wait_for_events("child_roi_events")
    assert obj_tracked, (
      f"Object not tracked within {EVENT_WAIT}s – cannot trigger sensor events")

    # Publish several sensor readings; Analytics emits a region EVENT each time
    # a value is received while objects are present in the sensor area.
    sensor_name = "TestSensor_child"
    for i in range(5):
      helper.send_sensor_value(client, sensor_name, 100 + i)
      time.sleep(0.2)

    sensor_appeared = helper.wait_for_events("parent_sensor_events")
    assert sensor_appeared, (
      f"Timed out after {EVENT_WAIT}s: no sensor events arrived on parent scene topic")

    parent_events = helper.parent_sensor_events
    assert len(parent_events) > 0, "Parent scene should have sensor events from child"

    # Validate schema – sensor events publish as region events
    for event in parent_events:
      check_event_contains_data(event, "region")

    # Republish preserves the child scene_id in the payload
    for event in parent_events:
      assert event["scene_id"] == helper.child_id, (
        f"Event scene_id {event['scene_id']} must equal child_id {helper.child_id}")

    # The region_id in the event must match the sensor uid created in the child
    for event in parent_events:
      assert event.get("region_id") == helper.sensor_uid, (
        f"Event region_id {event.get('region_id')} must equal sensor uid {helper.sensor_uid}")

    log.info(f"PASS: {len(parent_events)} sensor events correctly propagated to parent scene")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T29236")
def test_child_attribute_sensor_event_propagated_to_parent(objData, params, result_recorder):
  """! Verify attribute singleton events from a child scene reach the parent.

  Distinct from the environmental sensor case and from
  test_sensors_send_mqtt_messages (which does not cover parent republish).

  Analytics republishes region-type EVENT messages triggered by
  an attribute singleton sensor (e.g. badge reader) in a linked child scene
  onto the parent scene's MQTT EVENT topic, with region_id matching the
  child attribute-sensor uid.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    helper.create_attribute_sensor(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    obj_tracked = helper.wait_for_events("child_roi_events")
    assert obj_tracked, (
      f"Object not tracked within {EVENT_WAIT}s – cannot trigger attribute events")

    for i in range(5):
      helper.send_sensor_value(client, "TestAttrSensor_child", f"badge-{i}")
      time.sleep(0.2)

    sensor_appeared = helper.wait_for_events("parent_attribute_sensor_events")
    assert sensor_appeared, (
      f"Timed out after {EVENT_WAIT}s: no attribute sensor events on parent topic")

    for event in helper.parent_attribute_sensor_events:
      check_event_contains_data(event, "region")
      assert event["scene_id"] == helper.child_id
      assert event.get("region_id") == helper.attribute_sensor_uid

    log.info(f"PASS: {len(helper.parent_attribute_sensor_events)} attribute "
             "sensor events propagated to parent")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T21480")
def test_parent_event_attributes_match_child_event(objData, params, result_recorder):
  """! Verify that region_id, region_name, count category keys and values, and
  the from_child_scene metadata attribution in the parent's republished event
  match those in the child's original event.

  When Analytics republishes a child scene's ROI EVENT on the
  parent scene's EVENT topic, the region_id, region_name, object counts, and
  a from_child_scene metadata attribution must all match the child's
  original event.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    # Wait for both child and parent events.
    child_roi_ok = helper.wait_for_events("child_roi_events")
    parent_roi_ok = helper.wait_for_events("parent_roi_events")

    assert child_roi_ok, "No ROI events received on child scene topic"
    assert parent_roi_ok, "No ROI events received on parent scene topic"

    child_evt = helper.child_roi_events[0]
    parent_evt = helper.parent_roi_events[0]
    assert_event_objects_have_visibility(child_evt)
    assert_event_objects_have_visibility(parent_evt)

    # The region UID and name must be identical
    assert child_evt.get("region_id") == parent_evt.get("region_id"), (
      "region_id mismatch between child and parent events")
    assert child_evt.get("region_name") == parent_evt.get("region_name"), (
      "region_name mismatch between child and parent events")

    # Object counts must match in both keys and values
    child_counts = child_evt.get("counts", {})
    parent_counts = parent_evt.get("counts", {})
    assert child_counts == parent_counts, (
      f"Count mismatch between child and parent events: {child_counts} vs {parent_counts}")

    # Parent event must carry 'metadata' with from_child_scene set
    assert "metadata" in parent_evt, "Parent event missing 'metadata' field"
    assert "from_child_scene" in parent_evt.get("metadata", {}), (
      "Parent event metadata missing 'from_child_scene' attribution")

    log.info("PASS: Parent event attributes match child event attributes")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T21481")
def test_child_event_propagation_is_timely(objData, params, result_recorder):
  """! Verify that event propagation from child to parent occurs with minimal
  delay (within PROPAGATION_LIMIT seconds of the first child event).

  The delay between a ROI event first appearing on the child
  scene's EVENT topic and its republished counterpart appearing on the
  parent scene's EVENT topic must not exceed PROPAGATION_LIMIT seconds.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    child_appeared = helper.wait_for_events("child_roi_events")
    assert child_appeared, f"No child ROI events received within {EVENT_WAIT}s"

    parent_appeared = helper.wait_for_events(
      "parent_roi_events", timeout=PROPAGATION_LIMIT)
    assert parent_appeared, (
      f"No parent ROI events received within {PROPAGATION_LIMIT}s of child events")

    propagation_delay = (helper.first_received_at("parent_roi_events")
                         - helper.first_received_at("child_roi_events"))
    log.info(f"Propagation delay: {propagation_delay:.2f}s")
    assert propagation_delay <= PROPAGATION_LIMIT, (
      f"Event propagation delay {propagation_delay:.2f}s exceeds "
      f"limit {PROPAGATION_LIMIT}s")

    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T21482")
def test_no_events_without_parent_link(objData, params, result_recorder):
  """! Verify that child scene events are NOT republished on a parent topic
  when no parent-child link exists (unlinked child).

  If a child scene is never linked to a parent scene, ROI and
  tripwire events generated in that scene must not appear on any parent
  scene's MQTT EVENT topic.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client, link=False)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    time.sleep(NEGATIVE_OBSERVE)

    assert len(helper.parent_roi_events) == 0, (
      "ROI events must NOT appear on parent topic when no parent link exists")
    assert len(helper.parent_tripwire_events) == 0, (
      "Tripwire events must NOT appear on parent topic when no parent link exists")

    log.info("PASS: No events appeared on unlinked parent topic without parent link")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T21483")
def test_event_region_id_matches_child_definition(objData, params, result_recorder):
  """! Verify that the region_id in a parent scene ROI event matches the ROI
  uid originally defined in the child scene.

  The region_id field of a ROI event republished on the parent
  scene's EVENT topic must equal the uid of the ROI as originally created
  in the linked child scene.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    ok = helper.wait_for_events("parent_roi_events")
    assert ok, f"No parent ROI events within {EVENT_WAIT}s"

    for event in helper.parent_roi_events:
      assert event.get("region_id") == helper.roi_uid, (
        f"Parent event region_id {event.get('region_id')} "
        f"does not match child ROI uid {helper.roi_uid}")

    log.info("PASS: Parent event region_id correctly references child ROI uid")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T29237")
def test_events_stop_after_child_unlinked(objData, params, result_recorder):
  """! Verify that after unlinking a child from its parent, subsequent child
  events are no longer republished on the parent's MQTT EVENT topic.

  Once a child scene is unlinked from its parent (via
  deleteChildSceneLink), ROI/tripwire EVENT messages generated afterwards in
  the child scene must no longer be republished on the parent scene's EVENT
  topic, even though they continued to propagate before the unlink.

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    helper.wait_for_analytics_geometry(client, rest_client)

    # Phase-1: confirm events propagate while linked
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    log.info("Step 1: Publishing while child is linked to parent")
    linked_ok = helper.wait_for_events("parent_roi_events")
    assert linked_ok, "Prerequisite failed: no events received while child is linked"
    log.info(f"Events while linked: {len(helper.parent_roi_events)}")
    stop_event.set()
    send_thread.join()

    # Step 2 – Unlink child from parent
    log.info("Step 2: Unlinking child from parent")
    helper.unlink_child(rest_client)

    time.sleep(NEGATIVE_OBSERVE)

    # Clear accumulators then resume sending detections, events must not arrive
    # on the parent topic.
    helper.parent_roi_events.clear()
    helper.parent_tripwire_events.clear()

    log.info("Step 3: Publishing after unlink – no events should appear on parent topic")
    stop_event = threading.Event()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    time.sleep(NEGATIVE_OBSERVE)

    assert len(helper.parent_roi_events) == 0, (
      "ROI events must NOT propagate to parent after child is unlinked")
    assert len(helper.parent_tripwire_events) == 0, (
      "Tripwire events must NOT propagate to parent after child is unlinked")

    log.info("PASS: Events stopped propagating after child was unlinked")
    result_recorder.success()
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return


@pytest.mark.test_name("NEX-T10520")
def test_regulated_data_stops_after_child_unlinked(objData, params, result_recorder):
  """! Verify that after unlinking a child from its parent, raw DATA_REGULATED
  object data from the child scene is no longer forwarded to the parent
  scene's DATA_REGULATED topic (while the child continues to receive its own
  data).

  Complements test_events_stop_after_child_unlinked, which covers the
  Analytics EVENT topic (ROI/tripwire); this test covers the lower-level
  raw regulated-data forwarding path, using the same unlink mechanism
  (ChildSceneTest.unlink_child / deleteChildSceneLink).

  @param    objData          Pytest fixture with detection data.
  @param    params           Dict of test parameters.
  @param    result_recorder  Pytest fixture recording the Zephyr test result.
  """
  FRAME_RATE = 10
  MAX_WAIT = 10
  NUM_PUBLISH_ITERATIONS = 3

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  connected = False
  parent_received = []
  child_received = []

  def on_connect(mqttc, obj, flags, rc):
    nonlocal connected
    log.info("Connected!")
    connected = True
    mqttc.subscribe(PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=helper.parent_id))
    mqttc.subscribe(PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=helper.child_id))

  def on_message(mqttc, obj, msg):
    topic = PubSub.parseTopic(msg.topic)
    data = json.loads(msg.payload.decode("utf-8"))
    if topic['scene_id'] == helper.parent_id:
      parent_received.append(data)
      log.info(f"Parent received data: {len(data.get('objects', []))} objects")
    elif topic['scene_id'] == helper.child_id:
      child_received.append(data)
      log.info(f"Child received data: {len(data.get('objects', []))} objects")

  def publish_data(obj_data, obj_category="person"):
    cam_id = obj_data["id"]
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
    for iteration in range(NUM_PUBLISH_ITERATIONS):
      for i in range(5):
        obj_data["timestamp"] = get_iso_time()
        obj_data["objects"][obj_category][0]["bounding_box"]["y"] = 100 + (i * 20)
        obj_data["objects"][obj_category][0]["category"] = obj_category
        client.publish(topic, json.dumps(obj_data))
        log.info(
          f"Published object via camera {cam_id}: y={100 + (i * 20)} (iter {iteration})")
        time.sleep(1.0 / FRAME_RATE)

  def wait_for_messages(timeout=MAX_WAIT):
    start = time.time()
    while time.time() - start < timeout:
      if parent_received or child_received:
        return
      time.sleep(0.5)
    assert parent_received or child_received, (
      f"Timed out after {timeout} seconds waiting for MQTT messages "
      "on parent/child scenes")

  try:
    helper.setup_scenes(rest_client)

    client = PubSub(params["auth"], None, params["rootcert"],
                    params["broker_url"], int(params["broker_port"]))
    client.onConnect = on_connect
    client.onMessage = on_message
    client.connect()
    client.loopStart()

    start = time.time()
    while not connected and time.time() - start < MAX_WAIT:
      time.sleep(0.5)
    assert connected, "MQTT client failed to connect within timeout"

    log.info("Step 1: Publishing data to child scene while linked to parent")
    publish_data(objData, obj_category="person")
    wait_for_messages()

    assert len(child_received) > 0, "Child scene should have received regulated data"
    assert len(parent_received) > 0, "Parent scene should have received regulated data"
    log.info(f"Child received {len(child_received)} messages")
    log.info(f"Parent received {len(parent_received)} messages")
    log.info("PASS: Parent scene received data from linked child scene")

    log.info("Step 2: Unlinking child scene from parent scene")
    helper.unlink_child(rest_client)

    log.info("Step 3: Publishing data to child scene after unlinking")
    parent_received.clear()
    child_received.clear()
    publish_data(objData, obj_category="person")
    wait_for_messages(timeout=5)

    assert len(child_received) > 0, "Child scene should still receive its own data"
    assert len(parent_received) == 0, (
      "Parent scene should not receive data from unlinked child scene")
    log.info("PASS: Parent scene did not receive data after child was unlinked")

    result_recorder.success()
  finally:
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
  return
