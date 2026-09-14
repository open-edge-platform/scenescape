#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for hierarchy ReID provenance and retrack interaction.

Covers the live MQTT path for ADR 0015:
  - Child DATA_EXTERNAL stamps vetted provenance for large crops
  - Child DATA_EXTERNAL withholds reid when the crop fails the area gate
  - Camera-claimed provenance cannot bypass the local bbox gate
  - retrack=False parents strip forwarded reid from regulated output
  - retrack=True parents preserve forwarded reid on regulated output
"""

import json
import queue
import threading

import pytest
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log
import tests.common_test_utils as common
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

from tests.functional.common_retrack import (
  LARGE_BBOX_PX,
  SMALL_BBOX_PX,
  RetrackTest,
)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db


def _collect_external_messages(h, client_holder, timeout=None):
  """Subscribe to child DATA_EXTERNAL and return messages that contain objects."""
  if timeout is None:
    timeout = h.MAX_WAIT
  ext_queue = queue.Queue()

  def _on_ext(mqttc, obj, msg):
    try:
      data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
      return
    if data.get("objects"):
      ext_queue.put(data)

  topic = PubSub.formatTopic(
    PubSub.DATA_EXTERNAL, scene_id=h.child_id, thing_type="+")
  client_holder[0] = h.make_client([topic], _on_ext)
  return ext_queue, timeout


def _drain_queue(q):
  items = []
  while True:
    try:
      items.append(q.get_nowait())
    except queue.Empty:
      break
  return items


def _wait_for_queue(q, timeout):
  try:
    first = q.get(timeout=timeout)
  except queue.Empty:
    return []
  rest = _drain_queue(q)
  return [first] + rest


def test_child_external_reid_stamped_with_provenance(
    objData, record_xml_attribute, params):
  """! Positive: large local crops forward reid on DATA_EXTERNAL with provenance
  naming the vetting child scene and source camera.
  """
  TEST_NAME = "NEX-T28654"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client_holder = [None]
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)
    ext_queue, timeout = _collect_external_messages(h, client_holder)

    payload = RetrackTest.with_reid_detection(objData, LARGE_BBOX_PX)
    send_thread = threading.Thread(
      target=h.publish_data, args=(payload, client_holder[0]), daemon=True)
    send_thread.start()
    messages = _wait_for_queue(ext_queue, timeout)
    send_thread.join()

    assert messages, f"No DATA_EXTERNAL messages within {timeout}s"
    reid_payloads = RetrackTest.collect_reid_payloads(messages)
    assert reid_payloads, (
      "Expected metadata.reid on child DATA_EXTERNAL for a large vetted crop")

    cameras = rest_client.getCameras({'scene': h.child_id})
    assert cameras.statusCode == 200, \
      f"Failed to list child cameras: {cameras.statusCode}"
    known_cam_ids = {objData["id"]}
    for cam in cameras.get('results', []):
      if cam.get('uid'):
        known_cam_ids.add(cam['uid'])
      if cam.get('name'):
        known_cam_ids.add(cam['name'])

    for oid, reid in reid_payloads:
      assert "provenance" in reid, f"Object {oid}: missing reid provenance"
      prov = reid["provenance"]
      assert prov.get("quality_vetted") is True, \
        f"Object {oid}: quality_vetted must be True, got {prov!r}"
      assert prov.get("origin_scene_id") == h.child_id, (
        f"Object {oid}: origin_scene_id expected {h.child_id}, got "
        f"{prov.get('origin_scene_id')!r}")
      assert prov.get("origin_camera_id") in known_cam_ids, (
        f"Object {oid}: origin_camera_id {prov.get('origin_camera_id')!r} "
        f"not in known cameras {known_cam_ids}")

    log.info(f"PASS: {len(reid_payloads)} external reid payload(s) stamped")
    exit_code = 0

  finally:
    if client_holder[0] is not None:
      client_holder[0].loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_child_external_reid_withheld_when_crop_too_small(
    objData, record_xml_attribute, params):
  """! Negative: crops at or below the minimum pixel area are not forwarded on
  hierarchy DATA_EXTERNAL even when the detector supplies an embedding.
  """
  TEST_NAME = "NEX-T28655"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client_holder = [None]
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)
    ext_queue, timeout = _collect_external_messages(h, client_holder)

    payload = RetrackTest.with_reid_detection(objData, SMALL_BBOX_PX)
    send_thread = threading.Thread(
      target=h.publish_data, args=(payload, client_holder[0]), daemon=True)
    send_thread.start()
    messages = _wait_for_queue(ext_queue, timeout)
    send_thread.join()

    assert messages, (
      f"No DATA_EXTERNAL messages within {timeout}s "
      "(objects must still publish without reid)")
    reid_payloads = RetrackTest.collect_reid_payloads(messages)
    assert not reid_payloads, (
      "Small crop must not forward metadata.reid on DATA_EXTERNAL, "
      f"found {len(reid_payloads)} reid payload(s)")

    log.info("PASS: small-crop reid withheld from DATA_EXTERNAL")
    exit_code = 0

  finally:
    if client_holder[0] is not None:
      client_holder[0].loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_camera_claimed_provenance_cannot_bypass_bbox_gate(
    objData, record_xml_attribute, params):
  """! Negative: a detector cannot claim upstream vetting to skip the local
  pixel-area gate. Spoofed provenance on a small crop must still withhold reid.
  """
  TEST_NAME = "NEX-T28656"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client_holder = [None]
  rest_client = None
  h = RetrackTest(params)

  try:
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)
    ext_queue, timeout = _collect_external_messages(h, client_holder)

    spoofed = {
      "origin_scene_id": "spoofed-scene",
      "origin_camera_id": "spoofed-cam",
      "quality_vetted": True,
    }
    payload = RetrackTest.with_reid_detection(
      objData, SMALL_BBOX_PX, provenance=spoofed)
    send_thread = threading.Thread(
      target=h.publish_data, args=(payload, client_holder[0]), daemon=True)
    send_thread.start()
    messages = _wait_for_queue(ext_queue, timeout)
    send_thread.join()

    assert messages, f"No DATA_EXTERNAL messages within {timeout}s"
    reid_payloads = RetrackTest.collect_reid_payloads(messages)
    assert not reid_payloads, (
      "Spoofed camera provenance must not bypass the bbox gate; "
      f"found {len(reid_payloads)} reid payload(s)")

    log.info("PASS: spoofed camera provenance ignored for small crop")
    exit_code = 0

  finally:
    if client_holder[0] is not None:
      client_holder[0].loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_retrack_false_parent_regulated_strips_reid(
    objData, record_xml_attribute, params):
  """! Positive: with retrack=False the parent accepts child IDs and strips
  forwarded reid, so parent DATA_REGULATED objects carry no metadata.reid.
  """
  TEST_NAME = "NEX-T28657"
  record_xml_attribute("name", TEST_NAME)
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
    payload = RetrackTest.with_reid_detection(objData, LARGE_BBOX_PX)
    h.publish_data(payload, client)
    h.wait_for_messages(require_parent=True, require_child=True)

    parent_snap, child_snap = h.snapshot_received()
    parent_ids = RetrackTest.collect_object_ids(parent_snap)
    child_ids = RetrackTest.collect_object_ids(child_snap)
    shared = parent_ids & child_ids
    assert shared, (
      "retrack=False expected overlapping IDs; "
      f"parent={parent_ids}, child={child_ids}")

    child_reid = RetrackTest.collect_reid_payloads(child_snap)
    assert child_reid, (
      "Child regulated output should still carry reid without provenance")

    parent_reid = RetrackTest.collect_reid_payloads(parent_snap)
    assert not parent_reid, (
      "retrack=False parent must strip forwarded reid from regulated output, "
      f"found {len(parent_reid)} reid payload(s)")

    log.info("PASS: retrack=False parent regulated strips reid")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return


def test_retrack_true_parent_regulated_preserves_reid(
    objData, record_xml_attribute, params):
  """! Positive: with retrack=True the parent re-tracks child detections and
  keeps forwarded reid on regulated output so UUID manager can query with it.
  """
  TEST_NAME = "NEX-T28658"
  record_xml_attribute("name", TEST_NAME)
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
    payload = RetrackTest.with_reid_detection(objData, LARGE_BBOX_PX)
    h.publish_data(payload, client)
    h.wait_for_messages(require_parent=True, require_child=True)

    parent_snap, child_snap = h.snapshot_received()
    parent_ids = RetrackTest.collect_object_ids(parent_snap)
    child_ids = RetrackTest.collect_object_ids(child_snap)
    shared = parent_ids & child_ids
    assert not shared, (
      "retrack=True expected distinct parent IDs; "
      f"shared={shared}, parent={parent_ids}, child={child_ids}")

    parent_reid = RetrackTest.collect_reid_payloads(parent_snap)
    assert parent_reid, (
      "retrack=True parent regulated output must preserve forwarded reid")

    for oid, reid in parent_reid:
      assert "embedding_vector" in reid, f"Parent object {oid}: missing embedding"
      # Regulated (non-hierarchy) output keeps embeddings but does not attach
      # provenance; provenance is hierarchy/DATA_EXTERNAL only.
      assert "provenance" not in reid, (
        f"Parent regulated object {oid} must not carry hierarchy provenance")

    log.info(
      f"PASS: retrack=True parent preserved reid on {len(parent_reid)} object(s)")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
