#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests validating that parent scene MQTT EVENT topic correctly
receives and republishes events (ROIs, tripwires, sensors) originating from
a linked child scene via SceneController.republishEvents."""

import threading
import time

import tests.common_test_utils as common
from tests.common_test_utils import check_event_contains_data
from tests.functional.common_child import ChildSceneTest, MAX_WAIT
from scene_common import log


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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    roi_appeared = helper.wait_for_events("parent_roi_events")
    assert roi_appeared, (
      f"Timed out after {MAX_WAIT}s: no ROI events arrived on parent scene topic")

    parent_events = helper.parent_roi_events
    assert len(parent_events) > 0, "Parent scene should have ROI events from child"

    # Validate event schema
    for event in parent_events:
      check_event_contains_data(event, "region")

    # The controller republishes on the parent MQTT topic but preserves the
    # original child scene_id in the payload (republishEvents does not rewrite
    # it).  Routing to parent_roi_events via the parent-scoped topic is the
    # proof of propagation.  Assert the payload scene_id equals the child uid.
    for event in parent_events:
      assert event["scene_id"] == helper.child_id, (
        f"Event scene_id {event['scene_id']} must equal child_id {helper.child_id}")

    # ObjectID and translation fields must be present
    for event in parent_events:
      for obj in event.get("objects", []):
        assert "id" in obj, "Event object missing 'id'"
        assert "translation" in obj, "Event object missing 'translation'"

    log.info(f"PASS: {len(parent_events)} ROI events correctly propagated to parent scene")
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    tw_appeared = helper.wait_for_events("parent_tripwire_events")
    assert tw_appeared, (
      f"Timed out after {MAX_WAIT}s: no tripwire events arrived on parent scene topic")

    parent_events = helper.parent_tripwire_events
    assert len(parent_events) > 0, "Parent scene should have tripwire events from child"

    for event in parent_events:
      check_event_contains_data(event, "tripwire")

    for event in parent_events:
      assert event["scene_id"] == helper.child_id, (
        f"Event scene_id {event['scene_id']} must equal child_id {helper.child_id}")

    for event in parent_events:
      for obj in event.get("objects", []):
        assert "id" in obj, "Event object missing 'id'"
        assert "translation" in obj, "Event object missing 'translation'"

    log.info(f"PASS: {len(parent_events)} tripwire events correctly propagated to parent scene")
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    # Wait until an object is being tracked (child ROI event confirms controller
    # has processed at least one frame) before publishing sensor readings.
    obj_tracked = helper.wait_for_events("child_roi_events")
    assert obj_tracked, f"Object not tracked within {MAX_WAIT}s – cannot trigger sensor events"

    # Publish several sensor readings, the controller emits a region EVENT each
    # time a value is received while objects are present.
    sensor_name = "TestSensor_child"
    for i in range(5):
      helper.send_sensor_value(client, sensor_name, 100 + i)
      time.sleep(0.2)

    sensor_appeared = helper.wait_for_events("parent_sensor_events")
    assert sensor_appeared, (
      f"Timed out after {MAX_WAIT}s: no sensor events arrived on parent scene topic")

    parent_events = helper.parent_sensor_events
    assert len(parent_events) > 0, "Parent scene should have sensor events from child"

    # Validate schema – sensor events publish as region events
    for event in parent_events:
      check_event_contains_data(event, "region")

    # The controller preserves the child scene_id in the republished payload
    for event in parent_events:
      assert event["scene_id"] == helper.child_id, (
        f"Event scene_id {event['scene_id']} must equal child_id {helper.child_id}")

    # The region_id in the event must match the sensor uid created in the child
    for event in parent_events:
      assert event.get("region_id") == helper.sensor_uid, (
        f"Event region_id {event.get('region_id')} must equal sensor uid {helper.sensor_uid}")

    log.info(f"PASS: {len(parent_events)} sensor events correctly propagated to parent scene")
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


def test_parent_event_attributes_match_child_event(objData, record_xml_attribute, params):
  """! Verify that region_id, region_name, count category keys and values, and
  the from_child_scene metadata attribution in the parent's republished event
  match those in the child's original event.

  @param    objData                 Pytest fixture with detection data.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @param    params                  Dict of test parameters.
  """
  TEST_NAME = "NEX-T21480"
  record_xml_attribute("name", TEST_NAME)
  log.info(f"Executing: {TEST_NAME}")
  exit_code = 1

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    # Wait for both child and parent events.
    child_roi_ok = helper.wait_for_events("child_roi_events")
    parent_roi_ok = helper.wait_for_events("parent_roi_events")

    assert child_roi_ok, "No ROI events received on child scene topic"
    assert parent_roi_ok, "No ROI events received on parent scene topic"

    child_evt = helper.child_roi_events[0]
    parent_evt = helper.parent_roi_events[0]

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
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    child_appeared = helper.wait_for_events("child_roi_events", timeout=MAX_WAIT)
    assert child_appeared, f"No child ROI events received within {MAX_WAIT}s"

    parent_appeared = helper.wait_for_events("parent_roi_events", timeout=MAX_WAIT)
    assert parent_appeared, (
      f"No parent ROI events received within {MAX_WAIT}s of child events")

    propagation_delay = (helper.first_received_at("parent_roi_events")
                         - helper.first_received_at("child_roi_events"))
    log.info(f"Propagation delay: {propagation_delay:.2f}s")
    assert propagation_delay <= MAX_WAIT, (
      f"Event propagation delay {propagation_delay:.2f}s exceeds limit {MAX_WAIT}s")

    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client, link=False)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    time.sleep(MAX_WAIT)

    assert len(helper.parent_roi_events) == 0, (
      "ROI events must NOT appear on parent topic when no parent link exists")
    assert len(helper.parent_tripwire_events) == 0, (
      "Tripwire events must NOT appear on parent topic when no parent link exists")

    log.info("PASS: No events appeared on unlinked parent topic without parent link")
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    ok = helper.wait_for_events("parent_roi_events")
    assert ok, f"No parent ROI events within {MAX_WAIT}s"

    for event in helper.parent_roi_events:
      assert event.get("region_id") == helper.roi_uid, (
        f"Parent event region_id {event.get('region_id')} "
        f"does not match child ROI uid {helper.roi_uid}")

    log.info("PASS: Parent event region_id correctly references child ROI uid")
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
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

  helper = ChildSceneTest(params)
  rest_client = helper.make_rest_client()
  client = None
  stop_event = threading.Event()
  send_thread = None
  try:
    helper.setup_scenes(rest_client)
    client = helper.connect_mqtt()

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

    time.sleep(MAX_WAIT)

    # Clear accumulators then resume sending detections, events must not arrive
    # on the parent topic.
    helper.parent_roi_events.clear()
    helper.parent_tripwire_events.clear()

    log.info("Step 3: Publishing after unlink – no events should appear on parent topic")
    stop_event = threading.Event()
    send_thread = helper.start_detection_thread(client, objData, stop_event)

    time.sleep(MAX_WAIT)

    assert len(helper.parent_roi_events) == 0, (
      "ROI events must NOT propagate to parent after child is unlinked")
    assert len(helper.parent_tripwire_events) == 0, (
      "Tripwire events must NOT propagate to parent after child is unlinked")

    log.info("PASS: Events stopped propagating after child was unlinked")
    exit_code = 0
  finally:
    stop_event.set()
    if send_thread:
      send_thread.join()
    if client:
      client.loopStop()
    helper.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
