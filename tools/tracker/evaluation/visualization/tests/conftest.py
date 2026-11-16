# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared scenario directories for the visualization tests."""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "target_born_moving"
TRACK_UUID = "6741d4a0-db7c-4b7a-a44f-c0af7b5d97ba"


@pytest.fixture(name="recording")
def fixture_recording(tmp_path):
  """Copy of the recorded scenario: 11 frames at 10 fps, one vehicle, all four files."""
  directory = tmp_path / "recording"
  shutil.copytree(FIXTURE, directory)
  return directory


@pytest.fixture(name="tracker_output")
def fixture_tracker_output(tmp_path):
  """Real tracker output: translation-only ground truth, UUID track ids, no estimator."""
  directory = tmp_path / "tracker_output"
  directory.mkdir()
  truth, tracks = [], []
  for frame in range(20):
    timestamp = f"2014-09-08T04:00:{frame // 10:02d}.{frame % 10}00Z"
    x = 0.1 * frame
    truth.append({"timestamp": timestamp, "objects": [
      {"id": 0, "category": "person", "translation": [x, 0.0, 0.0]}]})
    tracks.append({"id": "scene", "name": "scene", "timestamp": timestamp, "objects": [
      {"id": TRACK_UUID, "category": "person", "translation": [x, 0.2, 0.0],
       "velocity": [1.0, 0.0, 0.0], "size": [0.5, 0.5, 1.7], "rotation": [0.0, 0.0, 0.0, 1.0]}]})
  for name, records in (("groundtruth.jsonl", truth), ("tracks.jsonl", tracks)):
    (directory / name).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
  return directory


def timestamp_after(seconds):
  """ISO timestamp `seconds` after 2014-09-08T04:00:00Z, to the millisecond."""
  moment = datetime(2014, 9, 8, 4, tzinfo=timezone.utc) + timedelta(seconds=seconds)
  return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_jsonl(path, records):
  """Write records as JSON lines."""
  path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def iso_timestamp(epoch_seconds):
  """ISO timestamp in microseconds from 1970-01-01T00:00:00Z."""
  moment = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=epoch_seconds)
  return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


@pytest.fixture(name="early_detection")
def fixture_early_detection(tmp_path):
  """Truth object 0 and track "1" at 10 fps from 0.05 s on, and a detection at 0.

  The detection is the earliest timestamp, so times counted from it fall on half frames.
  """
  directory = tmp_path / "early_detection"
  directory.mkdir()
  truth, tracks = [], []
  for frame in range(11):
    timestamp = timestamp_after(0.05 + 0.1 * frame)
    x = 0.1 * frame
    truth.append({"timestamp": timestamp, "objects": [
      {"id": 0, "category": "person", "translation": [x, 0.0, 0.0]}]})
    tracks.append({"timestamp": timestamp, "objects": [
      {"id": "1", "category": "person", "translation": [x, 0.2, 0.0]}]})
  detections = [{"id": "camera", "timestamp": timestamp_after(0.0), "objects": {
    "person": [{"id": 0, "translation": [0.0, 0.0, 0.0], "size": [0.5, 0.5, 1.7]}]}}]
  for name, records in (("groundtruth.jsonl", truth), ("tracks.jsonl", tracks),
                        ("detections.jsonl", detections)):
    (directory / name).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
  return directory


@pytest.fixture(name="climbing_recording")
def fixture_climbing_recording(tmp_path):
  """Scenario with vertical motion: vehicle moving +x at 2 m/s while climbing at vz=0.5 m/s.

  11 frames at 10 fps (0.1 s intervals), 11-20 range, z = 0.5*t.
  """
  directory = tmp_path / "climbing_recording"
  directory.mkdir()

  truth, detections_list, tracks_list = [], [], []
  for frame in range(11):
    frame_num = frame + 11
    t = frame * 0.1
    timestamp = iso_timestamp(t)
    x = 2.0 * t  # 2 m/s in x
    z = 0.5 * t  # climbing at 0.5 m/s
    # groundtruth.jsonl
    truth.append({
      "timestamp": timestamp,
      "objects": [{
        "id": 1,
        "category": "vehicle",
        "translation": [x, 0.0, z],
        "size": [4.5, 1.8, 1.5],
        "rotation": [0.0, 0.0, 0.0, 1.0],
        "velocity": [2.0, 0.0, 0.5],
        "truth": {"speed": 2.0, "yaw_rate": 0.0, "acceleration": 0.0}
      }]
    })
    # detections.jsonl
    detections_list.append({
      "id": "camera",
      "timestamp": timestamp,
      "objects": {
        "vehicle": [{
          "id": 1,
          "translation": [x, 0.0, z],
          "size": [4.5, 1.8, 1.5]
        }]
      }
    })
    # tracks.jsonl
    tracks_list.append({
      "id": "MotionScenarioTest.ClimbingVehicle",
      "name": "MotionScenarioTest.ClimbingVehicle",
      "timestamp": timestamp,
      "objects": [{
        "id": "1",
        "category": "vehicle",
        "translation": [x, 0.0, z],
        "velocity": [2.0, 0.0, 0.5],
        "size": [4.5, 1.8, 1.5],
        "rotation": [0.0, 0.0, 0.0, 1.0]
      }]
    })

  write_jsonl(directory / "groundtruth.jsonl", truth)
  write_jsonl(directory / "detections.jsonl", detections_list)
  write_jsonl(directory / "tracks.jsonl", tracks_list)

  # estimator.jsonl: 13-state config with state_names including vz
  config = {
    "type": "config",
    "track_id": "1",
    "motion_models": ["CV", "CA", "CTRV"],
    "state_names": ["x", "y", "vx", "vy", "ax", "ay", "z", "vz", "length", "width", "height",
                    "yaw", "yaw_rate"],
    "measurement_names": ["x", "y", "z", "length", "width", "height", "yaw"],
  }
  estimator_records = [config]
  for frame in range(11):
    t = frame * 0.1
    timestamp = iso_timestamp(t)
    x = 2.0 * t
    z = 0.5 * t
    # State: [x, y, vx, vy, ax, ay, z, vz, length, width, height, yaw, yaw_rate]
    state = [x, 0.0, 2.0, 0.0, 0.0, 0.0, z, 0.5, 4.5, 1.8, 1.5, 0.0, 0.0]
    # Covariance: 13x13 diagonal with reasonable values
    cov_diag = [0.2, 0.2, 0.05, 0.05, 0.1, 0.1, 0.2, 0.05, 0.2, 0.2, 0.2, 0.05, 0.01]
    P = [[cov_diag[i] if i == j else 0.0 for j in range(13)] for i in range(13)]
    # Measurement predictions (null for first frame, 7 values after)
    z_pred = None if frame == 0 else [x, 0.0, z, 4.5, 1.8, 1.5, 0.0]
    S = None if frame == 0 else [[0.4 if i == j else 0.0 for j in range(7)] for i in range(7)]

    step = {
      "type": "step",
      "track_id": "1",
      "timestamp": timestamp,
      "mu": [0.34, 0.33, 0.33],
      "x": state,
      "P": P,
      "z_pred": z_pred,
      "S": S
    }
    estimator_records.append(step)

  write_jsonl(directory / "estimator.jsonl", estimator_records)
  return directory


@pytest.fixture(name="legacy_estimator_recording")
def fixture_legacy_estimator_recording(recording, tmp_path):
  """Copy of `recording` fixture with estimator.jsonl rewritten to 12-state (no vz).

  Only created if the recording fixture already has 13-state estimator.jsonl.
  """
  directory = tmp_path / "legacy_recording"
  directory.mkdir()

  # Copy the three JSONL files (no estimator yet)
  for name in ("groundtruth.jsonl", "detections.jsonl", "tracks.jsonl"):
    shutil.copy(recording / name, directory / name)

  # Load and transform the 13-state estimator.jsonl to 12-state
  estimator_path = recording / "estimator.jsonl"
  if not estimator_path.is_file():
    # No estimator; return empty directory
    return directory

  records = []
  for line in estimator_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
      continue
    record = json.loads(line)
    if record.get("type") == "config":
      # Remove "vz" from state_names (originally at index 7)
      state_names = record.get("state_names", [])
      if "vz" in state_names:
        state_names = [s for s in state_names if s != "vz"]
        record["state_names"] = state_names
      records.append(record)
    elif record.get("type") == "step":
      # Remove index 7 (vz position) and corresponding rows/columns from P
      x = record.get("x", [])
      P = record.get("P", [])
      z_pred = record.get("z_pred")
      S = record.get("S")

      # Remove vz (index 7) from state vector
      if len(x) > 7:
        x = x[:7] + x[8:]
        record["x"] = x

      # Remove row 7 and column 7 from covariance
      if P and len(P) > 7:
        P = [row[:7] + row[8:] for row in P]
        P = P[:7] + P[8:]
        record["P"] = P

      # z_pred stays the same (7 measurements)
      # S stays the same (7x7)
      records.append(record)
    else:
      records.append(record)

  write_jsonl(directory / "estimator.jsonl", records)
  return directory
