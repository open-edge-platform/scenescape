# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Self-validates tests/data/ptz/dwell_conformance.json against scene_common.positioning_dwell.

The Controller (Phase 4) and Tracker (Phase 5) consume the same file unmodified.
"""

import json
from pathlib import Path

import pytest

from scene_common import positioning_reasons as reasons
from scene_common.positioning_config import load_consumer_config
from scene_common.positioning_dwell import (
  DwellConfig, DwellTracker, PoseSnapshot, parse_timestamp_ns)
from scene_common.positioning_schema_guards import (
  check_payload_size, validate_pose_context_payload)
from scene_common.schema import SchemaValidation

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "tests" / "data" / "ptz" / "dwell_conformance.json"
SCHEMA_PATH = REPO_ROOT / "controller" / "src" / "schema" / "metadata.schema.json"

FIXTURE = json.loads(FIXTURE_PATH.read_text())
VECTORS = FIXTURE["vectors"]


@pytest.fixture(scope="module")
def schema():
  return SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)


def _replay(vector, schema):
  config = DwellConfig.from_consumer_config(load_consumer_config(vector["config"]))
  consumer = vector["consumer"]
  tracker = DwellTracker(consumer["source_id"], consumer["resolver_id"], config,
                         expected_frame_id=consumer["expected_frame_id"],
                         expected_calibration_version=consumer["expected_calibration_version"])
  checked = 0
  for index, event in enumerate(vector["events"]):
    if event["type"] == "status":
      payload = event["payload"]
      assert schema.validateMessage("positioning_status", payload, check_format=True)
      tracker.on_status(payload["resolver_id"], payload["status"],
                        parse_timestamp_ns(payload["timestamp"]))
    elif event["type"] == "pose":
      payload = event["payload"]
      assert schema.validateMessage("pose_context", payload, check_format=True), payload
      check_payload_size(json.dumps(payload))
      validate_pose_context_payload(payload)
      tracker.on_pose(PoseSnapshot.from_payload(payload))
    else:
      assert event["type"] == "observation"
      decision = tracker.evaluate(parse_timestamp_ns(event["timestamp"]),
                                  parse_timestamp_ns(event["local_now"]))
      expected = event["expected"]
      actual = {"admitted": decision.admitted}
      if not decision.admitted:
        actual["invalid_reason"] = decision.invalid_reason
        actual["reason_detail"] = decision.reason_detail
      assert actual == expected, f"{vector['name']} event #{index}"
      checked += 1
  return checked


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_dwell_conformance_vector(vector, schema):
  assert _replay(vector, schema) > 0


def test_fixture_metadata():
  assert FIXTURE["fixture_version"] == 1
  assert FIXTURE["epsilon_s"] == 1e-6
  names = [v["name"] for v in VECTORS]
  assert len(names) == len(set(names))


def test_fixture_covers_every_reason_detail():
  seen = set()
  admitted = False
  for vector in VECTORS:
    for event in vector["events"]:
      if event["type"] == "observation":
        expected = event["expected"]
        admitted |= expected["admitted"]
        if not expected["admitted"]:
          assert expected["invalid_reason"] == reasons.canonical_reason(expected["reason_detail"])
          seen.add(expected["reason_detail"])
  assert admitted
  assert seen == set(reasons.ALL_REASON_DETAILS)
