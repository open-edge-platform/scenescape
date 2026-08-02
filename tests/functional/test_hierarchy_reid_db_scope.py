#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Multi-controller hierarchy ReID DB-scope priority tests (NEX-T21928–21932).

Literal parent/child1/child2 Scene Controllers (and optional split VDMS) linked
as remote children. Each scenario uses a distinct REID_HIER_* compose profile.
"""

import threading
import time

import pytest
from scene_common import log

import tests.common_test_utils as common
from tests.functional.common_remote_child import RemoteHierarchySetup
from tests.functional.common_retrack import (
  RetrackTest,
  make_reid_embedding,
)
from tests.functional.hierarchy_ports import reid_endpoint
from tests.functional.reid_backend import (
  count_near_exact_uuids,
  ensure_reid_schema,
  query_reid_count,
  wait_for_reid_backend_ready,
)
from tests.utils import profiles
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

# Default for collection sorting; each test overrides via _env_matrix_setup.
SCENESCAPE_SPEC = FuncTestSpec(
  profile=profiles.REID_HIER_SHARED,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

# Feature accumulation needs >=12 frames; leave headroom, then prune + flush.
ENROLL_FRAMES = 40
PRUNE_EMPTY_FRAMES = 20
FLUSH_WAIT_SECS = 12
NEAR_EXACT_SCORE = 0.95
PARENT_WAIT_SECS = 30
ALIVE_HZ = 10.0
# Parent tracker drops unreliable tracks in <1s; leave headroom so the first
# child's gid leaves UUIDManager.active_ids before the second child queries.
TRACK_CLEAR_SECS = 5

# Keep child1/child2 crops far apart so geometry alone cannot merge them.
# Stay within a typical 1280x720 Demo camera frame.
BBOX_C1 = {"x": 100, "y": 100, "width": 100, "height": 100}  # area 10000
BBOX_C2 = {"x": 900, "y": 400, "width": 100, "height": 100}  # area 10000


def _spec(profile):
  return FuncTestSpec(profile=profile, auth=AUTH_CONTROLLER)


def _prepare_reid(ports, which="shared"):
  hostname, port = reid_endpoint(ports, which)
  assert wait_for_reid_backend_ready(
    use_tls=True, max_attempts=30, retry_interval=1,
    hostname=hostname, port=port), \
    f"ReID backend {which} failed to become ready at {hostname}:{port}"
  ensure_reid_schema(
    dimensions=256, similarity_metric="IP", hostname=hostname, port=port)
  return hostname, port


def _wait_uuid_count(embedding, hostname, port, expected_min=1, timeout=30):
  deadline = time.time() + timeout
  last = (0, [])
  while time.time() < deadline:
    last = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE, k_neighbors=20,
      hostname=hostname, port=port)
    if last[0] >= expected_min:
      return last
    time.sleep(1.0)
  return last


def _publish_child(hier, role, obj_data, embedding, bbox, prune=True):
  """Publish reid frames on a child camera; optionally prune to flush enrollment."""
  client = hier.make_child_client(role)
  camera_id = hier.child1_camera_id if role == "child1" else hier.child2_camera_id
  try:
    payload = RetrackTest.with_reid_detection(
      obj_data, bbox, embedding=embedding)
    payload["id"] = camera_id
    RetrackTest.publish_reid_frames(payload, client, num_frames=ENROLL_FRAMES)
    if prune:
      RetrackTest.publish_empty_frames(client, camera_id, count=PRUNE_EMPTY_FRAMES)
  finally:
    client.loopStop()


def _scene_log_snippet(env, service, needles=None, max_lines=40):
  """Return recent log lines from a compose service for assertion messages."""
  try:
    name = f"{env.project_name}-{service}-1"
    logs = env.docker.container.logs(name) or ""
  except Exception as exc:
    return f"<failed to read {service} logs: {exc}>"
  lines = logs.splitlines()
  if needles:
    filtered = [ln for ln in lines if any(n.lower() in ln.lower() for n in needles)]
    if filtered:
      lines = filtered
  return "\n".join(lines[-max_lines:])


class _ChildPublisher:
  """Continuously publish reid frames so parent tracks stay visible."""

  def __init__(self, hier, role, obj_data, embedding, bbox):
    self._stop = threading.Event()
    self._error = []
    camera_id = hier.child1_camera_id if role == "child1" else hier.child2_camera_id
    payload = RetrackTest.with_reid_detection(
      obj_data, bbox, embedding=embedding)
    payload["id"] = camera_id
    self._client = hier.make_child_client(role)
    self._payload = payload
    self._thread = threading.Thread(
      target=self._run, name=f"publish-{role}", daemon=True)

  def _run(self):
    try:
      while not self._stop.is_set():
        RetrackTest.publish_reid_frames(
          self._payload, self._client, num_frames=5)
    except Exception as exc:  # noqa: BLE001 - surface in parent wait
      self._error.append(exc)
    finally:
      try:
        self._client.loopStop()
      except Exception:  # noqa: BLE001
        pass

  def start(self):
    self._thread.start()
    return self

  def stop(self):
    self._stop.set()
    self._thread.join(timeout=10)
    if self._error:
      raise self._error[0]


def _parent_ids_while_publishing(hier, publishers, settle_secs=6, env=None):
  """Keep children publishing while collecting recent parent object ids."""
  started = [p.start() for p in publishers]
  try:
    try:
      hier.wait_for_parent_objects(timeout=PARENT_WAIT_SECS, min_messages=1)
    except AssertionError:
      if env is not None:
        snippet = _scene_log_snippet(
          env["env"], "parent-scene",
          needles=["error", "Exception", "FELL BEHIND", "SKIPPING",
                   "UNKNOWN", "Connected to remote", "reid", "VDMS"])
        raise AssertionError(
          f"Timed out waiting for parent objects while children published. "
          f"parent-scene logs:\n{snippet}") from None
      raise
    time.sleep(settle_secs)
    return hier.snapshot_recent_parent_ids(last_n=15)
  finally:
    for pub in started:
      pub.stop()


def _assert_distinct_parent_ids(ids_final, context, hier):
  if len(ids_final) >= 2:
    return
  recent = hier.snapshot_recent_parent_objects(last_n=20)
  raise AssertionError(
    f"{context}; got {ids_final}. Recent parent objects={recent}")


@pytest.mark.parametrize(
  "_env_matrix_setup",
  [_spec(profiles.REID_HIER_SHARED)],
  indirect=True,
  ids=["reid_hier_shared"],
)
def test_hierarchy_shared_db_cross_child_merge(
    objData, record_xml_attribute, hierarchy_env, _env_matrix_setup):
  """! NEX-T21928: shared DB + retrack → same embedding on C1 then C2 converges
  to one parent ID via shared-DB rematch; shared DB has uuid_count(E)==1.

  Sequential (C1 leave, then C2) is required: UUIDManager refuses to assign the
  same live database gid to two concurrent tracks (collision → no-match).
  Concurrent two-child merge via ReID alone is a documented product follow-up
  (ADR 0015 open question on live-gid sharing).
  """
  TEST_NAME = "NEX-T21928"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  parent_client = None
  hier = RemoteHierarchySetup(
    hierarchy_env["parent"], hierarchy_env["child1"], hierarchy_env["child2"])

  try:
    hostname, port = _prepare_reid(hierarchy_env["ports"], "shared")
    hier.setup(retrack=True, separate_children=False)
    parent_client = hier.make_parent_client()

    embedding = make_reid_embedding(seed=0.28)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE,
      hostname=hostname, port=port)
    assert before == 0, f"Embedding already in shared DB ({before} uuid(s))"

    _publish_child(hier, "child1", objData, embedding, BBOX_C1)
    time.sleep(FLUSH_WAIT_SECS)
    total = query_reid_count("person", hostname=hostname, port=port)
    uuid_count, matched = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    if uuid_count != 1:
      snippet = _scene_log_snippet(
        hierarchy_env["env"], "child1-scene",
        needles=["reid", "vdms", "error", "camera", "enroll", "fail", "Subscribed"])
      raise AssertionError(
        f"Expected one enrollment after C1, got {uuid_count} "
        f"(total person descriptors={total}, matches={matched}). "
        f"child1-scene logs:\n{snippet}")

    hier.reset_parent_received()
    ids_after_c1 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child1", objData, embedding, BBOX_C1)],
      settle_secs=10,
      env=hierarchy_env)
    assert len(ids_after_c1) == 1, (
      f"Expected one parent ID after C1 rematch; got {ids_after_c1}")
    c1_id = next(iter(ids_after_c1))

    # Let C1's parent track leave active_ids so C2 can adopt the same DB uuid.
    time.sleep(TRACK_CLEAR_SECS)

    _publish_child(hier, "child2", objData, embedding, BBOX_C1)
    time.sleep(FLUSH_WAIT_SECS)
    uuid_count, _ = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    assert uuid_count == 1, (
      f"Shared DB must keep a single UUID after C2; got {uuid_count}")

    hier.reset_parent_received()
    ids_after_c2 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child2", objData, embedding, BBOX_C1)],
      settle_secs=10,
      env=hierarchy_env)
    assert ids_after_c2 == {c1_id}, (
      f"Parent should rematch C2 to C1's shared-DB ID; "
      f"c1_id={c1_id}, c2_ids={ids_after_c2}")

    log.info(f"PASS: shared DB uuid_count=1, parent id={c1_id}")
    exit_code = 0
  finally:
    if parent_client is not None:
      parent_client.loopStop()
    hier.teardown()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


@pytest.mark.parametrize(
  "_env_matrix_setup",
  [_spec(profiles.REID_HIER_CHILDREN_ONLY)],
  indirect=True,
  ids=["reid_hier_children_only"],
)
def test_hierarchy_children_share_db_parent_none(
    objData, record_xml_attribute, hierarchy_env, _env_matrix_setup):
  """! NEX-T21929: children share DB (enroll once); parent has no ReID so
  C1↔C2 do not merge via ReID at parent.
  """
  TEST_NAME = "NEX-T21929"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  parent_client = None
  hier = RemoteHierarchySetup(
    hierarchy_env["parent"], hierarchy_env["child1"], hierarchy_env["child2"])

  try:
    hostname, port = _prepare_reid(hierarchy_env["ports"], "shared")
    hier.setup(retrack=True)
    parent_client = hier.make_parent_client()

    embedding = make_reid_embedding(seed=0.29)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE,
      hostname=hostname, port=port)
    assert before == 0, f"Embedding already in DB ({before} uuid(s))"

    _publish_child(hier, "child1", objData, embedding, BBOX_C1)
    time.sleep(FLUSH_WAIT_SECS)
    uuid_count, _ = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    assert uuid_count == 1, f"Children should enroll once; got {uuid_count}"

    hier.reset_parent_received()
    ids_c1 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child1", objData, embedding, BBOX_C1)],
      env=hierarchy_env)
    assert len(ids_c1) == 1, f"Expected one parent ID from C1; got {ids_c1}"
    c1_id = next(iter(ids_c1))

    _publish_child(hier, "child2", objData, embedding, BBOX_C2)
    time.sleep(FLUSH_WAIT_SECS)
    uuid_count, _ = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    assert uuid_count == 1, f"Second child must not double-enroll; got {uuid_count}"

    # Let C1 tracks expire before observing C2 alone.
    time.sleep(5)
    hier.reset_parent_received()
    ids_c2 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child2", objData, embedding, BBOX_C2)],
      env=hierarchy_env)
    assert ids_c2, "Parent saw no objects from child2 alone"
    assert c1_id not in ids_c2, (
      f"Without parent ReID, C2 must not adopt C1's ID; "
      f"c1_id={c1_id}, c2_ids={ids_c2}")

    hier.reset_parent_received()
    ids_final = _parent_ids_while_publishing(
      hier,
      [
        _ChildPublisher(hier, "child1", objData, embedding, BBOX_C1),
        _ChildPublisher(hier, "child2", objData, embedding, BBOX_C2),
      ],
      settle_secs=10,
      env=hierarchy_env)
    assert ids_final, "Parent should still show objects without ReID"
    _assert_distinct_parent_ids(
      ids_final, "Without parent ReID, C1 and C2 must not merge", hier)

    log.info(f"PASS: children uuid_count=1, parent ids (no merge)={ids_final}")
    exit_code = 0
  finally:
    if parent_client is not None:
      parent_client.loopStop()
    hier.teardown()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


@pytest.mark.parametrize(
  "_env_matrix_setup",
  [_spec(profiles.REID_HIER_PARENT_ONLY)],
  indirect=True,
  ids=["reid_hier_parent_only"],
)
def test_hierarchy_parent_has_db_children_none(
    objData, record_xml_attribute, hierarchy_env, _env_matrix_setup):
  """! NEX-T21930: children have no ReID; parent enrolls forwarded crops on
  query-no-match, then rematches C2 to the same UUID (sequential).

  Scope: parent-only ReID with embedding passthrough. Children never write the
  DB; the parent is the sole enroller when the query finds no prior row. If a
  crop were already enrolled (not this profile), rematch would skip re-enroll.
  """
  TEST_NAME = "NEX-T21930"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  parent_client = None
  hier = RemoteHierarchySetup(
    hierarchy_env["parent"], hierarchy_env["child1"], hierarchy_env["child2"])

  try:
    hostname, port = _prepare_reid(hierarchy_env["ports"], "shared")
    hier.setup(retrack=True)
    parent_client = hier.make_parent_client()

    embedding = make_reid_embedding(seed=0.30)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE,
      hostname=hostname, port=port)
    assert before == 0, f"Embedding already in parent DB ({before} uuid(s))"

    _publish_child(hier, "child1", objData, embedding, BBOX_C1)
    time.sleep(FLUSH_WAIT_SECS)
    total = query_reid_count("person", hostname=hostname, port=port)
    uuid_count, matched = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    if uuid_count != 1:
      snippet = _scene_log_snippet(
        hierarchy_env["env"], "parent-scene",
        needles=["reid", "vdms", "error", "enroll", "fail", "Promoted"])
      raise AssertionError(
        f"Expected parent enrollment after C1, got {uuid_count} "
        f"(total person descriptors={total}, matches={matched}). "
        f"parent-scene logs:\n{snippet}")

    hier.reset_parent_received()
    ids_after_c1 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child1", objData, embedding, BBOX_C1)],
      settle_secs=10,
      env=hierarchy_env)
    assert len(ids_after_c1) == 1, (
      f"Expected one parent ID after C1; got {ids_after_c1}")
    c1_id = next(iter(ids_after_c1))

    time.sleep(TRACK_CLEAR_SECS)

    _publish_child(hier, "child2", objData, embedding, BBOX_C2)
    time.sleep(FLUSH_WAIT_SECS)
    uuid_count, _ = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    assert uuid_count == 1, (
      f"Parent must not double-enroll after C2 rematch; got {uuid_count}")

    hier.reset_parent_received()
    ids_after_c2 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child2", objData, embedding, BBOX_C2)],
      settle_secs=10,
      env=hierarchy_env)
    assert ids_after_c2 == {c1_id}, (
      f"Parent should rematch C2 to C1's parent-enrolled ID; "
      f"c1_id={c1_id}, c2_ids={ids_after_c2}")

    log.info(f"PASS: parent-only enroll uuid_count=1, parent id={c1_id}")
    exit_code = 0
  finally:
    if parent_client is not None:
      parent_client.loopStop()
    hier.teardown()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


@pytest.mark.parametrize(
  "_env_matrix_setup",
  [_spec(profiles.REID_HIER_PARTIAL)],
  indirect=True,
  ids=["reid_hier_partial"],
)
def test_hierarchy_partial_db_no_cross_merge(
    objData, record_xml_attribute, hierarchy_env, _env_matrix_setup):
  """! NEX-T21931: parent+child1 share reid-a; child2 has no DB → C2 does not
  merge into C1's parent UUID via ReID.
  """
  TEST_NAME = "NEX-T21931"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  parent_client = None
  hier = RemoteHierarchySetup(
    hierarchy_env["parent"], hierarchy_env["child1"], hierarchy_env["child2"])

  try:
    hostname, port = _prepare_reid(hierarchy_env["ports"], "a")
    hier.setup(retrack=True)
    parent_client = hier.make_parent_client()

    embedding = make_reid_embedding(seed=0.31)
    before, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE,
      hostname=hostname, port=port)
    assert before == 0, f"Embedding already in reid-a ({before} uuid(s))"

    _publish_child(hier, "child1", objData, embedding, BBOX_C1)
    time.sleep(FLUSH_WAIT_SECS)
    uuid_count, _ = _wait_uuid_count(embedding, hostname, port, expected_min=1)
    assert uuid_count == 1, f"C1 path should enroll once on shared DB; got {uuid_count}"

    hier.reset_parent_received()
    ids_c1 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child1", objData, embedding, BBOX_C1)],
      env=hierarchy_env)
    assert len(ids_c1) == 1, f"Expected one parent ID after C1; got {ids_c1}"
    c1_id = next(iter(ids_c1))

    _publish_child(hier, "child2", objData, embedding, BBOX_C2)
    time.sleep(FLUSH_WAIT_SECS)
    uuid_count, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE,
      hostname=hostname, port=port)
    assert uuid_count == 1, f"C2 without DB must not enroll; got {uuid_count}"

    hier.reset_parent_received()
    ids_final = _parent_ids_while_publishing(
      hier,
      [
        _ChildPublisher(hier, "child1", objData, embedding, BBOX_C1),
        _ChildPublisher(hier, "child2", objData, embedding, BBOX_C2),
      ],
      settle_secs=10,
      env=hierarchy_env)
    _assert_distinct_parent_ids(
      ids_final,
      f"C2 must not merge into C1 parent UUID via ReID; c1_id={c1_id}",
      hier)
    # Retracking may mint fresh parent gids when both children are live; the
    # policy under test is no ReID-driven convergence to a single ID.

    log.info(f"PASS: partial DB, c1_id={c1_id}, final={ids_final}")
    exit_code = 0
  finally:
    if parent_client is not None:
      parent_client.loopStop()
    hier.teardown()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0


@pytest.mark.parametrize(
  "_env_matrix_setup",
  [_spec(profiles.REID_HIER_SPLIT)],
  indirect=True,
  ids=["reid_hier_split"],
)
def test_hierarchy_split_dbs_no_cross_merge(
    objData, record_xml_attribute, hierarchy_env, _env_matrix_setup):
  """! NEX-T21932 (negative): child1→reid-a, child2→reid-b; each DB enrolls
  once; parent IDs for C1 vs C2 differ.
  """
  TEST_NAME = "NEX-T21932"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  exit_code = 1
  parent_client = None
  hier = RemoteHierarchySetup(
    hierarchy_env["parent"], hierarchy_env["child1"], hierarchy_env["child2"])

  try:
    host_a, port_a = _prepare_reid(hierarchy_env["ports"], "a")
    host_b, port_b = _prepare_reid(hierarchy_env["ports"], "b")
    hier.setup(retrack=True)
    parent_client = hier.make_parent_client()

    embedding = make_reid_embedding(seed=0.32)
    for host, port, label in (
        (host_a, port_a, "reid-a"), (host_b, port_b, "reid-b")):
      before, _ = count_near_exact_uuids(
        embedding, score_threshold=NEAR_EXACT_SCORE,
        hostname=host, port=port)
      assert before == 0, f"Embedding already in {label} ({before} uuid(s))"

    _publish_child(hier, "child1", objData, embedding, BBOX_C1)
    time.sleep(FLUSH_WAIT_SECS)
    count_a, _ = _wait_uuid_count(embedding, host_a, port_a, expected_min=1)
    assert count_a == 1, f"reid-a uuid_count expected 1, got {count_a}"

    hier.reset_parent_received()
    ids_c1 = _parent_ids_while_publishing(
      hier,
      [_ChildPublisher(hier, "child1", objData, embedding, BBOX_C1)],
      env=hierarchy_env)
    assert len(ids_c1) == 1, f"Expected one parent ID after C1; got {ids_c1}"
    c1_id = next(iter(ids_c1))

    _publish_child(hier, "child2", objData, embedding, BBOX_C2)
    time.sleep(FLUSH_WAIT_SECS)
    count_b, _ = _wait_uuid_count(embedding, host_b, port_b, expected_min=1)
    assert count_b == 1, f"reid-b uuid_count expected 1, got {count_b}"
    count_a, _ = count_near_exact_uuids(
      embedding, score_threshold=NEAR_EXACT_SCORE,
      hostname=host_a, port=port_a)
    assert count_a == 1, f"reid-a must stay at 1 UUID; got {count_a}"

    hier.reset_parent_received()
    ids_final = _parent_ids_while_publishing(
      hier,
      [
        _ChildPublisher(hier, "child1", objData, embedding, BBOX_C1),
        _ChildPublisher(hier, "child2", objData, embedding, BBOX_C2),
      ],
      settle_secs=10,
      env=hierarchy_env)
    _assert_distinct_parent_ids(
      ids_final,
      f"Split DBs: parent IDs for C1 vs C2 must differ; c1_id={c1_id}",
      hier)

    log.info(
      f"PASS: split DBs count_a={count_a} count_b={count_b} "
      f"parent ids={ids_final}")
    exit_code = 0
  finally:
    if parent_client is not None:
      parent_client.loopStop()
    hier.teardown()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
