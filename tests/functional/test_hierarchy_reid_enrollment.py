#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for hierarchy ReID enrollment scope against a live backend.

Validates ADR 0015 enrollment policy end-to-end:
  - A child scene that owns the source camera enrolls a local vetted crop
  - After the first confirmed write, child DATA_EXTERNAL stamps will_enroll
  - A retrack=True parent may query with the forwarded embedding but must not
    create a second enrolled UUID for the same crop
"""

import json
import queue
import time

import pytest
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common import log
import tests.common_test_utils as common
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

from tests.functional.common_retrack import (
  LARGE_BBOX_PX,
  RetrackTest,
  make_reid_embedding,
)
from tests.functional.reid_backend import (
  count_near_exact_uuids,
  ensure_reid_schema,
  get_reid_core_profile_module,
  wait_for_reid_backend_ready,
)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=get_reid_core_profile_module(),
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

# Feature accumulation needs >=12 frames; leave headroom, then prune + flush.
ENROLL_FRAMES = 40
PRUNE_EMPTY_FRAMES = 15
FLUSH_WAIT_SECS = 10
NEAR_EXACT_SCORE = 0.95


def _wait_for_enrollment(embedding, expected_min_uuids=1, timeout=30):
  """Poll the ReID backend until near-exact UUID count reaches expected_min_uuids."""
  deadline = time.time() + timeout
  last = (0, [])
  while time.time() < deadline:
    last = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE, k_neighbors=20)
    if last[0] >= expected_min_uuids:
      return last
    time.sleep(1.0)
  return last


def _prepare_reid_backend():
  assert wait_for_reid_backend_ready(use_tls=True, max_attempts=30, retry_interval=1), \
    "ReID backend failed to become ready"
  # Match controller reid-config.json COSINE -> IP descriptor metric.
  ensure_reid_schema(dimensions=256, similarity_metric="IP")


def test_hierarchy_child_enrolls_local_crop(
    objData, record_xml_attribute, params):
  """! Positive: child scene owning the camera enrolls the vetted local crop
  into the shared ReID database (at least one near-exact UUID for the embedding).
  """
  TEST_NAME = "NEX-T21925"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    _prepare_reid_backend()
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    # Child enrollment does not depend on retrack; keep True so the parent path
    # is also live while we verify the child still owns enrollment.
    h.set_retrack(rest_client, True)
    client = h.make_client()

    embedding = make_reid_embedding(seed=0.42)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE, k_neighbors=20)
    assert before == 0, (
      f"Injected embedding already present in ReID DB before publish ({before} uuid(s))")

    payload = RetrackTest.with_reid_detection(
      objData, LARGE_BBOX_PX, embedding=embedding)
    RetrackTest.publish_reid_frames(payload, client, num_frames=ENROLL_FRAMES)
    RetrackTest.publish_empty_frames(client, objData["id"], count=PRUNE_EMPTY_FRAMES)
    time.sleep(FLUSH_WAIT_SECS)

    uuid_count, matched = _wait_for_enrollment(embedding, expected_min_uuids=1)
    assert uuid_count >= 1, (
      "Child camera crop was not enrolled in the ReID backend; "
      f"near-exact uuid_count={uuid_count}, matches={matched}")

    # Process-level write confirmation unlocks will_enroll on hierarchy output.
    ext_queue = queue.Queue()

    def _on_ext(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
      except Exception:
        return
      if data.get("objects"):
        ext_queue.put(data)

    ext_client = h.make_client(
      topics=[PubSub.formatTopic(
        PubSub.DATA_EXTERNAL, scene_id=h.child_id, thing_type="+")],
      on_msg=_on_ext)
    try:
      RetrackTest.publish_reid_frames(payload, client, num_frames=20)
      deadline = time.time() + 15
      messages = []
      while time.time() < deadline and not messages:
        try:
          messages.append(ext_queue.get(timeout=1.0))
        except queue.Empty:
          continue
      while True:
        try:
          messages.append(ext_queue.get_nowait())
        except queue.Empty:
          break
      reid_payloads = RetrackTest.collect_reid_payloads(messages)
      assert reid_payloads, (
        "Expected metadata.reid on child DATA_EXTERNAL after confirmed enrollment")
      assert any(
        (reid.get("provenance") or {}).get("will_enroll") is True
        for _, reid in reid_payloads), (
        "After a confirmed child write, DATA_EXTERNAL provenance must stamp "
        f"will_enroll; got {[reid.get('provenance') for _, reid in reid_payloads]}")
    finally:
      ext_client.loopStop()

    log.info(f"PASS: child enrolled {uuid_count} unique uuid(s) for local crop "
             "and stamped will_enroll on DATA_EXTERNAL")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return

def test_hierarchy_retrack_true_parent_does_not_double_enroll(
    objData, record_xml_attribute, params):
  """! Positive: with retrack=True the parent queries using the forwarded
  embedding but must not enroll a second UUID for the same child crop.
  """
  TEST_NAME = "NEX-T21926"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  ext_client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    _prepare_reid_backend()
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, True)
    client = h.make_client()

    embedding = make_reid_embedding(seed=0.77)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE, k_neighbors=20)
    assert before == 0, (
      f"Injected embedding already present in ReID DB before publish ({before} uuid(s))")

    payload = RetrackTest.with_reid_detection(
      objData, LARGE_BBOX_PX, embedding=embedding)
    h.reset()

    # Phase 1: enroll and confirm the write, mirroring
    # test_hierarchy_child_enrolls_local_crop. Until reid_write_confirmed
    # flips true, _hierarchyReidPublishPolicy returns 'withhold' and the
    # child deliberately strips metadata.reid from DATA_EXTERNAL (ADR 0015) —
    # so there is nothing to observe on the parent side yet.
    RetrackTest.publish_reid_frames(payload, client, num_frames=ENROLL_FRAMES)
    RetrackTest.publish_empty_frames(client, objData["id"], count=PRUNE_EMPTY_FRAMES)
    time.sleep(FLUSH_WAIT_SECS)

    uuid_count, matched = _wait_for_enrollment(embedding, expected_min_uuids=1)
    assert uuid_count >= 1, (
      "Expected child enrollment of the crop; "
      f"near-exact uuid_count={uuid_count}, matches={matched}")

    # Phase 2: now that the write is confirmed, the child's hierarchy policy
    # becomes 'will_enroll' and forwards the embedding. Subscribe to the
    # parent's DATA_EXTERNAL and re-publish to observe it.
    ext_queue = queue.Queue()

    def _on_ext(mqttc, obj, msg):
      try:
        data = json.loads(msg.payload.decode("utf-8"))
      except Exception:
        return
      if data.get("objects"):
        ext_queue.put(data)

    ext_client = h.make_client(
      topics=[PubSub.formatTopic(
        PubSub.DATA_EXTERNAL, scene_id=h.parent_id, thing_type="+")],
      on_msg=_on_ext)

    h.reset()
    RetrackTest.publish_reid_frames(payload, client, num_frames=20)
    h.wait_for_messages(require_parent=True, require_child=True, timeout=15)

    deadline = time.time() + 15
    messages = []
    while time.time() < deadline and not messages:
      try:
        messages.append(ext_queue.get(timeout=1.0))
      except queue.Empty:
        continue
    while True:
      try:
        messages.append(ext_queue.get_nowait())
      except queue.Empty:
        break

    parent_reid = RetrackTest.collect_reid_payloads(messages)
    assert parent_reid, (
      "retrack=True parent must receive forwarded reid after the child's "
      "write is confirmed (post-enrollment)")

    RetrackTest.publish_empty_frames(client, objData["id"], count=PRUNE_EMPTY_FRAMES)
    time.sleep(FLUSH_WAIT_SECS + 5)

    uuid_count, matched = _wait_for_enrollment(embedding, expected_min_uuids=1)
    assert uuid_count == 1, (
      "retrack=True parent must not double-enroll the child crop; "
      f"expected 1 unique uuid, found {uuid_count}, matches={matched}")

    log.info("PASS: parent queried without creating a second enrolled UUID")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if ext_client is not None:
      ext_client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return

def test_hierarchy_retrack_false_parent_still_single_enrollment(
    objData, record_xml_attribute, params):
  """! Boundary: with retrack=False the parent strips reid entirely; only the
  child camera owner enrolls, so the unique UUID count for the crop remains 1.
  """
  TEST_NAME = "NEX-T21927"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  client = None
  rest_client = None
  h = RetrackTest(params)

  try:
    _prepare_reid_backend()
    rest_client = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest_client.authenticate(params['user'], params['password'])

    h.setup_scenes(rest_client)
    h.set_retrack(rest_client, False)
    client = h.make_client()

    embedding = make_reid_embedding(seed=0.91)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE, k_neighbors=20)
    assert before == 0, (
      f"Injected embedding already present in ReID DB before publish ({before} uuid(s))")

    payload = RetrackTest.with_reid_detection(
      objData, LARGE_BBOX_PX, embedding=embedding)
    h.reset()
    RetrackTest.publish_reid_frames(payload, client, num_frames=ENROLL_FRAMES)
    h.wait_for_messages(require_parent=True, require_child=True, timeout=15)
    parent_snap, _ = h.snapshot_received()
    assert not RetrackTest.collect_reid_payloads(parent_snap), (
      "retrack=False parent regulated output must not carry reid")

    RetrackTest.publish_empty_frames(client, objData["id"], count=PRUNE_EMPTY_FRAMES)
    time.sleep(FLUSH_WAIT_SECS)

    uuid_count, matched = _wait_for_enrollment(embedding, expected_min_uuids=1)
    assert uuid_count == 1, (
      "Expected exactly one enrolled UUID from the child when retrack=False; "
      f"got {uuid_count}, matches={matched}")

    log.info("PASS: retrack=False keeps single child-owned enrollment")
    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    if rest_client is not None:
      h.teardown_scenes(rest_client)
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
