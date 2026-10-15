# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared positioning contracts: reasons, quality, config, payload guards, and MQTT schemas."""

import copy
import json
import math
from pathlib import Path

import jsonschema
import numpy as np
import pytest

from controller import external_source
from scene_common import positioning_reasons as reasons
from scene_common.positioning_config import PositioningConfigError, load_consumer_config
from scene_common.positioning_dwell import (
  DwellConfig, DwellTracker, PoseSnapshot, parse_timestamp_ns)
from scene_common.positioning_quality import calibration_score, score, temporal_score
from scene_common.positioning_schema_guards import (
  MAX_POSE_CONTEXT_BYTES, PoseContextGuardError, check_payload_size,
  validate_pose_context_payload)
from scene_common.schema import SchemaValidation

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "controller" / "src" / "schema" / "metadata.schema.json"
SCHEMA_DOC = json.loads(SCHEMA_PATH.read_text())

VALID_POSE = {
  "schema_version": 1,
  "source_id": "atag-ptzcam3",
  "timestamp": "2026-10-01T10:15:30.123Z",
  "valid_until": "2026-10-01T10:15:30.623Z",
  "sequence": 10432,
  "valid": True,
  "pose": {
    "frame_id": "scene:3bc091c7-e449-46a0-9540-29c499bca18c",
    "transform_direction": "scene_from_camera",
    "matrix_layout": "row_major",
    "matrix_4x4": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 4], [0, 0, 0, 1]],
    "translation_unit": "m",
  },
  "motion_state": "stationary",
  "sample_age_s": 0.004,
  "timestamp_uncertainty_s": 0.012,
  "calibration_version": "atag-ptzcam3-v3",
  "quality": {"score": 0.94, "temporal_score": 0.98, "calibration_score": 0.96,
              "reprojection_rms_px": 1.2},
}
INVALID_POSE = {
  "schema_version": 1,
  "source_id": "atag-ptzcam3",
  "timestamp": "2026-10-01T10:15:30.450Z",
  "valid_until": "2026-10-01T10:15:30.950Z",
  "sequence": 10433,
  "valid": False,
  "motion_state": "settling",
  "sample_age_s": 0.005,
  "timestamp_uncertainty_s": 0.012,
  "calibration_version": "atag-ptzcam3-v3",
  "invalid_reason": "invalid_pose",
  "reason_detail": "settling",
}
STATUS = {"resolver_id": "positioning", "status": "online", "timestamp": "2026-10-01T09:00:00Z"}
CONSUMER_CONFIG = {
  "max_pose_age_s": 0.5,
  "max_clock_offset_s": 0.05,
  "max_detection_pipeline_latency_s": 1.0,
  "max_detection_timestamp_uncertainty_s": 0.05,
}


@pytest.fixture(scope="module")
def schema():
  return SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)


# --- reasons -------------------------------------------------------------------------------

def test_canonical_reasons_match_controller_external_source():
  assert reasons.REASON_NO_POSE_AVAILABLE == external_source.REASON_NO_POSE_AVAILABLE
  assert reasons.REASON_POSE_EXPIRED == external_source.REASON_POSE_EXPIRED
  assert reasons.REASON_INVALID_POSE == external_source.REASON_INVALID_POSE


def test_ptz_reason_detail_mapping():
  assert reasons.PTZ_REASON_DETAILS == {
    "no_sample": "no_pose_available",
    "sample_stale": "pose_expired",
    "moving": "invalid_pose",
    "settling": "invalid_pose",
    "calibration_missing": "invalid_pose",
    "calibration_changed": "invalid_pose",
    "invalid_sample": "invalid_pose",
    "backlash_unknown": "invalid_pose",
  }
  assert set(reasons.ALL_REASON_DETAILS.values()) <= reasons.CANONICAL_REASONS
  assert not set(reasons.PTZ_REASON_DETAILS) & set(reasons.DWELL_REASON_DETAILS)
  with pytest.raises(KeyError):
    reasons.canonical_reason("unknown_detail")


def test_schema_enums_match_reason_sets():
  props = SCHEMA_DOC["definitions"]["pose_context"]["properties"]
  assert set(props["invalid_reason"]["enum"]) == reasons.CANONICAL_REASONS
  assert set(props["reason_detail"]["enum"]) == set(reasons.PTZ_REASON_DETAILS)


# --- quality -------------------------------------------------------------------------------

def test_quality_scores():
  assert temporal_score(0.1, 0.05, 0.5) == pytest.approx(0.7)
  assert temporal_score(0.6, 0.0, 0.5) == 0.0
  assert temporal_score(-1.0, 0.0, 0.5) == 1.0
  assert calibration_score(0.0, 2.0) == 1.0
  assert calibration_score(2.0, 2.0) == pytest.approx(math.exp(-0.5))
  assert score(0.5, 0.8) == pytest.approx(0.4)
  with pytest.raises(ValueError):
    temporal_score(0.1, 0.0, 0.0)
  with pytest.raises(ValueError):
    calibration_score(1.0, 0.0)


# --- configuration -------------------------------------------------------------------------

def test_consumer_config_valid_and_extra_keys_ignored():
  config = load_consumer_config({**CONSUMER_CONFIG, "poll_interval_s": 0.2})
  assert config.max_pose_age_s == 0.5
  dwell = DwellConfig.from_consumer_config(config)
  assert dwell.max_detection_pipeline_latency_ns == 1_000_000_000
  assert dwell.max_detection_timestamp_uncertainty_ns == 50_000_000


@pytest.mark.parametrize("key,value", [
  ("max_pose_age_s", None),
  ("max_pose_age_s", 0.0),
  ("max_clock_offset_s", -0.1),
  ("max_detection_pipeline_latency_s", float("inf")),
  ("max_detection_timestamp_uncertainty_s", -0.001),
  ("max_detection_timestamp_uncertainty_s", float("nan")),
  ("max_pose_age_s", True),
  ("max_pose_age_s", "0.5"),
])
def test_consumer_config_rejected(key, value):
  values = dict(CONSUMER_CONFIG)
  values[key] = value
  with pytest.raises(PositioningConfigError):
    load_consumer_config(values)


def test_consumer_config_zero_detection_uncertainty_allowed():
  load_consumer_config({**CONSUMER_CONFIG, "max_detection_timestamp_uncertainty_s": 0.0})


# --- payload guards ------------------------------------------------------------------------

def test_guards_accept_design_examples():
  validate_pose_context_payload(VALID_POSE)
  validate_pose_context_payload(INVALID_POSE)
  check_payload_size(json.dumps(VALID_POSE))


def test_guard_rejects_oversized_payload():
  check_payload_size(b"x" * MAX_POSE_CONTEXT_BYTES)
  with pytest.raises(PoseContextGuardError):
    check_payload_size(b"x" * (MAX_POSE_CONTEXT_BYTES + 1))


def _with_matrix(matrix):
  payload = copy.deepcopy(VALID_POSE)
  payload["pose"]["matrix_4x4"] = matrix
  return payload


@pytest.mark.parametrize("matrix", [
  [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, float("nan")], [0, 0, 0, 1]],
  [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, float("inf")], [0, 0, 0, 1]],
  [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
  [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]],
  [[2, 0, 0, 0], [0, 2, 0, 0], [0, 0, 2, 0], [0, 0, 0, 1]],
  [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]],
  [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 1]],
  [[True, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
])
def test_guard_rejects_bad_matrix(matrix):
  with pytest.raises(PoseContextGuardError):
    validate_pose_context_payload(_with_matrix(matrix))


def test_guard_rejects_non_finite_scalars():
  payload = copy.deepcopy(VALID_POSE)
  payload["sample_age_s"] = float("nan")
  with pytest.raises(PoseContextGuardError):
    validate_pose_context_payload(payload)


def test_guard_accepts_rotated_rigid_matrix():
  angle = np.radians(37.0)
  matrix = [[np.cos(angle), -np.sin(angle), 0, 1.5], [np.sin(angle), np.cos(angle), 0, 2.0],
            [0, 0, 1, 4.0], [0, 0, 0, 1]]
  validate_pose_context_payload(_with_matrix([[float(v) for v in row] for row in matrix]))


# --- MQTT schemas --------------------------------------------------------------------------

def test_schema_accepts_design_examples(schema):
  assert schema.validateMessage("pose_context", VALID_POSE, check_format=True)
  assert schema.validateMessage("pose_context", INVALID_POSE, check_format=True)
  assert schema.validateMessage("positioning_status", STATUS, check_format=True)


def _mutated(base, **changes):
  payload = copy.deepcopy(base)
  for key, value in changes.items():
    if value is ...:
      payload.pop(key, None)
    else:
      payload[key] = value
  return payload


POSE_SCHEMA_INVALID = {
  "valid_without_pose": _mutated(VALID_POSE, pose=...),
  "valid_without_quality": _mutated(VALID_POSE, quality=...),
  "valid_with_invalid_reason": _mutated(VALID_POSE, invalid_reason="invalid_pose"),
  "valid_with_reason_detail": _mutated(VALID_POSE, reason_detail="moving"),
  "invalid_with_pose": _mutated(INVALID_POSE, pose=VALID_POSE["pose"]),
  "invalid_without_reason": _mutated(INVALID_POSE, invalid_reason=...),
  "unknown_reason": _mutated(INVALID_POSE, invalid_reason="other"),
  "unknown_reason_detail": _mutated(INVALID_POSE, reason_detail="dwell_incomplete"),
  "unknown_motion_state": _mutated(INVALID_POSE, motion_state="parked"),
  "schema_version_2": _mutated(VALID_POSE, schema_version=2),
  "negative_sequence": _mutated(VALID_POSE, sequence=-1),
  "missing_valid_until": _mutated(VALID_POSE, valid_until=...),
  "extra_field": _mutated(VALID_POSE, extra=1),
  "bad_timestamp": _mutated(VALID_POSE, timestamp="yesterday"),
  "valid_not_boolean": _mutated(VALID_POSE, valid=1),
  "matrix_3_rows": _mutated(VALID_POSE, pose={**VALID_POSE["pose"],
                                               "matrix_4x4": VALID_POSE["pose"]["matrix_4x4"][:3]}),
  "column_major": _mutated(VALID_POSE, pose={**VALID_POSE["pose"], "matrix_layout": "column_major"}),
  "score_above_one": _mutated(VALID_POSE, quality={**VALID_POSE["quality"], "score": 1.5}),
}


@pytest.mark.parametrize("name", sorted(POSE_SCHEMA_INVALID))
def test_pose_context_schema_rejects(schema, name):
  assert not schema.validateMessage("pose_context", POSE_SCHEMA_INVALID[name], check_format=True)


@pytest.mark.parametrize("payload", [
  _mutated(STATUS, status="degraded"),
  _mutated(STATUS, resolver_id=...),
  _mutated(STATUS, extra=True),
])
def test_positioning_status_schema_rejects(schema, payload):
  assert not schema.validateMessage("positioning_status", payload, check_format=True)


def _contains_key(node, key):
  if isinstance(node, dict):
    return key in node or any(_contains_key(v, key) for v in node.values())
  if isinstance(node, list):
    return any(_contains_key(v, key) for v in node)
  return False


@pytest.mark.parametrize("name", ["pose_context", "positioning_status"])
def test_fragments_are_draft4_and_self_contained(name):
  """Phase 5 copies these fragments unchanged into the RapidJSON (draft-04) Tracker schema."""
  fragment = copy.deepcopy(SCHEMA_DOC["definitions"][name])
  for keyword in ("$ref", "const", "if", "then", "else", "$defs"):
    assert not _contains_key(fragment, keyword), keyword
  fragment["$schema"] = "http://json-schema.org/draft-04/schema#"
  jsonschema.Draft4Validator.check_schema(fragment)
  validator = jsonschema.Draft4Validator(fragment)
  if name == "pose_context":
    assert validator.is_valid(VALID_POSE) and validator.is_valid(INVALID_POSE)
    for payload in POSE_SCHEMA_INVALID.values():
      if payload is not POSE_SCHEMA_INVALID["bad_timestamp"]:
        assert not validator.is_valid(payload)
  else:
    assert validator.is_valid(STATUS)


# --- dwell API edge cases not covered by the shared fixture --------------------------------

def test_timestamp_parsing_is_exact_and_requires_timezone():
  assert parse_timestamp_ns("1970-01-01T00:00:01.000001Z") == 1_000_001_000
  assert parse_timestamp_ns("1970-01-01T01:00:00+01:00") == 0
  with pytest.raises(ValueError):
    parse_timestamp_ns("2026-10-01T10:00:00")


def test_status_for_other_resolver_is_ignored_and_calibration_change_resets():
  config = DwellConfig.from_consumer_config(load_consumer_config(CONSUMER_CONFIG))
  tracker = DwellTracker("cam", "positioning", config)
  tracker.on_status("positioning", "online", 1)
  tracker.on_pose(PoseSnapshot("cam", 1, 5, 10, 0, True, "stationary", "v1", "scene:a"))
  tracker.on_status("other", "offline", 2)
  assert tracker.stationary_since_ns == 5
  tracker.set_expected_calibration_version("v2")
  assert tracker.stationary_since_ns is None
