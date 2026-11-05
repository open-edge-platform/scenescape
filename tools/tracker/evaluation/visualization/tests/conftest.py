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
