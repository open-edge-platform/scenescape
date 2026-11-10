# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared timeline helpers."""

import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

# Add evaluation root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.timeline import (
  parse_timestamp,
  deduplicate_frames_by_timestamp,
  require_fps,
  timestamp_to_frame,
  reference_timestamp,
  resolve_ground_truth_path,
)


def _ts(index, interval_ms=100):
  total_ms = index * interval_ms
  seconds = total_ms // 1000
  millis = total_ms % 1000
  return f"2024-01-01T00:00:{seconds:02d}.{millis:03d}Z"


class TestParseTimestamp:
  def test_parses_z_suffix(self):
    dt = parse_timestamp("2024-01-01T00:00:01.500Z")
    assert dt == datetime(2024, 1, 1, 0, 0, 1, 500000, tzinfo=timezone.utc)


class TestDeduplicate:
  def test_drops_duplicate_timestamps_keeping_first(self):
    frames = [
      {"timestamp": _ts(0), "objects": [{"id": "a"}]},
      {"timestamp": _ts(0), "objects": [{"id": "b"}]},
      {"timestamp": _ts(1), "objects": [{"id": "c"}]},
    ]
    result = deduplicate_frames_by_timestamp(frames)
    assert len(result) == 2
    assert result[0]["objects"][0]["id"] == "a"
    assert result[1]["timestamp"] == _ts(1)


class TestRequireFps:
  def test_returns_configured_value(self):
    assert require_fps(10.0) == 10.0

  def test_raises_when_missing(self):
    with pytest.raises(RuntimeError, match="Frame rate is required"):
      require_fps(None)


class TestTimestampToFrame:
  def test_reference_maps_to_frame_one(self):
    ref = parse_timestamp(_ts(0))
    assert timestamp_to_frame(ref, ref, 10.0) == 1

  def test_rounds_to_nearest_frame(self):
    ref = parse_timestamp(_ts(0))
    assert timestamp_to_frame(parse_timestamp(_ts(3)), ref, 10.0) == 4


class TestReferenceTimestamp:
  def test_returns_min_first_timestamp(self):
    gt = [{"timestamp": _ts(2)}]
    tracker = [{"timestamp": _ts(0)}]
    assert reference_timestamp(gt, tracker) == parse_timestamp(_ts(0))

  def test_ignores_empty_lists(self):
    tracker = [{"timestamp": _ts(5)}]
    assert reference_timestamp([], tracker) == parse_timestamp(_ts(5))

  def test_all_empty_returns_none(self):
    assert reference_timestamp([], []) is None


class TestResolveGroundTruthPath:
  def test_accepts_plain_string(self):
    assert resolve_ground_truth_path("/tmp/gt.jsonl") == "/tmp/gt.jsonl"

  def test_unwraps_single_element_iterator(self):
    assert resolve_ground_truth_path(iter(["/tmp/gt.jsonl"])) == "/tmp/gt.jsonl"

  def test_rejects_non_path_input(self):
    with pytest.raises(RuntimeError, match="file path string"):
      resolve_ground_truth_path(iter([{"timestamp": _ts(0)}]))
