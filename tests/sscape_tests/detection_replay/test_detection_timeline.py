# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from detection_timeline import Detection, DetectionTimeline


def write_jsonl(path, records):
  path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
  return path


def record(timestamp, boxes=()):
  return {
    "timestamp": timestamp,
    "objects": {"person": [
      {"category": "person", "confidence": 0.9,
       "bounding_box_px": {"x": x, "y": 10, "width": 20, "height": 40}}
      for x in boxes
    ]},
  }


@pytest.fixture
def timeline(tmp_path):
  # Variable-rate records at 0, 65, 120 and 179 ms.
  return DetectionTimeline.from_jsonl(write_jsonl(tmp_path / "cam.json", [
    record("2026-11-13T09:20:12.270Z", [0]),
    record("2026-11-13T09:20:12.335Z", [1]),
    record("2026-11-13T09:20:12.390Z", [2, 3]),
    record("2026-11-13T09:20:12.449Z"),
  ]))


def xs(detections):
  return [detection.x for detection in detections]


def test_parses_detections(timeline):
  assert len(timeline) == 4
  assert timeline.at_frame(0) == (Detection("person", 0.9, 0, 10, 20, 40),)
  assert timeline.at_frame(3) == ()


@pytest.mark.parametrize("seconds, expected", [
  (0.0, [0]),
  (1 / 15, [2, 3]),   # 66.7 ms: the record at 65 ms is older, use the next one
  (0.065, [1]),       # exact match
  (0.12, [2, 3]),
  (2 / 15, []),
])
def test_at_time_uses_first_record_not_older_than_frame(timeline, seconds, expected):
  assert xs(timeline.at_time(seconds)) == expected


def test_at_time_past_last_record_is_none(timeline):
  assert timeline.at_time(0.2) is None


def test_at_frame_out_of_range_is_none(timeline):
  assert timeline.at_frame(4) is None
  assert timeline.at_frame(-1) is None


@pytest.mark.parametrize("mode, seconds, expected", [
  ("time", 1 / 15, [2, 3]),
  ("frame", 1 / 15, [1]),
  ("frame", 2 / 15, [2, 3]),
])
def test_lookup_modes(timeline, mode, seconds, expected):
  assert xs(timeline.lookup(mode, seconds, 15.0)) == expected


def test_lookup_unknown_mode_raises(timeline):
  with pytest.raises(ValueError):
    timeline.lookup("nearest", 0.0, 15.0)


def test_skips_blank_lines(tmp_path):
  path = tmp_path / "cam.json"
  path.write_text(json.dumps(record("2026-11-13T09:20:12.270Z", [5])) + "\n\n")
  assert len(DetectionTimeline.from_jsonl(path)) == 1


def test_invalid_record_reports_line(tmp_path):
  path = write_jsonl(tmp_path / "cam.json", [record("2026-11-13T09:20:12.270Z"), {"objects": {}}])
  with pytest.raises(ValueError, match=r"cam.json:2"):
    DetectionTimeline.from_jsonl(path)


def test_decreasing_timestamps_raise(tmp_path):
  path = write_jsonl(tmp_path / "cam.json", [
    record("2026-11-13T09:20:12.335Z"), record("2026-11-13T09:20:12.270Z")])
  with pytest.raises(ValueError, match="must not decrease"):
    DetectionTimeline.from_jsonl(path)


def test_empty_metadata_raises(tmp_path):
  path = tmp_path / "cam.json"
  path.write_text("")
  with pytest.raises(ValueError, match="no records"):
    DetectionTimeline.from_jsonl(path)
