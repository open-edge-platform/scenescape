# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared scenario directories for the visualization tests."""

import json
import shutil
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
