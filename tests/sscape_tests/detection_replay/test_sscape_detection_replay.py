# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace

import pytest

import sscape_detection_replay as replaymod
from sscape_detection_replay import SscapeDetectionReplay

SECOND = 1_000_000_000
CLOCK_TIME_NONE = 2**64 - 1
# The shared Gst stand-in is a MagicMock; give it the constants the element
# computes with. Plain assignment: monkeypatch would delete them on undo.
replaymod.Gst.SECOND = SECOND
replaymod.Gst.CLOCK_TIME_NONE = CLOCK_TIME_NONE


def make_prop(name):
  return SimpleNamespace(name=name)


class RecordingVideoFrame:
  frames = []

  def __init__(self, buffer, caps=None):
    self.regions = []
    RecordingVideoFrame.frames.append(self)

  def add_region(self, x, y, w, h, label="", confidence=0.0):
    self.regions.append((x, y, w, h, label, confidence))


class FakeSegment:
  def to_stream_time(self, _format, position):
    return position


@pytest.fixture
def metadata(tmp_path):
  path = tmp_path / "cam.json"
  path.write_text("\n".join(json.dumps({
    "timestamp": timestamp,
    "objects": {"person": [{"category": "person", "confidence": 1.0,
                            "bounding_box_px": {"x": x, "y": 5, "width": 6, "height": 7}}]},
  }) for timestamp, x in (("2026-11-13T09:20:12.000Z", 1), ("2026-11-13T09:20:12.100Z", 2))))
  return path


@pytest.fixture
def element(metadata, monkeypatch):
  monkeypatch.setattr(replaymod, "VideoFrame", RecordingVideoFrame)
  RecordingVideoFrame.frames = []
  element = SscapeDetectionReplay()
  element.segment = FakeSegment()
  element.do_set_property(make_prop("metadata"), str(metadata))
  assert element.do_start()
  return element


def caps(numerator=15, denominator=1, found=True):
  structure = SimpleNamespace(get_fraction=lambda _name: (found, numerator, denominator))
  return SimpleNamespace(get_structure=lambda _index: structure)


def regions_at(element, seconds):
  RecordingVideoFrame.frames = []
  element.do_transform_ip(SimpleNamespace(pts=round(seconds * SECOND)))
  return [region for frame in RecordingVideoFrame.frames for region in frame.regions]


def test_defaults():
  element = SscapeDetectionReplay()
  assert element.do_get_property(make_prop("metadata")) is None
  assert element.do_get_property(make_prop("sync-mode")) == "time"


def test_unknown_sync_mode_raises():
  with pytest.raises(ValueError):
    SscapeDetectionReplay().do_set_property(make_prop("sync-mode"), "nearest")


def test_start_fails_without_metadata():
  assert SscapeDetectionReplay().do_start() is False


def test_start_fails_on_missing_file(tmp_path):
  element = SscapeDetectionReplay()
  element.do_set_property(make_prop("metadata"), str(tmp_path / "missing.json"))
  assert element.do_start() is False


def test_time_mode_adds_regions_of_next_record(element):
  assert element.do_set_caps(caps(), None)
  assert regions_at(element, 0.0) == [(1, 5, 6, 7, "person", 1.0)]
  assert regions_at(element, 0.05) == [(2, 5, 6, 7, "person", 1.0)]
  assert regions_at(element, 0.5) == []


def test_frame_mode_uses_frame_index(element):
  element.do_set_property(make_prop("sync-mode"), "frame")
  assert element.do_set_caps(caps(10), None)
  assert regions_at(element, 0.1) == [(2, 5, 6, 7, "person", 1.0)]


def test_frame_mode_needs_frame_rate(element):
  element.do_set_property(make_prop("sync-mode"), "frame")
  assert element.do_set_caps(caps(found=False), None) is False


def test_buffer_without_timestamp_passes_through(element):
  element.do_set_caps(caps(), None)
  RecordingVideoFrame.frames = []
  assert element.do_transform_ip(SimpleNamespace(pts=CLOCK_TIME_NONE)) == replaymod.Gst.FlowReturn.OK
  assert RecordingVideoFrame.frames == []
