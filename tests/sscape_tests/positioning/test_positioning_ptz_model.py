# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ptz_calibration v1: JSON Schema and the Python loader accept/reject the same payloads."""

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from positioning.ptz_model import PTZCalibrationError, load_ptz_model

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads(
  (REPO_ROOT / "docs" / "user-guide" / "api-docs" / "positioning" / "v1"
   / "ptz_calibration.schema.json").read_text())
VALID = json.loads(
  (REPO_ROOT / "tests" / "data" / "ptz" / "provisional_pose_math.json").read_text())["ptz_calibration"]
VALIDATOR = jsonschema.Draft7Validator(SCHEMA)


def _mutate(path, value=None, delete=False):
  payload = copy.deepcopy(VALID)
  target = payload
  for key in path[:-1]:
    target = target[key]
  if delete:
    del target[path[-1]]
  else:
    target[path[-1]] = value
  return payload


def test_schema_is_valid_draft7():
  jsonschema.Draft7Validator.check_schema(SCHEMA)


def test_valid_payload_accepted_by_schema_and_loader():
  VALIDATOR.validate(VALID)
  model = load_ptz_model(VALID)
  assert model.calibration_version == VALID["calibration_version"]
  assert model.composition_order == ("pan", "home", "tilt")
  assert model.pan.backlash == ((-0.2366, 0.37), (-0.0366, 0.01), (0.1634, 1.68))
  assert model.tilt.backlash == 2.73
  assert model.reprojection_rms_px == 1.2
  assert sum(c * c for c in model.pan.axis) == pytest.approx(1.0)


# Rejected by both the JSON Schema and the loader.
SCHEMA_AND_LOADER_INVALID = {
  "missing_calibration_version": _mutate(["calibration_version"], delete=True),
  "unknown_parameterization": _mutate(["parameterization_version"], "v2"),
  "scale_field_forbidden": _mutate(["axes", "pan", "scale"], 153.36),
  "invert_field_forbidden": _mutate(["axes", "tilt", "invert"], True),
  "curve_too_short": _mutate(["axes", "pan", "curve"], [0.0]),
  "bad_frame": _mutate(["axes", "pan", "frame"], "world"),
  "bad_approach": _mutate(["axes", "tilt", "approach_direction"], "up"),
  "negative_backlash": _mutate(["axes", "tilt", "backlash"], -0.1),
  "backlash_node_not_pair": _mutate(["axes", "pan", "backlash"], [[0.1, 0.2, 0.3]]),
  "duplicate_composition_element": _mutate(["composition_order"], ["pan", "pan", "home"]),
  "composition_missing_tilt": _mutate(["composition_order"], ["pan", "home"]),
  "missing_quality": _mutate(["quality"], delete=True),
  "missing_tilt_axis": _mutate(["axes", "tilt"], delete=True),
  "axis_wrong_length": _mutate(["axes", "pan", "axis"], [0.0, 1.0]),
  "string_number": _mutate(["settle_interval_s"], "0.6"),
  "missing_position_space_uri": _mutate(["position_space", "uri"], delete=True),
  "zero_settle_threshold": _mutate(["settle_angular_threshold_deg"], 0),
  "zero_settle_interval": _mutate(["settle_interval_s"], 0),
  "zero_backlash_home_tolerance": _mutate(["axes", "pan", "backlash_home_tolerance_deg"], 0),
  "zero_backlash_history": _mutate(["axes", "tilt", "backlash_history_s"], 0),
}

# Semantic checks only the loader can enforce.
LOADER_ONLY_INVALID = {
  "settle_threshold_exceeds_travel": _mutate(["settle_angular_threshold_deg"], 1000.0),
  "home_tolerance_exceeds_travel": _mutate(["axes", "tilt", "backlash_home_tolerance_deg"], 1000.0),
  "axis_not_unit": _mutate(["axes", "pan", "axis"], [0.5, 0.5, 0.5]),
  "frame_inconsistent_with_order": _mutate(["axes", "tilt", "frame"], "world_home"),
  "empty_range": _mutate(["position_space", "pan_max"], -1.0),
  "home_outside_range": _mutate(["axes", "tilt", "home_position"], 1.5),
  "constant_curve": _mutate(["axes", "pan", "curve"], [1.0, 0.0, 0.0]),
  "duplicate_backlash_positions": _mutate(["axes", "pan", "backlash"], [[0.1, 1.0], [0.1, 2.0]]),
}


@pytest.mark.parametrize("name", sorted(SCHEMA_AND_LOADER_INVALID))
def test_invalid_rejected_by_schema_and_loader(name):
  payload = SCHEMA_AND_LOADER_INVALID[name]
  assert not VALIDATOR.is_valid(payload)
  with pytest.raises(PTZCalibrationError):
    load_ptz_model(payload)


@pytest.mark.parametrize("name", sorted(LOADER_ONLY_INVALID))
def test_semantic_invalid_rejected_by_loader(name):
  payload = LOADER_ONLY_INVALID[name]
  assert VALIDATOR.is_valid(payload)
  with pytest.raises(PTZCalibrationError):
    load_ptz_model(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_non_finite_or_bool_rejected(value):
  with pytest.raises(PTZCalibrationError):
    load_ptz_model(_mutate(["axes", "pan", "home_position"], value))


def test_provenance_optional():
  load_ptz_model(_mutate(["provenance"], delete=True))
