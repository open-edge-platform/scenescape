#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from scene_common.reid_constants import SCHEMA_NAME
from tests.functional.reid_backend import wait_for_reid_backend_ready
from tests.functional.reid_multi_controller_support import assert_schema_rejected
from tests.functional.reid_scene_collector import (
  SceneIdentityCollector,
  assert_single_global_id,
)
from tests.functional.reid_vdms_state import (
  seed_descriptor_set,
  seed_schema_marker,
  vdms_client,
)
from tests.utils.profiles import REID_MULTI_CONTROLLER
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

SCENESCAPE_SPEC = FuncTestSpec(
  profile=REID_MULTI_CONTROLLER,
  auth=AUTH_CONTROLLER,
)

STUB = pytest.mark.skip(
  reason="Zephyr stub; implementation and NEX-T markers are later steps")

SCENE_TOPIC = "scenescape/data/scene/test-scene/person"


def scene_message(*objects):
  """Build a scene payload from (id, reid_state) pairs for the person category."""
  return json.dumps({
    "objects": [{"id": gid, "category": "person", "reid_state": state}
                for gid, state in objects]
  })


@STUB
def test_concurrent_schema_init_on_empty_vdms():
  """
  ## Name
  Concurrent schema init on empty VDMS

  ## Objective
  Verify three Scene Controllers sharing one empty VDMS, with their first
  schema-initialization attempts forced to overlap by a test-only barrier,
  initialize the same ReID descriptor set with no schema error and marker
  rows that agree on dimensions and metric. Repeat against a fresh VDMS
  database each time so the creation race is exercised reliably.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller

  ## Steps
  1. Repeat K iterations (default 10, at least 5); each recreates VDMS with a new empty volume and unique descriptor-set name, then restarts all three controllers so no process-local schema state carries over.
  2. Start three controllers sharing endpoint, descriptor set, scene, and ReID config (COSINE scoring, which creates IP descriptor sets), with a compose-overlay-only hook that wraps the schema create call and is inert when its env var is unset.
  3. Barrier A: before the VDMS create call, each hook writes an arrival record to a shared directory and blocks until all three records exist, within a 30 s bounded wait.
  4. Subscribe to scenescape/data/scene/<scene_id>/+, then republish the same valid 256-dimensional embedding until all three controllers have arrived; one publish is not enough because delivery order is not controlled.
  5. Fail naming any controller that missed Barrier A; do not pre-create the descriptor set with the host ensure_reid_schema helper.
  6. On release, each hook logs monotonic start/end times and outcome (created or already exists); assert start skew is at most 50 ms and exactly one controller created the set.
  7. Barrier B: after the create call returns and before the marker read or write, hold each controller until all three create calls have returned (10 s bound) so losers race the winner's marker write.
  8. Wait up to 15 s after release for each controller process to report schema ready, and fail naming any that times out.
  9. Assert no schema RuntimeError is raised or logged, including errors swallowed by connect.
  10. Query every ReidSchemaMarker row for the set and assert at least one row and the only pair is (256, IP); duplicate rows are acceptable.
  11. Fail the run on the first failing iteration, keep per-controller logs and timelines, and do not retry to mask a flake; cap each iteration at 180 s.
  """
  pass


@STUB
def test_stable_gid_across_three_controllers():
  """
  ## Name
  Stable global ID across three controllers

  ## Objective
  Verify that after warm-up, interleaved scene messages from all three
  controllers contain exactly one nonempty global ID for the single injected
  object across the full capture window.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller

  ## Steps
  1. Confirm each of the three controllers is schema-ready against the shared empty VDMS.
  2. Keep publishing the same person detection and embedding through enrollment.
  3. Exclude warm-up, pending_collection, and initial query-no-match messages from the identity set.
  4. Open a bounded post-warmup capture window and keep detections flowing.
  5. Assert at least one qualifying publication is attributed to each controller.
  6. Assert the set of nonempty target global IDs has exactly one member.
  7. Fail if that set is empty, and include the full observed set when it has more than one ID.
  """
  pass


@pytest.mark.fresh_stack
@pytest.mark.test_name("NEX-T#####")
@pytest.mark.parametrize("seed_dimensions, seed_metric, diagnostic", [
  pytest.param(128, "IP", "has 128 dimensions, expected 256", id="dimensions"),
  pytest.param(256, "L2", "uses metric L2, expected IP", id="metric"),
])
def test_conflicting_schema_rejected(scenescape_env, params, result_recorder,
                                     seed_dimensions, seed_metric, diagnostic):
  """
  ## Name
  Reject conflicting ReID schema

  ## Objective
  Verify a controller does not report schema ready when an isolated VDMS
  already has a descriptor set or marker whose dimensions or metric disagree
  with the controller configuration.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller
  - Negative

  ## Steps
  1. In a fresh Compose project, before any embedding is published, seed VDMS with a descriptor set and marker for the shared set name whose dimensions or metric differ from the controller configuration, including a few descriptors.
  2. Snapshot the seeded state with an authenticated VDMS client: descriptor-set properties and descriptor count, every ReidSchemaMarker row, and the list of descriptor sets.
  3. Wait for VDMS to accept host connections and every controller to report subscribed, so a timeout cannot be blamed on startup or connectivity.
  4. Republish a valid embedding until each controller's own log shows its schema-initialization attempt failing, within a 30 s bound per controller; fail naming any controller without one.
  5. For each controller, assert its log contains the ensureSchema mismatch error naming the set, expected and found dimensions or metric, and no VDMS connection or timeout errors.
  6. Assert no controller logs a successful ensureSchema (created or verified) line, so the failure is a rejection rather than a bare wait timeout.
  7. Snapshot again after every controller has logged at least two failed attempts, and assert it equals the seeded snapshot: same properties and descriptor count, marker rows unchanged, no new descriptor sets or markers.
  """
  assert wait_for_reid_backend_ready(), "VDMS did not become ready for the host client"
  with vdms_client(set_name=SCHEMA_NAME) as db:
    seed_descriptor_set(db, SCHEMA_NAME, seed_dimensions, seed_metric, descriptors=3)
    seed_schema_marker(db, SCHEMA_NAME, seed_dimensions, seed_metric)

  assert_schema_rejected(scenescape_env, params, SCHEMA_NAME, diagnostic)
  result_recorder.success()


@pytest.mark.fresh_stack
@pytest.mark.test_name("NEX-T#####")
@pytest.mark.parametrize("marker_dimensions, marker_metric, diagnostic", [
  pytest.param(None, "IP", "schema marker returned no dimensions", id="no-dimensions"),
  pytest.param(256, None, "uses metric Missing property, expected IP", id="no-metric"),
])
def test_incomplete_schema_marker_rejected(scenescape_env, params, result_recorder,
                                           marker_dimensions, marker_metric, diagnostic):
  """
  ## Name
  Reject incomplete ReID schema marker

  ## Objective
  Verify initialization does not report ready when the shared descriptor-set
  marker is missing required dimensions or metric. Container health or a
  host-side connection must not count as ready.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller
  - Negative

  ## Steps
  1. In a fresh Compose project, before any embedding is published, seed VDMS with the shared descriptor set, so creation reports it already exists, plus an incomplete ReidSchemaMarker missing dimensions or metric.
  2. Snapshot the seeded state with an authenticated VDMS client: descriptor-set properties and descriptor count, every ReidSchemaMarker row, and the list of descriptor sets.
  3. Wait for VDMS to accept host connections and every controller to report subscribed, so a timeout cannot be blamed on startup or connectivity.
  4. Republish a valid embedding until each controller's own log shows its schema-initialization attempt failing, within a 30 s bound per controller; fail naming any controller without one.
  5. For each controller, assert its log contains the ensureSchema error naming the set, with no VDMS connection or timeout errors; a missing dimensions value reports no dimensions, and a missing metric reports the VDMS 'Missing property' value as the metric.
  6. Assert no controller logs a successful ensureSchema (created or verified) line, so the failure is a rejection rather than a bare wait timeout.
  7. Snapshot again after every controller has logged at least two failed attempts, and assert it equals the seeded snapshot: the marker was not repaired or replaced, descriptors are unchanged, and no new sets or markers exist.
  """
  assert wait_for_reid_backend_ready(), "VDMS did not become ready for the host client"
  with vdms_client(set_name=SCHEMA_NAME) as db:
    seed_descriptor_set(db, SCHEMA_NAME, 256, "IP", descriptors=3)
    seed_schema_marker(db, SCHEMA_NAME, marker_dimensions, marker_metric)

  assert_schema_rejected(scenescape_env, params, SCHEMA_NAME, diagnostic)
  result_recorder.success()


@pytest.mark.test_name("NEX-T#####")
def test_split_gid_fails_assertion(result_recorder):
  """
  ## Name
  Fail when post-warmup global IDs split

  ## Objective
  Verify the identity assertion fails, and prints the full ID set, when two
  distinct nonempty global IDs appear after warm-up. Exercise the collector
  without Docker.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller
  - Negative

  ## Steps
  1. Feed the collector a post-warmup window containing two distinct nonempty target global IDs.
  2. Interleave the messages so arrival order cannot hide the split.
  3. Run the same assertion used for the live three-controller capture.
  4. Assert the check fails and the failure text includes both observed IDs.
  """
  traffic = [("c1", "gid-a"), ("c2", "gid-b"), ("c3", "gid-a"), ("c1", "gid-b")]
  for ordering in (traffic, list(reversed(traffic))):
    collector = SceneIdentityCollector()
    collector.end_warmup()
    for source, gid in ordering:
      collector.ingest(SCENE_TOPIC, scene_message((gid, "matched")), source=source)

    with pytest.raises(AssertionError) as failure:
      assert_single_global_id(collector)
    text = str(failure.value)
    assert "gid-a" in text and "gid-b" in text, text
    assert "split" in text, text

  result_recorder.success()


@pytest.mark.test_name("NEX-T#####")
def test_missing_gid_fails_assertion(result_recorder):
  """
  ## Name
  Fail when no qualifying global ID is observed

  ## Objective
  Verify a capture with no nonempty target global ID fails instead of passing
  vacuously. Exercise the collector without Docker.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller
  - Negative

  ## Steps
  1. Feed the collector a bounded capture that has scene traffic but no nonempty target global ID.
  2. Run the same assertion used for the live three-controller capture.
  3. Assert the check fails because the qualifying ID set is empty.
  """
  collector = SceneIdentityCollector()
  collector.end_warmup()
  collector.ingest(SCENE_TOPIC, scene_message(("", "matched"), (None, "matched")), source="c1")
  collector.ingest(SCENE_TOPIC, json.dumps({"objects": [{"category": "person"}]}), source="c2")
  collector.ingest(SCENE_TOPIC, json.dumps({"objects": []}), source="c3")

  assert collector.message_count() == 3
  assert collector.errors() == []
  with pytest.raises(AssertionError) as failure:
    assert_single_global_id(collector)
  assert "no qualifying global ID" in str(failure.value)
  assert collector.qualifying_ids() == set()

  result_recorder.success()


@pytest.mark.test_name("NEX-T#####")
def test_malformed_scene_messages_fail(result_recorder):
  """
  ## Name
  Fail on malformed scene messages

  ## Objective
  Verify JSON decode errors and unexpected objects fail the capture instead
  of being dropped. Do not fold unrelated object IDs into the target set.
  Exercise the collector without Docker.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller
  - Negative

  ## Steps
  1. Inject one scene payload that is not valid JSON and one payload for an unexpected object.
  2. Retain callback and decode errors instead of skipping them.
  3. Assert the run fails visibly and names the collection or decode error.
  4. Assert the unexpected object's ID is not added to the target global-ID set.
  """
  collector = SceneIdentityCollector()
  collector.end_warmup()
  collector.ingest(SCENE_TOPIC, scene_message(("target-gid", "matched")), source="c1")
  collector.ingest(SCENE_TOPIC, "{not valid json", source="c2")
  collector.ingest(
    SCENE_TOPIC,
    json.dumps({"objects": [{"id": "intruder-gid", "category": "vehicle"}]}),
    source="c3")

  errors = collector.errors()
  assert len(errors) == 2, errors
  with pytest.raises(AssertionError) as failure:
    assert_single_global_id(collector)
  text = str(failure.value)
  assert "decode error" in text, text
  assert "unexpected object" in text, text
  assert collector.qualifying_ids() == {"target-gid"}
  assert "intruder-gid" not in collector.excluded_ids()

  result_recorder.success()


@pytest.mark.test_name("NEX-T#####")
def test_warmup_only_gids_do_not_pass(result_recorder):
  """
  ## Name
  Warm-up-only IDs do not satisfy identity assertion

  ## Objective
  Verify a nonempty global ID seen only during warm-up, pending collection,
  or the initial no-match window cannot satisfy the post-warmup identity
  check. Exercise the collector without Docker.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller
  - Negative

  ## Steps
  1. Feed the collector messages whose only nonempty target global ID is before the warm-up gate.
  2. Close the gate and provide an empty post-warmup window.
  3. Assert those warm-up IDs are excluded from the qualifying set.
  4. Assert the identity check fails rather than passing on warm-up-only IDs.
  """
  collector = SceneIdentityCollector()
  collector.ingest(SCENE_TOPIC, scene_message(("warm-gid", "pending_collection")), source="c1")
  collector.ingest(SCENE_TOPIC, scene_message(("nomatch-gid", "query_no_match")), source="c2")
  collector.end_warmup()
  collector.ingest(SCENE_TOPIC, scene_message(("late-pending-gid", "pending_collection")), source="c3")
  collector.ingest(SCENE_TOPIC, json.dumps({"objects": []}), source="c1")

  assert collector.qualifying_ids() == set()
  assert collector.excluded_ids() == {"warm-gid", "nomatch-gid", "late-pending-gid"}
  with pytest.raises(AssertionError) as failure:
    assert_single_global_id(collector)
  assert "no qualifying global ID" in str(failure.value)

  result_recorder.success()
