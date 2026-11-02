#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.utils.profiles import REID_CORE
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

SCENESCAPE_SPEC = FuncTestSpec(
  profile=REID_CORE,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.skip(
  reason="Zephyr stub; implementation and NEX-T markers are later steps")


def test_concurrent_schema_init_on_empty_vdms():
  """
  ## Name
  Concurrent schema init on empty VDMS

  ## Objective
  Verify three Scene Controllers sharing one empty VDMS initialize the same
  ReID descriptor set concurrently, with no schema error, and every marker
  row agrees on dimensions and metric.

  ## Labels
  - Functional
  - ReID
  - Multi-Controller

  ## Steps
  1. Start one empty VDMS and three controllers sharing endpoint, descriptor set, scene, and COSINE metric.
  2. Subscribe to scenescape/data/scene/<scene_id>/+ before publishing detections.
  3. Inject one valid 256-dimensional person embedding so every controller runs ensureSchema together.
  4. Do not pre-create the descriptor set with the host ensure_reid_schema helper.
  5. Wait until each controller process reports schema ready, and fail naming any controller that times out.
  6. Assert no schema RuntimeError is raised or logged, including errors swallowed by connect.
  7. Query every ReidSchemaMarker row and assert the only pair is (256, COSINE).
  """
  pass


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


def test_conflicting_schema_rejected():
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
  1. In a separate Compose project, seed VDMS with a marker whose dimensions or metric differ.
  2. Start the controllers against that seeded database, not the positive run's volume.
  3. Publish a valid embedding so each controller attempts schema initialization.
  4. Assert readiness is rejected or times out, and no controller reports schema ready.
  5. Assert diagnostics name the dimension or metric mismatch.
  """
  pass


def test_incomplete_schema_marker_rejected():
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
  1. Seed an isolated VDMS with an incomplete ReidSchemaMarker for the shared descriptor set.
  2. Start the controllers against that database, separate from the positive run.
  3. Publish a valid embedding so each controller attempts schema initialization.
  4. Assert no controller reports schema ready within the bounded wait.
  5. Assert the failure names the incomplete marker.
  """
  pass


def test_split_gid_fails_assertion():
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
  pass


def test_missing_gid_fails_assertion():
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
  pass


def test_malformed_scene_messages_fail():
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
  pass


def test_warmup_only_gids_do_not_pass():
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
  pass
