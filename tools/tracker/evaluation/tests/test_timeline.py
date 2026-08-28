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
  compute_fps,
  timestamp_to_frame,
  reference_timestamp,
  build_frame_indexed_tracks,
  normalize_histories_to_fps,
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


class TestComputeFps:
  def test_prefers_base_fps(self):
    assert compute_fps([], base_fps=25.0) == 25.0

  def test_derives_from_timestamps(self):
    timestamps = [parse_timestamp(_ts(i)) for i in range(11)]  # 10 gaps * 100ms = 1s
    assert compute_fps(timestamps) == pytest.approx(10.0)

  def test_single_timestamp_defaults(self):
    assert compute_fps([parse_timestamp(_ts(0))]) == 30.0


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


class TestBuildFrameIndexedTracks:
  def test_builds_shared_reference_indices(self):
    ref = parse_timestamp(_ts(0))
    frames = [
      {"timestamp": _ts(0), "objects": [{"id": "x", "translation": [1.0, 2.0, 0.0]}]},
      {"timestamp": _ts(1), "objects": [{"id": "x", "translation": [1.5, 2.5, 0.0]}]},
    ]
    tracks = build_frame_indexed_tracks(
      frames, ref, 10.0,
      id_fn=lambda o: o["id"],
      pos_fn=lambda o: (o["translation"][0], o["translation"][1]),
    )
    assert tracks == {"x": {1: (1.0, 2.0), 2: (1.5, 2.5)}}

  def test_id_fn_none_skips_object(self):
    ref = parse_timestamp(_ts(0))
    frames = [{"timestamp": _ts(0), "objects": [
      {"id": "keep", "translation": [1.0, 2.0, 0.0]},
      {"id": "skip", "translation": [3.0, 4.0, 0.0]},
    ]}]
    tracks = build_frame_indexed_tracks(
      frames, ref, 10.0,
      id_fn=lambda o: None if o["id"] == "skip" else o["id"],
      pos_fn=lambda o: (o["translation"][0], o["translation"][1]),
    )
    assert list(tracks.keys()) == ["keep"]


class TestNormalizeHistoriesToFps:
  def test_maps_to_epoch_grid(self):
    histories = {
      "a": [(parse_timestamp(_ts(0)), [0.0]), (parse_timestamp(_ts(5)), [1.0])],
    }
    result = normalize_histories_to_fps(histories, 10.0)
    times = [t for t, _ in result["a"]]
    # Two unique timestamps -> indices 0 and 1 on a 10 fps grid (0.0s and 0.1s)
    assert (times[1] - times[0]).total_seconds() == pytest.approx(0.1)
