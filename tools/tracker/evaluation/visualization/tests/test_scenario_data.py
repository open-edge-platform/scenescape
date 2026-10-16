# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for loading robot-vision scenario recordings.

fixtures/target_born_moving is recorder output of MotionScenarioTest.TargetBornMovingAcquiresSpeed
(controller/src/robot_vision/test). Regenerate with:
  RV_SCENARIO_DIR=<dir> RobotVisionTests \
    --gtest_filter=MotionScenarioTest.TargetBornMovingAcquiresSpeed

schema/camera-data.schema.json is a copy of tracker/schema/camera-data.schema.json from branch
ITEP-97104_tracker_3d_detections (3D detections); use the tracker schema once that is merged.
"""

import json
import math
import shutil
import sys
from pathlib import Path

import jsonschema
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from visualization.scenario_data import (  # noqa: E402 pylint: disable=wrong-import-position
  align_track_to_truth,
  load_scenario,
  yaw_from_quaternion,
)

TESTS_DIR = Path(__file__).parent
FIXTURE = TESTS_DIR / "fixtures" / "target_born_moving"
REPO_ROOT = TESTS_DIR.parents[4]


def write_jsonl(path, records):
  """Write records as JSON lines."""
  path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def validator(schema_path):
  """JSON schema validator for a schema file."""
  return jsonschema.Draft202012Validator(json.loads(Path(schema_path).read_text(encoding="utf-8")))


@pytest.mark.parametrize("file_name, schema_path", [
  ("tracks.jsonl", REPO_ROOT / "tracker" / "schema" / "scene-data.schema.json"),
  ("detections.jsonl", TESTS_DIR / "schema" / "camera-data.schema.json"),
])
def test_recorded_files_match_schemas(file_name, schema_path):
  """Recorded tracks and detections follow the canonical schemas."""
  schema = validator(schema_path)
  lines = (FIXTURE / file_name).read_text(encoding="utf-8").splitlines()
  assert lines
  for number, line in enumerate(lines, 1):
    errors = [error.message for error in schema.iter_errors(json.loads(line))]
    assert not errors, f"{file_name}:{number}: {errors}"


def test_loads_recorded_scenario():
  """All four recorded files load into tables and an estimator trace."""
  scenario = load_scenario(FIXTURE)

  truth = scenario.ground_truth
  assert len(truth) == 11
  assert scenario.object_ids == ["1"]
  assert set(truth["category"]) == {"vehicle"}
  assert truth["t"].iloc[0] == 0.0
  assert truth["t"].iloc[-1] == pytest.approx(1.0)
  assert truth["speed"].tolist() == [10.0] * 11
  assert truth["yaw"].tolist() == [0.0] * 11
  assert truth["length"].iloc[0] == 4.5

  detections = scenario.detections
  assert len(detections) == 11
  assert set(detections["sensor_id"]) == {"camera"}
  assert set(detections["object_id"]) == {"1"}
  assert detections["yaw"].isna().all()

  assert scenario.track_ids == ["1"]
  assert len(scenario.tracks) == 11

  trace = scenario.estimator["1"]
  assert trace.motion_models == ["CV", "CA", "CTRV"]
  assert trace.t.tolist() == scenario.tracks["t"].tolist()
  assert trace.state.shape == (11, 12)
  assert trace.covariance.shape == (11, 12, 12)
  assert trace.predicted_measurement_cov.shape == (11, 7, 7)
  assert np.isnan(trace.predicted_measurement[0]).all()
  assert np.isfinite(trace.predicted_measurement[1:]).all()
  np.testing.assert_allclose(trace.model_probability.sum(axis=1), 1.0)
  np.testing.assert_array_equal(trace.state[:, trace.state_index("vx")], scenario.tracks["vx"])


def test_loads_several_objects_and_sensors(tmp_path):
  """Several objects, optional fields, orientation and pixel-only detections."""
  quarter_turn = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
  write_jsonl(tmp_path / "groundtruth.jsonl", [
    {"timestamp": "2026-01-01T00:00:01.000000Z", "objects": [
      {"id": 1, "category": "person", "translation": [1.0, 2.0, 0.0]},
      {"id": "b", "category": "vehicle", "translation": [5.0, 6.0, 0.0], "rotation": quarter_turn,
       "velocity": [0.0, 3.0, 0.0], "size": [4.5, 1.8, 1.5]},
    ]},
  ])
  write_jsonl(tmp_path / "detections.jsonl", [
    {"id": "lidar", "timestamp": "2026-01-01T00:00:00.500000Z", "objects": {
      "vehicle": [{"id": 7, "translation": [5.1, 6.1, 0.0], "size": [4.4, 1.7, 1.4],
                   "rotation": quarter_turn}],
      "person": [{"bounding_box_px": {"x": 0, "y": 0, "width": 10, "height": 20}}],
    }},
  ])

  scenario = load_scenario(tmp_path)

  assert scenario.object_ids == ["1", "b"]
  person, vehicle = (scenario.ground_truth.iloc[i] for i in range(2))
  assert person["t"] == 0.5
  assert math.isnan(person["yaw"]) and math.isnan(person["speed"]) and math.isnan(person["length"])
  assert vehicle["yaw"] == pytest.approx(math.pi / 2)
  assert vehicle["speed"] == 3.0
  assert len(scenario.detections) == 1
  detection = scenario.detections.iloc[0]
  assert (detection["t"], detection["sensor_id"], detection["object_id"]) == (0.0, "lidar", "7")
  assert detection["yaw"] == pytest.approx(math.pi / 2)
  assert scenario.tracks.empty and not scenario.estimator


def test_aligns_track_to_truth(tmp_path):
  """Track rows get the ground truth at the same time, NaN while coasting past its end."""
  shutil.copy(FIXTURE / "groundtruth.jsonl", tmp_path)
  tracks = (FIXTURE / "tracks.jsonl").read_text(encoding="utf-8").splitlines()
  coast = json.loads(tracks[-1])
  coast["timestamp"] = "1970-01-01T00:00:01.500000Z"
  (tmp_path / "tracks.jsonl").write_text("\n".join(tracks + [json.dumps(coast)]) + "\n",
                                         encoding="utf-8")

  aligned = align_track_to_truth(load_scenario(tmp_path), "1")

  assert len(aligned) == 12
  assert aligned["x_gt"].iloc[0] == aligned["x"].iloc[0] == 0.0
  assert aligned["x_gt"].iloc[10] == pytest.approx(10.0)
  assert aligned["x_gt"].iloc[:11].notna().all()
  assert math.isnan(aligned["x_gt"].iloc[11])

  (tmp_path / "groundtruth.jsonl").unlink()
  assert align_track_to_truth(load_scenario(tmp_path), "1")["x_gt"].isna().all()


def test_rejects_directory_without_scenario_files(tmp_path):
  """A directory without any scenario file is an error."""
  with pytest.raises(FileNotFoundError):
    load_scenario(tmp_path)


@pytest.mark.parametrize("yaw", [0.0, 1.0, -2.5, math.pi - 1e-9])
def test_yaw_from_quaternion(yaw):
  """Yaw round-trips through a z-rotation quaternion."""
  assert yaw_from_quaternion([0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]) == pytest.approx(yaw)


def test_yaw_from_missing_quaternion_is_nan():
  """No rotation gives NaN yaw."""
  assert math.isnan(yaw_from_quaternion(None))
