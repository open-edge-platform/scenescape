# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for loading robot-vision scenario recordings.

fixtures/target_born_moving is recorder output of MotionScenarioTest.TargetBornMovingAcquiresSpeed
(controller/src/robot_vision/test). Regenerate with:
  RV_SCENARIO_DIR=<dir> RobotVisionTests \
    --gtest_filter=MotionScenarioTest.TargetBornMovingAcquiresSpeed
"""

import json
import math
import shutil
import sys
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from visualization.scenario_data import (  # noqa: E402 pylint: disable=wrong-import-position
  PIPELINE_RUN_FILES,
  align_track_to_truth,
  frame_rate,
  load_scenario,
  match_tracks_to_truth,
  yaw_from_quaternion,
)

TESTS_DIR = Path(__file__).parent
FIXTURE = TESTS_DIR / "fixtures" / "target_born_moving"
REPO_ROOT = TESTS_DIR.parents[4]


def write_jsonl(path, records):
  """Write records as JSON lines."""
  path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def validator(schema_path):
  """JSON schema validator for a schema file, in the draft its $schema declares."""
  schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
  return jsonschema.validators.validator_for(schema)(schema)


@pytest.mark.parametrize("file_name, schema_path", [
  ("tracks.jsonl", REPO_ROOT / "tracker" / "schema" / "scene-data.schema.json"),
  ("detections.jsonl", REPO_ROOT / "tracker" / "schema" / "camera-data.schema.json"),
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
  assert trace.state.shape == (11, 13)
  assert trace.covariance.shape == (11, 13, 13)
  assert trace.predicted_measurement_cov.shape == (11, 7, 7)
  assert np.isnan(trace.predicted_measurement[0]).all()
  assert np.isfinite(trace.predicted_measurement[1:]).all()
  np.testing.assert_allclose(trace.model_probability.sum(axis=1), 1.0)
  np.testing.assert_array_equal(trace.state[:, trace.state_index("vx")], scenario.tracks["vx"])
  np.testing.assert_array_equal(trace.state[:, trace.state_index("vz")], scenario.tracks["vz"])


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


def test_matches_tracks_to_truth(tmp_path):
  """Tracks pair with the nearest ground-truth object, whatever their ids."""
  scenario = load_scenario(FIXTURE)
  assert frame_rate(scenario.ground_truth) == pytest.approx(10.0)
  assert match_tracks_to_truth(scenario) == [("1", "1")]

  tracks = (FIXTURE / "tracks.jsonl").read_text(encoding="utf-8").replace('"id":"1"', '"id":"uuid"')
  (tmp_path / "tracks.jsonl").write_text(tracks, encoding="utf-8")
  shutil.copy(FIXTURE / "groundtruth.jsonl", tmp_path)
  assert match_tracks_to_truth(load_scenario(tmp_path)) == [("uuid", "1")]

  (tmp_path / "groundtruth.jsonl").unlink()
  assert not match_tracks_to_truth(load_scenario(tmp_path))


@pytest.mark.parametrize("fps", [None, 10.0])
def test_matches_tracks_when_an_earlier_detection_sets_the_time_origin(early_detection, fps):
  """Frames count from the first track or truth sample, as in the evaluators, not a detection.

  Without an explicit rate, float noise in the derived rate happens to break the rounding ties.
  """
  assert match_tracks_to_truth(load_scenario(early_detection), fps) == [("1", "0")]

  (early_detection / "detections.jsonl").unlink()
  assert match_tracks_to_truth(load_scenario(early_detection), fps) == [("1", "0")]


def test_loads_pipeline_run_directory(tmp_path):
  """An evaluation pipeline run directory loads like a scenario directory without estimator."""
  for name, path in PIPELINE_RUN_FILES.items():
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / name, tmp_path / path)

  run = load_scenario(tmp_path)
  recording = load_scenario(FIXTURE)

  for table in ("ground_truth", "detections", "tracks"):
    pd.testing.assert_frame_equal(getattr(run, table), getattr(recording, table))
  assert not run.estimator
  assert run.files == {name: tmp_path / path for name, path in PIPELINE_RUN_FILES.items()}


def test_detections_are_in_the_scene_only_for_recordings(tmp_path):
  """Recorder detections have scene coordinates and ground-truth ids; a pipeline run's do not."""
  for name, path in PIPELINE_RUN_FILES.items():
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / name, tmp_path / path)

  assert load_scenario(FIXTURE).detections_in_scene
  assert not load_scenario(tmp_path).detections_in_scene


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


def test_loads_climbing_recording(climbing_recording):
  """Climbing recording loads with vz and z vertical motion data."""
  scenario = load_scenario(climbing_recording)

  # Ground truth
  truth = scenario.ground_truth
  assert len(truth) == 11
  assert scenario.object_ids == ["1"]
  assert set(truth["category"]) == {"vehicle"}
  assert truth["t"].iloc[0] == 0.0
  assert truth["t"].iloc[-1] == pytest.approx(1.0)
  # Check z and vz follow the expected pattern: z = 0.5*t, vz = 0.5 m/s
  for i, z in enumerate(truth["z"]):
    t = i * 0.1
    assert z == pytest.approx(0.5 * t, abs=1e-6)
  assert truth["vz"].iloc[0] == pytest.approx(0.5, abs=1e-6)
  np.testing.assert_allclose(truth["vz"].to_numpy(), 0.5, atol=1e-6)

  # Detections
  detections = scenario.detections
  assert len(detections) == 11
  assert set(detections["sensor_id"]) == {"camera"}
  assert set(detections["object_id"]) == {"1"}
  # Check detections also have z
  for i, z in enumerate(detections["z"]):
    t = i * 0.1
    assert z == pytest.approx(0.5 * t, abs=1e-6)

  # Tracks
  assert scenario.track_ids == ["1"]
  assert len(scenario.tracks) == 11
  # Check z and vz in tracks
  for i, z in enumerate(scenario.tracks["z"]):
    t = i * 0.1
    assert z == pytest.approx(0.5 * t, abs=1e-6)
  assert scenario.tracks["vz"].iloc[0] == pytest.approx(0.5, abs=1e-6)

  # Estimator trace
  trace = scenario.estimator["1"]
  assert trace.motion_models == ["CV", "CA", "CTRV"]
  assert trace.has_state("vz")
  assert trace.state_index("vz") == 7
  assert trace.state.shape == (11, 13)
  assert trace.covariance.shape == (11, 13, 13)
  # Check that vz in the state vector matches tracks
  np.testing.assert_array_almost_equal(trace.state[:, trace.state_index("vz")],
                                       scenario.tracks["vz"].values, decimal=5)

  # Scenario has_vertical_motion should be True
  assert scenario.has_vertical_motion


def test_planar_recording_has_no_vertical_motion(recording):
  """The planar fixture has z=0 and vz=NaN or 0, so has_vertical_motion is False."""
  scenario = load_scenario(recording)
  assert not scenario.has_vertical_motion


def test_tracker_output_has_no_vertical_motion(tracker_output):
  """Tracker output (no estimator) with z=0 has has_vertical_motion False."""
  scenario = load_scenario(tracker_output)
  assert not scenario.has_vertical_motion


def test_legacy_12_state_recording_loads(legacy_estimator_recording):
  """A recording with 12-state estimator (no vz) loads and behaves correctly."""
  scenario = load_scenario(legacy_estimator_recording)

  trace = scenario.estimator["1"]
  # The trace should not have vz in state_names
  assert not trace.has_state("vz")
  assert trace.has_state("z")
  assert trace.state.shape == (11, 12)  # 12 states now
  assert trace.covariance.shape == (11, 12, 12)

  # state_index("vz") should raise ValueError
  with pytest.raises(ValueError):
    trace.state_index("vz")


def test_trace_has_state():
  """EstimatorTrace.has_state() returns True only for states in config."""
  from visualization.scenario_data import EstimatorTrace

  config_13 = {"state_names": ["x", "y", "vx", "vy", "ax", "ay", "z", "vz",
                               "length", "width", "height", "yaw", "yaw_rate"]}
  trace_13 = EstimatorTrace(
    config=config_13,
    t=np.array([0.0]),
    model_probability=np.array([[0.5, 0.3, 0.2]]),
    state=np.zeros((1, 13)),
    covariance=np.zeros((1, 13, 13)),
    predicted_measurement=np.zeros((1, 7)),
    predicted_measurement_cov=np.zeros((1, 7, 7)),
  )
  assert trace_13.has_state("vz")
  assert trace_13.has_state("x")
  assert not trace_13.has_state("foo")

  config_12 = {"state_names": ["x", "y", "vx", "vy", "ax", "ay",
                               "z", "length", "width", "height", "yaw", "yaw_rate"]}
  trace_12 = EstimatorTrace(
    config=config_12,
    t=np.array([0.0]),
    model_probability=np.array([[0.5, 0.3, 0.2]]),
    state=np.zeros((1, 12)),
    covariance=np.zeros((1, 12, 12)),
    predicted_measurement=np.zeros((1, 7)),
    predicted_measurement_cov=np.zeros((1, 7, 7)),
  )
  assert not trace_12.has_state("vz")
  assert trace_12.has_state("z")

